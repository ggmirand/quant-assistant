# backend/src/routers/options.py
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel
import datetime as dt
import math
import time
import numpy as np

try:
    import yfinance as yf
except Exception:
    yf = None

import requests

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
    goal: str = "directional"  # future: "income" | "hedge"
    positions: list[PortfolioPos] = []

# ---------- Yahoo v7 fallback ----------
UA = "Mozilla/5.0 (compatible; QuantAssistant/1.0; +https://localhost)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _req_json(url, params=None, retries=2, timeout=4.0):
    last_err = None
    for i in range(retries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                last_err = RuntimeError("429 Too Many Requests")
                # brief backoff
                time.sleep(0.6 if i < retries else 0)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            # small backoff then retry
            time.sleep(0.4 if i < retries else 0)
    raise last_err

def _v7_options_book(symbol: str):
    """
    Minimal options fetch via Yahoo v7 API (no auth). Returns:
    { price, expiries:[YYYY-MM-DD], chains:[{expiry,dte,calls,puts}] }
    """
    base = f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}"
    j0 = _req_json(base)
    res = (j0 or {}).get("optionChain", {}).get("result") or []
    if not res:
        return {"price": None, "expiries": [], "chains": []}
    node0 = res[0]
    price = None
    try:
        price = float(node0.get("quote", {}).get("regularMarketPrice"))
    except Exception:
        price = None

    # expiration list is unix timestamps
    exp_ts = node0.get("expirationDates") or []
    expiries = []
    for ts in exp_ts:
        try:
            d = dt.datetime.utcfromtimestamp(int(ts)).date().isoformat()
            expiries.append(d)
        except Exception:
            continue

    chains = []
    # initial result may already include an options chain (for earliest expiry)
    for chunk in res:
        for opts in chunk.get("options", []):
            exp_ts_single = opts.get("expirationDate")
            if exp_ts_single:
                try:
                    d = dt.datetime.utcfromtimestamp(int(exp_ts_single)).date()
                    e = d.isoformat()
                except Exception:
                    continue
            else:
                continue
            calls = opts.get("calls", []) or []
            puts  = opts.get("puts",  []) or []
            # normalize fields to match yfinance-like dicts
            def norm(rows):
                out = []
                for r in rows:
                    try:
                        out.append({
                            "strike": float(r.get("strike")),
                            "bid": float(r.get("bid") or 0.0),
                            "ask": float(r.get("ask") or 0.0),
                            "lastPrice": float(r.get("lastPrice") or 0.0),
                            "impliedVolatility": float(r.get("impliedVolatility") or 0.0),
                        })
                    except Exception:
                        continue
                return out
            chains.append({
                "expiry": e,
                "dte": max((d - dt.date.today()).days, 0),
                "calls": norm(calls),
                "puts":  norm(puts)
            })

    return {"price": price, "expiries": expiries, "chains": chains}

# ---------- Core chain loader with robust fallbacks ----------
def load_chain(symbol: str, min_dte=7, max_dte=45):
    """
    Try yfinance first; on JSON/parse/network errors, fall back to Yahoo v7.
    Always returns {price, expiries, chains, note?}.
    """
    symbol = symbol.upper().strip()
    note = None
    book = {"price": None, "expiries": [], "chains": []}

    # 1) yfinance path
    if yf is not None:
        try:
            tkr = yf.Ticker(symbol)
            expiries = list(getattr(tkr, "options", []) or [])
            # filter by DTE
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

            # price
            S = None
            try:
                info = tkr.fast_info
                S = float(info.get("last_price"))
            except Exception:
                try:
                    hist = tkr.history(period="5d", interval="1d")
                    S = float(hist["Close"].dropna().iloc[-1])
                except Exception:
                    S = None

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
                    # continue other expiries
                    continue

            if chains:
                book = {"price": S, "expiries": [e for _, e, _ in valid], "chains": chains}
                if note:
                    book["note"] = note
                return book
            # else fall through to v7
        except Exception as ex:
            # JSONDecodeError or others → fall back
            msg = str(ex)
            if "429" in msg or "Too Many Requests" in msg:
                note = "Rate limited by data source (HTTP 429). Please wait ~1–2 minutes or reduce refresh frequency."
            else:
                note = f"yfinance error: {type(ex).__name__}"

    # 2) Yahoo v7 fallback
    try:
        v7 = _v7_options_book(symbol)
        # filter v7 expiries by DTE window
        today = dt.date.today()
        chains_filt = []
        for ch in v7.get("chains", []):
            try:
                d = dt.date.fromisoformat(ch["expiry"])
                dte = (d - today).days
                if min_dte <= dte <= max_dte:
                    chains_filt.append({**ch, "dte": dte})
            except Exception:
                continue
        exp_filt = [ch["expiry"] for ch in chains_filt]
        book = {"price": v7.get("price"), "expiries": exp_filt, "chains": chains_filt}
        if not exp_filt:
            book["note"] = note or "No expiries in requested window."
        elif note:
            book["note"] = note
        return book
    except Exception as ex:
        msg = str(ex)
        if "429" in msg or "Too Many Requests" in msg:
            note = "Rate limited by data source (HTTP 429). Please wait ~1–2 minutes or reduce refresh frequency."
        else:
            note = f"provider error: {type(ex).__name__}"
        return {"price": None, "expiries": [], "chains": [], "note": note}

# ---------- Enrichment, selection, simulation ----------
def enrich_contracts(S, expiry_iso, rows, is_call: bool):
    out = []
    if not rows:
        return out
    try:
        expiry = dt.datetime.fromisoformat(expiry_iso).date()
    except Exception:
        return out
    T = max(((expiry - dt.date.today()).days) / 365.0, 1.0 / 365.0)
    r = 0.0  # short-dated simplification

    for rrow in rows:
        K = float(rrow.get("strike") or 0.0)
        bid = float(rrow.get("bid") or 0.0)
        ask = float(rrow.get("ask") or 0.0)
        last = float(rrow.get("lastPrice") or 0.0)
        premium = (bid + ask) / 2.0 if (bid > 0 or ask > 0) else last
        iv_raw = float(rrow.get("impliedVolatility") or 0.0)
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
            prob_above = prob_ST_above_K(S, K, T, r, sigma)  # put ITM prob ~ 1 - this
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
        lr = np.log(close / close.shift(1)).dropna().values
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
    """Return option candidates near |delta| target within DTE window, filtered by buying power."""
    book = load_chain(symbol, min_dte=min_dte, max_dte=max_dte)
    if not book or not book.get("chains"):
        return {"symbol": symbol.upper(), "price": book.get("price"), "note": book.get("note"), "candidates": []}

    S = float(book.get("price") or 0.0)
    candidates = []
    for ch in book["chains"]:
        calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
        puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
        for c in [pick_by_target_delta(calls, target_abs_delta),
                  pick_by_target_delta(puts,  target_abs_delta)]:
            if not c:
                continue
            if (c["mid_price"] * 100.0) <= buying_power:
                candidates.append(c)

    if not candidates:
        for ch in book["chains"]:
            calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
            puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
            for c in [pick_by_target_delta(calls, target_abs_delta),
                      pick_by_target_delta(puts,  target_abs_delta)]:
                if c: candidates.append(c)

    final = sorted(candidates, key=lambda c: (abs(abs(c["delta"] or 9) - target_abs_delta), c["expiry"]))[:limit]
    return {
        "symbol": symbol.upper(),
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
    tickers = list({p.symbol.upper().strip() for p in req.positions if p.symbol})
    out = []
    for sym in tickers:
        book = load_chain(sym, min_dte=7, max_dte=45)
        if not book or not book.get("chains"):
            if book and book.get("note"):
                out.append({"symbol": sym, "note": book["note"], "suggestion": None})
            continue
        S = float(book.get("price") or 0.0)
        if S <= 0:
            continue

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

    out = sorted(out, key=lambda x: (abs(abs((x.get("suggestion") or {}).get("delta") or 9) - 0.25),
                                     (x.get("suggestion") or {}).get("expiry", "9999-12-31")))[:3]
    top_note = None
    for item in out:
        if isinstance(item, dict) and item.get("note") and "Rate limited" in item["note"]:
            top_note = item["note"]; break
    return {"suggestions": out, **({"note": top_note} if top_note else {})}

