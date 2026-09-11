import logging
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.bot import Bot
from app.db.models.crawl import Page
from app.db.models.knowledge import Chunk, Document
from app.embeddings.service import EmbeddingService
from app.knowledge.chunking import SemanticChunker
from app.knowledge.markdown import CanonicalMarkdownGenerator

logger = logging.getLogger(__name__)


def run_knowledge_indexing_pipeline(
    bot_id: str,
    db: Session,
    embedding_provider: Optional[str] = None,
    chunk_size: int = 700,
    chunk_overlap: int = 80,
) -> Dict[str, Any]:
    """
    Core knowledge indexing pipeline:
    1. Loads all successfully crawled pages for the given bot_id.
    2. Generates canonical Markdown (website.md) with source attribution.
    3. Persists/updates the canonical Document record for the bot.
    4. Semantically chunks the content preserving hierarchy and metadata.
    5. Generates vector embeddings via EmbeddingService (FastEmbed, Mock, OpenAI, Gemini).
    6. Removes stale chunks for this bot_id and bulk inserts new embedded chunks into pgvector.
    7. Sets bot status to 'READY'.

    Strict Multi-Tenant Invariant: Every document and chunk is explicitly bound to bot_id.
    """
    bot = db.get(Bot, bot_id)
    if not bot:
        logger.error(f"Bot '{bot_id}' not found for knowledge indexing")
        return {"status": "failed", "bot_id": bot_id, "message": "Bot not found"}

    try:
        # 1. Fetch crawled pages for this bot
        pages = (
            db.scalars(
                select(Page)
                .where(Page.bot_id == bot.id, Page.crawl_status == "SUCCESS")
                .order_by(Page.created_at.asc())
            )
            .all()
        )
        logger.info(f"Bot '{bot.id}': Indexing {len(pages)} crawled pages...")

        # 2. Generate canonical Markdown
        canonical_md = CanonicalMarkdownGenerator.generate(bot, pages)
        content_hash = CanonicalMarkdownGenerator.compute_hash(canonical_md)

        # 3. Upsert canonical Document record
        canonical_doc = db.scalar(
            select(Document).where(
                Document.bot_id == bot.id,
                Document.type == "canonical_markdown",
            )
        )
        if canonical_doc:
            canonical_doc.markdown_content = canonical_md
            canonical_doc.content = canonical_md
            canonical_doc.content_hash = content_hash
            canonical_doc.source_url = bot.website_url
        else:
            canonical_doc = Document(
                bot_id=bot.id,
                type="canonical_markdown",
                markdown_content=canonical_md,
                content=canonical_md,
                content_hash=content_hash,
                source_url=bot.website_url,
            )
            db.add(canonical_doc)

        # 4. Semantic Chunking
        chunker = SemanticChunker(target_chunk_size=chunk_size, overlap=chunk_overlap)
        chunks = chunker.chunk_pages(pages)
        logger.info(f"Bot '{bot.id}': Generated {len(chunks)} semantic chunks")

        # 5. Generate Vector Embeddings
        embeddings = []
        if chunks:
            chunk_texts = [c.content for c in chunks]
            embeddings = EmbeddingService.embed_texts(chunk_texts, provider=embedding_provider)
            logger.info(
                f"Bot '{bot.id}': Generated {len(embeddings)} embeddings "
                f"via {embedding_provider or 'default'} (dim={len(embeddings[0]) if embeddings else 0})"
            )

        # 6. Atomic replacement of bot chunks to prevent duplicates / orphans
        db.execute(delete(Chunk).where(Chunk.bot_id == bot.id))

        if chunks:
            new_chunks = [
                Chunk(
                    bot_id=bot.id,
                    page_id=c.page_id,
                    content=c.content,
                    embedding=embeddings[i] if i < len(embeddings) else None,
                    chunk_index=c.chunk_index,
                    chunk_metadata=c.metadata,
                )
                for i, c in enumerate(chunks)
            ]
            db.add_all(new_chunks)

        # 7. Update Bot state to READY
        bot.status = "READY"
        db.commit()

        logger.info(f"Bot '{bot.id}' successfully indexed and set to READY state.")
        return {
            "status": "success",
            "bot_id": bot.id,
            "pages_count": len(pages),
            "chunks_count": len(chunks),
            "canonical_markdown_length": len(canonical_md),
            "message": f"Successfully indexed {len(chunks)} chunks from {len(pages)} pages.",
        }

    except Exception as e:
        logger.error(f"Knowledge indexing failed for bot '{bot_id}': {str(e)}", exc_info=True)
        db.rollback()
        bot.status = "FAILED"
        try:
            db.commit()
        except Exception:
            pass
        return {
            "status": "failed",
            "bot_id": bot_id,
            "pages_count": 0,
            "chunks_count": 0,
            "canonical_markdown_length": 0,
            "message": f"Indexing failed: {str(e)}",
        }

