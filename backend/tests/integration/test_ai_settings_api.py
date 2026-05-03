"""Integration tests for the AI settings API endpoints.

Uses the shared ``client`` fixture which provides an httpx.AsyncClient
with the FastAPI app's ``get_db`` dependency overridden to use the
Testcontainers-backed, savepoint-isolated session.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.llm_config import LlmConfig
from app.models.llm_usage_log import LlmUsageLog


class TestGetAiSettings:
    async def test_returns_defaults_for_new_client(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-settings"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_provider"] == "anthropic"
        assert data["chat_model"] == "claude-sonnet-4-20250514"
        assert data["booking_provider"] == "anthropic"
        assert data["ocr_provider"] == "mistral"
        assert data["use_global_fallback"] is True
        assert data["langsmith_enabled"] is False
        assert data["anthropic_key_set"] is False
        assert data["anthropic_key_hint"] is None

    async def test_returns_existing_config(
        self,
        client: AsyncClient,
        sample_client: Client,
        sample_config: LlmConfig,
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-settings"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["anthropic_key_set"] is True
        assert data["anthropic_key_hint"] is not None
        assert "****" in data["anthropic_key_hint"]

    async def test_404_for_unknown_client(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/clients/{fake_id}/ai-settings")
        assert resp.status_code == 404


class TestUpdateAiSettings:
    async def test_update_provider_and_model(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.patch(
            f"/api/v1/clients/{sample_client.id}/ai-settings",
            json={
                "chat_provider": "openai",
                "chat_model": "gpt-4o",
                "langsmith_enabled": True,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_provider"] == "openai"
        assert data["chat_model"] == "gpt-4o"
        assert data["langsmith_enabled"] is True
        assert data["booking_provider"] == "anthropic"

    async def test_set_api_key(
        self, client: AsyncClient, sample_client: Client
    ):
        test_key = "sk-ant-api03-newkey-1234567890"

        resp = await client.patch(
            f"/api/v1/clients/{sample_client.id}/ai-settings",
            json={"anthropic_api_key": test_key},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["anthropic_key_set"] is True
        assert "****" in data["anthropic_key_hint"]
        assert test_key not in data["anthropic_key_hint"]

    async def test_set_multiple_keys(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.patch(
            f"/api/v1/clients/{sample_client.id}/ai-settings",
            json={
                "anthropic_api_key": "key-anthropic",
                "mistral_api_key": "key-mistral",
                "openai_api_key": "key-openai-12345",
                "tavily_api_key": "tvly-test-key-12",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["anthropic_key_set"] is True
        assert data["mistral_key_set"] is True
        assert data["openai_key_set"] is True
        assert data["tavily_key_set"] is True

    async def test_disable_fallback(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.patch(
            f"/api/v1/clients/{sample_client.id}/ai-settings",
            json={"use_global_fallback": False},
        )

        assert resp.status_code == 200
        assert resp.json()["use_global_fallback"] is False

    async def test_404_for_unknown_client(self, client: AsyncClient):
        fake_id = uuid.uuid4()
        resp = await client.patch(
            f"/api/v1/clients/{fake_id}/ai-settings",
            json={"chat_provider": "openai"},
        )
        assert resp.status_code == 404


class TestDeleteKey:
    async def test_delete_existing_key(
        self,
        client: AsyncClient,
        sample_client: Client,
        sample_config: LlmConfig,
    ):
        resp = await client.delete(
            f"/api/v1/clients/{sample_client.id}/ai-settings/keys/anthropic"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["provider"] == "anthropic"

        check = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-settings"
        )
        assert check.json()["anthropic_key_set"] is False

    async def test_delete_unknown_provider(
        self,
        client: AsyncClient,
        sample_client: Client,
        sample_config: LlmConfig,
    ):
        resp = await client.delete(
            f"/api/v1/clients/{sample_client.id}/ai-settings/keys/unknown_provider"
        )
        assert resp.status_code == 400


class TestGetModels:
    async def test_returns_all_providers(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-settings/models"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "anthropic" in data["providers"]
        assert "mistral" in data["providers"]
        assert "openai" in data["providers"]
        for provider_models in data["providers"].values():
            assert len(provider_models) >= 1
            assert "id" in provider_models[0]
            assert "label" in provider_models[0]


class TestTestKey:
    async def test_unsupported_provider(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.post(
            f"/api/v1/clients/{sample_client.id}/ai-settings/test",
            json={"provider": "unknown", "api_key": "test-key"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "Unbekannter" in data["error"]

    async def test_valid_key(
        self, client: AsyncClient, sample_client: Client
    ):
        with patch(
            "app.routers.ai_settings.test_api_key", new_callable=AsyncMock
        ) as mock_test:
            mock_test.return_value = {
                "valid": True,
                "model": "anthropic/claude-3-5-haiku-20241022",
            }

            resp = await client.post(
                f"/api/v1/clients/{sample_client.id}/ai-settings/test",
                json={"provider": "anthropic", "api_key": "sk-ant-valid-key"},
            )

        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    async def test_invalid_key(
        self, client: AsyncClient, sample_client: Client
    ):
        with patch(
            "app.routers.ai_settings.test_api_key", new_callable=AsyncMock
        ) as mock_test:
            mock_test.return_value = {
                "valid": False,
                "error": "Authentication failed",
            }

            resp = await client.post(
                f"/api/v1/clients/{sample_client.id}/ai-settings/test",
                json={"provider": "anthropic", "api_key": "bad-key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "Authentication" in data["error"]


class TestGetUsageLogs:
    async def test_returns_logs(
        self,
        client: AsyncClient,
        sample_client: Client,
        sample_usage_logs: list[LlmUsageLog],
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-usage"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        assert data[0]["provider"] == "anthropic"

    async def test_empty_logs(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-usage"
        )

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_filter_by_operation(
        self,
        client: AsyncClient,
        sample_client: Client,
        sample_usage_logs: list[LlmUsageLog],
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-usage",
            params={"operation": "ocr"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert all(entry["operation"] == "ocr" for entry in data)


class TestGetUsageSummary:
    async def test_summary_with_data(
        self,
        client: AsyncClient,
        sample_client: Client,
        sample_usage_logs: list[LlmUsageLog],
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-usage/summary"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "last_30_days"
        assert data["call_count"] == 5
        assert data["total_tokens"] > 0
        assert data["total_input_tokens"] > 0
        assert data["total_output_tokens"] > 0
        assert len(data["by_operation"]) >= 1

    async def test_summary_empty(
        self, client: AsyncClient, sample_client: Client
    ):
        resp = await client.get(
            f"/api/v1/clients/{sample_client.id}/ai-usage/summary"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["call_count"] == 0
        assert data["total_tokens"] == 0
        assert float(data["total_cost_eur"]) == 0.0
