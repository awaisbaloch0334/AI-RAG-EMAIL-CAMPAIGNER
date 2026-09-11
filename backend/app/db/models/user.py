import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.bot import Bot
    from app.db.models.contact import Contact
    from app.db.models.campaign import Campaign


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """
    User model representing an account owner.
    Enforces the ownership boundary: 1 User -> 1 or more Bots.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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

    # HubSpot OAuth 2.0 Integration
    hubspot_access_token: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    hubspot_refresh_token: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    hubspot_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    hubspot_portal_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    hubspot_connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    bots: Mapped[List["Bot"]] = relationship(
        "Bot",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    contacts: Mapped[List["Contact"]] = relationship(
        "Contact",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    campaigns: Mapped[List["Campaign"]] = relationship(
        "Campaign",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"

