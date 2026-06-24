"""Schemas de jobs."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: UUID
    kind: str
    status: str
    total: int
    processed: int
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
