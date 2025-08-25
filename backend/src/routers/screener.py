# backend/src/routers/screener.py
from fastapi import APIRouter, Query
import datetime as dt
import time
import requests
from typing import Dict, Any, List

try:
    import yfinance as yf
except Exception:
    yf = None

# Reuse our option idea engine
try:
    from .options import pick_contracts_for_symbol
except Exception:
    pick_contracts_for_symbol = None

router = APIRouter()

UA = "Mozilla/5.0 (compatible; QuantAssistant/1.0)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _req_json(url, params=None, retries=2, timeout=5.0):
    last = None
    for i in range(retries+1):
        try:
            r = S.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                last = RuntimeError("429 Too Many Requests")
                time.sleep(0.6 if i < retries else 0)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.4 if i < retries else 0)
    raise last

# --- Sector performance (kept lightweight) ---
# We’ll fetch SPDR sector ETFs as a proxy: XLB,XLE,XLK,XLY,XLP,XLV,XLI,XLF,XLU,XLC,XLRE
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

def _pct_change_yesterday_close(symbol: str) -> float | None:
    if yf is None:
        return None
    try:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d")
        c = hist["Close"].dropna()
        if len(c) < 2:
            return None
        return float((c.iloc[-1] / c.iloc[-2] - 1.0) * 100.0)
    except Exception:
        return None

@router.get("/sectors")
def sectors() -> Dict[str, Any]:
    """Return simple sector % change using SPDR ETFs as proxies."""
    out = {}
    for name, etf in SECTOR_ETF_MAP.items():
        chg = _pct_change_yesterday_close(etf)
        if chg is None:
            continue
        out[name] = f"{chg:.2f}%"
    return {"Rank A: Real-Time Performance": out, "as_of": dt.datetime.utcnow().isoformat(timespec="seconds")+"Z"}

# --- Real top gainers (Yahoo predefined screener) ---
def yahoo_day_gainers(count=20) -> List[Dict[str, Any]]:
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    j = _req_json(url, params={"count": str(count), "scrIds": "day_gainers"})
    # Structure: finance.result[0].quotes[]
    quotes = (((j or {}).get("finance") or {}).get("result") or [{}])[0].get("quotes") or []
    rows = []
    for q in quotes:
        sym = q.get("symbol")
        if not sym or "." in sym:  # skip weird tickers like BRK.B / foreign suffixes
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
    """Top gainers (real tickers) via Yahoo predefined screener."""
    try:
        gainers = yahoo_day_gainers(25)[:12]
        return {"top_gainers": gainers}
    except Exception as e:
        return {"top_gainers": [], "note": f"top gainers unavailable: {type(e).__name__}"}

# --- Sector click-through: 3 best ideas + short news blurb ---
# Static, high-quality large-cap universe per sector (keeps calls light & fast)
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

def _quote_batch(symbols: list[str]) -> list[dict]:
    # Yahoo quote batch
    url = "https://query2.finance.yahoo.com/v7/finance/quote"
    j = _req_json(url, params={"symbols": ",".join(symbols[:50])})
    return ((j or {}).get("quoteResponse") or {}).get("result") or []

def _news_for_symbols(symbols: list[str], limit=4) -> list[dict]:
    # Yahoo search/news (very light; not perfect but free)
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
def sector_ideas(sector: str = Query(..., description="e.g., Technology"), buying_power: float = Query(3000.0, ge=0.0)):
    """
    When user clicks a sector, produce up to 3 best ideas from a curated universe:
    - If options engine returns a contract: suggest that option (with its probabilities).
    - Else: suggest simple 'buy shares' with 20-trading-day positive-return probability.
    """
    sector = sector.strip()
    ticks = SECTOR_UNIVERSE.get(sector, [])
    if not ticks:
        return {"sector": sector, "ideas": [], "news": [], "note": "Unknown sector or not supported."}

    ideas = []
    for t in ticks:
        try:
            if pick_contracts_for_symbol is not None:
                idea = pick_contracts_for_symbol(t, buying_power)
                if idea and idea.get("suggestion"):
                    idea["mode"] = "OPTION"
                    ideas.append(idea)
                    time.sleep(0.1)
                    if len(ideas) >= 6:
                        break
        except Exception:
            continue

    # If not enough options, fill with simple share suggestions (fallback)
    if len(ideas) < 3 and yf is not None:
        for t in ticks:
            try:
                if any(x.get("symbol")==t for x in ideas):
                    continue
                hist = yf.Ticker(t).history(period="1y", interval="1d")
                c = hist["Close"].dropna()
                if len(c) < 60:
                    continue
                # Estimate chance that 20d forward return > 0 under normal approx
                import numpy as np
                lr = np.log(c / c.shift(1)).dropna().values
                mu_d, sig_d = float(np.mean(lr)), float(np.std(lr))
                T = 20.0
                mu_T = mu_d * T
                sig_T = sig_d * (T**0.5)
                # P(R_T > 0) = P(Z > -mu_T/sig_T)
                import math
                from math import erf, sqrt
                if sig_T <= 0:
                    p_pos = 0.5
                else:
                    z = -mu_T / sig_T
                    p_pos = 0.5 * (1 - erf(z / sqrt(2)))

                # simple thought/explain
                thought = [
                    "Fallback to shares due to thin/expensive options or rate limits.",
                    "Used 1‑year daily returns to estimate 20‑day probability of gain.",
                ]
                explain = (f"This is a simple share buy idea. Over about a month (20 trading days), "
                           f"based on the past year’s moves, this stock has roughly a {(p_pos*100):.1f}% chance "
                           f"to end higher than today. You can still lose money if the price falls.")

                ideas.append({
                    "symbol": t,
                    "under_price": float(c.iloc[-1]),
                    "mode": "SHARES",
                    "explanation": explain,
                    "thought_process": thought,
                    "confidence": int(max(30, min(80, p_pos*100))),  # heuristic
                    "share_probability_up_20d": p_pos,
                })
                time.sleep(0.05)
                if len(ideas) >= 3:
                    break
            except Exception:
                continue

    # rank: prefer OPTION ideas by confidence, else SHARES by prob
    def key_fn(x):
        conf = x.get("confidence", 0)
        med = (x.get("sim") or {}).get("pl_p50", -9999)
        prob = x.get("share_probability_up_20d", 0)
        return (-conf, -med, -prob)

    ideas = sorted(ideas, key=key_fn)[:3]
    news = _news_for_symbols([i.get("symbol") for i in ideas], limit=4)

    return {"sector": sector, "ideas": ideas, "news": news}
