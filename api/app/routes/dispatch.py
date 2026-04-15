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

from typing import Annotated, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.mcp.client import MCPClient
from app.mcp.dependencies import get_mcp_client
from app.mcp.linear import (
    ActionItemInput,
    LinearAuthError,
    LinearClient,
    LinearError,
)
from app.models.io import (
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
