from fastapi import APIRouter, Query
import datetime as dt
import time
from typing import Dict, Any, List, Optional

import requests

try:
    import yfinance as yf
except Exception:
    yf = None

router = APIRouter()

UA = "Mozilla/5.0 (compatible; QuantAssistant/0.8)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _req_json(url, params=None, timeout=6.0):
    r = S.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

# ---------- Sector performance via SPDR ETFs (reliable) ----------
SECTOR_ETF_MAP = {
    "Materials": "XLB",
    "Energy": "XLE",
    "Technology": "XLK",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Financials": "XLF",
    "Utilities": "XLU",
    "Communication Services": "XLC",
    "Real Estate": "XLRE",
}

def _sector_change_percent(ticker: str) -> Optional[float]:
    """
    Return today's % change for an ETF.
    Strategy:
      1) yfinance fast_info regular*ChangePercent
      2) fallback: last close vs prev close (5d history)
    Never raises—returns None on failure.
    """
    if yf is None:
        return None
    try:
        t = yf.Ticker(ticker)
        fi = getattr(t, "fast_info", {}) or {}
        for key in ("regularMarketChangePercent", "regular_market_change_percent"):
            val = fi.get(key)
            if val is not None:
                return float(val)
        # fallback: 5d close-to-close
        hist = t.history(period="5d", interval="1d")
        c = hist["Close"].dropna()
        if len(c) >= 2:
            return float((c.iloc[-1] / c.iloc[-2] - 1.0) * 100.0)
    except Exception:
        return None
    return None

@router.get("/sectors")
def sectors() -> Dict[str, Any]:
    out: Dict[str, str] = {}
    for name, etf in SECTOR_ETF_MAP.items():
        chg = _sector_change_percent(etf)
        if chg is not None:
            out[name] = f"{chg:.2f}%"
        time.sleep(0.02)
    note = None if out else "sector data temporarily unavailable (rate-limit or no internet)"
    return {
        "Rank A: Real-Time Performance": out,
        "note": note,
        "as_of": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

# ---------- Top gainers (Yahoo predefined) with filtering ----------
def yahoo_day_gainers(count=24):
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    j = _req_json(url, params={"count": str(count), "scrIds": "day_gainers"})
    quotes = (((j or {}).get("finance") or {}).get("result") or [{}])[0].get("quotes") or []
    rows = []
    for q in quotes:
        sym = q.get("symbol")
        if not sym or "." in sym:  # strip foreign/odd tickers like BRK.B
            continue
        try:
            price = float(q.get("regularMarketPrice"))
            change_pct = float(q.get("regularMarketChangePercent"))
        except Exception:
            continue
        rows.append({
            "ticker": sym,
            "price": price,
            "change_percentage": f"{change_pct:.2f}%",
            "name": q.get("shortName") or q.get("longName") or sym
        })
    return rows

@router.get("/top-movers")
def top_movers():
    try:
        gainers = yahoo_day_gainers(24)[:12]
        return {"top_gainers": gainers}
    except Exception as e:
        return {"top_gainers": [], "note": f"top gainers unavailable: {type(e).__name__}"}

# ---------- Quick Screener (per-ticker hardening + helpful notes) ----------
def _rsi14(series):
    import numpy as np
    s = series.dropna()
    if len(s) < 20:
        return None
    d = s.diff().dropna()
    up = d.clip(lower=0.0); down = -d.clip(upper=0.0)
    roll_up = up.ewm(alpha=1/14, adjust=False).mean()
    roll_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = (roll_up/roll_down).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    rsi = 100 - (100/(1+rs))
    return float(rsi.iloc[-1])

def _ema(series, span): 
    return series.ewm(span=span, adjust=False).mean()

@router.get("/scan")
def scan(
    symbols: str = Query(...),
    min_volume: int = Query(0, ge=0),
    include_history: int = Query(1),
    history_days: int = Query(180, ge=30, le=400),
):
    """
    Returns rows for tickers that load; collects notes for any that fail (rate limits, no history, etc.).
    Never throws.
    """
    results: List[Dict[str, Any]] = []
    notes: List[str] = []
    if yf is None:
        return {"results": [], "note": "yfinance not installed"}
    tickers = [x.strip().upper() for x in symbols.split(",") if x.strip()]
    if not tickers:
        return {"results": [], "note": "no tickers provided"}

    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period=f"{max(60, history_days)}d", interval="1d")
            if hist is None or hist.empty:
                notes.append(f"{t}: no history")
                continue
            close = hist["Close"].dropna()
            vol = hist["Volume"].dropna()
            if close.empty or vol.empty:
                notes.append(f"{t}: empty series")
                continue

            price = float(close.iloc[-1])
            volume = int(vol.iloc[-1])
            if volume < min_volume:
                notes.append(f"{t}: volume {volume} < min {min_volume}")
                continue

            ema12 = _ema(close, 12).iloc[-1]
            ema26 = _ema(close, 26).iloc[-1]
            rsi = _rsi14(close) or 50.0
            mom_5d = float(price / float(close.iloc[-6]) - 1.0) if len(close) > 6 else 0.0

            score = (0.4 if ema12 > ema26 else 0.0) \
                    + (0.3 if mom_5d > 0 else 0.0) \
                    + 0.3 * max(0.0, 1.0 - abs(rsi-50)/50)

            row = {
                "symbol": t, "price": float(price), "volume": int(volume),
                "ema_short": float(ema12), "ema_long": float(ema26),
                "rsi": float(rsi), "mom_5d": float(mom_5d),
                "volume_rank_pct": 0.5, "score": float(score),
            }
            if include_history:
                row["closes"] = [round(float(x), 2) for x in close.tail(history_days).tolist()]
                row["volumes"] = [int(x) for x in vol.tail(history_days).tolist()]
            results.append(row)
            time.sleep(0.02)
        except Exception as e:
            notes.append(f"{t}: data error ({type(e).__name__})")
            continue

    results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    note = "; ".join(notes) if notes else None
    if not results and not note:
        note = "no results (symbols invalid or rate-limited)"
    return {"results": results, "note": note}
