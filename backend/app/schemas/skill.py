import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    skill_key: str
    category: str
    title: str
    content: str
    source: str
    source_entity_id: uuid.UUID | None
    confidence: Decimal
    usage_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SkillUpdate(BaseModel):
    title: str | None = Field(None, max_length=255)
    content: str | None = None
    category: str | None = Field(None, max_length=30)
    is_active: bool | None = None
