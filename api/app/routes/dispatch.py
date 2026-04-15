"""Dispatch routes — send processed meeting output to external tools.

Phase 3 ships the Linear handler; Gmail (T19) will land alongside.

Authorization trust model matches the rest of the API: the Next.js
layer authenticates the user and injects `user_id` in the body. The
route does *not* treat `meeting.user_id` as a membership check yet
because there's no concept of a team/org in the MVP — but we *do*
check that every dispatched action item actually belongs to the
meeting so a spoofed request can't leak IDs across meetings.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import models
from app.db.session import get_db
from app.mcp.client import MCPClient
from app.mcp.dependencies import get_mcp_client
from app.mcp.gmail import GmailAuthError, GmailClient, GmailError
from app.mcp.linear import (
    ActionItemInput,
    LinearAuthError,
    LinearClient,
    LinearError,
)
from app.models.io import (
    GmailDispatchRequest,
    GmailDispatchResponse,
    LinearDispatchCreated,
    LinearDispatchError,
    LinearDispatchRequest,
    LinearDispatchResponse,
)

router = APIRouter(tags=["dispatch"])


def get_linear_client() -> Callable[[str], LinearClient]:
    """Factory dependency — keeps tests free to swap in a fake client
    without monkey-patching. Returns a function so the API key stays out
    of DI (only the route knows which user's key to hand off)."""
    return lambda api_key: LinearClient(api_key=api_key)


@router.post(
    "/meetings/{meeting_id}/dispatch/linear",
    response_model=LinearDispatchResponse,
)
def dispatch_linear(
    payload: LinearDispatchRequest,
    meeting_id: Annotated[UUID, Path()],
    db: Annotated[Session, Depends(get_db)],
    mcp: Annotated[MCPClient, Depends(get_mcp_client)],
    linear_factory: Annotated[
        Callable[[str], LinearClient], Depends(get_linear_client)
    ],
) -> LinearDispatchResponse:
    meeting = db.get(models.Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    api_key = mcp.get_integration_key(payload.user_id, "linear")
    if not api_key:
        raise HTTPException(
            status_code=409,
            detail="Linear integration is not configured for this user",
        )

    items_by_id = {item.id: item for item in meeting.action_items}
    missing = [i for i in payload.action_item_ids if i not in items_by_id]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Action items not found on this meeting: "
                f"{', '.join(str(i) for i in missing)}"
            ),
        )

    selected = [items_by_id[i] for i in payload.action_item_ids]
    inputs = [
        ActionItemInput(title=item.title, description=_build_description(item))
        for item in selected
    ]

    client = linear_factory(api_key)
    try:
        result = client.create_issues(inputs, team_id=payload.team_id)
    except LinearAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LinearError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Result ordering from `create_issues` mirrors input ordering for
    # successes; errors carry `action_item_title`. Match both back to the
    # originating action_item_id so the UI can pair them with rows.
    title_to_id: dict[str, UUID] = {item.title: item.id for item in selected}

    created = [
        LinearDispatchCreated(
            action_item_id=selected[idx].id,
            identifier=issue.identifier,
            url=issue.url,
        )
        for idx, issue in enumerate(result.created)
    ]
    errors = [
        LinearDispatchError(
            action_item_id=title_to_id.get(err.action_item_title),
            message=err.message,
        )
        for err in result.errors
    ]
    return LinearDispatchResponse(created=created, errors=errors)


def _build_description(item: models.ActionItem) -> str:
    """Assemble a short, Linear-ready markdown description."""
    parts: list[str] = []
    if item.owner:
        parts.append(f"**Owner:** {item.owner}")
    if item.due_date:
        parts.append(f"**Due:** {item.due_date.isoformat()}")
    parts.append(f"> {item.source_quote}")
    return "\n\n".join(parts)


# ------------------------------------------------------------------
# Gmail dispatch
# ------------------------------------------------------------------


GmailClientFactory = Callable[[str, str, str], GmailClient]


def get_gmail_client() -> GmailClientFactory:
    """Factory dependency — lets tests swap in a fake GmailClient."""

    def _make(refresh_token: str, client_id: str, client_secret: str) -> GmailClient:
        return GmailClient(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )

    return _make


def get_google_oauth_app(
    settings: Annotated[Settings, Depends(get_settings)],
) -> tuple[str, str]:
    """Return the server-side Google OAuth app credentials.

    These are app-wide (not per-user) and come from env; tests override
    this to bypass the real env.
    """
    return settings.google_client_id, settings.google_client_secret


@router.post(
    "/meetings/{meeting_id}/dispatch/gmail",
    response_model=GmailDispatchResponse,
)
def dispatch_gmail(
    payload: GmailDispatchRequest,
    meeting_id: Annotated[UUID, Path()],
    db: Annotated[Session, Depends(get_db)],
    mcp: Annotated[MCPClient, Depends(get_mcp_client)],
    gmail_factory: Annotated[GmailClientFactory, Depends(get_gmail_client)],
    google_app: Annotated[tuple[str, str], Depends(get_google_oauth_app)],
) -> GmailDispatchResponse:
    meeting = db.get(models.Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    refresh_token = mcp.get_integration_key(payload.user_id, "gmail")
    if not refresh_token:
        raise HTTPException(
            status_code=409,
            detail="Gmail integration is not configured for this user",
        )

    client_id, client_secret = google_app
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=409,
            detail="Google OAuth app credentials are not configured on the server",
        )

    items_by_id = {item.id: item for item in meeting.action_items}
    missing = [i for i in payload.action_item_ids if i not in items_by_id]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Action items not found on this meeting: "
                f"{', '.join(str(i) for i in missing)}"
            ),
        )

    selected_items = [items_by_id[i] for i in payload.action_item_ids]
    subject = payload.subject or f"Follow-up: {meeting.title}"
    body_text = _build_gmail_body(meeting=meeting, action_items=selected_items)

    gmail = gmail_factory(refresh_token, client_id, client_secret)
    try:
        draft = gmail.create_draft(
            to=list(payload.recipients),
            subject=subject,
            body_text=body_text,
        )
    except GmailAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except GmailError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GmailDispatchResponse(
        draft_id=draft.draft_id,
        draft_url=f"https://mail.google.com/mail/u/0/#drafts?compose={draft.message_id}",
    )


def _build_gmail_body(
    *,
    meeting: models.Meeting,
    action_items: list[models.ActionItem],
) -> str:
    """Compose a plain-text follow-up email body.

    The body layout is deliberately plain-text only — Gmail's draft
    composer happily upgrades it to rich-text, but we don't want to
    ship broken HTML in a draft."""
    lines: list[str] = []
    summary = meeting.summary
    if summary is not None:
        lines.append("TL;DR")
        lines.append(summary.tldr)
        lines.append("")
        if summary.highlights:
            lines.append("Highlights")
            for h in summary.highlights:
                lines.append(f"- {h}")
            lines.append("")

    if action_items:
        lines.append("Action items")
        for item in action_items:
            owner = f" ({item.owner})" if item.owner else ""
            due = f" — due {item.due_date.isoformat()}" if item.due_date else ""
            lines.append(f"- {item.title}{owner}{due}")

    return "\n".join(lines).rstrip() + "\n"
