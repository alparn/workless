import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import Client
from app.models.llm_config import LlmConfig
from app.models.llm_usage_log import LlmUsageLog
from app.schemas.llm import (
    AiSettingsResponse,
    AiSettingsUpdate,
    AvailableModelsResponse,
    DeleteKeyResponse,
    KeyTestRequest,
    KeyTestResponse,
    UsageLogEntry,
    UsageSummary,
)
from app.services.crypto import decrypt_api_key, encrypt_api_key, mask_key
from app.services.llm_service import AVAILABLE_MODELS, SUPPORTED_PROVIDERS, test_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/clients/{client_id}", tags=["ai-settings"])


async def _get_or_create_config(
    client_id: uuid.UUID, db: AsyncSession
) -> LlmConfig:
    result = await db.execute(
        select(LlmConfig).where(LlmConfig.client_id == client_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = LlmConfig(client_id=client_id)
        db.add(config)
        await db.flush()
        await db.refresh(config)
    return config


def _build_response(config: LlmConfig) -> AiSettingsResponse:
    def _hint(enc: bytes | None) -> str | None:
        if not enc:
            return None
        try:
            return mask_key(decrypt_api_key(enc))
        except Exception:
            return "****"

    return AiSettingsResponse(
        chat_provider=config.chat_provider,
        chat_model=config.chat_model,
        booking_provider=config.booking_provider,
        booking_model=config.booking_model,
        ocr_provider=config.ocr_provider,
        use_global_fallback=config.use_global_fallback,
        langsmith_enabled=config.langsmith_enabled,
        anthropic_key_set=config.anthropic_api_key_enc is not None,
        mistral_key_set=config.mistral_api_key_enc is not None,
        openai_key_set=config.openai_api_key_enc is not None,
        tavily_key_set=config.tavily_api_key_enc is not None,
        anthropic_key_hint=_hint(config.anthropic_api_key_enc),
        mistral_key_hint=_hint(config.mistral_api_key_enc),
        openai_key_hint=_hint(config.openai_api_key_enc),
        tavily_key_hint=_hint(config.tavily_api_key_enc),
    )


@router.get("/ai-settings", response_model=AiSettingsResponse)
async def get_ai_settings(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AiSettingsResponse:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    config = await _get_or_create_config(client_id, db)
    return _build_response(config)


@router.patch("/ai-settings", response_model=AiSettingsResponse)
async def update_ai_settings(
    client_id: uuid.UUID,
    payload: AiSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> AiSettingsResponse:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    config = await _get_or_create_config(client_id, db)

    for field in (
        "chat_provider", "chat_model", "booking_provider", "booking_model",
        "ocr_provider", "use_global_fallback", "langsmith_enabled",
    ):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(config, field, value)

    key_fields = {
        "anthropic_api_key": "anthropic_api_key_enc",
        "mistral_api_key": "mistral_api_key_enc",
        "openai_api_key": "openai_api_key_enc",
        "tavily_api_key": "tavily_api_key_enc",
    }
    for payload_field, db_field in key_fields.items():
        raw_key = getattr(payload, payload_field, None)
        if raw_key is not None:
            setattr(config, db_field, encrypt_api_key(raw_key))

    await db.flush()
    await db.refresh(config)
    return _build_response(config)


@router.post("/ai-settings/test", response_model=KeyTestResponse)
async def test_key(
    client_id: uuid.UUID,
    body: KeyTestRequest,
    db: AsyncSession = Depends(get_db),
) -> KeyTestResponse:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    if body.provider not in SUPPORTED_PROVIDERS:
        return KeyTestResponse(valid=False, error=f"Unbekannter Anbieter: {body.provider}")

    result = await test_api_key(body.provider, body.api_key)
    return KeyTestResponse(**result)


@router.delete("/ai-settings/keys/{provider}", response_model=DeleteKeyResponse)
async def delete_key(
    client_id: uuid.UUID,
    provider: str,
    db: AsyncSession = Depends(get_db),
) -> DeleteKeyResponse:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    config = await _get_or_create_config(client_id, db)

    field_map = {
        "anthropic": "anthropic_api_key_enc",
        "mistral": "mistral_api_key_enc",
        "openai": "openai_api_key_enc",
        "tavily": "tavily_api_key_enc",
    }
    db_field = field_map.get(provider)
    if not db_field:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unbekannter Anbieter: {provider}")

    setattr(config, db_field, None)
    await db.flush()

    return DeleteKeyResponse(deleted=True, provider=provider)


@router.get("/ai-settings/models", response_model=AvailableModelsResponse)
async def get_available_models(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AvailableModelsResponse:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return AvailableModelsResponse(providers=AVAILABLE_MODELS)


@router.get("/ai-usage", response_model=list[UsageLogEntry])
async def get_usage_logs(
    client_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    operation: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[LlmUsageLog]:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        select(LlmUsageLog)
        .where(LlmUsageLog.client_id == client_id, LlmUsageLog.created_at >= since)
        .order_by(LlmUsageLog.created_at.desc())
        .limit(limit)
    )
    if operation:
        query = query.where(LlmUsageLog.operation == operation)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/ai-usage/summary", response_model=UsageSummary)
async def get_usage_summary(
    client_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> UsageSummary:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    totals = await db.execute(
        select(
            func.coalesce(func.sum(LlmUsageLog.input_tokens), 0),
            func.coalesce(func.sum(LlmUsageLog.output_tokens), 0),
            func.coalesce(func.sum(LlmUsageLog.thinking_tokens), 0),
            func.coalesce(func.sum(LlmUsageLog.total_tokens), 0),
            func.coalesce(func.sum(LlmUsageLog.estimated_cost_eur), Decimal("0")),
            func.count(),
        ).where(
            LlmUsageLog.client_id == client_id,
            LlmUsageLog.created_at >= since,
        )
    )
    row = totals.one()

    by_op_result = await db.execute(
        select(
            LlmUsageLog.operation,
            func.sum(LlmUsageLog.total_tokens),
            func.sum(LlmUsageLog.estimated_cost_eur),
            func.count(),
        )
        .where(LlmUsageLog.client_id == client_id, LlmUsageLog.created_at >= since)
        .group_by(LlmUsageLog.operation)
        .order_by(func.sum(LlmUsageLog.total_tokens).desc())
    )
    by_operation = [
        {
            "operation": op,
            "total_tokens": int(tokens or 0),
            "cost_eur": str(cost or Decimal("0")),
            "count": cnt,
        }
        for op, tokens, cost, cnt in by_op_result.all()
    ]

    by_day_result = await db.execute(
        select(
            func.date_trunc("day", LlmUsageLog.created_at).label("day"),
            func.sum(LlmUsageLog.input_tokens),
            func.sum(LlmUsageLog.output_tokens),
            func.sum(LlmUsageLog.estimated_cost_eur),
            func.count(),
        )
        .where(LlmUsageLog.client_id == client_id, LlmUsageLog.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    by_day = [
        {
            "date": day.strftime("%Y-%m-%d") if day else "",
            "input_tokens": int(inp or 0),
            "output_tokens": int(out or 0),
            "cost_eur": str(cost or Decimal("0")),
            "count": cnt,
        }
        for day, inp, out, cost, cnt in by_day_result.all()
    ]

    return UsageSummary(
        period=f"last_{days}_days",
        total_input_tokens=int(row[0]),
        total_output_tokens=int(row[1]),
        total_thinking_tokens=int(row[2]),
        total_tokens=int(row[3]),
        total_cost_eur=row[4],
        call_count=int(row[5]),
        by_operation=by_operation,
        by_day=by_day,
    )
