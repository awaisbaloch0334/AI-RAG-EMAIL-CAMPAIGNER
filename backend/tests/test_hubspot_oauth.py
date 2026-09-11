from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import uuid
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.contacts.oauth import HubSpotOAuthService
from app.db.database import SessionLocal
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


@pytest.fixture
def test_user(db: Session):
    suffix = uuid.uuid4().hex[:6]
    user = User(
        email=f"oauth_test_{suffix}@example.com",
        password_hash="mocked_hash_for_testing",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user

    # Cleanup
    db.delete(user)
    db.commit()


def test_generate_authorization_url(test_user):
    url = HubSpotOAuthService.generate_authorization_url(test_user.id)
    expected_base = f"{settings.hubspot_auth_base_url.rstrip('/')}/oauth/authorize"
    assert url.startswith(expected_base)
    assert f"client_id={settings.hubspot_client_id}" in url
    assert "crm.objects.contacts.read" in url

    # Parse state param
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert "state" in qs
    state_token = qs["state"][0]

    payload = jwt.decode(
        state_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == test_user.id
    assert payload["purpose"] == "hubspot_oauth"


def test_invalid_state_rejection(db: Session):
    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        HubSpotOAuthService.exchange_code_for_tokens(
            code="test_code",
            state="invalid.tampered.token",
            db=db,
        )


def test_exchange_code_for_tokens(db: Session, test_user):
    state_token = jwt.encode(
        {
            "sub": test_user.id,
            "purpose": "hubspot_oauth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "oauth_token_abc_123",
        "refresh_token": "refresh_token_xyz_456",
        "expires_in": 1800,
    }

    mock_info_resp = MagicMock()
    mock_info_resp.status_code = 200
    mock_info_resp.json.return_value = {
        "hub_id": 247349614,
        "user": "test@example.com",
    }

    with patch("httpx.Client.post", return_value=mock_token_resp), patch("httpx.Client.get", return_value=mock_info_resp):
        updated_user = HubSpotOAuthService.exchange_code_for_tokens("valid_code", state_token, db)
        assert updated_user.hubspot_access_token == "oauth_token_abc_123"
        assert updated_user.hubspot_refresh_token == "refresh_token_xyz_456"
        assert updated_user.hubspot_portal_id == "247349614"
        assert updated_user.hubspot_token_expires_at is not None


def test_auto_refresh_token_when_expired(db: Session, test_user):
    test_user.hubspot_access_token = "old_expired_token"
    test_user.hubspot_refresh_token = "valid_refresh_token"
    test_user.hubspot_token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    mock_refresh_resp = MagicMock()
    mock_refresh_resp.status_code = 200
    mock_refresh_resp.json.return_value = {
        "access_token": "freshly_refreshed_access_token",
        "refresh_token": "new_rotated_refresh_token",
        "expires_in": 1800,
    }

    with patch("httpx.Client.post", return_value=mock_refresh_resp):
        token = HubSpotOAuthService.get_valid_access_token(test_user, db)
        assert token == "freshly_refreshed_access_token"
        assert test_user.hubspot_access_token == "freshly_refreshed_access_token"
        assert test_user.hubspot_refresh_token == "new_rotated_refresh_token"


def test_disconnect_user(db: Session, test_user):
    test_user.hubspot_access_token = "token_to_clear"
    test_user.hubspot_portal_id = "12345"
    db.commit()

    HubSpotOAuthService.disconnect_user(test_user, db)
    assert test_user.hubspot_access_token is None
    assert test_user.hubspot_refresh_token is None
    assert test_user.hubspot_portal_id is None


def test_oauth_api_endpoints_integration(client: TestClient, db: Session):
    # Setup registered user
    suffix = uuid.uuid4().hex[:6]
    email = f"oauth_endpoint_user_{suffix}@example.com"
    pwd = "SecurePassword123!"

    reg = client.post("/api/auth/register", json={"email": email, "password": pwd})
    assert reg.status_code == 201

    login = client.post("/api/auth/login", json={"email": email, "password": pwd})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test /authorize
    auth_resp = client.get("/api/auth/hubspot/authorize", headers=headers)
    assert auth_resp.status_code == 200
    data = auth_resp.json()
    assert "url" in data
    assert f"{settings.hubspot_auth_base_url.rstrip('/')}/oauth/authorize" in data["url"]

    # 2. Test /status initially
    status_resp = client.get("/api/auth/hubspot/status", headers=headers)
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["connected"] is False
    assert data["portal_id"] is None

    # 3. Simulate callback redirect
    state_token = jwt.encode(
        {
            "sub": reg.json()["id"],
            "purpose": "hubspot_oauth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with patch("app.api.routes.hubspot_oauth.HubSpotOAuthService.exchange_code_for_tokens") as mock_exchange:
        callback_resp = client.get(
            f"/api/auth/hubspot/callback?code=hubspot_code_123&state={state_token}",
            follow_redirects=False,
        )
        assert callback_resp.status_code == 303
        assert "/dashboard?hubspot=connected" in callback_resp.headers["location"]
        mock_exchange.assert_called_once()

    # 4. Simulate user with active token in DB
    user_record = db.get(User, reg.json()["id"])
    user_record.hubspot_access_token = "oauth_live_token"
    user_record.hubspot_portal_id = "247349614"
    db.commit()

    status_after = client.get("/api/auth/hubspot/status", headers=headers)
    assert status_after.status_code == 200
    data_after = status_after.json()
    assert data_after["connected"] is True
    assert data_after["portal_id"] == "247349614"

    # 5. Test /disconnect
    disc_resp = client.post("/api/auth/hubspot/disconnect", headers=headers)
    assert disc_resp.status_code == 200
    assert disc_resp.json()["success"] is True

    # 6. Check /status after disconnect
    status_disc = client.get("/api/auth/hubspot/status", headers=headers)
    assert status_disc.json()["connected"] is False
