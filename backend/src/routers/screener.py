from fastapi import APIRouter, Query
import datetime as dt
import time
from typing import Dict, Any, List

import requests

try:
    import yfinance as yf
except Exception:
    yf = None

# Option engine for sector ideas (present in options.py)
try:
    from .options import pick_contracts_for_symbol
except Exception:
    pick_contracts_for_symbol = None

router = APIRouter()

UA = "Mozilla/5.0 (compatible; QuantAssistant/0.4)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _req_json(url, params=None, timeout=5.0):
    r = S.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

# -------- Sector performance via sector ETFs (no-500) --------
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

@router.get("/sectors")
def sectors() -> Dict[str, Any]:
    """
    Sector % change using SPDR ETFs.
    1) Try yfinance fast_info regular-market % change
    2) Fallback: compute from the last two daily closes
    Never raises: returns { note } if unavailable.
    """
    out: Dict[str, str] = {}
    if yf is None:
        return {
            "Rank A: Real-Time Performance": out,
            "note": "yfinance not installed",
            "as_of": dt.datetime.utcnow().isoformat() + "Z",
        }

    for name, etf in SECTOR_ETF_MAP.items():
        chg = None
        try:
            t = yf.Ticker(etf)
            # fast_info may use either camelCase or snake_case depending on version
            try:
                fi = t.fast_info or {}
                for key in ("regularMarketChangePercent", "regular_market_change_percent"):
                    if key in fi and fi[key] is not None:
                        chg = float(fi[key])
                        break
            except Exception:
                chg = None

            if chg is None:
                hist = t.history(period="5d", interval="1d")
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    c = hist["Close"].dropna()
                    if len(c) >= 2:
                        chg = float((c.iloc[-1] / c.iloc[-2] - 1.0) * 100.0)

            if chg is not None:
                out[name] = f"{chg:.2f}%"
        except Exception:
            # swallow and continue (never 500)
            pass
        time.sleep(0.02)

    note = None if out else "sector data temporarily unavailable"
    return {
        "Rank A: Real-Time Performance": out,
        "note": note,
        "as_of": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

# -------- Real top gainers via Yahoo predefined screener --------
def yahoo_day_gainers(count=24):
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    j = _req_json(url, params={"count": str(count), "scrIds": "day_gainers"})
    quotes = (((j or {}).get("finance") or {}).get("result") or [{}])[0].get("quotes") or []
    rows = []
    for q in quotes:
        sym = q.get("symbol")
        if not sym or "." in sym:
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

# -------- Quick screener --------
def _rsi14(series):
    import numpy as np
    s = series.dropna()
    if len(s) < 20:
        return None
    delta = s.diff().dropna()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    roll_up = up.ewm(alpha=1/14, adjust=False).mean()
    roll_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = (roll_up / roll_down).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])

def _ema(series, span): return series.ewm(span=span, adjust=False).mean()

@router.get("/scan")
def scan(
    symbols: str = Query(...),
    min_volume: int = Query(1_000_000, ge=0),
    include_history: int = Query(1),
    history_days: int = Query(180, ge=30, le=400),
):
    results = []
    if yf is None:
        return {"results": [], "note": "yfinance not installed"}

    for t in [x.strip().upper() for x in symbols.split(",") if x.strip()]:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period=f"{max(60, history_days)}d", interval="1d")
            if hist is None or hist.empty:
                continue
            close = hist["Close"].dropna()
            vol = hist["Volume"].dropna()
            price = float(close.iloc[-1])
            volume = int(vol.iloc[-1])

            ema12 = _ema(close, 12).iloc[-1]
            ema26 = _ema(close, 26).iloc[-1]
            rsi = _rsi14(close) or 50.0
            mom_5d = float(price / float(close.iloc[-6]) - 1.0) if len(close) > 6 else 0.0

            score = 0.0
            if ema12 > ema26: score += 0.4
            if mom_5d > 0: score += 0.3
            score += 0.3 * max(0.0, 1.0 - abs(rsi - 50)/50)

            row = {
                "symbol": t,
                "price": price,
                "volume": volume,
                "ema_short": float(ema12),
                "ema_long": float(ema26),
                "rsi": float(rsi),
                "mom_5d": float(mom_5d),
                "volume_rank_pct": 0.5,  # placeholder
                "score": float(score),
            }
            if include_history:
                row["closes"] = [round(float(x), 2) for x in close.tail(history_days).tolist()]
                row["volumes"] = [int(x) for x in vol.tail(history_days).tolist()]
            results.append(row)
            time.sleep(0.02)
        except Exception:
            continue

    results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return {"results": results, "note": None}

# -------- Sector click-through (ideas + headlines) --------
SECTOR_UNIVERSE = {
    "Technology": ["AAPL","MSFT","NVDA","AMD","AVGO","CRM","ADBE","QCOM"],
    "Communication Services": ["META","GOOGL","NFLX","DIS"],
    "Consumer Discretionary": ["AMZN","TSLA","HD","NKE"],
    "Consumer Staples": ["WMT","COST","PEP","PG"],
    "Health Care": ["LLY","UNH","JNJ","MRK","PFE"],
    "Industrials": ["CAT","BA","UNP","GE"],
    "Financials": ["JPM","BAC","V","MA","GS"],
    "Energy": ["XOM","CVX","SLB"],
    "Materials": ["LIN","APD","FCX"],
    "Utilities": ["NEE","DUK","SO"],
    "Real Estate": ["PLD","AMT","EQIX"],
}

def _news_for_symbols(symbols: List[str], limit=4) -> List[dict]:
    out = []
    for sym in symbols[:3]:
        try:
            url = "https://query2.finance.yahoo.com/v1/finance/search"
            j = _req_json(url, params={"q": sym, "newsCount": str(limit)})
            news = (j or {}).get("news") or []
            for n in news[:2]:
                title = n.get("title")
                publisher = n.get("publisher")
                link = None
                for u in (n.get("linkPresentation") or []):
                    if isinstance(u, dict) and u.get("url"):
                        link = u["url"]; break
                out.append({"symbol": sym, "title": title, "publisher": publisher, "url": link})
        except Exception:
            continue
    return out[:limit]

@router.get("/sector-ideas")
def sector_ideas(sector: str = Query(...), buying_power: float = Query(3000.0, ge=0.0)):
    sector = sector.strip()
    ticks = SECTOR_UNIVERSE.get(sector, [])
    if not ticks:
        return {"sector": sector, "ideas": [], "news": [], "note": "Unknown or unsupported sector."}

    ideas = []
    if pick_contracts_for_symbol:
        for t in ticks:
            try:
                idea = pick_contracts_for_symbol(t, buying_power)
                if idea and idea.get("suggestion"):
                    idea["mode"] = "OPTION"
                    ideas.append(idea)
                    time.sleep(0.05)
                    if len(ideas) >= 6: break
            except Exception:
                continue

    if len(ideas) > 3:
        ideas = sorted(ideas, key=lambda x: (-x.get("confidence",0), - (x.get("sim") or {}).get("pl_p50",-9999)))[:3]

    news = _news_for_symbols([i.get("symbol") for i in ideas], limit=4)
    return {"sector": sector, "ideas": ideas[:3], "news": news}
