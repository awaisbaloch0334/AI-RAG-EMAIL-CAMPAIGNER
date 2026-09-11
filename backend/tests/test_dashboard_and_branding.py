import uuid
import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models.bot import Bot
from app.db.models.user import User
from app.db.models.branding import BrandSettings
from app.auth.security import create_access_token, hash_password
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


def create_test_user_and_token(db, email_prefix="dash_test"):
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("Secret123!"))
    db.add(user)
    db.commit()
    token = create_access_token(subject=user.id)
    return user, token


def test_dashboard_route_serves_dark_theme_spa(client):
    """Verify GET /dashboard returns the fixed dark-theme Admin Dashboard HTML."""
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    # Verify strict instructor design system tokens
    assert "charcoal-deep" in html
    assert "#080A0D" in html
    assert "#111418" in html
    assert "#1A1D21" in html
    assert "#D6A84F" in html
    assert "#C8CBD0" in html
    # Verify core SPA elements
    assert "BrandingCustomizerView" in html
    assert "BotsOverviewView" in html
    assert "CrawlKnowledgeView" in html
    assert "EmbedCodeView" in html
    assert "ConversationsView" in html


def test_get_and_put_bot_branding(client, db):
    """Verify owner can get and customize their bot's visual branding."""
    user, token = create_test_user_and_token(db, "brand_owner")
    bot = Bot(
        name="Brandable Bot",
        website_url="https://brandable.example.com",
        user_id=user.id,
        status="READY",
    )
    db.add(bot)
    db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET branding (initial defaults)
    get_res = client.get(f"/api/bots/{bot.id}/branding", headers=headers)
    assert get_res.status_code == 200
    brand_data = get_res.json()
    assert brand_data["bot_id"] == bot.id
    assert brand_data["primary_color"] == "#D6A84F"
    assert brand_data["background_color"] == "#FFFFFF"
    assert brand_data["position"] == "bottom-right"

    # 2. PUT custom branding
    custom_update = {
        "company_name": "Emerald Cloud Corp",
        "primary_color": "#059669",
        "secondary_color": "#10B981",
        "background_color": "#0F172A",
        "text_color": "#F8FAFC",
        "logo_url": "https://emerald.example.com/logo.svg",
        "position": "bottom-left",
    }
    put_res = client.put(f"/api/bots/{bot.id}/branding", json=custom_update, headers=headers)
    assert put_res.status_code == 200
    updated_brand = put_res.json()
    assert updated_brand["company_name"] == "Emerald Cloud Corp"
    assert updated_brand["primary_color"] == "#059669"
    assert updated_brand["background_color"] == "#0F172A"
    assert updated_brand["text_color"] == "#F8FAFC"
    assert updated_brand["position"] == "bottom-left"

    # 3. Verify public widget-config immediately reflects customized colors
    widget_res = client.get(f"/api/bots/{bot.id}/widget-config")
    assert widget_res.status_code == 200
    w_data = widget_res.json()
    assert w_data["branding"]["primary_color"] == "#059669"
    assert w_data["branding"]["background_color"] == "#0F172A"
    assert w_data["branding"]["text_color"] == "#F8FAFC"
    assert w_data["branding"]["company_name"] == "Emerald Cloud Corp"
    assert w_data["branding"]["position"] == "bottom-left"

    # Cleanup
    db.delete(user)
    db.commit()


def test_branding_tenant_isolation(client, db):
    """Verify users cannot access or alter branding for bots owned by other users."""
    user_a, token_a = create_test_user_and_token(db, "owner_a")
    user_b, token_b = create_test_user_and_token(db, "intruder_b")

    bot_a = Bot(
        name="Tenant A Bot",
        website_url="https://tenant-a.com",
        user_id=user_a.id,
        status="READY",
    )
    db.add(bot_a)
    db.commit()

    # User B tries to read User A's branding -> 404 (multi-tenant isolation)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    res_get = client.get(f"/api/bots/{bot_a.id}/branding", headers=headers_b)
    assert res_get.status_code == 404

    # User B tries to update User A's branding -> 404
    res_put = client.put(
        f"/api/bots/{bot_a.id}/branding",
        json={"primary_color": "#FF0000"},
        headers=headers_b,
    )
    assert res_put.status_code == 404

    # Unauthenticated request -> 401
    res_unauth = client.get(f"/api/bots/{bot_a.id}/branding")
    assert res_unauth.status_code == 401

    # Cleanup
    db.delete(user_a)
    db.delete(user_b)
    db.commit()
