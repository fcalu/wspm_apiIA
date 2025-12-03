from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes_health import router as health_router
from app.api.v1.routes_nfl import router as nfl_router
from app.api.v1.routes_nba import router as nba_router        # ⬅️ NUEVO
from app.api.v1.routes_soccer import router as soccer_router  # ⬅️ NUEVO


app = FastAPI(
    title="WSPM API",
    description="Backend FastAPI para modelos WSPM con datos de ESPN (no oficial).",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(nfl_router, prefix="/api/v1")
app.include_router(nba_router, prefix="/api/v1")       # ⬅️ NUEVO
app.include_router(soccer_router, prefix="/api/v1")    # ⬅️ NUEVO


@app.get("/")
async def root():
    return {"message": "WSPM API base funcionando"}
