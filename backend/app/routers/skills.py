import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent_skill import AgentSkill
from app.schemas.skill import SkillResponse, SkillUpdate
from app.services.skill_manager import VALID_CATEGORIES, deactivate_skill

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


@router.get("", response_model=list[SkillResponse])
async def list_skills(
    client_id: uuid.UUID = Query(...),
    category: str | None = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> list[AgentSkill]:
    query = select(AgentSkill).where(AgentSkill.client_id == client_id)
    if active_only:
        query = query.where(AgentSkill.is_active.is_(True))
    if category:
        query = query.where(AgentSkill.category == category)
    query = query.order_by(AgentSkill.confidence.desc(), AgentSkill.updated_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentSkill:
    skill = await db.get(AgentSkill, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return skill


@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: uuid.UUID,
    payload: SkillUpdate,
    db: AsyncSession = Depends(get_db),
) -> AgentSkill:
    skill = await db.get(AgentSkill, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "category" in update_data and update_data["category"] not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
        )

    for field, value in update_data.items():
        setattr(skill, field, value)

    await db.flush()
    await db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    skill = await deactivate_skill(skill_id, db)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
