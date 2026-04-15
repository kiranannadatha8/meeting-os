"""BullMQ producer — wraps the `bullmq` Python library.

Why a thin module: the route handler shouldn't know how to construct a Queue
or what the connection URL is. This also makes it easy to swap the queue
name per-test for isolation.
"""
from __future__ import annotations

from bullmq import Queue

from app.config import get_settings

DEFAULT_QUEUE_NAME = "meetings"
JOB_NAME = "process-meeting"

_queue_name = DEFAULT_QUEUE_NAME


def get_queue_name() -> str:
    return _queue_name


def set_queue_name(name: str) -> None:
    """Override the active queue name (used by integration tests for isolation)."""
    global _queue_name
    _queue_name = name


def _connection_opts() -> dict[str, str]:
    return {"connection": get_settings().redis_url}


async def enqueue_meeting_job(meeting_id: str) -> None:
    """Push a job onto the BullMQ queue. Awaits the underlying Redis write."""
    queue = Queue(_queue_name, _connection_opts())
    try:
        await queue.add(JOB_NAME, {"meeting_id": meeting_id})
    finally:
        await queue.close()
