import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat_message import ChatMessage
from app.models.client import Client
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_agent import run_agent_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/clients/{client_id}/chat", tags=["chat"])

_HISTORY_LIMIT = 60  # messages to load as context


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_history(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessage]:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.client_id == client_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(_HISTORY_LIMIT)
    )
    return list(result.scalars().all())


@router.post("")
async def send_message(
    client_id: uuid.UUID,
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    # Load existing history (excluding the new message)
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.client_id == client_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(_HISTORY_LIMIT - 1)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in history_result.scalars().all()
    ]

    # Save user message to DB before streaming
    user_msg = ChatMessage(client_id=client_id, role="user", content=body.message)
    db.add(user_msg)
    await db.commit()

    # Build full message list for the agent
    messages = history + [{"role": "user", "content": body.message}]

    async def event_stream():
        full_text = ""
        try:
            async for chunk in run_agent_stream(messages, db, client, client_id):
                if chunk.get("type") == "text":
                    full_text += chunk.get("delta", "")
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("Agent stream error: %s", exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            # Persist the assistant response regardless of how the stream ended
            if full_text.strip():
                db.add(ChatMessage(client_id=client_id, role="assistant", content=full_text))
                await db.commit()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    result = await db.execute(
        select(ChatMessage).where(ChatMessage.client_id == client_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)
    await db.commit()
