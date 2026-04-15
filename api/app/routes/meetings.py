"""POST /meetings — upload transcript and enqueue. GET /meetings — list per user."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.models.io import MeetingCreateResponse, MeetingSummaryItem
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
