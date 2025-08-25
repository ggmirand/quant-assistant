# backend/src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers (some may be optional in your repo)
try:
    from .routers import screener
except Exception:
    screener = None
try:
    from .routers import options
except Exception:
    options = None
try:
    from .routers import simulator
except Exception:
    simulator = None

app = FastAPI(title="Quant Assistant API")

# --- CORS for local UI on 5173 ---
ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

# Mount routers under /api
if screener:
    app.include_router(screener.router, prefix="/api/screener", tags=["screener"])
if options:
    app.include_router(options.router, prefix="/api/options", tags=["options"])
if simulator:
    app.include_router(simulator.router, prefix="/api/simulator", tags=["simulator"])

@app.get("/")
def root():
    return {"message": "Quant Assistant API. See /docs"}

