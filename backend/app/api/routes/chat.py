from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_bot
from app.chat.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummaryResponse,
    MessageResponse,
)
from app.chat.service import ChatService
from app.db.database import get_db
from app.db.models.bot import Bot
from app.db.models.chat import Conversation, Message

router = APIRouter(prefix="/api/bots/{bot_id}", tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the bot and receive a grounded RAG response",
)
def send_chat_message(
    bot_id: str,
    req: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Public/widget-accessible RAG chat endpoint.
    Retrieves knowledge chunks strictly scoped to bot_id, defends against prompt injection
    in crawled text, and returns an answer with source citations.
    """
    bot = db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

    if bot.status not in ("READY", "PROCESSING"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bot is currently in '{bot.status}' state and not ready for chat. Please wait for indexing to complete.",
        )

    answer, citations, conv = ChatService.process_message(
        db=db,
        bot=bot,
        query=req.query,
        session_id=req.session_id,
        provider=req.provider,
    )

    return ChatResponse(
        answer=answer,
        sources=citations,
        conversation_id=conv.id,
        session_id=conv.session_id,
    )


@router.post(
    "/chat/stream",
    summary="Send a message and stream the response via Server-Sent Events (SSE)",
)
async def stream_chat_message(
    bot_id: str,
    req: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Real-time streaming chat endpoint using Server-Sent Events (SSE).
    Streams tokens directly to the frontend widget for responsive typing animations.
    """
    bot = db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

    if bot.status not in ("READY", "PROCESSING"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Bot is in '{bot.status}' state and not ready for chat.",
        )

    return StreamingResponse(
        ChatService.stream_message(
            db=db,
            bot=bot,
            query=req.query,
            session_id=req.session_id,
            provider=req.provider,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List past chat conversations for this bot (Owner authenticated)",
)
def list_conversations(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """
    Retrieve all conversation sessions scoped strictly to this bot.
    Enforces multi-tenant ownership via get_current_bot.
    """
    total = db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.bot_id == bot.id)
    ) or 0

    convs = (
        db.scalars(
            select(Conversation)
            .where(Conversation.bot_id == bot.id)
            .order_by(Conversation.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        .all()
    )

    items = []
    for c in convs:
        msg_count = db.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == c.id)
        ) or 0
        items.append(
            ConversationSummaryResponse(
                id=c.id,
                bot_id=c.bot_id,
                session_id=c.session_id,
                message_count=msg_count,
                created_at=c.created_at,
            )
        )

    return ConversationListResponse(conversations=items, total=total)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Retrieve full transcript of a specific conversation (Owner authenticated)",
)
def get_conversation_detail(
    conversation_id: str,
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Fetch full turn-by-turn message transcript of a conversation.
    Enforces multi-tenant boundary: conversation must strictly belong to bot_id.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.bot_id != bot.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = (
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
        )
        .all()
    )

    msg_items = [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]

    return ConversationDetailResponse(
        id=conv.id,
        bot_id=conv.bot_id,
        session_id=conv.session_id,
        created_at=conv.created_at,
        messages=msg_items,
    )

