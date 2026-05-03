import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_skill import AgentSkill
from app.models.client import Client
from app.schemas.client import ClientCreate, ClientResponse, ClientUpdate
from app.services.industry_catalog import get_industry_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


async def _seed_industry_skills(
    client_id: uuid.UUID, industry: str | None, db: AsyncSession
) -> None:
    """Create starter skills for the client's industry (idempotent)."""
    profile = get_industry_profile(industry)
    if not profile or not profile.starter_skills:
        return

    for skill_def in profile.starter_skills:
        existing = await db.execute(
            select(AgentSkill).where(
                AgentSkill.client_id == client_id,
                AgentSkill.skill_key == skill_def["skill_key"],
            )
        )
        if existing.scalar_one_or_none():
            continue

        db.add(AgentSkill(
            client_id=client_id,
            skill_key=skill_def["skill_key"],
            category=skill_def["category"],
            title=skill_def["title"],
            content=skill_def["content"],
            source="industry_starter",
            confidence=Decimal("0.80"),
        ))
    await db.flush()
    logger.info("Seeded industry skills for client %s (industry=%s)", client_id, industry)


@router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = Client(**payload.model_dump())
    db.add(client)
    await db.flush()
    await db.refresh(client)

    if client.industry:
        await _seed_industry_skills(client.id, client.industry, db)

    return client


@router.get("", response_model=list[ClientResponse])
async def list_clients(db: AsyncSession = Depends(get_db)) -> list[Client]:
    result = await db.execute(select(Client).order_by(Client.company_name))
    return list(result.scalars().all())


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    update_data = payload.model_dump(exclude_unset=True)
    old_industry = client.industry
    for field, value in update_data.items():
        setattr(client, field, value)
    await db.flush()
    await db.refresh(client)

    if "industry" in update_data and client.industry != old_industry:
        await _seed_industry_skills(client.id, client.industry, db)

    return client
