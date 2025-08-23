from fastapi import APIRouter
from pydantic import BaseModel
import numpy as np
from ..services import data_providers as dp
from ..services import mock_data
from ..services import options_pricing as op
from ..services import data_providers as providers
from ..services import mock_data as mocks
from ..services import data_providers as dp
from ..services import data_providers
from ..services import monte_carlo as mc
router = APIRouter()
class SimRequest(BaseModel):
    symbol: str
    days: int = 30
    n_paths: int = 2000
    barrier: float | None = None
@router.post("/monte-carlo")
def monte_carlo(req: SimRequest):
    df = dp.daily_series(req.symbol, "full")
    rets = np.log(df["adj_close"]).diff().dropna()
    mu = float(rets.mean()*252); sigma = float(rets.std()*np.sqrt(252))
    cfg = mc.MCConfig(s0=float(df["adj_close"].iloc[-1]), mu=mu, sigma=sigma, days=req.days, n_paths=req.n_paths, barrier=req.barrier)
    res = mc.simulate(cfg); term = np.array(res["terminal_prices"])
    p5,p50,p95 = np.percentile(term,[5,50,95]); res["summary"]={"p5":float(p5),"p50":float(p50),"p95":float(p95),"mu_ann":mu,"sigma_ann":sigma}; return res
