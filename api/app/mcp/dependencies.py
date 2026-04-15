"""FastAPI dependency wiring for the MCP client."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.mcp.client import MCPClient
from app.mcp.crypto import get_active_key
from app.mcp.store import DbIntegrationStore


def get_mcp_client(
    db: Annotated[Session, Depends(get_db)],
) -> MCPClient:
    return MCPClient(store=DbIntegrationStore(db), encryption_key=get_active_key())
