from fastapi import FastAPI

from app.routes.dispatch import router as dispatch_router
from app.routes.health import router as health_router
from app.routes.integrations import router as integrations_router
from app.routes.meetings import router as meetings_router
from app.routes.search import router as search_router
from app.routes.sse import router as sse_router

app = FastAPI(
    title="MeetingOS API",
    description="Agent orchestration + ingestion for MeetingOS.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(meetings_router)
app.include_router(integrations_router)
app.include_router(dispatch_router)
app.include_router(search_router)
app.include_router(sse_router)
