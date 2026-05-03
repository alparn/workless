"""Tests for the LLM database models."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.llm_config import LlmConfig
from app.models.llm_usage_log import LlmUsageLog
from app.services.crypto import encrypt_api_key


class TestLlmConfig:
    @pytest.mark.asyncio
    async def test_create_with_defaults(self, db: AsyncSession, sample_client: Client):
        config = LlmConfig(client_id=sample_client.id)
        db.add(config)
        await db.flush()
        await db.refresh(config)

        assert config.id is not None
        assert config.chat_provider == "anthropic"
        assert config.chat_model == "claude-sonnet-4-20250514"
        assert config.booking_provider == "anthropic"
        assert config.ocr_provider == "mistral"
        assert config.use_global_fallback is True
        assert config.langsmith_enabled is False
        assert config.anthropic_api_key_enc is None

    @pytest.mark.asyncio
    async def test_create_with_encrypted_keys(self, db: AsyncSession, sample_client: Client):
        enc_key = encrypt_api_key("sk-test-key-12345")
        config = LlmConfig(
            client_id=sample_client.id,
            chat_provider="openai",
            chat_model="gpt-4o",
            anthropic_api_key_enc=enc_key,
        )
        db.add(config)
        await db.flush()

        result = await db.execute(
            select(LlmConfig).where(LlmConfig.client_id == sample_client.id)
        )
        loaded = result.scalar_one()
        assert loaded.chat_provider == "openai"
        assert loaded.anthropic_api_key_enc is not None

    @pytest.mark.asyncio
    async def test_unique_constraint_per_client(self, db: AsyncSession, sample_client: Client):
        config1 = LlmConfig(client_id=sample_client.id)
        db.add(config1)
        await db.flush()

        config2 = LlmConfig(client_id=sample_client.id)
        db.add(config2)
        with pytest.raises(Exception):
            await db.flush()

    @pytest.mark.asyncio
    async def test_cascade_delete(self, db: AsyncSession):
        from sqlalchemy import delete

        client = Client(
            company_name="Cascade GmbH",
            chart_of_accounts="SKR03",
            account_length=4,
        )
        db.add(client)
        await db.flush()

        config = LlmConfig(client_id=client.id)
        db.add(config)
        await db.flush()

        await db.execute(delete(Client).where(Client.id == client.id))
        await db.flush()

        result = await db.execute(
            select(LlmConfig).where(LlmConfig.client_id == client.id)
        )
        assert result.scalar_one_or_none() is None


class TestLlmUsageLog:
    @pytest.mark.asyncio
    async def test_create_log(self, db: AsyncSession, sample_client: Client):
        log = LlmUsageLog(
            client_id=sample_client.id,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            operation="chat",
            input_tokens=150,
            output_tokens=80,
            total_tokens=230,
            estimated_cost_eur=Decimal("0.003"),
            duration_ms=450,
        )
        db.add(log)
        await db.flush()

        assert log.id is not None
        assert log.thinking_tokens == 0

    @pytest.mark.asyncio
    async def test_multiple_logs_per_client(self, db: AsyncSession, sample_client: Client):
        for i in range(5):
            log = LlmUsageLog(
                client_id=sample_client.id,
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                operation=f"op_{i}",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                estimated_cost_eur=Decimal("0.001"),
                duration_ms=200,
            )
            db.add(log)

        await db.flush()

        result = await db.execute(
            select(LlmUsageLog).where(LlmUsageLog.client_id == sample_client.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 5

    @pytest.mark.asyncio
    async def test_optional_document_id(self, db: AsyncSession, sample_client: Client):
        doc_id = uuid.uuid4()
        log = LlmUsageLog(
            client_id=sample_client.id,
            provider="mistral",
            model="mistral-large-latest",
            operation="ocr",
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            estimated_cost_eur=Decimal("0.005"),
            duration_ms=1200,
            document_id=doc_id,
        )
        db.add(log)
        await db.flush()

        assert log.document_id == doc_id
