import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge import Chunk
from app.embeddings.service import EmbeddingService
from app.rag.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class VectorRetriever:
    """
    Performs bot-scoped vector similarity search using PostgreSQL + pgvector.
    NON-NEGOTIABLE SECURITY INVARIANT:
    Retrieval queries must ALWAYS include `where(Chunk.bot_id == bot_id)`.
    Never retrieve or compare vectors across tenant boundaries.
    """

    @classmethod
    def retrieve(
        cls,
        bot_id: str,
        query: str,
        db: Session,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        provider: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        """
        Embed the user query and retrieve the top-k most semantically relevant chunks
        strictly belonging to `bot_id`.
        """
        if not query or not query.strip():
            return []

        # 1. Compute query vector
        query_vector = EmbeddingService.embed_query(query.strip(), provider=provider)

        # 2. Query pgvector using cosine distance (<=>)
        # Cosine distance = 1 - cosine_similarity. Smaller distance means higher similarity.
        distance_expr = Chunk.embedding.cosine_distance(query_vector).label("distance")

        stmt = (
            select(Chunk, distance_expr)
            .where(
                Chunk.bot_id == bot_id,
                Chunk.embedding.is_not(None),
            )
            .order_by(distance_expr.asc())
            .limit(top_k)
        )

        rows = db.execute(stmt).all()
        retrieved: List[RetrievedChunk] = []

        for chunk, distance in rows:
            # Distance is float; convert to similarity score
            # cosine distance in pgvector ranges from 0 to 2
            dist_val = float(distance) if distance is not None else 1.0
            similarity = max(0.0, 1.0 - dist_val)

            if score_threshold is not None and similarity < score_threshold:
                continue

            metadata = chunk.chunk_metadata or {}
            source_url = metadata.get("source_url") or ""
            page_title = metadata.get("page_title") or "Website Knowledge"
            section = metadata.get("section") or "General"

            retrieved.append(
                RetrievedChunk(
                    id=chunk.id,
                    bot_id=chunk.bot_id,
                    page_id=chunk.page_id,
                    content=chunk.content,
                    source_url=source_url,
                    page_title=page_title,
                    section=section,
                    chunk_index=chunk.chunk_index,
                    similarity_score=similarity,
                    metadata=metadata,
                )
            )

        logger.info(
            f"Bot '{bot_id}': Retrieved {len(retrieved)} chunks for query '{query[:40]}...' (top_k={top_k})"
        )
        return retrieved

