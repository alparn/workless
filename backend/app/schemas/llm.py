import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AiSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chat_provider: str
    chat_model: str
    booking_provider: str
    booking_model: str
    ocr_provider: str
    use_global_fallback: bool
    langsmith_enabled: bool

    anthropic_key_set: bool = False
    mistral_key_set: bool = False
    openai_key_set: bool = False
    tavily_key_set: bool = False

    anthropic_key_hint: str | None = None
    mistral_key_hint: str | None = None
    openai_key_hint: str | None = None
    tavily_key_hint: str | None = None


class AiSettingsUpdate(BaseModel):
    chat_provider: str | None = Field(None, max_length=30)
    chat_model: str | None = Field(None, max_length=80)
    booking_provider: str | None = Field(None, max_length=30)
    booking_model: str | None = Field(None, max_length=80)
    ocr_provider: str | None = Field(None, max_length=30)
    use_global_fallback: bool | None = None
    langsmith_enabled: bool | None = None

    anthropic_api_key: str | None = Field(None, min_length=1)
    mistral_api_key: str | None = Field(None, min_length=1)
    openai_api_key: str | None = Field(None, min_length=1)
    tavily_api_key: str | None = Field(None, min_length=1)


class KeyTestRequest(BaseModel):
    provider: str
    api_key: str


class KeyTestResponse(BaseModel):
    valid: bool
    error: str | None = None


class DeleteKeyResponse(BaseModel):
    deleted: bool
    provider: str


class UsageLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    estimated_cost_eur: Decimal
    duration_ms: int
    created_at: datetime


class UsageSummary(BaseModel):
    period: str
    total_input_tokens: int
    total_output_tokens: int
    total_thinking_tokens: int
    total_tokens: int
    total_cost_eur: Decimal
    call_count: int
    by_operation: list[dict]
    by_day: list[dict]


class AvailableModelsResponse(BaseModel):
    providers: dict[str, list[dict]]
