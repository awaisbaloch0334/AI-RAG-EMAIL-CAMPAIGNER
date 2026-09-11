from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_bot
from app.db.database import get_db
from app.db.models.bot import Bot
from app.db.models.knowledge import Chunk, Document
from app.knowledge.indexing import run_knowledge_indexing_pipeline
from app.knowledge.schemas import (
    CanonicalMarkdownResponse,
    ChunkListResponse,
    ChunkResponse,
    IndexingRequest,
    IndexingResponse,
)

router = APIRouter(prefix="/api/bots/{bot_id}", tags=["knowledge"])


@router.post(
    "/index",
    response_model=IndexingResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger knowledge indexing for this bot",
)
def trigger_indexing(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
    payload: Optional[IndexingRequest] = None,
):
    """
    Assemble canonical Markdown (website.md), semantically chunk pages, generate vector
    embeddings, and index vectors in PostgreSQL pgvector.
    Advances bot status to 'READY'.
    Strict multi-tenant security: only the verified owner of bot_id can trigger indexing.
    """
    provider = payload.embedding_provider if payload else None
    result = run_knowledge_indexing_pipeline(
        bot_id=bot.id,
        db=db,
        embedding_provider=provider,
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"],
        )

    return IndexingResponse(
        status=result["status"],
        bot_id=result["bot_id"],
        pages_count=result["pages_count"],
        chunks_count=result["chunks_count"],
        canonical_markdown_length=result["canonical_markdown_length"],
        message=result["message"],
    )


@router.get(
    "/knowledge/markdown",
    response_model=CanonicalMarkdownResponse,
    summary="Retrieve canonical website.md document for this bot",
)
def get_canonical_markdown(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Fetch the canonical human-readable website.md document generated for this bot.
    Strict multi-tenant boundary: only the verified bot owner can access this document.
    """
    doc = db.scalar(
        select(Document).where(
            Document.bot_id == bot.id,
            Document.type == "canonical_markdown",
        )
    )
    if not doc or not doc.markdown_content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canonical Markdown document not found. Ensure website crawling and indexing have completed.",
        )

    return CanonicalMarkdownResponse(
        bot_id=doc.bot_id,
        markdown_content=doc.markdown_content,
        content_hash=doc.content_hash,
        source_url=doc.source_url,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "/chunks",
    response_model=ChunkListResponse,
    summary="List embedded knowledge chunks for this bot",
)
def list_chunks(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Max chunks to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
):
    """
    Retrieve stored knowledge chunks and metadata for this bot.
    Strict multi-tenant boundary: retrieves ONLY chunks scoped to bot_id.
    """
    total = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.bot_id == bot.id)
    ) or 0

    chunks = (
        db.scalars(
            select(Chunk)
            .where(Chunk.bot_id == bot.id)
            .order_by(Chunk.chunk_index.asc())
            .offset(offset)
            .limit(limit)
        )
        .all()
    )

    items = [
        ChunkResponse(
            id=c.id,
            bot_id=c.bot_id,
            page_id=c.page_id,
            chunk_index=c.chunk_index,
            content=c.content,
            chunk_metadata=c.chunk_metadata or {},
            created_at=c.created_at,
        )
        for c in chunks
    ]

    return ChunkListResponse(chunks=items, total=total)

