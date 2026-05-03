"""Unit-tests for the LLM service (pure logic, no DB, no IO)."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.llm_config import LlmConfig
from app.services.crypto import encrypt_api_key
from app.services.llm_service import (
    AVAILABLE_MODELS,
    SUPPORTED_PROVIDERS,
    _litellm_model,
    _resolve_key,
)


class TestLitellmModel:
    def test_anthropic_prefix(self):
        assert _litellm_model("anthropic", "claude-sonnet-4-20250514") == "anthropic/claude-sonnet-4-20250514"

    def test_mistral_prefix(self):
        assert _litellm_model("mistral", "mistral-large-latest") == "mistral/mistral-large-latest"

    def test_openai_no_prefix(self):
        assert _litellm_model("openai", "gpt-4o") == "gpt-4o"

    def test_unknown_provider(self):
        assert _litellm_model("unknown", "some-model") == "some-model"


class TestResolveKey:
    def test_client_key_takes_precedence(self):
        config = MagicMock(spec=LlmConfig)
        config.anthropic_api_key_enc = encrypt_api_key("client-key-12345678")
        config.use_global_fallback = True

        result = _resolve_key(config, "anthropic")
        assert result == "client-key-12345678"

    def test_global_fallback_when_no_client_key(self):
        config = MagicMock(spec=LlmConfig)
        config.anthropic_api_key_enc = None
        config.use_global_fallback = True

        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = "global-key-abcdef"
            result = _resolve_key(config, "anthropic")

        assert result == "global-key-abcdef"

    def test_no_fallback_when_disabled(self):
        config = MagicMock(spec=LlmConfig)
        config.anthropic_api_key_enc = None
        config.use_global_fallback = False

        result = _resolve_key(config, "anthropic")
        assert result is None

    def test_no_config_uses_global(self):
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = "global-key"
            result = _resolve_key(None, "anthropic")

        assert result == "global-key"

    def test_no_config_no_global(self):
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            result = _resolve_key(None, "anthropic")

        assert result is None

    def test_corrupted_key_falls_back(self):
        config = MagicMock(spec=LlmConfig)
        config.anthropic_api_key_enc = b"corrupted-data-not-valid"
        config.use_global_fallback = True

        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = "fallback-key"
            result = _resolve_key(config, "anthropic")

        assert result == "fallback-key"


class TestProviderConstants:
    def test_supported_providers(self):
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "mistral" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS

    def test_available_models_structure(self):
        for provider in SUPPORTED_PROVIDERS:
            assert provider in AVAILABLE_MODELS
            models = AVAILABLE_MODELS[provider]
            assert len(models) >= 1
            for m in models:
                assert "id" in m
                assert "label" in m
