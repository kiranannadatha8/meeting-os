"""Pydantic I/O models — request/response contracts for the HTTP layer."""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthOut(BaseModel):
    status: str = Field(..., examples=["ok"])


class MeetingStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class SourceType(StrEnum):
    text = "text"
    audio = "audio"


class MeetingCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: MeetingStatus


class MeetingSummaryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: MeetingStatus
    source_type: SourceType
    created_at: datetime


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    rationale: str
    source_quote: str


class ActionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    owner: str | None
    due_date: date | None
    source_quote: str


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tldr: str
    highlights: list[str]


class MeetingDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: MeetingStatus
    source_type: SourceType
    source_filename: str
    transcript: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    decisions: list[DecisionOut]
    action_items: list[ActionItemOut]
    summary: SummaryOut | None
    langsmith_run_ids: list[str] | None = None
