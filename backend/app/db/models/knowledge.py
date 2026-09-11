import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.bot import Bot
    from app.db.models.crawl import Page


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """
    Document holds clean normalized knowledge artifacts (e.g. canonical website.md,
    per-page markdown, structured extracts).
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    bot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("pages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        default="page",
        nullable=False,
    )  # e.g., 'page', 'canonical_markdown'
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    markdown_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(
        "Bot",
        back_populates="documents",
    )
    page: Mapped[Optional["Page"]] = relationship(
        "Page",
        back_populates="documents",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} bot_id={self.bot_id} type={self.type}>"


class Chunk(Base):
    """
    Chunk represents a segment of website knowledge embedded for vector retrieval.
    CRITICAL: bot_id must always be used to filter retrieval queries.
    """
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    bot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("pages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    embedding = mapped_column(
        Vector(),
        nullable=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    chunk_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(
        "Bot",
        back_populates="chunks",
    )
    page: Mapped[Optional["Page"]] = relationship(
        "Page",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} bot_id={self.bot_id} chunk_index={self.chunk_index}>"


class Asset(Base):
    """
    Asset stores metadata for visual assets (images, screenshots, logos).
    """
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    bot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("pages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # e.g., 'image', 'screenshot', 'logo'
    source_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    storage_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )
    asset_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(
        "Bot",
        back_populates="assets",
    )
    page: Mapped[Optional["Page"]] = relationship(
        "Page",
        back_populates="assets",
    )

    def __repr__(self) -> str:
        return f"<Asset id={self.id} bot_id={self.bot_id} type={self.type}>"

