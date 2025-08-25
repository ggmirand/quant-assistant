# backend/src/routers/options.py
from fastapi import APIRouter, Query, Body
from pydantic import BaseModel
import datetime as dt
import math
import time
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:
    yf = None

import requests

router = APIRouter()

# ---------------- Black–Scholes helpers ----------------
SQRT_2 = math.sqrt(2.0)
def norm_cdf(x: float) -> float: return 0.5 * (1.0 + math.erf(x / SQRT_2))
def bs_d1(S, K, T, r, sigma):
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0: return float("nan")
    return (math.log(S/K) + (r + 0.5*sigma*sigma)*T) / (sigma*math.sqrt(T))
def bs_d2(d1, sigma, T): return d1 - sigma*math.sqrt(T) if math.isfinite(d1) and sigma>0 and T>0 else float("nan")
def call_delta(S,K,T,r,sigma): return norm_cdf(bs_d1(S,K,T,r,sigma))
def put_delta(S,K,T,r,sigma):  return call_delta(S,K,T,r,sigma) - 1.0

def prob_ST_above_x(S, x, T, r, sigma):
    # Risk‑neutral chance S_T > x in lognormal model
    if not (S>0 and x>0 and T>0 and sigma>0): return float("nan")
    d = (math.log(S/x) + (r - 0.5*sigma*sigma)*T) / (sigma*math.sqrt(T))
    return norm_cdf(d)

# ---------------- Models ----------------
class IdeaReq(BaseModel):
    symbol: str
    buying_power: float

class ScanReq(BaseModel):
    buying_power: float
    universe: list[str] | None = None  # optional custom universe

# ---------------- Yahoo v7 (fallback) ----------------
UA = "Mozilla/5.0 (compatible; QuantAssistant/1.0)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _req_json(url, params=None, retries=2, timeout=4.0):
    last_err = None
    for i in range(retries+1):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                last_err = RuntimeError("429 Too Many Requests")
                time.sleep(0.6 if i < retries else 0)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.4 if i < retries else 0)
    raise last_err

def _v7_options_book(symbol: str):
    base = f"https://query2.finance.yahoo.com/v7/finance/options/{symbol}"
    j0 = _req_json(base)
    res = (j0 or {}).get("optionChain", {}).get("result") or []
    if not res:
        return {"price": None, "expiries": [], "chains": []}
    node0 = res[0]
    price = None
    try: price = float(node0.get("quote", {}).get("regularMarketPrice"))
    except Exception: price = None

    exp_ts = node0.get("expirationDates") or []
    expiries = []
    for ts in exp_ts:
        try:
            d = dt.datetime.utcfromtimestamp(int(ts)).date().isoformat()
            expiries.append(d)
        except Exception: continue

    chains = []
    for chunk in res:
        for opts in chunk.get("options", []):
            exp_ts_single = opts.get("expirationDate")
            if not exp_ts_single: continue
            try:
                d = dt.datetime.utcfromtimestamp(int(exp_ts_single)).date()
                e = d.isoformat()
            except Exception:
                continue
            calls = opts.get("calls", []) or []
            puts  = opts.get("puts",  []) or []

            def norm(rows):
                out=[]
                for r in rows:
                    try:
                        out.append({
                            "strike": float(r.get("strike")),
                            "bid": float(r.get("bid") or 0.0),
                            "ask": float(r.get("ask") or 0.0),
                            "lastPrice": float(r.get("lastPrice") or 0.0),
                            "openInterest": int(r.get("openInterest") or 0),
                            "volume": int(r.get("volume") or 0),
                            "impliedVolatility": float(r.get("impliedVolatility") or 0.0),
                        })
                    except Exception:
                        continue
                return out
            chains.append({"expiry": e, "dte": max((d - dt.date.today()).days, 0),
                           "calls": norm(calls), "puts": norm(puts)})
    return {"price": price, "expiries": expiries, "chains": chains}

# ---------------- Data loading (with fallbacks) ----------------
def load_chain(symbol: str, min_dte=21, max_dte=45):
    symbol = symbol.upper().strip()
    note = None
    # 1) yfinance path
    if yf is not None:
        try:
            tkr = yf.Ticker(symbol)
            expiries = list(getattr(tkr, "options", []) or [])
            today = dt.date.today()
            valid=[]
            for e in expiries:
                try:
                    d=dt.date.fromisoformat(e); dte=(d-today).days
                    if min_dte <= dte <= max_dte: valid.append((d,e,dte))
                except Exception: continue
            # price
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
                    oc=tkr.option_chain(e_str)
                    calls=oc.calls.to_dict(orient="records")
                    puts= oc.puts.to_dict(orient="records")
                    chains.append({"expiry":e_str,"dte":dte,"calls":calls,"puts":puts})
                except Exception as ex:
                    if "429" in str(ex) or "Too Many Requests" in str(ex):
                        note="Rate limited by data source (HTTP 429). Please wait ~1–2 minutes or reduce refresh."
                    continue
            if chains:
                book={"price":S,"expiries":[e for _,e,_ in valid],"chains":chains}
                if note: book["note"]=note
                return book
        except Exception as ex:
            if "429" in str(ex) or "Too Many Requests" in str(ex):
                note="Rate limited by data source (HTTP 429). Please wait ~1–2 minutes or reduce refresh."
            else:
                note=f"yfinance error: {type(ex).__name__}"

    # 2) Yahoo v7 fallback
    try:
        v7=_v7_options_book(symbol)
        today=dt.date.today()
        chains_filt=[]
        for ch in v7.get("chains", []):
            try:
                d=dt.date.fromisoformat(ch["expiry"]); dte=(d-today).days
                if min_dte <= dte <= max_dte:
                    ch["dte"]=dte
                    chains_filt.append(ch)
            except Exception: continue
        book={"price": v7.get("price"), "expiries": [c["expiry"] for c in chains_filt], "chains": chains_filt}
        if not book["expiries"]:
            book["note"]=note or "No expiries in requested window."
        elif note:
            book["note"]=note
        return book
    except Exception as ex:
        msg=str(ex)
        if "429" in msg or "Too Many Requests" in msg:
            note="Rate limited by data source (HTTP 429). Please wait ~1–2 minutes or reduce refresh."
        else:
            note=f"provider error: {type(ex).__name__}"
        return {"price":None,"expiries":[],"chains":[],"note":note}

# ---------------- Indicators & selection ----------------
def fetch_hist(symbol: str, days=200):
    if yf is None: return None
    try:
        hist = yf.Ticker(symbol).history(period=f"{max(60,days)}d", interval="1d")
        if hist is None or hist.empty: return None
        return hist["Close"].dropna()
    except Exception:
        return None

def ema(series: pd.Series, span: int): return series.ewm(span=span, adjust=False).mean()

def compute_trend(symbol: str):
    S = fetch_hist(symbol, days=200)
    if S is None or len(S) < 50:
        return {"trend":"neutral","score":0.0,"notes":["Insufficient history for robust trend."]}
    ema20 = ema(S, 20); ema50 = ema(S, 50)
    ret10 = (S.iloc[-1]/S.iloc[-11] - 1.0) if len(S) > 11 else 0.0
    # RSI(14)
    delta = S.diff().dropna()
    up = delta.clip(lower=0.0); down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1/14, adjust=False).mean()
    roll_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = (roll_up/roll_down).replace([np.inf,-np.inf], np.nan).fillna(0.0)
    rsi = 100 - (100/(1+rs))
    rsi_val = float(rsi.iloc[-1])

    score = 0.0
    notes = []
    if ema20.iloc[-1] > ema50.iloc[-1]: score += 0.4; notes.append("EMA20 > EMA50 (uptrend).")
    else: notes.append("EMA20 ≤ EMA50 (down/sideways).")
    if ret10 > 0: score += 0.3; notes.append(f"10‑day momentum +{ret10*100:.1f}%.")
    else: notes.append(f"10‑day momentum {ret10*100:.1f}%.")

    # RSI closeness to 50 -> stability (closer less overbought/oversold)
    score += 0.3 * max(0.0, 1.0 - abs(rsi_val-50)/50)
    notes.append(f"RSI(14) ≈ {rsi_val:.1f}.")

    trend = "up" if score >= 0.55 else ("down" if score <= 0.35 else "neutral")
    return {"trend":trend, "score":score, "notes":notes, "rsi": rsi_val}

def enrich_contracts(S, expiry_iso, rows, is_call: bool):
    out=[]
    if not rows: return out
    try: expiry = dt.datetime.fromisoformat(expiry_iso).date()
    except Exception: return out
    T = max(((expiry - dt.date.today()).days)/365.0, 1.0/365.0)
    r = 0.0
    for rrow in rows:
        K = float(rrow.get("strike") or 0.0)
        bid = float(rrow.get("bid") or 0.0)
        ask = float(rrow.get("ask") or 0.0)
        last= float(rrow.get("lastPrice") or 0.0)
        oi  = int(rrow.get("openInterest") or 0)
        vol = int(rrow.get("volume") or 0)
        premium = (bid+ask)/2.0 if (bid>0 or ask>0) else last
        iv_raw  = float(rrow.get("impliedVolatility") or 0.0)
        sigma = max(iv_raw, 1e-6)
        if not (math.isfinite(S) and K>0 and premium>0): continue
        dlt = call_delta(S,K,T,r,sigma) if is_call else (call_delta(S,K,T,r,sigma)-1.0)
        breakeven = (K + premium) if is_call else (K - premium)
        # PoP: chance payoff > 0 => S_T > breakeven (call) or < breakeven (put)
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
    # 0..100: liquidity (spread/oi/vol), data presence, reasonable greeks
    score = 0
    premium = c.get("mid_price",0)
    # We don't have spread here (only mid), so use OI/Vol proxies
    oi = c.get("oi",0); vol = c.get("volume",0)
    if oi >= 500: score += 35
    elif oi >= 200: score += 25
    elif oi >= 50: score += 15
    if vol >= 200: score += 20
    elif vol >= 50: score += 12
    elif vol >= 10: score += 6
    if c.get("iv"): score += 15
    if c.get("delta") is not None and 0.1 <= abs(c["delta"]) <= 0.6: score += 15
    # affordability — higher premium uses more BP (small nudge)
    if premium*100 <= 300: score += 10
    elif premium*100 <= 800: score += 6
    else: score += 2
    return min(100, score)

def estimate_mu_sigma_daily(symbol: str):
    if yf is None: return None, None
    try:
        hist = yf.Ticker(symbol).history(period="1y", interval="1d")
        close = hist["Close"].dropna()
        if len(close) < 30: return None, None
        lr = np.log(close / close.shift(1)).dropna().values
        mu_d = float(np.mean(lr)); sig_d=float(np.std(lr))
        return mu_d, sig_d
    except Exception:
        return None, None

def simulate_option_pl_samples(symbol: str, S: float, K: float, premium: float, T_days: int, otype: str, n_paths=1200, sample_out=300):
    mu_d, sig_d = estimate_mu_sigma_daily(symbol)
    if mu_d is None or sig_d is None or S<=0 or K<=0 or T_days<=0: return None
    T=float(T_days)
    Z=np.random.normal(0,1,size=n_paths)
    ST=S*np.exp((mu_d-0.5*sig_d**2)*T + sig_d*np.sqrt(T)*Z)
    payoff = (np.maximum(ST-K,0.0)-premium) if otype.upper()=="CALL" else (np.maximum(K-ST,0.0)-premium)
    p5,p50,p95 = np.percentile(payoff, [5,50,95])
    prob_profit=float((payoff>0).mean())
    # sample subset to plot as histogram client-side
    if n_paths>sample_out:
        idx=np.linspace(0,n_paths-1,sample_out).astype(int)
        samples=payoff[idx].round(2).tolist()
    else:
        samples=payoff.round(2).tolist()
    return {"pl_p5": float(p5), "pl_p50": float(p50), "pl_p95": float(p95), "prob_profit": prob_profit, "samples": samples}

def pick_contracts_for_symbol(symbol: str, buying_power: float):
    # Load book
    book = load_chain(symbol, min_dte=21, max_dte=45)
    S = book.get("price") or 0.0
    if not book.get("chains"):
        return {"note": book.get("note"), "under_price": S, "candidates": []}
    trend = compute_trend(symbol)
    prefer = trend["trend"]  # up/down/neutral
    target_delta = 0.30

    # build all candidates with filters
    cands=[]
    for ch in book["chains"]:
        calls = enrich_contracts(S, ch["expiry"], ch["calls"], True)
        puts  = enrich_contracts(S, ch["expiry"], ch["puts"],  False)
        rows = []
        if prefer=="up": rows += calls
        elif prefer=="down": rows += puts
        else: rows += calls + puts
        for c in rows:
            # affordability
            if c["mid_price"]*100.0 > buying_power: continue
            # liquidity gates
            if (c.get("oi",0) < 50) and (c.get("volume",0) < 10): continue
            # delta proximity
            if c.get("delta") is None: continue
            c["delta_diff"]=abs(abs(c["delta"])-target_delta)
            c["conf"]=confidence_score(c)
            c["dte"]=ch["dte"]
            cands.append(c)

    if not cands:
        return {"note": book.get("note") or "No affordable/liquid contracts in DTE window.", "under_price": S, "candidates": []}

    # Rank: delta closeness, higher confidence, nearer expiry (but within window)
    cands_sorted = sorted(cands, key=lambda x: (x["delta_diff"], -x["conf"], x["expiry"]))
    best = cands_sorted[0]
    # Simulation for best
    days=(dt.date.fromisoformat(best["expiry"])-dt.date.today()).days
    sim=simulate_option_pl_samples(symbol, S, best["strike"], best["mid_price"], days, best["type"])
    # explanation + thought process
    thought = [
        f"Trend check: {', '.join(trend['notes'])}",
        f"Target delta ≈ 0.30; picked {best['type']} with Δ={best['delta']:.2f} and DTE={days}.",
        f"Liquidity filter: OI={best.get('oi',0)}, Vol={best.get('volume',0)}.",
        f"Affordability: premium ≈ ${best['mid_price']:.2f} (${best['mid_price']*100:.0f} per contract).",
    ]
    # 8th‑grade explanation
    if best["type"]=="CALL":
        summary=(f"This is a CALL. You pay about ${best['mid_price']:.2f} now. "
                 f"If the stock ends above ${best['breakeven']:.2f} on expiry ({best['expiry']}), you make money; "
                 f"otherwise you can lose up to what you paid. The model’s chance of profit is "
                 f"{(best.get('chance_profit') or 0)*100:.1f}%.")
    else:
        summary=(f"This is a PUT. You pay about ${best['mid_price']:.2f} now. "
                 f"If the stock ends below ${best['breakeven']:.2f} on expiry ({best['expiry']}), you make money; "
                 f"otherwise you can lose up to what you paid. The model’s chance of profit is "
                 f"{(best.get('chance_profit') or 0)*100:.1f}%.")

    return {
        "symbol": symbol.upper(),
        "under_price": S,
        "trend": trend,
        "note": book.get("note"),
        "suggestion": best,
        "confidence": best["conf"],
        "cost_estimate": round(best["mid_price"]*100.0, 2),
        "sim": sim,
        "explanation": summary,
        "thought_process": thought
    }

# ---------------- Endpoints ----------------
@router.get("/idea")
def idea(symbol: str = Query(...), buying_power: float = Query(..., ge=0.0)):
    """One best contract for a specific ticker + buying power."""
    return pick_contracts_for_symbol(symbol, buying_power)

DEFAULT_UNIVERSE = [
    "AAPL","MSFT","NVDA","AMZN","META","TSLA","GOOGL","AVGO","AMD",
    "NFLX","JPM","BRK-B","XOM","V","MA","COST","LIN","PEP","WMT","CRM"
]

@router.post("/scan-ideas")
def scan_ideas(req: ScanReq):
    """Scan a large-cap universe and return top 1–3 option ideas."""
    uni = [u.upper().strip() for u in (req.universe or DEFAULT_UNIVERSE) if u]
    ideas=[]
    for sym in uni:
        try:
            res = pick_contracts_for_symbol(sym, req.buying_power)
            if res.get("suggestion"): ideas.append(res)
        except Exception:
            continue
        # small pause to be polite to free endpoints
        time.sleep(0.15)
        if len(ideas) >= 6:  # gather a few then pick best 3
            break
    # rank by confidence then median simulated P/L if present
    def rank_key(x):
        conf = x.get("confidence",0)
        med  = (x.get("sim") or {}).get("pl_p50", -9999)
        return (-conf, -med)
    ideas_sorted = sorted(ideas, key=rank_key)[:3]
    note=None
    for r in ideas:
        if r.get("note"): note=r["note"]; break
    return {"ideas": ideas_sorted, **({"note": note} if note else {})}
