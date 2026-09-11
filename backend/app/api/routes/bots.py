from typing import Annotated, List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_bot, get_current_user
from app.bots.schemas import (
    BotCreateRequest,
    BotListResponse,
    BotResponse,
    BotUpdateRequest,
    BrandingResponse,
    BrandingUpdateRequest,
)
from app.bots.service import BotService
from app.db.database import get_db
from app.db.models.bot import Bot
from app.db.models.branding import BrandSettings
from app.db.models.user import User

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.post(
    "",
    response_model=BotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chatbot project",
)
def create_bot(
    req: BotCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Creates a new bot associated with the authenticated user.
    Backend sets user_id = current_user.id; never trusts client-provided identity.
    """
    bot = BotService.create_bot(db, current_user.id, req)
    return bot


@router.get(
    "",
    response_model=BotListResponse,
    summary="List all bots owned by current user",
)
def list_bots(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Returns only the bots belonging to the authenticated user.
    """
    bots = BotService.list_bots_for_user(db, current_user.id)
    return BotListResponse(bots=bots, total=len(bots))


@router.get(
    "/{bot_id}",
    response_model=BotResponse,
    summary="Get details of a specific bot",
)
def get_bot(
    bot: Annotated[Bot, Depends(get_current_bot)],
):
    """
    Returns bot details if and only if owned by the authenticated user.
    """
    return bot


@router.patch(
    "/{bot_id}",
    response_model=BotResponse,
    summary="Update bot details",
)
def update_bot(
    req: BotUpdateRequest,
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Updates bot properties with strict ownership verification.
    """
    updated_bot = BotService.update_bot(db, bot, req)
    return updated_bot


@router.delete(
    "/{bot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a bot and all associated data",
)
def delete_bot(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Deletes the bot and cascades deletion to all child pages, chunks, assets, and conversations.
    """
    BotService.delete_bot(db, bot)
    return None


@router.get(
    "/{bot_id}/branding",
    response_model=BrandingResponse,
    summary="Get branding settings for this bot (Owner authenticated)",
)
def get_bot_branding(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Returns visual branding configuration strictly for this bot.
    """
    brand = db.get(BrandSettings, bot.id)
    if not brand:
        return BrandingResponse(
            bot_id=bot.id,
            company_name=bot.name,
            primary_color="#D6A84F",
            secondary_color="#F0C76A",
            background_color="#FFFFFF",
            text_color="#111827",
            font_family="Inter, system-ui, sans-serif",
            position="bottom-right",
        )
    return brand


@router.put(
    "/{bot_id}/branding",
    response_model=BrandingResponse,
    summary="Update or create visual branding for this bot (Owner authenticated)",
)
def update_bot_branding(
    req: BrandingUpdateRequest,
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Updates or creates custom branding settings for this bot.
    Changes immediately reflect on the embeddable chat widget.
    """
    brand = db.get(BrandSettings, bot.id)
    if not brand:
        brand = BrandSettings(bot_id=bot.id)
        db.add(brand)

    if req.company_name is not None:
        brand.company_name = req.company_name
    if req.logo_url is not None:
        brand.logo_url = req.logo_url
    if req.favicon_url is not None:
        brand.favicon_url = req.favicon_url
    if req.primary_color is not None:
        brand.primary_color = req.primary_color
    if req.secondary_color is not None:
        brand.secondary_color = req.secondary_color
    if req.background_color is not None:
        brand.background_color = req.background_color
    if req.text_color is not None:
        brand.text_color = req.text_color
    if req.font_family is not None:
        brand.font_family = req.font_family
    if req.position is not None:
        brand.position = req.position

    db.commit()
    db.refresh(brand)
    return brand

