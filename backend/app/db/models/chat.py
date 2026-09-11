import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.db.models.bot import Bot


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Conversation(Base):
    """
    Conversation tracks chat sessions for a specific bot.
    CRITICAL: bot_id scopes all conversations.
    """
    __tablename__ = "conversations"

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
    session_id: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(
        "Bot",
        back_populates="conversations",
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} bot_id={self.bot_id} session_id={self.session_id}>"


class Message(Base):
    """
    Message records an individual exchange turn (user, assistant, or system) in a conversation.
    """
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=generate_uuid,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} conversation_id={self.conversation_id} role={self.role}>"

