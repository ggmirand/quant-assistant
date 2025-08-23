from fastapi import APIRouter
from ..services import options_sources as osrc, options_pricing as op
router = APIRouter()
@router.get("/best-trades")
def best_trades(symbol: str, buying_power: float, target_delta: float = 0.25, max_days: int = 45, r: float = 0.04):
    chain = osrc.tradier_chain(symbol); options=[]
    if chain.get("options") and chain["options"].get("option"):
        for c in chain["options"]["option"]:
            if c.get("days_to_expiration", 999) > max_days: continue
            g = c.get("greeks", {}); dabs = abs(float(g.get("delta",0.0)))
            if dabs==0 or abs(dabs-target_delta) > 0.05: continue
            S=float(c.get("underlying_price",0.0)); K=float(c["strike"]); T=float(c.get("days_to_expiration",30))/365.0; sigma=float(g.get("mid_iv", g.get("iv",0.3)))
            prob = op.prob_finish_above_strike(op.BSParams(S=S,K=K,T=T,r=r,sigma=sigma))
            options.append({"symbol":symbol,"expiry":c["expiration_date"],"strike":K,"type":c["option_type"],"delta":float(g.get("delta",0.0)),"iv":sigma,"prob_finish_above_strike":prob,"mid_price":float(c.get("last",0.0))})
    options.sort(key=lambda x: (x["expiry"], -abs(x["delta"])))
    max_premium = 0.05*buying_power
    options = [o for o in options if (o["mid_price"] or 0) <= max_premium]
    return {"candidates": options[:20]}
