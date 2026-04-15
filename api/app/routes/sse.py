"""SSE stream for meeting status transitions.

`GET /meetings/{meeting_id}/events` holds an SSE connection open and
emits a `status` event whenever the meeting's status (or error_message)
changes in the DB. The stream closes as soon as the status is terminal
(`complete` or `failed`) — the client's EventSource handles transient
reconnects transparently.

Server-side polling (default 500ms) is fine at this scale: a worker
writing the new row and the route reading it every half-second is
cheaper than wiring a pub/sub channel for a single-user MVP.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractContextManager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse

from app.db import models
from app.db.session import SessionLocal

TERMINAL_STATUSES = {"complete", "failed"}
DEFAULT_POLL_INTERVAL = 0.5
MAX_STREAM_SECONDS = 600.0

SessionFactory = Callable[[], AbstractContextManager]

router = APIRouter(tags=["sse"])


def get_session_factory() -> SessionFactory:
    """Default: the production session factory. Overridden in tests."""
    return SessionLocal


def _read_status(
    factory: SessionFactory, meeting_id: UUID
) -> tuple[str, str | None] | None:
    """Open a short-lived session so each poll sees fresh committed state."""
    with factory() as session:
        meeting = session.get(models.Meeting, meeting_id)
        if meeting is None:
            return None
        return (meeting.status, meeting.error_message)


def _format_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_stream(
    meeting_id: UUID,
    factory: SessionFactory,
    *,
    initial: tuple[str, str | None],
    poll_interval: float,
    max_duration: float = MAX_STREAM_SECONDS,
) -> AsyncIterator[str]:
    status, err = initial
    yield _format_event("status", {"status": status, "error_message": err})
    last: tuple[str, str | None] = initial
    if status in TERMINAL_STATUSES:
        return

    elapsed = 0.0
    while elapsed <= max_duration:
        await asyncio.sleep(poll_interval)
        elapsed += max(poll_interval, 0.001)

        current = _read_status(factory, meeting_id)
        if current is None:
            yield _format_event("error", {"error": "not_found"})
            return

        if current != last:
            status, err = current
            yield _format_event(
                "status", {"status": status, "error_message": err}
            )
            last = current

        if current[0] in TERMINAL_STATUSES:
            return


@router.get("/meetings/{meeting_id}/events")
async def meeting_events(
    meeting_id: Annotated[UUID, Path()],
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
    poll_interval: Annotated[float, Query(ge=0, le=10)] = DEFAULT_POLL_INTERVAL,
) -> StreamingResponse:
    # Up-front 404 so clients don't wait through a disconnect to learn
    # their meeting id is wrong.
    initial = _read_status(factory, meeting_id)
    if initial is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    stream = _event_stream(
        meeting_id, factory, initial=initial, poll_interval=poll_interval
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "x-accel-buffering": "no",
        },
    )
