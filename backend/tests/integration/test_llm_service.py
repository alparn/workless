"""Integration tests for the LLM service (require DB for config lookup)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.llm_config import LlmConfig
from app.services.crypto import encrypt_api_key
from app.services.llm_service import completion


class TestCompletion:
    async def test_raises_without_key(self, db: AsyncSession, sample_client: Client):
        with patch("app.services.llm_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            mock_settings.mistral_api_key = ""
            mock_settings.openai_api_key = ""

            with pytest.raises(ValueError, match="Kein API-Key"):
                await completion(
                    sample_client.id, db,
                    operation="chat",
                    messages=[{"role": "user", "content": "test"}],
                )

    async def test_successful_completion_logs_usage(
        self, db: AsyncSession, sample_config: LlmConfig, sample_client: Client
    ):
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 0

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]

        with patch("app.services.llm_service.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            mock_litellm.completion_cost = MagicMock(return_value=0.001)

            response = await completion(
                sample_client.id, db,
                operation="chat",
                messages=[{"role": "user", "content": "Hallo"}],
            )

            assert response == mock_response
            mock_litellm.acompletion.assert_called_once()

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
            assert call_kwargs["api_key"] == "sk-ant-test-key-1234567890abcdef"

    async def test_system_prompt_anthropic(
        self, db: AsyncSession, sample_config: LlmConfig, sample_client: Client
    ):
        mock_response = MagicMock()
        mock_response.usage = None

        with patch("app.services.llm_service.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            await completion(
                sample_client.id, db,
                operation="chat",
                messages=[{"role": "user", "content": "test"}],
                system="Du bist ein Buchhalter",
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["system"] == "Du bist ein Buchhalter"
            assert call_kwargs["messages"] == [{"role": "user", "content": "test"}]

    async def test_operation_routing_chat(self, db: AsyncSession, sample_client: Client):
        config = LlmConfig(
            client_id=sample_client.id,
            chat_provider="openai",
            chat_model="gpt-4o",
            booking_provider="anthropic",
            booking_model="claude-sonnet-4-20250514",
            anthropic_api_key_enc=encrypt_api_key("anthropic-key"),
            openai_api_key_enc=encrypt_api_key("openai-key"),
            use_global_fallback=False,
        )
        db.add(config)
        await db.flush()

        mock_response = MagicMock()
        mock_response.usage = None

        with patch("app.services.llm_service.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            await completion(
                sample_client.id, db,
                operation="chat",
                messages=[{"role": "user", "content": "test"}],
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["api_key"] == "openai-key"

    async def test_operation_routing_booking(self, db: AsyncSession, sample_client: Client):
        config = LlmConfig(
            client_id=sample_client.id,
            chat_provider="openai",
            chat_model="gpt-4o",
            booking_provider="mistral",
            booking_model="mistral-large-latest",
            mistral_api_key_enc=encrypt_api_key("mistral-key"),
            openai_api_key_enc=encrypt_api_key("openai-key"),
            use_global_fallback=False,
        )
        db.add(config)
        await db.flush()

        mock_response = MagicMock()
        mock_response.usage = None

        with patch("app.services.llm_service.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)

            await completion(
                sample_client.id, db,
                operation="suggest_booking",
                messages=[{"role": "user", "content": "test"}],
            )

            call_kwargs = mock_litellm.acompletion.call_args[1]
            assert call_kwargs["model"] == "mistral/mistral-large-latest"
            assert call_kwargs["api_key"] == "mistral-key"
