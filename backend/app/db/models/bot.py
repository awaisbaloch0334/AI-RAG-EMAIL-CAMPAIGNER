import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.crawl import CrawlJob, Page
    from app.db.models.knowledge import Document, Chunk, Asset
    from app.db.models.branding import BrandSettings
    from app.db.models.chat import Conversation
    from app.db.models.campaign import Campaign


def generate_bot_id() -> str:
    return f"bot_{uuid.uuid4().hex[:12]}"


class Bot(Base):
    """
    Bot model representing a website-specific chatbot project.
    Core isolation invariant: bot_id is the retrieval and knowledge boundary.
    """
    __tablename__ = "bots"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_bot_id,
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    website_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        nullable=False,
        index=True,
    )  # PENDING, CRAWLING, PROCESSING, INDEXING, READY, FAILED
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
    user: Mapped["User"] = relationship(
        "User",
        back_populates="bots",
    )
    crawl_jobs: Mapped[List["CrawlJob"]] = relationship(
        "CrawlJob",
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    pages: Mapped[List["Page"]] = relationship(
        "Page",
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    assets: Mapped[List["Asset"]] = relationship(
        "Asset",
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    brand_settings: Mapped[Optional["BrandSettings"]] = relationship(
        "BrandSettings",
        back_populates="bot",
        uselist=False,
        cascade="all, delete-orphan",
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    campaigns: Mapped[List["Campaign"]] = relationship(
        "Campaign",
        back_populates="bot",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Bot id={self.id} name={self.name} status={self.status}>"

