from fastapi import FastAPI
from .routers import screener, options, simulator, portfolio, allocation

app = FastAPI(
    title="Quant Assistant API",
    version="0.3.0",
    description="Educational quant toolkit: screener, options ideas, simulator, portfolio ingestion."
)
app.include_router(screener.router, prefix="/api/screener", tags=["Screener"])
app.include_router(options.router,  prefix="/api/options",  tags=["Options Ideas"])
app.include_router(simulator.router, prefix="/api/simulator", tags=["Simulator"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(allocation.router, prefix="/api/allocation", tags=["Diversification Sandbox"])

@app.get("/health")
def health(): return {"ok": True}
