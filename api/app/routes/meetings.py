"""Meeting routes.

- `POST /meetings` — upload transcript (or audio) and enqueue for processing.
- `GET /meetings` — list meetings scoped to a user.
- `GET /meetings/{id}` — full detail payload consumed by the results UI.
- `POST /meetings/{id}/retry` — re-queue a failed meeting.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import models
from app.db.session import get_db
from app.ingestion.parser import (
    UnsupportedTranscriptFormatError,
    classify_source,
    parse_transcript,
)
from app.ingestion.whisper_adapter import (
    AUDIO_SIZE_LIMIT_BYTES,
    AudioTooLargeError,
    TranscriptionError,
    transcribe_audio,
)
from app.models.io import (
    MeetingCreateResponse,
    MeetingDetail,
    MeetingSummaryItem,
)
from app.queue import enqueue_meeting_job

router = APIRouter(tags=["meetings"])


@router.post(
    "/meetings",
    response_model=MeetingCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_meeting(
    title: Annotated[str, Form(min_length=1, max_length=500)],
    user_id: Annotated[str, Form(min_length=1, max_length=255)],
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingCreateResponse:
    body = await file.read()
    filename = file.filename or ""

    kind = classify_source(filename)
    if kind == "unsupported":
        raise HTTPException(
            status_code=422, detail=f"Unsupported upload type: {filename or '<no filename>'}"
        )

    if kind == "text":
        try:
            transcript = parse_transcript(filename, body)
        except UnsupportedTranscriptFormatError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        source_type = "text"
    else:  # audio
        if len(body) > AUDIO_SIZE_LIMIT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio payload exceeds {AUDIO_SIZE_LIMIT_BYTES} byte limit",
            )
        try:
            transcript = transcribe_audio(body, filename=filename)
        except AudioTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except TranscriptionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            # Audio bytes never get persisted — clearing the local reference
            # is what "delete after transcription" means in the in-memory path.
            del body
        source_type = "audio"

    meeting = models.Meeting(
        user_id=user_id,
        title=title,
        source_type=source_type,
        source_filename=filename,
        transcript=transcript,
        status="queued",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    await enqueue_meeting_job(str(meeting.id))

    return MeetingCreateResponse.model_validate(meeting)


@router.get("/meetings", response_model=list[MeetingSummaryItem])
def list_meetings(
    db: Annotated[Session, Depends(get_db)],
    user_id: Annotated[str, Query(min_length=1, max_length=255)],
) -> list[MeetingSummaryItem]:
    rows = db.execute(
        select(models.Meeting)
        .where(models.Meeting.user_id == user_id)
        .order_by(models.Meeting.created_at.desc())
    ).scalars().all()
    return [MeetingSummaryItem.model_validate(row) for row in rows]


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: Annotated[UUID, Path()],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingDetail:
    """Return the full payload for the results UI.

    `selectinload` keeps this to three queries (meeting + decisions/items +
    summary) regardless of how many children exist — good enough at this scale.
    """
    meeting = db.execute(
        select(models.Meeting)
        .where(models.Meeting.id == meeting_id)
        .options(
            selectinload(models.Meeting.decisions),
            selectinload(models.Meeting.action_items),
            selectinload(models.Meeting.summary),
        )
    ).scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingDetail.model_validate(meeting)


@router.post("/meetings/{meeting_id}/retry", response_model=MeetingCreateResponse, status_code=202)
async def retry_meeting(
    meeting_id: Annotated[UUID, Path()],
    db: Annotated[Session, Depends(get_db)],
) -> MeetingCreateResponse:
    """Re-queue a failed meeting. Rejects anything not in `failed` so we
    never trample an in-flight run."""
    meeting = db.get(models.Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Only failed meetings can be retried; current status: {meeting.status}",
        )
    meeting.status = "queued"
    meeting.error_message = None
    db.commit()
    db.refresh(meeting)

    await enqueue_meeting_job(str(meeting.id))

    return MeetingCreateResponse.model_validate(meeting)
