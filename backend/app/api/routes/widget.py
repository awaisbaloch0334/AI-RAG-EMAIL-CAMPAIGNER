from pathlib import Path
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.bot import Bot
from app.db.models.branding import BrandSettings

router = APIRouter(tags=["widget"])


class BrandingConfig(BaseModel):
    company_name: str = "Website Assistant"
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#2563EB"
    secondary_color: Optional[str] = "#1D4ED8"
    background_color: str = "#FFFFFF"
    text_color: str = "#111827"
    font_family: str = "Inter, system-ui, sans-serif"
    position: str = "bottom-right"


class WidgetConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bot_id: str
    bot_name: str
    website_url: str
    status: str
    greeting_message: str = "Hi! How can I help you today?"
    branding: BrandingConfig


@router.get(
    "/api/bots/{bot_id}/widget-config",
    response_model=WidgetConfigResponse,
    summary="Get public widget branding and configuration for this bot",
)
def get_widget_config(
    bot_id: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Public configuration endpoint called by widget.js and the chat iframe.
    Returns visual branding, colors, company name, and greeting message.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    bot = db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    # Fetch custom brand settings if present, else provide polished defaults
    brand = db.get(BrandSettings, bot.id)

    dummy_markers = ("data:image", "base64", "no-image", "no_image", "noimage", "placeholder", "dummy", "blank.gif", "spacer.gif", "default-image")
    bad_greens = ("#61CE70", "#25D366", "#128C7E", "#79D45E", "#78D25F")
    if brand and bot.website_url:
        curr_logo = (brand.logo_url or "").strip().lower()
        curr_col = (brand.primary_color or "").strip().upper()
        curr_comp = (brand.company_name or "").strip()
        needs_heal = (
            (curr_logo and any(m in curr_logo for m in dummy_markers))
            or (curr_col in bad_greens)
            or (curr_comp.lower() in (bot.name.lower(), "website assistant") and bool(re.search(r"(?i)\b(chatbot|bot|ai assistant|assistant)\b", curr_comp)))
        )
        if needs_heal:
            try:
                from app.tasks.crawl_tasks import auto_enrich_bot_branding
                auto_enrich_bot_branding(db, bot, [])
                db.refresh(brand)
            except Exception:
                pass

    raw_company = (brand.company_name if brand and brand.company_name else bot.name).strip()
    # Clean company name: strip trailing "Chatbot", "Bot", "Assistant", or "AI" if present
    clean_company = re.sub(r"(?i)\s+(chatbot|bot|assistant|ai)$", "", raw_company).strip()
    if not clean_company:
        clean_company = raw_company

    branding = BrandingConfig(
        company_name=raw_company,
        logo_url=(brand.logo_url if brand else None),
        favicon_url=(brand.favicon_url if brand else None),
        primary_color=(brand.primary_color if brand and brand.primary_color else "#D6A84F"),
        secondary_color=(brand.secondary_color if brand and brand.secondary_color else "#F0C76A"),
        background_color=(brand.background_color if brand and brand.background_color else "#FFFFFF"),
        text_color=(brand.text_color if brand and brand.text_color else "#111827"),
        font_family=(brand.font_family if brand and brand.font_family else "Inter, system-ui, sans-serif"),
        position=(brand.position if brand and brand.position else "bottom-right"),
    )

    greeting_message = f"Hello! I am the AI Assistant for {clean_company}. How can I help you today?"

    return WidgetConfigResponse(
        bot_id=bot.id,
        bot_name=bot.name,
        website_url=bot.website_url,
        status=bot.status,
        greeting_message=greeting_message,
        branding=branding,
    )


@router.get(
    "/widget/chat",
    response_class=HTMLResponse,
    summary="Serve the standalone chat application HTML to run inside the iframe",
)
def serve_chat_iframe():
    """
    Returns the standalone React chat application HTML that runs inside the sandboxed iframe.
    """
    chat_html_path = Path(__file__).resolve().parents[3] / "static" / "chat" / "index.html"
    if not chat_html_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat iframe interface not found",
        )
    return HTMLResponse(content=chat_html_path.read_text(encoding="utf-8"))


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    summary="Serve the Customer Admin Dashboard application",
)
def serve_dashboard():
    """
    Returns the Customer Admin Dashboard single-page application.
    """
    dashboard_html_path = Path(__file__).resolve().parents[3] / "static" / "dashboard" / "index.html"
    if not dashboard_html_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin dashboard interface not found",
        )
    return HTMLResponse(
        content=dashboard_html_path.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

