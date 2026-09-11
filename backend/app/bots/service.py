import re
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bots.schemas import BotCreateRequest, BotUpdateRequest
from app.db.models.bot import Bot
from app.db.models.branding import BrandSettings


class BotService:
    @staticmethod
    def create_bot(db: Session, user_id: str, req: BotCreateRequest) -> Bot:
        """
        Create a new bot associated with the authenticated user.
        Strict multi-tenant boundary: user_id is assigned directly from authentication context.
        """
        bot = Bot(
            user_id=user_id,
            name=req.name.strip(),
            website_url=str(req.website_url),
            status="PENDING",
        )
        db.add(bot)
        db.flush()

        # Initialize default brand settings with clean organization name
        initial_company = re.sub(r"(?i)\s+(chatbot|bot|assistant|ai)$", "", bot.name).strip() or bot.name
        brand_settings = BrandSettings(
            bot_id=bot.id,
            company_name=initial_company,
            primary_color="#2563EB",
            background_color="#FFFFFF",
            text_color="#111827",
            font_family="Inter",
            position="bottom-right",
        )
        db.add(brand_settings)

        db.commit()
        db.refresh(bot)
        return bot

    @staticmethod
    def list_bots_for_user(db: Session, user_id: str) -> List[Bot]:
        """List all bots owned by the specified user."""
        stmt = (
            select(Bot)
            .where(Bot.user_id == user_id)
            .order_by(Bot.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_bot(db: Session, bot_id: str, user_id: str) -> Optional[Bot]:
        """Retrieve a bot verifying user ownership."""
        stmt = select(Bot).where(Bot.id == bot_id, Bot.user_id == user_id)
        return db.scalar(stmt)

    @staticmethod
    def update_bot(db: Session, bot: Bot, req: BotUpdateRequest) -> Bot:
        """Update bot attributes."""
        if req.name is not None:
            bot.name = req.name.strip()
        if req.website_url is not None:
            bot.website_url = str(req.website_url)

        db.commit()
        db.refresh(bot)
        return bot

    @staticmethod
    def delete_bot(db: Session, bot: Bot) -> None:
        """Delete a bot and cascade all associated data."""
        db.delete(bot)
        db.commit()

