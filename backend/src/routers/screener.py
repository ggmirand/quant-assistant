from fastapi import APIRouter, Query
from ..services import data_providers as dp
router = APIRouter()
@router.get("/sectors")
def sectors(): return dp.sector_performance()
@router.get("/top-movers")
def top_movers(): return dp.top_gainers_losers()
@router.get("/scan")
def scan(symbols: str = Query(...), ema_short: int = 12, ema_long: int = 26, min_volume: int = 500000, rsi_overbought: int = 70, rsi_oversold: int = 30):
    out=[]
    for s in [x.strip().upper() for x in symbols.split(",") if x.strip()]:
        df = dp.daily_series(s, "compact")
        if df.empty: continue
        df["ema_s"] = dp.ema(df["adj_close"], ema_short)
        df["ema_l"] = dp.ema(df["adj_close"], ema_long)
        df["rsi"] = dp.rsi(df["adj_close"])
        last = df.iloc[-1]
        out.append({"symbol": s, "price": float(last["adj_close"]), "volume": int(last["volume"]),
                    "ema_short": float(last["ema_s"]), "ema_long": float(last["ema_l"]), "rsi": float(last["rsi"]),
                    "signals":{"trend_up": bool(last["ema_s"]>last["ema_l"]), "oversold": bool(last["rsi"]<=rsi_oversold),
                               "overbought": bool(last["rsi"]>=rsi_overbought), "meets_min_volume": bool(last["volume"]>=min_volume)}})
    return {"results": out}
