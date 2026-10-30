from fastapi import FastAPI

from app.routers.health import router as health_router
from app.routers.analysis import router as analysis_router
from app.routers.players import router as players_router
from app.routers.games import router as games_router
from app.routers.agent import router as agent_router

app = FastAPI(
    title="DUGOUT AI",
    description="AI Baseball Decision Intelligence Platform",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(analysis_router)
app.include_router(players_router)
app.include_router(games_router)
app.include_router(agent_router)

@app.get("/")
async def root():
    return {
        "service": "DUGOUT AI",
        "message": "Welcome to DUGOUT AI",
    }