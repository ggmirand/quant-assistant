from fastapi import APIRouter, Query
from ..services import data_providers as dp
import numpy as np

router = APIRouter()

@router.get("/sectors")
def sectors():
    return dp.sector_performance()

@router.get("/top-movers")
def top_movers():
    return dp.top_gainers_losers()

@router.get("/scan")
def scan(
    symbols: str = Query(..., description="Comma-separated symbols"),
    ema_short: int = 12,
    ema_long: int = 26,
    min_volume: int = 500000,
    rsi_overbought: int = 70,
    rsi_oversold: int = 30,
    include_history: bool = True,
    history_days: int = 30,
):
    """
    Technical scan with optional recent close/volume history.
    Returns for each symbol:
      - price, volume, EMA(12/26), RSI, signals
      - closes: last N adjusted closes (for charts)
      - volumes: last N volumes (for charts)
      - mom_5d: 5-day return
      - volume_rank_pct: cross-sectional percentile among provided symbols
      - score: composite 0..100 (trend, volume, RSI closeness to 50, 5d momentum)
    """
    raw = []
    for s in [x.strip().upper() for x in symbols.split(",") if x.strip()]:
        df = dp.daily_series(s, "compact")
        if df.empty:
            continue
        df["ema_s"] = dp.ema(df["adj_close"], ema_short)
        df["ema_l"] = dp.ema(df["adj_close"], ema_long)
        df["rsi"]   = dp.rsi(df["adj_close"])
        last = df.iloc[-1]

        # recent closes & volumes for charts + momentum
        tail = df.tail(max(history_days, 6)).copy()
        closes = tail["adj_close"].to_list()
        vols_hist = tail["volume"].to_list()

        # 5-day simple return
        if len(tail) >= 6:
            mom_5d = float((tail["adj_close"].iloc[-1] / tail["adj_close"].iloc[-6]) - 1.0)
        else:
            mom_5d = float("nan")

        entry = {
            "symbol": s,
            "price": float(last["adj_close"]),
            "volume": int(last["volume"]),
            "ema_short": float(last["ema_s"]),
            "ema_long": float(last["ema_l"]),
            "rsi": float(last["rsi"]),
            "signals": {
                "trend_up": bool(last["ema_s"] > last["ema_l"]),
                "oversold": bool(last["rsi"] <= rsi_oversold),
                "overbought": bool(last["rsi"] >= rsi_overbought),
                "meets_min_volume": bool(last["volume"] >= min_volume),
            },
            "mom_5d": mom_5d,
        }
        if include_history:
            entry["closes"] = closes[-history_days:]
            entry["volumes"] = vols_hist[-history_days:]

        raw.append(entry)

    if not raw:
        return {"results": []}

    # Cross-sectional volume percentile
    vols = np.array([r["volume"] for r in raw], dtype=float)
    order = vols.argsort()
    pct = np.empty_like(order, dtype=float)
    pct[order] = np.arange(len(vols)) / max(len(vols) - 1, 1)
    for i, r in enumerate(raw):
        r["volume_rank_pct"] = float(pct[i])

    # Composite score 0..100
    def clamp(x, lo, hi): return max(lo, min(hi, x))
    for r in raw:
        trend = 1.0 if r["signals"]["trend_up"] else 0.0
        volp  = r.get("volume_rank_pct", 0.0)
        rsi   = r.get("rsi", 50.0)
        rsi_term = clamp(1.0 - abs((rsi - 50.0)/50.0), 0.0, 1.0)
        m5 = r.get("mom_5d")
        if m5 is None or np.isnan(m5): m5 = 0.0
        m5 = clamp(m5, -1.0, 1.0)
        m5_term = (m5 + 1.0)/2.0
        score = 40*trend + 30*volp + 20*rsi_term + 10*m5_term
        r["score"] = round(float(score), 2)

    raw.sort(key=lambda x: x["score"], reverse=True)
    return {"results": raw}
