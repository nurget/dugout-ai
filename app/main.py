from fastapi import FastAPI

from app.routers.health import router as health_router
from app.routers.agent import router as agent_router
from app.routers.auth import router as auth_router
from app.routers.team import router as team_router

app = FastAPI(
    title="DUGOUT AI",
    description="AI Baseball Decision Intelligence Platform",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(team_router)


@app.get("/")
async def root():
    return {
        "service": "DUGOUT AI",
        "message": "Welcome to DUGOUT AI",
    }
