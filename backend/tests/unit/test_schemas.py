"""Tests for Pydantic schemas (validation, serialization)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.llm import (
    AiSettingsResponse,
    AiSettingsUpdate,
    AvailableModelsResponse,
    KeyTestRequest,
    KeyTestResponse,
    UsageSummary,
)


class TestAiSettingsUpdate:
    def test_empty_update_valid(self):
        update = AiSettingsUpdate()
        assert update.chat_provider is None
        assert update.anthropic_api_key is None

    def test_partial_update(self):
        update = AiSettingsUpdate(chat_provider="openai", chat_model="gpt-4o")
        assert update.chat_provider == "openai"
        assert update.chat_model == "gpt-4o"
        assert update.booking_provider is None

    def test_api_key_min_length(self):
        with pytest.raises(ValidationError):
            AiSettingsUpdate(anthropic_api_key="")

    def test_api_key_valid(self):
        update = AiSettingsUpdate(anthropic_api_key="sk-ant-test-key")
        assert update.anthropic_api_key == "sk-ant-test-key"

    def test_all_fields(self):
        update = AiSettingsUpdate(
            chat_provider="mistral",
            chat_model="mistral-large-latest",
            booking_provider="openai",
            booking_model="gpt-4o",
            ocr_provider="claude_vision",
            use_global_fallback=False,
            langsmith_enabled=True,
            anthropic_api_key="key-a",
            mistral_api_key="key-m",
            openai_api_key="key-o",
            tavily_api_key="key-t",
        )
        assert update.chat_provider == "mistral"
        assert update.langsmith_enabled is True

    def test_provider_max_length(self):
        with pytest.raises(ValidationError):
            AiSettingsUpdate(chat_provider="x" * 31)


class TestAiSettingsResponse:
    def test_defaults(self):
        resp = AiSettingsResponse(
            chat_provider="anthropic",
            chat_model="claude-sonnet-4-20250514",
            booking_provider="anthropic",
            booking_model="claude-sonnet-4-20250514",
            ocr_provider="mistral",
            use_global_fallback=True,
            langsmith_enabled=False,
        )
        assert resp.anthropic_key_set is False
        assert resp.anthropic_key_hint is None

    def test_with_keys(self):
        resp = AiSettingsResponse(
            chat_provider="anthropic",
            chat_model="claude-sonnet-4-20250514",
            booking_provider="anthropic",
            booking_model="claude-sonnet-4-20250514",
            ocr_provider="mistral",
            use_global_fallback=True,
            langsmith_enabled=False,
            anthropic_key_set=True,
            anthropic_key_hint="sk-ant...****cdef",
        )
        assert resp.anthropic_key_set is True
        assert "****" in resp.anthropic_key_hint


class TestKeyTestRequest:
    def test_valid(self):
        req = KeyTestRequest(provider="anthropic", api_key="sk-test")
        assert req.provider == "anthropic"

    def test_missing_fields(self):
        with pytest.raises(ValidationError):
            KeyTestRequest(provider="anthropic")


class TestKeyTestResponse:
    def test_valid_key(self):
        resp = KeyTestResponse(valid=True)
        assert resp.error is None

    def test_invalid_key(self):
        resp = KeyTestResponse(valid=False, error="Invalid API key")
        assert resp.valid is False
        assert "Invalid" in resp.error


class TestUsageSummary:
    def test_full_summary(self):
        summary = UsageSummary(
            period="last_30_days",
            total_input_tokens=10000,
            total_output_tokens=5000,
            total_thinking_tokens=0,
            total_tokens=15000,
            total_cost_eur=Decimal("1.50"),
            call_count=42,
            by_operation=[
                {"operation": "chat", "total_tokens": 8000, "cost_eur": "0.80", "count": 20},
            ],
            by_day=[
                {"date": "2026-04-30", "input_tokens": 500, "output_tokens": 250, "cost_eur": "0.05", "count": 3},
            ],
        )
        assert summary.total_tokens == 15000
        assert summary.call_count == 42
        assert len(summary.by_operation) == 1


class TestAvailableModelsResponse:
    def test_structure(self):
        resp = AvailableModelsResponse(
            providers={
                "anthropic": [{"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"}],
                "openai": [{"id": "gpt-4o", "label": "GPT-4o"}],
            }
        )
        assert "anthropic" in resp.providers
        assert resp.providers["anthropic"][0]["id"] == "claude-sonnet-4-20250514"
