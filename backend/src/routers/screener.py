from fastapi import APIRouter, Query
import datetime as dt
import time
from typing import Dict, Any, List, Optional

import io
import requests
import pandas as pd

try:
    import yfinance as yf
except Exception:
    yf = None

router = APIRouter()

UA = "Mozilla/5.0 (compatible; QuantAssistant/0.9)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _req_json(url, params=None, timeout=6.0):
    r = S.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

# ------------------------ Stooq fallback helpers (EOD CSV) ------------------------
def _stooq_hist_daily(symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
    """
    Fetch EOD daily history from Stooq: https://stooq.com/q/d/l/?s=aapl.us&i=d
    Returns DataFrame with Date, Open, High, Low, Close, Volume or None.
    """
    try:
        sym = symbol.lower()
        if not sym.endswith(".us"):
            sym = sym + ".us"
        url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
        r = S.get(url, timeout=5)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").tail(max(60, days))
        return df
    except Exception:
        return None

def _hist_close_series(symbol: str, days: int = 365) -> Optional[pd.Series]:
    """
    Try yfinance history first (intraday/EOD), fallback to Stooq EOD CSV.
    Returns a pandas Series of Close, indexed by date.
    """
    # yfinance first
    if yf is not None:
        try:
            t = yf.Ticker(symbol)
            h = t.history(period=f"{max(60, days)}d", interval="1d")
            if h is not None and not h.empty and "Close" in h:
                return h["Close"].dropna()
        except Exception:
            pass
    # Stooq fallback
    df = _stooq_hist_daily(symbol, days)
    if df is None or df.empty:
        return None
    return df.set_index("Date")["Close"].dropna()

def _last_price(symbol: str) -> Optional[float]:
    """Fast last price: yfinance fast_info, fallback to last Close from Stooq."""
    if yf is not None:
        try:
            info = yf.Ticker(symbol).fast_info
            for k in ("last_price", "regularMarketPrice", "regular_market_price"):
                v = info.get(k)
                if v is not None:
                    return float(v)
        except Exception:
            pass
    s = _hist_close_series(symbol, 10)
    return float(s.iloc[-1]) if s is not None and len(s) else None

# ------------------------ Sector performance via SPDR ETFs ------------------------
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
    Try yfinance fast_info change% first; fallback to close-to-close using history (yfinance or Stooq).
    """
    # yfinance change%
    if yf is not None:
        try:
            t = yf.Ticker(ticker)
            fi = getattr(t, "fast_info", {}) or {}
            for key in ("regularMarketChangePercent", "regular_market_change_percent"):
                val = fi.get(key)
                if val is not None:
                    return float(val)
        except Exception:
            pass
    # close-to-close (works with Stooq if needed)
    s = _hist_close_series(ticker, 5)
    if s is None or len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[-2] - 1.0) * 100.0)

@router.get("/sectors")
def sectors() -> Dict[str, Any]:
    out: Dict[str, str] = {}
    for name, etf in SECTOR_ETF_MAP.items():
        chg = _sector_change_percent(etf)
        if chg is not None:
            out[name] = f"{chg:.2f}%"
        time.sleep(0.02)  # avoid hammering
    note = None if out else "sector data temporarily unavailable (rate-limit or offline)"
    return {
        "Rank A: Real-Time Performance": out,
        "note": note,
        "as_of": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

# ------------------------ Top gainers (Yahoo predefined) ------------------------
def yahoo_day_gainers(count=24):
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    j = _req_json(url, params={"count": str(count), "scrIds": "day_gainers"})
    quotes = (((j or {}).get("finance") or {}).get("result") or [{}])[0].get("quotes") or []
    rows = []
    for q in quotes:
        sym = q.get("symbol")
        if not sym or "." in sym:  # filter non-standard like BRK.B
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

# ------------------------ Quick Screener (yahoo→stooq fallback per ticker) ------------------------
def _rsi14(series: pd.Series) -> Optional[float]:
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

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

@router.get("/scan")
def scan(
    symbols: str = Query(...),
    min_volume: int = Query(0, ge=0),
    include_history: int = Query(1),
    history_days: int = Query(180, ge=30, le=400),
):
    results: List[Dict[str, Any]] = []
    notes: List[str] = []
    tickers = [x.strip().upper() for x in symbols.split(",") if x.strip()]
    if not tickers:
        return {"results": [], "note": "no tickers provided"}

    for t in tickers:
        try:
            s_close = _hist_close_series(t, history_days)
            if s_close is None or s_close.empty:
                notes.append(f"{t}: no history")
                continue

            price = float(s_close.iloc[-1])
            # We don't have intraday volume from Stooq; leave as 0 if absent
            volume = 0
            if yf is not None:
                try:
                    vol_series = yf.Ticker(t).history(period=f"{max(60, history_days)}d", interval="1d")["Volume"].dropna()
                    if len(vol_series):
                        volume = int(vol_series.iloc[-1])
                except Exception:
                    pass

            if volume < min_volume:
                notes.append(f"{t}: volume {volume} < min {min_volume}") if min_volume>0 else None

            ema12 = _ema(s_close, 12).iloc[-1]
            ema26 = _ema(s_close, 26).iloc[-1]
            rsi = _rsi14(s_close) or 50.0
            mom_5d = float(price / float(s_close.iloc[-6]) - 1.0) if len(s_close) > 6 else 0.0

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
                row["closes"] = [round(float(x), 2) for x in s_close.tail(history_days).tolist()]
                # If we didn't get volume history, send empty list to keep UI happy
                if yf is not None:
                    try:
                        vol_series = yf.Ticker(t).history(period=f"{max(60, history_days)}d", interval="1d")["Volume"].dropna()
                        row["volumes"] = [int(x) for x in vol_series.tail(history_days).tolist()]
                    except Exception:
                        row["volumes"] = []
                else:
                    row["volumes"] = []
            results.append(row)
            time.sleep(0.02)
        except Exception as e:
            notes.append(f"{t}: data error ({type(e).__name__})")
            continue

    results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    note = "; ".join(notes) if notes else None
    if not results and not note:
        note = "no results (symbols invalid or providers offline)"
    return {"results": results, "note": note}
