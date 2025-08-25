from fastapi import APIRouter, Query
import datetime as dt
import math
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:
    yf = None

router = APIRouter()

# ----- light Black–Scholes bits -----
SQRT_2 = math.sqrt(2.0)
def norm_cdf(x: float) -> float: return 0.5 * (1.0 + math.erf(x / SQRT_2))
def bs_d1(S, K, T, r, sigma):
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0: return float("nan")
    return (math.log(S/K) + (r + 0.5*sigma*sigma)*T) / (sigma*math.sqrt(T))
def call_delta(S,K,T,r,sigma): return norm_cdf(bs_d1(S,K,T,r,sigma))
def prob_ST_above_x(S, x, T, r, sigma):
    if not (S>0 and x>0 and T>0 and sigma>0): return float("nan")
    d = (math.log(S/x) + (r - 0.5*sigma*sigma)*T) / (sigma*math.sqrt(T))
    return norm_cdf(d)

def ema(series: pd.Series, span: int): return series.ewm(span=span, adjust=False).mean()

def fetch_hist(symbol: str, days=200):
    if yf is None: return None
    try:
        hist = yf.Ticker(symbol).history(period=f"{max(60,days)}d", interval="1d")
        if hist is None or hist.empty: return None
        return hist["Close"].dropna()
    except Exception:
        return None

def compute_trend(symbol: str):
    S = fetch_hist(symbol, days=200)
    if S is None or len(S) < 50:
        return {"trend":"neutral","score":0.0,"notes":["Insufficient history for trend."], "rsi": None}
    ema20 = ema(S, 20); ema50 = ema(S, 50)
    ret10 = (S.iloc[-1]/S.iloc[-11] - 1.0) if len(S) > 11 else 0.0
    delta = S.diff().dropna()
    up = delta.clip(lower=0.0); down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1/14, adjust=False).mean()
    roll_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = (roll_up/roll_down).replace([np.inf,-np.inf], np.nan).fillna(0.0)
    rsi = 100 - (100/(1+rs))
    rsi_val = float(rsi.iloc[-1])
    score = 0.0; notes=[]
    if ema20.iloc[-1] > ema50.iloc[-1]: score += 0.4; notes.append("EMA20 > EMA50 (uptrend).")
    else: notes.append("EMA20 ≤ EMA50 (not an uptrend).")
    if ret10 > 0: score += 0.3; notes.append(f"10-day momentum +{ret10*100:.1f}%.")
    else: notes.append(f"10-day momentum {ret10*100:.1f}%.")
    score += 0.3 * max(0.0, 1.0 - abs(rsi_val-50)/50)
    notes.append(f"RSI(14) ≈ {rsi_val:.1f}.")
    trend = "up" if score >= 0.55 else ("down" if score <= 0.35 else "neutral")
    return {"trend":trend, "score":score, "notes":notes, "rsi": rsi_val}

def enrich_contracts(S, expiry_iso, rows, is_call: bool):
    out=[]
    if not rows: return out
    try: expiry = dt.date.fromisoformat(expiry_iso)
    except Exception: return out
    T = max(((expiry - dt.date.today()).days)/365.0, 1.0/365.0)
    r = 0.0
    for rrow in rows:
        try:
            K = float(rrow.get("strike") or rrow.get("Strike") or 0.0)
            bid = float(rrow.get("bid") or rrow.get("Bid") or 0.0)
            ask = float(rrow.get("ask") or rrow.get("Ask") or 0.0)
            last= float(rrow.get("lastPrice") or rrow.get("Last Price") or 0.0)
            oi  = int(rrow.get("openInterest") or rrow.get("Open Interest") or 0)
            vol = int(rrow.get("volume") or rrow.get("Volume") or 0)
            iv  = float(rrow.get("impliedVolatility") or rrow.get("Implied Volatility") or 0.0)
        except Exception:
            continue
        premium = (bid+ask)/2.0 if (bid>0 or ask>0) else last
        if not (math.isfinite(S) and K>0 and premium>0): continue
        sigma = max(iv, 1e-6)
        dlt = call_delta(S,K,T,r,sigma)
        if not is_call: dlt = dlt - 1.0
        breakeven = (K + premium) if is_call else (K - premium)
        p_profit = prob_ST_above_x(S, breakeven, T, r, sigma) if is_call else (1.0 - prob_ST_above_x(S, breakeven, T, r, sigma))
        out.append({
            "expiry": expiry_iso, "type": "CALL" if is_call else "PUT",
            "strike": round(K,4), "mid_price": round(premium,4), "iv": round(sigma,6),
            "delta": round(dlt,4) if math.isfinite(dlt) else None,
            "breakeven": round(breakeven,4),
            "oi": oi, "volume": vol,
            "chance_profit": round(p_profit,6) if math.isfinite(p_profit) else None,
        })
    return out

def confidence_score(c):
    score = 0
    premium = c.get("mid_price",0)
    oi = c.get("oi",0); vol = c.get("volume",0)
    if oi >= 500: score += 35
    elif oi >= 200: score += 25
    elif oi >= 50: score += 15
    if vol >= 200: score += 20
    elif vol >= 50: score += 12
    elif vol >= 10: score += 6
    if c.get("iv"): score += 15
    if c.get("delta") is not None and 0.1 <= abs(c["delta"]) <= 0.6: score += 15
    if premium*100 <= 300: score += 10
    elif premium*100 <= 800: score += 6
    else: score += 2
    return min(100, score)

def simulate_option_pl_samples(symbol: str, S: float, K: float, premium: float, T_days: int, otype: str, n_paths=900, sample_out=300):
    if yf is None or S<=0 or K<=0 or T_days<=0: return None
    try:
        hist = yf.Ticker(symbol).history(period="1y", interval="1d")
        close = hist["Close"].dropna()
        if len(close) < 30: return None
        lr = np.log(close / close.shift(1)).dropna().values
        mu_d = float(np.mean(lr)); sig_d = float(np.std(lr))
    except Exception:
        return None
    T=float(T_days)
    Z=np.random.normal(0,1,size=n_paths)
    ST=S*np.exp((mu_d-0.5*sig_d**2)*T + sig_d*np.sqrt(T)*Z)
    payoff = (np.maximum(ST-K,0.0)-premium) if otype.upper()=="CALL" else (np.maximum(K-ST,0.0)-premium)
    p5,p50,p95 = np.percentile(payoff, [5,50,95])
    prob_profit=float((payoff>0).mean())
    if n_paths>sample_out:
        idx=np.linspace(0,n_paths-1,sample_out).astype(int)
        samples=payoff[idx].round(2).tolist()
    else:
        samples=payoff.round(2).tolist()
    return {"pl_p5": float(p5), "pl_p50": float(p50), "pl_p95": float(p95), "prob_profit": prob_profit, "samples": samples}

def _load_chain_yf(symbol: str, dte_lo: int, dte_hi: int):
    """Only yfinance; skip malformed expiries safely."""
    symbol = symbol.upper().strip()
    if yf is None:
        return {"price": None, "expiries": [], "chains": [], "note": "yfinance not installed"}
    try:
        tkr = yf.Ticker(symbol)
        expiries = list(getattr(tkr, "options", []) or [])
        today = dt.date.today()
        valid=[]
        for e in expiries:
            try:
                d=dt.date.fromisoformat(e); dte=(d-today).days
                if dte_lo <= dte <= dte_hi: valid.append((d,e,dte))
            except Exception: 
                continue

        # Underlying price
        S=None
        try:
            info=tkr.fast_info; S=float(info.get("last_price"))
        except Exception:
            try:
                hist=tkr.history(period="5d", interval="1d")
                S=float(hist["Close"].dropna().iloc[-1])
            except Exception: S=None

        chains=[]
        for _,e_str,dte in valid:
            try:
                oc=tkr.option_chain(e_str)   # <-- sometimes raises JSONDecodeError; we catch it
                calls=oc.calls.to_dict(orient="records")
                puts= oc.puts.to_dict(orient="records")
                chains.append({"expiry":e_str,"dte":dte,"calls":calls,"puts":puts})
            except Exception:
                # skip bad expiry instead of failing whole endpoint
                continue
        note = None if chains else f"No usable option chains in {dte_lo}–{dte_hi} DTE."
        return {"price": S, "expiries": [e for _,e,_ in valid], "chains": chains, "note": note}
    except Exception as ex:
        return {"price": None, "expiries": [], "chains": [], "note": f"yfinance error: {type(ex).__name__}"}

def load_chain_multiwindow(symbol: str):
    """Try 21–45 (preferred), then 14–60, then 30–90 DTE."""
    for lo,hi in [(21,45),(14,60),(30,90)]:
        book = _load_chain_yf(symbol, lo, hi)
        if book.get("chains"):
            book["picked_window"] = (lo,hi)
            return book
        last = book
    last["picked_window"] = None
    return last

def pick_contracts_for_symbol(symbol: str, buying_power: float):
    book = load_chain_multiwindow(symbol)
    S = book.get("price") or 0.0
    if not book.get("chains"):
        return {"note": book.get("note") or "No option expiries fetched.", "under_price": S, "candidates": []}
    trend = compute_trend(symbol)
    prefer = trend["trend"]
    target_delta = 0.30

    cands=[]
    for ch in book["chains"]:
        calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
        puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
        rows = calls if prefer=="up" else (puts if prefer=="down" else calls+puts)
        for c in rows:
            if c["mid_price"]*100.0 > buying_power: continue
            if (c.get("oi",0) < 50) and (c.get("volume",0) < 10): continue
            if c.get("delta") is None: continue
            c["delta_diff"]=abs(abs(c["delta"])-target_delta)
            c["conf"]=confidence_score(c)
            c["dte"]=ch["dte"]
            cands.append(c)

    if not cands:
        return {"note": (book.get("note") or "No affordable/liquid contracts in tested DTE windows."),
                "under_price": S, "candidates": []}

    cands_sorted = sorted(cands, key=lambda x: (x["delta_diff"], -x["conf"], x["expiry"]))
    best = cands_sorted[0]
    days=(dt.date.fromisoformat(best["expiry"])-dt.date.today()).days
    sim=simulate_option_pl_samples(symbol, S, best["strike"], best["mid_price"], days, best["type"])
    thought = [
        f"Trend check: {', '.join(trend['notes'])}",
        f"Target delta ≈ 0.30; picked {best['type']} with Δ={best['delta']:.2f} and DTE={days}.",
        f"Liquidity filter: OI={best.get('oi',0)}, Vol={best.get('volume',0)}.",
        f"Affordability: premium ≈ ${best['mid_price']:.2f} (${best['mid_price']*100:.0f} per contract).",
    ]
    if best["type"]=="CALL":
        summary=(f"This is a CALL. You pay about ${best['mid_price']:.2f}. "
                 f"If the stock finishes above ${best['breakeven']:.2f} on {best['expiry']}, you profit; "
                 f"otherwise your max loss is what you paid. The model’s profit chance is "
                 f"{(best.get('chance_profit') or 0)*100:.1f}%.")
    else:
        summary=(f"This is a PUT. You pay about ${best['mid_price']:.2f}. "
                 f"If the stock finishes below ${best['breakeven']:.2f} on {best['expiry']}, you profit; "
                 f"otherwise your max loss is what you paid. The model’s profit chance is "
                 f"{(best.get('chance_profit') or 0)*100:.1f}%.")

    return {
        "symbol": symbol.upper(),
        "under_price": S,
        "note": book.get("note"),
        "picked_window": book.get("picked_window"),
        "suggestion": best,
        "confidence": best["conf"],
        "cost_estimate": round(best["mid_price"]*100.0, 2),
        "sim": sim,
        "explanation": summary,
        "thought_process": thought
    }

@router.get("/idea")
def idea(symbol: str = Query(...), buying_power: float = Query(..., ge=0.0)):
    return pick_contracts_for_symbol(symbol, buying_power)
