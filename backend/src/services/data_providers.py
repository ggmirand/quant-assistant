from __future__ import annotations
import pandas as pd, numpy as np, httpx
from functools import lru_cache
from ..utils import config
from . import mock_data
ALPHA = "https://www.alphavantage.co/query"
def _get(url: str, params: dict, headers: dict | None = None):
    with httpx.Client(timeout=30) as c:
        r = c.get(url, params=params, headers=headers); r.raise_for_status(); return r.json()
@lru_cache(maxsize=64)
def sector_performance() -> dict:
    if config.MOCK_MODE or not config.ALPHA_KEY: return mock_data.sector_performance()
    return _get(ALPHA, {"function":"SECTOR","apikey":config.ALPHA_KEY})
@lru_cache(maxsize=64)
def top_gainers_losers() -> dict:
    if config.MOCK_MODE or not config.ALPHA_KEY: return mock_data.top_gainers_losers()
    return _get(ALPHA, {"function":"TOP_GAINERS_LOSERS","apikey":config.ALPHA_KEY})
def daily_series(symbol: str, outputsize: str = "compact"):
    if config.MOCK_MODE or not config.ALPHA_KEY: return mock_data.daily_series(symbol)
    j = _get(ALPHA, {"function":"TIME_SERIES_DAILY_ADJUSTED","symbol":symbol,"outputsize":outputsize,"apikey":config.ALPHA_KEY})
    key = next(k for k in j.keys() if "Time Series" in k)
    df = pd.DataFrame(j[key]).T.rename_axis("date").reset_index()
    for col in df.columns:
        if col != "date": df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["date"]); df = df.sort_values("date").reset_index(drop=True)
    df.rename(columns={"5. adjusted close":"adj_close","6. volume":"volume"}, inplace=True)
    return df[["date","adj_close","volume"]]
def ema(series: pd.Series, span: int) -> pd.Series: return series.ewm(span=span, adjust=False).mean()
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff(); up, down = delta.clip(lower=0), -delta.clip(upper=0)
    roll_up = up.ewm(span=period, adjust=False).mean(); roll_down = down.ewm(span=period, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan); return 100 - (100/(1+rs))
