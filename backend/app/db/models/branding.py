from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.bot import Bot


class BrandSettings(Base):
    """
    BrandSettings stores visual identity extracted from the website.
    Maintained separately from RAG text knowledge.
    """
    __tablename__ = "brand_settings"

    bot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    company_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    logo_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )
    favicon_url: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
    )
    primary_color: Mapped[Optional[str]] = mapped_column(
        String(32),
        default="#2563EB",
        nullable=True,
    )
    secondary_color: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    background_color: Mapped[Optional[str]] = mapped_column(
        String(32),
        default="#FFFFFF",
        nullable=True,
    )
    text_color: Mapped[Optional[str]] = mapped_column(
        String(32),
        default="#111827",
        nullable=True,
    )
    font_family: Mapped[Optional[str]] = mapped_column(
        String(64),
        default="Inter",
        nullable=True,
    )
    position: Mapped[Optional[str]] = mapped_column(
        String(32),
        default="bottom-right",
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
        back_populates="brand_settings",
    )

    def __repr__(self) -> str:
        return f"<BrandSettings bot_id={self.bot_id} company_name={self.company_name}>"

