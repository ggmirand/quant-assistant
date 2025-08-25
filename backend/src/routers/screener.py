# backend/src/routers/screener.py
from fastapi import APIRouter, Query
import datetime as dt
import time
from typing import Dict, Any, List, Tuple

import requests

try:
    import yfinance as yf
except Exception:
    yf = None

# Option engine (for sector ideas)
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
                time.sleep(0.7 if i < retries else 0)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(0.5 if i < retries else 0)
    if last:
        raise last

# -------- Sector performance via sector ETFs (live change %) --------
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

def _quote_batch(symbols: List[str]) -> List[dict]:
    url = "https://query2.finance.yahoo.com/v7/finance/quote"
    j = _req_json(url, params={"symbols": ",".join(symbols[:50])})
    return ((j or {}).get("quoteResponse") or {}).get("result") or []

@router.get("/sectors")
def sectors() -> Dict[str, Any]:
    """Return sector % change using SPDR ETFs (live change %, not yesterday)."""
    rows = _quote_batch(list(SECTOR_ETF_MAP.values()))
    change_by_symbol = {r.get("symbol"): r.get("regularMarketChangePercent") for r in rows}
    out = {}
    for name, etf in SECTOR_ETF_MAP.items():
        chg = change_by_symbol.get(etf)
        if chg is None:
            continue
        try:
            out[name] = f"{float(chg):.2f}%"
        except Exception:
            continue
    return {"Rank A: Real-Time Performance": out, "as_of": dt.datetime.utcnow().isoformat(timespec="seconds")+"Z"}

# -------- Real top gainers via Yahoo predefined screener --------
def yahoo_day_gainers(count=24) -> List[Dict[str, Any]]:
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

# -------- Lightweight screener (RESTORED) --------
def _rsi14(series) -> float | None:
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

def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

@router.get("/scan")
def scan(
    symbols: str = Query(..., description="Comma-separated tickers"),
    min_volume: int = Query(1_000_000, ge=0),
    include_history: int = Query(1),
    history_days: int = Query(180, ge=30, le=400),
):
    """Basic screener for a user-supplied list."""
    tickers = [t.strip().upper() for t in symbols.split(",") if t.strip()]
    results = []

    if yf is None:
        return {"results": [], "note": "yfinance not installed"}

    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period=f"{max(60, history_days)}d", interval="1d")
            if hist is None or hist.empty:
                continue
            close = hist["Close"].dropna()
            vol = hist["Volume"].dropna()
            price = float(close.iloc[-1])
            volume = int(vol.iloc[-1])
            if volume < min_volume:
                # still include, but mark
                pass
            ema12 = _ema(close, 12).iloc[-1]
            ema26 = _ema(close, 26).iloc[-1]
            rsi = _rsi14(close) or 50.0
            mom_5d = float(price / float(close.iloc[-6]) - 1.0) if len(close) > 6 else 0.0

            # Quick “score”: trend + momentum + RSI closeness to 50
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
                "volume_rank_pct": 0.5,  # placeholder (needs multi-stock relative calc)
                "signals": {
                    "trend_up": ema12 > ema26,
                    "oversold": rsi < 35,
                    "overbought": rsi > 65,
                    "meets_min_volume": volume >= min_volume,
                },
                "score": float(score),
            }
            if include_history:
                # send normalized arrays (not huge)
                row["closes"] = [round(float(x), 2) for x in close.tail(history_days).tolist()]
                row["volumes"] = [int(x) for x in vol.tail(history_days).tolist()]
            results.append(row)
            time.sleep(0.05)
        except Exception:
            continue

    results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return {"results": results, "note": None}

# -------- Sector click-through: 3 best ideas + headlines --------
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

    # fallback to shares if needed
    if len(ideas) < 3 and yf is not None:
        import numpy as np, math
        for t in ticks:
            try:
                if any(x.get("symbol")==t for x in ideas): continue
                hist = yf.Ticker(t).history(period="1y", interval="1d")
                c = hist["Close"].dropna()
                if len(c) < 60: continue
                lr = np.log(c / c.shift(1)).dropna().values
                mu_d, sig_d = float(np.mean(lr)), float(np.std(lr))
                T = 20.0
                mu_T = mu_d * T
                sig_T = sig_d * (T**0.5)
                p_pos = 0.5 if sig_T <= 0 else 0.5 * (1 - math.erf((-mu_T / sig_T) / math.sqrt(2)))
                ideas.append({
                    "symbol": t,
                    "under_price": float(c.iloc[-1]),
                    "mode": "SHARES",
                    "explanation": (f"This is a share buy idea. Over ~20 trading days, "
                                    f"based on last year’s moves, there’s about a {(p_pos*100):.1f}% "
                                    f"chance it ends higher than today."),
                    "thought_process": [
                        "Fallback to shares due to thin/expensive options or rate limits.",
                        "Used 1‑year daily returns to estimate 20‑day probability of gain."
                    ],
                    "confidence": int(max(30, min(80, p_pos*100))),
                    "share_probability_up_20d": p_pos,
                })
                time.sleep(0.05)
                if len(ideas) >= 3: break
            except Exception:
                continue

    def key_fn(x):
        conf = x.get("confidence", 0)
        med  = (x.get("sim") or {}).get("pl_p50", -9999)
        prob = x.get("share_probability_up_20d", 0)
        return (-conf, -med, -prob)

    ideas = sorted(ideas, key=key_fn)[:3]
    news = _news_for_symbols([i.get("symbol") for i in ideas], limit=4)
    return {"sector": sector, "ideas": ideas, "news": news}
