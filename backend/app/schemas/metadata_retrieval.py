"""
Pydantic schemas for Metadata Retrieval.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataRetrievalCreate(BaseModel):
    org_id: UUID
    package_xml: str = Field(..., description="package.xml content or simple type list")
    description: str | None = None


class MetadataRetrievalResponse(BaseModel):
    id: UUID
    org_id: UUID
    status: str
    package_xml: str
    artifact_key: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
