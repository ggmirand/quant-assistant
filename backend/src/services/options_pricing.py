from __future__ import annotations
import math
from dataclasses import dataclass
from scipy.stats import norm
@dataclass
class BSParams: S: float; K: float; T: float; r: float; sigma: float
def d1(p: BSParams) -> float: return (math.log(p.S/p.K) + (p.r + 0.5*p.sigma**2)*p.T) / (p.sigma*math.sqrt(p.T))
def d2(p: BSParams) -> float: return d1(p) - p.sigma*math.sqrt(p.T)
def prob_finish_above_strike(p: BSParams) -> float:
    if p.T <= 0 or p.sigma <= 0: return float('nan')
    from math import isfinite; val = norm.cdf(d2(p)); return float(val if isfinite(val) else 'nan')
