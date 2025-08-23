from __future__ import annotations
import httpx
from ..utils import config
def _get(url: str, params=None, headers=None):
    with httpx.Client(timeout=30) as c:
        r = c.get(url, params=params or {}, headers=headers or {}); r.raise_for_status(); return r.json()
def tradier_chain(symbol: str, expiration: str | None = None) -> dict:
    if config.MOCK_MODE or not config.TRADIER_TOKEN:
        return {"options":{"option":[
          {"expiration_date":"2025-10-17","strike":"100","option_type":"call","days_to_expiration":30,"underlying_price":100,"last":2.50,"greeks":{"delta":0.25,"mid_iv":0.30}},
          {"expiration_date":"2025-10-17","strike":"95","option_type":"put","days_to_expiration":30,"underlying_price":100,"last":2.10,"greeks":{"delta":-0.25,"mid_iv":0.32}}
        ]}}
    url="https://api.tradier.com/v1/markets/options/chains"
    params={"symbol":symbol}; 
    if expiration: params["expiration"]=expiration
    headers={"Authorization": f"Bearer {config.TRADIER_TOKEN}","Accept":"application/json"}
    return _get(url, params, headers)
def alpha_options(symbol: str, require_greeks: bool = True) -> dict:
    return {"optionChain":{"result":[]}}
