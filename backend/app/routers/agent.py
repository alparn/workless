"""API endpoints for the autonomous agent: notifications, runs, and control."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent_notification import AgentNotification
from app.models.agent_run import AgentRun

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    agent_run_id: uuid.UUID | None
    severity: str
    category: str
    title: str
    message: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    action_required: bool
    action_type: str | None
    action_data: dict | None
    is_read: bool
    read_at: datetime | None
    is_resolved: bool
    resolved_at: datetime | None
    created_at: datetime


class NotificationCountResponse(BaseModel):
    total: int
    unread: int
    action_required: int


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    run_type: str
    target_entity_type: str | None
    target_entity_id: uuid.UUID | None
    status: str
    strategy: str | None
    attempt_number: int
    result_summary: str | None
    details: dict | None
    error: str | None
    items_checked: int
    items_fixed: int
    items_flagged: int
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class AgentStatusResponse(BaseModel):
    supervisor_enabled: bool
    supervisor_interval_seconds: int
    max_ocr_retries: int
    notification_counts: NotificationCountResponse
    recent_runs_count: int


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get(
    "/{client_id}/notifications",
    response_model=list[NotificationResponse],
)
async def list_notifications(
    client_id: uuid.UUID,
    unread_only: bool = Query(False),
    severity: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AgentNotification]:
    query = (
        select(AgentNotification)
        .where(AgentNotification.client_id == client_id)
        .order_by(AgentNotification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        query = query.where(AgentNotification.is_read == False)
    if severity:
        query = query.where(AgentNotification.severity == severity)
    if category:
        query = query.where(AgentNotification.category == category)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get(
    "/{client_id}/notifications/count",
    response_model=NotificationCountResponse,
)
async def get_notification_counts(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> NotificationCountResponse:
    total_q = select(func.count(AgentNotification.id)).where(
        AgentNotification.client_id == client_id
    )
    unread_q = select(func.count(AgentNotification.id)).where(
        AgentNotification.client_id == client_id,
        AgentNotification.is_read == False,
    )
    action_q = select(func.count(AgentNotification.id)).where(
        AgentNotification.client_id == client_id,
        AgentNotification.action_required == True,
        AgentNotification.is_resolved == False,
    )
    total = (await db.execute(total_q)).scalar_one()
    unread = (await db.execute(unread_q)).scalar_one()
    action = (await db.execute(action_q)).scalar_one()
    return NotificationCountResponse(total=total, unread=unread, action_required=action)


@router.post(
    "/{client_id}/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
async def mark_notification_read(
    client_id: uuid.UUID,
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentNotification:
    n = await db.get(AgentNotification, notification_id)
    if not n or n.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.is_read = True
    n.read_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(n)
    return n


@router.post("/{client_id}/notifications/read-all")
async def mark_all_read(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(AgentNotification).where(
            AgentNotification.client_id == client_id,
            AgentNotification.is_read == False,
        )
    )
    notifications = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for n in notifications:
        n.is_read = True
        n.read_at = now
    await db.flush()
    return {"marked_read": len(notifications)}


@router.post(
    "/{client_id}/notifications/{notification_id}/resolve",
    response_model=NotificationResponse,
)
async def resolve_notification(
    client_id: uuid.UUID,
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentNotification:
    n = await db.get(AgentNotification, notification_id)
    if not n or n.client_id != client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.is_resolved = True
    n.resolved_at = datetime.now(timezone.utc)
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(n)
    return n


# ---------------------------------------------------------------------------
# Agent Runs
# ---------------------------------------------------------------------------

@router.get(
    "/{client_id}/runs",
    response_model=list[AgentRunResponse],
)
async def list_agent_runs(
    client_id: uuid.UUID,
    run_type: str | None = Query(None),
    run_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRun]:
    query = (
        select(AgentRun)
        .where(AgentRun.client_id == client_id)
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
    )
    if run_type:
        query = query.where(AgentRun.run_type == run_type)
    if run_status:
        query = query.where(AgentRun.status == run_status)

    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Agent Status & Control
# ---------------------------------------------------------------------------

@router.get("/{client_id}/status", response_model=AgentStatusResponse)
async def get_agent_status(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentStatusResponse:
    counts = await get_notification_counts(client_id, db)
    recent_runs = (await db.execute(
        select(func.count(AgentRun.id)).where(AgentRun.client_id == client_id)
    )).scalar_one()

    return AgentStatusResponse(
        supervisor_enabled=settings.supervisor_enabled,
        supervisor_interval_seconds=settings.supervisor_interval_seconds,
        max_ocr_retries=settings.supervisor_max_ocr_retries,
        notification_counts=counts,
        recent_runs_count=recent_runs,
    )


@router.post("/{client_id}/trigger-cycle")
async def trigger_supervisor_cycle(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually trigger a supervisor check for this client."""
    from app.models.client import Client
    from app.services.supervisor import supervisor as sup

    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    await sup._process_client(db, client)
    await db.commit()
    return {"status": "completed", "message": "Supervisor-Zyklus manuell ausgeführt"}


@router.post("/{client_id}/llm-review")
async def trigger_llm_review(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a full LLM-powered review of all open bookings."""
    from app.services.llm_reviewer import run_llm_review

    issues = await run_llm_review(
        db, client_id,
        trigger="batch_review",
    )
    return {
        "status": "completed",
        "issues_found": len(issues),
        "issues": issues,
    }
