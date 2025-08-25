# backend/src/routers/options.py
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel
import datetime as dt
import math
import numpy as np

try:
    import yfinance as yf
except Exception:
    yf = None  # if missing, endpoints will return empty/notes

router = APIRouter()

# ---------- Black–Scholes helpers ----------
SQRT_2 = math.sqrt(2.0)

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT_2))

def bs_d1(S, K, T, r, sigma):
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        return float("nan")
    return (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))

def bs_d2(d1, sigma, T):
    if not math.isfinite(d1) or sigma <= 0 or T <= 0:
        return float("nan")
    return d1 - sigma * math.sqrt(T)

def call_delta(S, K, T, r, sigma): return norm_cdf(bs_d1(S, K, T, r, sigma))
def put_delta(S, K, T, r, sigma):  return call_delta(S, K, T, r, sigma) - 1.0

def prob_ST_above_K(S, K, T, r, sigma):
    d1 = bs_d1(S, K, T, r, sigma)
    d2 = bs_d2(d1, sigma, T)
    return norm_cdf(d2)

# ---------- Models ----------
class PortfolioPos(BaseModel):
    symbol: str
    shares: float = 0.0
    cost_basis: float | None = None

class PortfolioReq(BaseModel):
    buying_power: float = 0.0
    goal: str = "directional"  # "directional" | "income" | "hedge" (future use)
    positions: list[PortfolioPos] = []

# ---------- Data fetch (with 429‑safe guards) ----------
def load_chain(symbol: str, min_dte=7, max_dte=45):
    """
    Fetch real option chains using yfinance.
    Returns a dict that ALWAYS has keys: price, expiries, chains, note (optional).
    Gracefully handles Yahoo rate limits (HTTP 429) and other errors.
    """
    if yf is None:
        return {"price": None, "expiries": [], "chains": [], "note": "yfinance not installed"}

    # Build ticker + expiries
    try:
        tkr = yf.Ticker(symbol)
        expiries = list(getattr(tkr, "options", []) or [])
    except Exception as e:
        return {"price": None, "expiries": [], "chains": [], "note": f"ticker fetch failed: {type(e).__name__}"}

    # Filter expiries by DTE
    today = dt.date.today()
    valid = []
    for e in expiries:
        try:
            d = dt.date.fromisoformat(e)
            dte = (d - today).days
            if min_dte <= dte <= max_dte:
                valid.append((d, e, dte))
        except Exception:
            continue

    # Underlying price
    S = None
    note = None
    try:
        info = tkr.fast_info
        S = float(info.get("last_price"))
    except Exception:
        try:
            hist = tkr.history(period="5d", interval="1d")
            S = float(hist["Close"].dropna().iloc[-1])
        except Exception:
            S = None

    # Pull chains per expiry; tolerate failures (incl. 429)
    chains = []
    for _, e_str, dte in valid:
        try:
            oc = tkr.option_chain(e_str)
            calls = oc.calls.to_dict(orient="records")
            puts  = oc.puts.to_dict(orient="records")
            chains.append({"expiry": e_str, "dte": dte, "calls": calls, "puts": puts})
        except Exception as ex:
            msg = str(ex)
            if "429" in msg or "Too Many Requests" in msg:
                note = "Rate limited by data source (HTTP 429). Please wait ~1–2 minutes or reduce refresh frequency."
            # skip this expiry; continue with others
            continue

    # If nothing usable came back
    if not chains and note is None and valid:
        note = "No option data returned (provider error). Try again later."

    return {"price": S, "expiries": [e for _, e, _ in valid], "chains": chains, **({"note": note} if note else {})}

# ---------- Enrichment, selection, and simulation ----------
def enrich_contracts(S, expiry_iso, rows, is_call: bool):
    out = []
    if not rows:
        return out
    try:
        expiry = dt.datetime.fromisoformat(expiry_iso).date()
    except Exception:
        return out
    T = max(((expiry - dt.date.today()).days) / 365.0, 1.0 / 365.0)
    r = 0.0  # short-dated: close enough

    for rrow in rows:
        K = float(rrow.get("strike") or rrow.get("Strike") or 0.0)
        bid = float(rrow.get("bid") or rrow.get("Bid") or 0.0)
        ask = float(rrow.get("ask") or rrow.get("Ask") or 0.0)
        last = float(rrow.get("lastPrice") or rrow.get("Last") or 0.0)
        premium = (bid + ask) / 2.0 if (bid > 0 or ask > 0) else last
        iv_raw = float(rrow.get("impliedVolatility") or rrow.get("impliedVolatility%") or 0.0)
        sigma = max(iv_raw, 1e-6)

        if not (math.isfinite(S) and K > 0 and premium > 0):
            continue

        if is_call:
            dlt = call_delta(S, K, T, r, sigma)
            prob_above = prob_ST_above_K(S, K, T, r, sigma)
            breakeven = K + premium
            otype = "CALL"
        else:
            dlt = put_delta(S, K, T, r, sigma)
            prob_above = prob_ST_above_K(S, K, T, r, sigma)  # report P(S_T > K); put ITM prob ~ 1 - this
            breakeven = K - premium
            otype = "PUT"

        out.append({
            "expiry": expiry_iso,
            "type": otype,
            "strike": round(K, 4),
            "mid_price": round(premium, 4),
            "iv": round(sigma, 6),
            "delta": round(dlt, 4) if math.isfinite(dlt) else None,
            "prob_finish_above_strike": round(prob_above, 6) if math.isfinite(prob_above) else None,
            "breakeven": round(breakeven, 4),
        })
    return out

def pick_by_target_delta(contracts, target_abs_delta=0.25):
    if not contracts:
        return None
    def key(c):
        d = c.get("delta")
        return abs(abs(d) - target_abs_delta) if d is not None else 999
    return sorted(contracts, key=key)[0]

def estimate_mu_sigma_daily(symbol: str):
    if yf is None:
        return None, None
    try:
        hist = yf.Ticker(symbol).history(period="1y", interval="1d")
        close = hist["Close"].dropna()
        if len(close) < 30:
            return None, None
        lr = np.log(close / close.shift(1)).dropna().values  # log-returns
        mu_d = float(np.mean(lr))
        sig_d = float(np.std(lr))
        return mu_d, sig_d
    except Exception:
        return None, None

def simulate_option_pl(symbol: str, S: float, K: float, premium: float, T_days: int, otype: str, n_paths=2000):
    mu_d, sig_d = estimate_mu_sigma_daily(symbol)
    if mu_d is None or sig_d is None or S <= 0 or K <= 0 or T_days <= 0:
        return None
    T = float(T_days)
    Z = np.random.normal(0, 1, size=n_paths)
    ST = S * np.exp((mu_d - 0.5 * sig_d**2) * T + sig_d * np.sqrt(T) * Z)
    if otype.upper() == "CALL":
        payoff = np.maximum(ST - K, 0.0) - premium
    else:
        payoff = np.maximum(K - ST, 0.0) - premium
    p5, p50, p95 = np.percentile(payoff, [5, 50, 95])
    prob_profit = float((payoff > 0.0).mean())
    return {"pl_p5": float(p5), "pl_p50": float(p50), "pl_p95": float(p95), "prob_profit": prob_profit}

# ---------- Public endpoints ----------
@router.get("/best-trades")
def best_trades(
    symbol: str = Query(..., description="Ticker, e.g. AAPL"),
    buying_power: float = Query(5000.0, ge=0.0),
    target_abs_delta: float = Query(0.25, ge=0.05, le=0.5),
    min_dte: int = Query(7, ge=1),
    max_dte: int = Query(45, ge=5),
    limit: int = Query(8, ge=1, le=20),
):
    """Return real option candidates near |delta| target within DTE window, filtered by buying power."""
    if yf is None:
        return {"note": "yfinance not installed in this image", "candidates": []}

    symbol = symbol.upper().strip()
    book = load_chain(symbol, min_dte=min_dte, max_dte=max_dte)
    if not book or not book.get("chains"):
        return {"symbol": symbol, "price": book.get("price"), "note": book.get("note"), "candidates": []}

    S = float(book.get("price") or 0.0)
    candidates = []
    for ch in book["chains"]:
        calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
        puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
        for c in [pick_by_target_delta(calls, target_abs_delta),
                  pick_by_target_delta(puts,  target_abs_delta)]:
            if not c: 
                continue
            if (c["mid_price"] * 100.0) <= buying_power:  # 1 contract affordability
                candidates.append(c)

    if not candidates:
        # fallback: include closest anyway
        for ch in book["chains"]:
            calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
            puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
            for c in [pick_by_target_delta(calls, target_abs_delta),
                      pick_by_target_delta(puts,  target_abs_delta)]:
                if c: candidates.append(c)

    final = sorted(candidates, key=lambda c: (abs(abs(c["delta"] or 9) - target_abs_delta), c["expiry"]))[:limit]

    return {
        "symbol": symbol,
        "price": S,
        "target_abs_delta": target_abs_delta,
        "min_dte": min_dte, "max_dte": max_dte,
        "note": book.get("note"),
        "candidates": final
    }

@router.post("/portfolio-suggestions")
def portfolio_suggestions(req: PortfolioReq = Body(...)):
    """
    Build 1–3 educational long-option ideas based on user's positions + buying power.
    Adds a simple MC P/L summary for each suggestion.
    """
    if yf is None:
        return {"suggestions": [], "note": "yfinance not installed"}

    tickers = list({p.symbol.upper().strip() for p in req.positions if p.symbol})
    out = []
    for sym in tickers:
        book = load_chain(sym, min_dte=7, max_dte=45)
        if not book or not book.get("chains"):
            # bubble up note if present
            if book and book.get("note"):
                out.append({"symbol": sym, "note": book["note"], "suggestion": None})
            continue
        S = float(book.get("price") or 0.0)
        if S <= 0:
            continue

        # pick top long call/put near 0.25 |delta| that fits budget
        ideas = []
        for ch in book["chains"]:
            calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
            puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
            for c in [pick_by_target_delta(calls, 0.25), pick_by_target_delta(puts, 0.25)]:
                if not c: 
                    continue
                if c["mid_price"] * 100.0 <= req.buying_power:
                    ideas.append(c)
        if not ideas:
            continue
        ideas = sorted(ideas, key=lambda c: (abs(abs(c["delta"] or 9) - 0.25), c["expiry"]))[:2]

        # attach quick MC P/L
        for c in ideas:
            days = (dt.date.fromisoformat(c["expiry"]) - dt.date.today()).days
            sim = simulate_option_pl(sym, S, c["strike"], c["mid_price"], days, c["type"])
            reasoning = []
            if c["type"] == "CALL":
                reasoning += [
                    "Directional long CALL near 0.25 delta (balanced risk/reward).",
                    "Breakeven = strike + premium; benefits from upside moves.",
                    "Risk limited to paid premium."
                ]
                prob_text = f"Risk‑neutral P(S_T > K) ≈ {(c.get('prob_finish_above_strike') or 0)*100:.1f}%."
            else:
                reasoning += [
                    "Directional long PUT near 0.25 delta (balanced risk/reward).",
                    "Breakeven = strike − premium; benefits from downside moves.",
                    "Risk limited to paid premium."
                ]
                pab = c.get("prob_finish_above_strike") or 0.0
                prob_text = f"Risk‑neutral P(S_T < K) ≈ {(1.0 - pab)*100:.1f}%."

            out.append({
                "symbol": sym,
                "under_price": S,
                "suggestion": c,
                "cost_estimate": round(c["mid_price"] * 100.0, 2),
                "sim": sim,
                "reasoning": reasoning + [prob_text],
                "note": "Educational example only. Not financial advice."
            })

    # top 3 across all symbols
    out = sorted(out, key=lambda x: (abs(abs((x.get("suggestion") or {}).get("delta") or 9) - 0.25),
                                     (x.get("suggestion") or {}).get("expiry", "9999-12-31")))[:3]
    # If any upstream note (e.g., rate limit) exists, surface it at the top level too
    top_note = None
    for item in out:
        if isinstance(item, dict) and item.get("note") and "Rate limited" in item["note"]:
            top_note = item["note"]; break
    return {"suggestions": out, **({"note": top_note} if top_note else {})}
