"""Integration-test conftest – Testcontainers Postgres.

Spins up a real Postgres container once per session (sync fixture).
All async fixtures are function-scoped and explicitly pinned to
loop_scope="function" so every async object lives on the test's own
event-loop.  Changes are rolled back via transaction for full isolation.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.database import Base, get_db
from app.models.client import Client
from app.models.llm_config import LlmConfig
from app.models.llm_usage_log import LlmUsageLog
from app.services.crypto import encrypt_api_key

_tables_created = False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url().replace("psycopg2", "asyncpg")


@pytest_asyncio.fixture(loop_scope="function")
async def db(postgres_url) -> AsyncGenerator[AsyncSession, None]:
    global _tables_created
    engine = create_async_engine(postgres_url, poolclass=NullPool)

    if not _tables_created:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True

    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await txn.rollback()

    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="function")
async def sample_client(db: AsyncSession) -> Client:
    obj = Client(
        id=uuid.uuid4(),
        company_name="Test GmbH",
        chart_of_accounts="SKR03",
        account_length=4,
        fiscal_year_start=date(2026, 1, 1),
        default_vat_rate=Decimal("19.00"),
        auto_booking_threshold=Decimal("0.85"),
    )
    db.add(obj)
    await db.flush()
    return obj


@pytest_asyncio.fixture(loop_scope="function")
async def sample_config(db: AsyncSession, sample_client: Client) -> LlmConfig:
    obj = LlmConfig(
        client_id=sample_client.id,
        chat_provider="anthropic",
        chat_model="claude-sonnet-4-20250514",
        booking_provider="anthropic",
        booking_model="claude-sonnet-4-20250514",
        ocr_provider="mistral",
        anthropic_api_key_enc=encrypt_api_key("sk-ant-test-key-1234567890abcdef"),
        use_global_fallback=True,
    )
    db.add(obj)
    await db.flush()
    return obj


@pytest_asyncio.fixture(loop_scope="function")
async def sample_usage_logs(
    db: AsyncSession, sample_client: Client
) -> list[LlmUsageLog]:
    logs: list[LlmUsageLog] = []
    for i, op in enumerate(["chat", "ocr", "suggest_booking", "classify", "chat"]):
        log = LlmUsageLog(
            client_id=sample_client.id,
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            operation=op,
            input_tokens=100 * (i + 1),
            output_tokens=50 * (i + 1),
            total_tokens=150 * (i + 1),
            estimated_cost_eur=Decimal(f"0.00{i + 1}"),
            duration_ms=200 * (i + 1),
        )
        db.add(log)
        logs.append(log)
    await db.flush()
    return logs
