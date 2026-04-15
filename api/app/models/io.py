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


class IntegrationProvider(StrEnum):
    linear = "linear"
    gmail = "gmail"


class IntegrationUpsertRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    provider: IntegrationProvider
    api_key: str = Field(..., min_length=1)
    metadata: dict[str, object] | None = None


class IntegrationStatus(BaseModel):
    linear: bool
    gmail: bool


class LinearDispatchRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    team_id: str = Field(..., min_length=1)
    action_item_ids: list[UUID] = Field(..., min_length=1)


class LinearDispatchCreated(BaseModel):
    action_item_id: UUID
    identifier: str
    url: str


class LinearDispatchError(BaseModel):
    action_item_id: UUID | None
    message: str


class LinearDispatchResponse(BaseModel):
    created: list[LinearDispatchCreated]
    errors: list[LinearDispatchError]


class GmailDispatchRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    recipients: list[str] = Field(..., min_length=1)
    action_item_ids: list[UUID] = Field(..., min_length=1)
    subject: str | None = None


class GmailDispatchResponse(BaseModel):
    draft_id: str
    draft_url: str


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
