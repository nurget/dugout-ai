from fastapi import FastAPI

from app.routers.health import router as health_router
from app.routers.analysis import router as analysis_router

app = FastAPI(
    title="DUGOUT AI",
    description="AI Baseball Decision Intelligence Platform",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(analysis_router)


@app.get("/")
async def root():
    return {
        "service": "DUGOUT AI",
        "message": "Welcome to DUGOUT AI",
    }