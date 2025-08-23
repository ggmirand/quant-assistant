from __future__ import annotations
import numpy as np
from dataclasses import dataclass
@dataclass
class MCConfig:
    s0: float; mu: float; sigma: float; days: int; n_paths: int = 2000; seed: int | None = 42; barrier: float | None = None
def simulate(cfg: MCConfig):
    if cfg.seed is not None: np.random.seed(cfg.seed)
    dt=1/252; steps=cfg.days; paths=np.zeros((cfg.n_paths,steps+1)); paths[:,0]=cfg.s0
    for t in range(1,steps+1):
        z=np.random.standard_normal(cfg.n_paths)
        paths[:,t]=paths[:,t-1]*np.exp((cfg.mu-0.5*cfg.sigma**2)*dt + cfg.sigma*np.sqrt(dt)*z)
    res={"terminal_prices":paths[:,-1].tolist()}
    if cfg.barrier is not None:
        touched=(paths>=cfg.barrier).any(axis=1) if cfg.barrier>=cfg.s0 else (paths<=cfg.barrier).any(axis=1)
        res["prob_touch"]=float(touched.mean())
    return res
