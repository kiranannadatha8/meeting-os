"""POST /meetings — upload transcript and enqueue. GET /meetings — list per user."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.ingestion.parser import UnsupportedTranscriptFormatError, parse_transcript
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

    try:
        transcript = parse_transcript(filename, body)
    except UnsupportedTranscriptFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    meeting = models.Meeting(
        user_id=user_id,
        title=title,
        source_type="text",
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
