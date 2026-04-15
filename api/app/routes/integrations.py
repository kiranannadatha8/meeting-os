"""Integration credential management — upsert, status, delete.

Authorization is handled upstream: Next.js route handlers inject the
signed-in user_id when proxying, so these endpoints trust the request
shape. That matches the existing meetings routes.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.mcp.client import MCPClient, UnknownProviderError
from app.mcp.dependencies import get_mcp_client
from app.models.io import (
    IntegrationProvider,
    IntegrationStatus,
    IntegrationUpsertRequest,
)

router = APIRouter(tags=["integrations"])


@router.put("/integrations", status_code=status.HTTP_200_OK)
def upsert_integration(
    payload: IntegrationUpsertRequest,
    mcp: Annotated[MCPClient, Depends(get_mcp_client)],
) -> dict[str, str]:
    try:
        mcp.save_integration(
            user_id=payload.user_id,
            provider=payload.provider.value,
            api_key=payload.api_key,
            metadata=payload.metadata,
        )
    except UnknownProviderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok", "provider": payload.provider.value}


@router.get("/integrations/status", response_model=IntegrationStatus)
def integration_status(
    mcp: Annotated[MCPClient, Depends(get_mcp_client)],
    user_id: Annotated[str, Query(min_length=1, max_length=255)],
) -> IntegrationStatus:
    return IntegrationStatus(**mcp.get_status(user_id))


@router.delete("/integrations", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    mcp: Annotated[MCPClient, Depends(get_mcp_client)],
    user_id: Annotated[str, Query(min_length=1, max_length=255)],
    provider: Annotated[IntegrationProvider, Query()],
) -> Response:
    mcp.delete_integration(user_id, provider.value)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
