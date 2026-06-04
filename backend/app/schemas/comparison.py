from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ComparisonCreate(BaseModel):
    source_retrieval_id: UUID
    target_retrieval_id: UUID

class ComparisonResponse(BaseModel):
    id: UUID
    source_retrieval_id: UUID
    target_retrieval_id: UUID
    status: str
    diff_summary: dict[str, Any] | None = None
    diff_artifact_key: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
