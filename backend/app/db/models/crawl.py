import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.bot import Bot
    from app.db.models.knowledge import Document, Chunk, Asset


def generate_uuid() -> str:
    return str(uuid.uuid4())


class CrawlJob(Base):
    """
    CrawlJob records an ingestion/crawl run for a specific bot.
    """
    __tablename__ = "crawl_jobs"

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
    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        nullable=False,
        index=True,
    )  # PENDING, RUNNING, COMPLETED, FAILED
    total_pages: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    processed_pages: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    failed_pages: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(
        "Bot",
        back_populates="crawl_jobs",
    )

    def __repr__(self) -> str:
        return f"<CrawlJob id={self.id} bot_id={self.bot_id} status={self.status}>"


class Page(Base):
    """
    Page records raw and structured content of a single crawled URL.
    """
    __tablename__ = "pages"

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
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        index=True,
        nullable=True,
    )
    crawl_status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        nullable=False,
    )  # PENDING, SUCCESS, FAILED
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
        back_populates="pages",
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="page",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="page",
        cascade="all, delete-orphan",
    )
    assets: Mapped[List["Asset"]] = relationship(
        "Asset",
        back_populates="page",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Page id={self.id} bot_id={self.bot_id} url={self.url}>"

