"""Unified LLM service that reads per-client config and tracks usage.

Every LLM call in the application goes through ``completion()`` or
``stream_completion()`` which:
  1. Resolve provider + model + API key for the client
  2. Call the LLM via ``litellm``
  3. Log token usage + estimated cost to ``llm_usage_log``
"""

import logging
import time
import uuid
from decimal import Decimal

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm_config import LlmConfig
from app.models.llm_usage_log import LlmUsageLog
from app.services.crypto import decrypt_api_key

logger = logging.getLogger(__name__)

litellm.drop_params = True
litellm.suppress_debug_info = True

PROVIDER_MODEL_PREFIX = {
    "anthropic": "anthropic/",
    "mistral": "mistral/",
    "openai": "",
}

SUPPORTED_PROVIDERS = ["anthropic", "mistral", "openai"]

AVAILABLE_MODELS: dict[str, list[dict[str, str]]] = {
    "anthropic": [
        {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
        {"id": "claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet"},
        {"id": "claude-3-5-haiku-20241022", "label": "Claude 3.5 Haiku"},
    ],
    "mistral": [
        {"id": "mistral-large-latest", "label": "Mistral Large"},
        {"id": "mistral-medium-latest", "label": "Mistral Medium"},
        {"id": "mistral-small-latest", "label": "Mistral Small"},
    ],
    "openai": [
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o Mini"},
        {"id": "gpt-4-turbo", "label": "GPT-4 Turbo"},
    ],
}

USD_TO_EUR = Decimal("0.92")


async def resolve_api_key(
    client_id: uuid.UUID, db: AsyncSession, provider: str
) -> str | None:
    """Public helper to resolve an API key for a provider (client-specific or global fallback)."""
    config = await _get_config(client_id, db)
    return _resolve_key(config, provider)


def _resolve_key(config: LlmConfig | None, provider: str) -> str | None:
    """Return decrypted API key for ``provider`` from client config or global fallback."""
    if config:
        enc_field = f"{provider}_api_key_enc"
        enc_blob: bytes | None = getattr(config, enc_field, None)
        if enc_blob:
            try:
                return decrypt_api_key(enc_blob)
            except Exception:
                logger.warning("Failed to decrypt %s key for client", provider)

        if not config.use_global_fallback:
            return None

    global_keys = {
        "anthropic": settings.anthropic_api_key,
        "mistral": settings.mistral_api_key,
        "openai": getattr(settings, "openai_api_key", ""),
    }
    key = global_keys.get(provider, "")
    return key if key else None


async def _get_config(client_id: uuid.UUID, db: AsyncSession) -> LlmConfig | None:
    result = await db.execute(
        select(LlmConfig).where(LlmConfig.client_id == client_id)
    )
    return result.scalar_one_or_none()


def _litellm_model(provider: str, model: str) -> str:
    prefix = PROVIDER_MODEL_PREFIX.get(provider, "")
    return f"{prefix}{model}"


async def _log_usage(
    db: AsyncSession,
    client_id: uuid.UUID,
    provider: str,
    model: str,
    operation: str,
    response: litellm.ModelResponse,
    duration_ms: int,
    document_id: uuid.UUID | None = None,
) -> None:
    usage = getattr(response, "usage", None)
    if not usage:
        return

    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    thinking_tokens = 0

    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    if cache_read or cache_write:
        pass

    total = input_tokens + output_tokens + thinking_tokens

    try:
        cost_usd = litellm.completion_cost(completion_response=response)
        cost_eur = Decimal(str(cost_usd)) * USD_TO_EUR
    except Exception:
        cost_eur = Decimal("0")

    log = LlmUsageLog(
        client_id=client_id,
        provider=provider,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        total_tokens=total,
        estimated_cost_eur=cost_eur,
        document_id=document_id,
        duration_ms=duration_ms,
    )
    db.add(log)
    try:
        await db.flush()
    except Exception:
        logger.exception("Failed to log LLM usage")


async def completion(
    client_id: uuid.UUID,
    db: AsyncSession,
    *,
    operation: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 4096,
    temperature: float | None = None,
    tools: list[dict] | None = None,
    thinking: dict | None = None,
    document_id: uuid.UUID | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> litellm.ModelResponse:
    """Single non-streaming LLM call with automatic config resolution and usage tracking."""
    config = await _get_config(client_id, db)

    if operation in ("chat", "review", "skill"):
        provider = provider_override or (config.chat_provider if config else "anthropic")
        model = model_override or (config.chat_model if config else "claude-sonnet-4-20250514")
    else:
        provider = provider_override or (config.booking_provider if config else "anthropic")
        model = model_override or (config.booking_model if config else "claude-sonnet-4-20250514")

    api_key = _resolve_key(config, provider)
    if not api_key:
        raise ValueError(
            f"Kein API-Key für {provider} konfiguriert. "
            "Bitte unter KI-Einstellungen einen Key hinterlegen."
        )

    litellm_model = _litellm_model(provider, model)

    kwargs: dict = {
        "model": litellm_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "api_key": api_key,
    }
    if system:
        if provider == "anthropic":
            kwargs["system"] = system
        else:
            kwargs["messages"] = [{"role": "system", "content": system}] + messages
    if temperature is not None:
        kwargs["temperature"] = temperature
    if tools:
        kwargs["tools"] = tools
    if thinking and provider == "anthropic":
        kwargs["thinking"] = thinking
        kwargs["max_tokens"] = max_tokens + thinking.get("budget_tokens", 0)

    t0 = time.monotonic()
    response = await litellm.acompletion(**kwargs)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    await _log_usage(db, client_id, provider, model, operation, response, elapsed_ms, document_id)

    return response


async def stream_completion(
    client_id: uuid.UUID,
    db: AsyncSession,
    *,
    operation: str,
    messages: list[dict],
    system: str | None = None,
    max_tokens: int = 8192,
    tools: list[dict] | None = None,
):
    """Streaming LLM call. Yields chunks. Usage is logged after stream completes."""
    config = await _get_config(client_id, db)

    provider = config.chat_provider if config else "anthropic"
    model = config.chat_model if config else "claude-sonnet-4-20250514"

    api_key = _resolve_key(config, provider)
    if not api_key:
        raise ValueError(
            f"Kein API-Key für {provider} konfiguriert. "
            "Bitte unter KI-Einstellungen einen Key hinterlegen."
        )

    litellm_model = _litellm_model(provider, model)

    kwargs: dict = {
        "model": litellm_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "api_key": api_key,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if system:
        if provider == "anthropic":
            kwargs["system"] = system
        else:
            kwargs["messages"] = [{"role": "system", "content": system}] + messages
    if tools:
        kwargs["tools"] = tools

    t0 = time.monotonic()
    response = await litellm.acompletion(**kwargs)

    total_input = 0
    total_output = 0

    async for chunk in response:
        usage = getattr(chunk, "usage", None)
        if usage:
            total_input = getattr(usage, "prompt_tokens", 0) or total_input
            total_output = getattr(usage, "completion_tokens", 0) or total_output
        yield chunk

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if total_input or total_output:
        try:
            cost_usd = litellm.completion_cost(
                model=litellm_model,
                prompt_tokens=total_input,
                completion_tokens=total_output,
            )
            cost_eur = Decimal(str(cost_usd)) * USD_TO_EUR
        except Exception:
            cost_eur = Decimal("0")

        log = LlmUsageLog(
            client_id=client_id,
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            estimated_cost_eur=cost_eur,
            duration_ms=elapsed_ms,
        )
        db.add(log)
        try:
            await db.flush()
        except Exception:
            logger.exception("Failed to log streaming LLM usage")


async def test_api_key(provider: str, api_key: str) -> dict:
    """Send a minimal request to validate the API key works."""
    model_map = {
        "anthropic": "anthropic/claude-3-5-haiku-20241022",
        "mistral": "mistral/mistral-small-latest",
        "openai": "gpt-4o-mini",
    }
    model = model_map.get(provider)
    if not model:
        return {"valid": False, "error": f"Unbekannter Anbieter: {provider}"}

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            api_key=api_key,
        )
        return {"valid": True, "model": model}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}
