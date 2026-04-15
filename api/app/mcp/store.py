"""SQLAlchemy-backed implementation of the `IntegrationStore` protocol."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.mcp.client import IntegrationRecord


def _to_record(row: models.Integration) -> IntegrationRecord:
    return IntegrationRecord(
        id=row.id,
        user_id=row.user_id,
        provider=row.provider,  # type: ignore[arg-type]
        encrypted_key=row.encrypted_key,
        metadata=row.metadata_,
    )


class DbIntegrationStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, record: IntegrationRecord) -> IntegrationRecord:
        existing = self._session.execute(
            select(models.Integration).where(
                models.Integration.user_id == record.user_id,
                models.Integration.provider == record.provider,
            )
        ).scalar_one_or_none()

        if existing is None:
            row = models.Integration(
                id=record.id,
                user_id=record.user_id,
                provider=record.provider,
                encrypted_key=record.encrypted_key,
                metadata_=record.metadata,
            )
            self._session.add(row)
        else:
            existing.encrypted_key = record.encrypted_key
            existing.metadata_ = record.metadata
            row = existing
        self._session.commit()
        self._session.refresh(row)
        return _to_record(row)

    def get(self, user_id: str, provider: str) -> IntegrationRecord | None:
        row = self._session.execute(
            select(models.Integration).where(
                models.Integration.user_id == user_id,
                models.Integration.provider == provider,
            )
        ).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    def list_for_user(self, user_id: str) -> list[IntegrationRecord]:
        rows = self._session.execute(
            select(models.Integration).where(
                models.Integration.user_id == user_id,
            )
        ).scalars().all()
        return [_to_record(r) for r in rows]

    def delete(self, user_id: str, provider: str) -> bool:
        row = self._session.execute(
            select(models.Integration).where(
                models.Integration.user_id == user_id,
                models.Integration.provider == provider,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True
