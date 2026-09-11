import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.bot import Bot
    from app.db.models.contact import Contact


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Campaign(Base):
    """
    Campaign model representing an email marketing campaign.
    Belongs to a User and links to a Bot as its knowledge source for RAG.
    """
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    bot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="DRAFT",
        nullable=False,
        index=True,
    )  # DRAFT, GENERATING, READY, SENDING, COMPLETED, ARCHIVED
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
        back_populates="campaigns",
    )
    bot: Mapped["Bot"] = relationship(
        "Bot",
        back_populates="campaigns",
    )
    campaign_emails: Mapped[List["CampaignEmail"]] = relationship(
        "CampaignEmail",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} name={self.name} status={self.status}>"


class CampaignEmail(Base):
    """
    CampaignEmail model representing an individual personalized email
    generated for a contact in a campaign.
    """
    __tablename__ = "campaign_emails"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", name="uq_campaign_email_contact"),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    contact_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    subject: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    body: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
        nullable=False,
        index=True,
    )  # PENDING, GENERATED, SENT, FAILED
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    campaign: Mapped["Campaign"] = relationship(
        "Campaign",
        back_populates="campaign_emails",
    )
    contact: Mapped["Contact"] = relationship(
        "Contact",
        back_populates="campaign_emails",
    )

    def __repr__(self) -> str:
        return f"<CampaignEmail id={self.id} campaign_id={self.campaign_id} contact_id={self.contact_id} status={self.status}>"

