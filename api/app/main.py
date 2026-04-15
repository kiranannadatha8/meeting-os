from fastapi import FastAPI

from app.routes.health import router as health_router
from app.routes.meetings import router as meetings_router

app = FastAPI(
    title="MeetingOS API",
    description="Agent orchestration + ingestion for MeetingOS.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(meetings_router)
