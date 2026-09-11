import uuid
import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models.bot import Bot
from app.db.models.branding import BrandSettings
from app.db.models.user import User
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_widget_config_with_custom_branding(client, db):
    """Verify /api/bots/{bot_id}/widget-config returns custom brand settings."""
    user = User(email=f"widget_{uuid.uuid4().hex[:8]}@example.com", password_hash="dummy")
    db.add(user)
    db.commit()

    bot = Bot(
        name="Acme SuperBot",
        website_url="https://acme-super.example.com",
        user_id=user.id,
        status="READY",
    )
    db.add(bot)
    db.commit()

    brand = BrandSettings(
        bot_id=bot.id,
        company_name="Acme SuperBot Inc",
        logo_url="https://acme-super.example.com/logo.png",
        primary_color="#10B981",
        secondary_color="#059669",
        background_color="#FFFFFF",
        text_color="#1F2937",
        font_family="Poppins, sans-serif",
        position="bottom-left",
    )
    db.add(brand)
    db.commit()

    resp = client.get(f"/api/bots/{bot.id}/widget-config")
    assert resp.status_code == 200
    data = resp.json()

    assert data["bot_id"] == bot.id
    assert data["bot_name"] == "Acme SuperBot"
    assert data["branding"]["company_name"] == "Acme SuperBot Inc"
    assert data["branding"]["primary_color"] == "#10B981"
    assert data["branding"]["position"] == "bottom-left"
    assert data["branding"]["logo_url"] == "https://acme-super.example.com/logo.png"
    assert "Acme SuperBot" in data["greeting_message"]

    # Cleanup
    db.delete(user)
    db.commit()


def test_widget_config_with_defaults(client, db):
    """Verify /api/bots/{bot_id}/widget-config provides sensible defaults if brand settings unconfigured."""
    user = User(email=f"widget_def_{uuid.uuid4().hex[:8]}@example.com", password_hash="dummy")
    db.add(user)
    db.commit()

    bot = Bot(
        name="DefaultBot",
        website_url="https://default.example.com",
        user_id=user.id,
        status="READY",
    )
    db.add(bot)
    db.commit()

    resp = client.get(f"/api/bots/{bot.id}/widget-config")
    assert resp.status_code == 200
    data = resp.json()

    assert data["bot_id"] == bot.id
    assert data["branding"]["primary_color"] == "#D6A84F"
    assert data["branding"]["position"] == "bottom-right"
    assert data["branding"]["company_name"] == "DefaultBot"

    # Cleanup
    db.delete(user)
    db.commit()


def test_widget_config_not_found(client):
    """Verify /api/bots/{bot_id}/widget-config returns 404 for invalid bot_id."""
    resp = client.get("/api/bots/non-existent-bot-9999/widget-config")
    assert resp.status_code == 404


def test_static_widget_js_served(client):
    """Verify /static/widget.js is accessible and contains widget loader logic."""
    resp = client.get("/static/widget.js")
    assert resp.status_code == 200
    assert "rag-launcher-btn" in resp.text
    assert "__RAG_WIDGET_LOADED__" in resp.text


def test_standalone_chat_iframe_served(client):
    """Verify /widget/chat serves the React chat application HTML."""
    resp = client.get("/widget/chat")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "ChatApp" in resp.text
    assert "untrusted_website_reference_data" not in resp.text  # Frontend doesn't leak internal prompt tags
    assert "CLOSE_CHAT" in resp.text

