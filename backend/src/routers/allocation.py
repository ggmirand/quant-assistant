from fastapi import APIRouter
from pydantic import BaseModel
import numpy as np
router = APIRouter()
class WeightsRequest(BaseModel):
    tickers: list[str]; exp_returns: list[float]; cov: list[list[float]]
@router.post("/efficient-frontier")
def efficient_frontier(req: WeightsRequest):
    n=len(req.tickers); grid=[]; cov=np.array(req.cov)
    for _ in range(5000):
        w=np.random.dirichlet(np.ones(n)); mu=float(np.dot(w, req.exp_returns)); vol=float(np.sqrt(w @ cov @ w)); sharpe=mu/vol if vol>0 else 0.0
        grid.append({"weights":w.tolist(),"mu":mu,"vol":vol,"sharpe":sharpe})
    grid.sort(key=lambda x:-x["sharpe"]); return {"top":grid[:25]}
