import uuid
import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models.user import User
from app.db.models.bot import Bot
from app.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def db():
    """Direct database session for assertions and test setup/teardown."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_auth_registration_and_login(client: TestClient, db):
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"auth_test_{unique_suffix}@example.com"
    password = "securePassword123!"

    # 1. Register
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_resp.status_code == 201, reg_resp.text
    user_data = reg_resp.json()
    assert user_data["email"] == email
    assert "id" in user_data
    assert "password" not in user_data
    assert "password_hash" not in user_data
    user_id = user_data["id"]

    # 2. Duplicate registration attempt must fail
    dup_resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert dup_resp.status_code == 400
    assert "already registered" in dup_resp.json()["detail"].lower()

    # 3. Login with correct password
    login_resp = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # 4. Login with wrong password
    bad_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 5. Access /api/auth/me with Bearer token
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["id"] == user_id
    assert me_data["email"] == email

    # 6. Access /api/auth/me without token fails
    unauth_resp = client.get("/api/auth/me")
    assert unauth_resp.status_code == 401

    # Cleanup
    user_in_db = db.get(User, user_id)
    if user_in_db:
        db.delete(user_in_db)
        db.commit()


def test_bot_crud_and_multi_tenant_ownership(client: TestClient, db):
    # Setup User A
    user_a_email = f"user_a_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "password123!"
    client.post("/api/auth/register", json={"email": user_a_email, "password": pwd})
    token_a = client.post("/api/auth/login", json={"email": user_a_email, "password": pwd}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Setup User B
    user_b_email = f"user_b_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": user_b_email, "password": pwd})
    token_b = client.post("/api/auth/login", json={"email": user_b_email, "password": pwd}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User A creates Bot A1
    create_resp_a = client.post(
        "/api/bots",
        json={"name": "Doctor Clinic AI", "website_url": "https://clinic.example.com"},
        headers=headers_a,
    )
    assert create_resp_a.status_code == 201, create_resp_a.text
    bot_a1 = create_resp_a.json()
    assert bot_a1["id"].startswith("bot_")
    assert bot_a1["name"] == "Doctor Clinic AI"
    assert bot_a1["status"] == "PENDING"
    bot_a1_id = bot_a1["id"]

    # 2. User B creates Bot B1
    create_resp_b = client.post(
        "/api/bots",
        json={"name": "Bank Portal Bot", "website_url": "https://bank.example.com"},
        headers=headers_b,
    )
    assert create_resp_b.status_code == 201
    bot_b1 = create_resp_b.json()
    bot_b1_id = bot_b1["id"]

    # 3. User A lists bots -> should ONLY see Bot A1
    list_a = client.get("/api/bots", headers=headers_a).json()
    assert list_a["total"] == 1
    assert list_a["bots"][0]["id"] == bot_a1_id
    assert list_a["bots"][0]["name"] == "Doctor Clinic AI"

    # 4. User B lists bots -> should ONLY see Bot B1
    list_b = client.get("/api/bots", headers=headers_b).json()
    assert list_b["total"] == 1
    assert list_b["bots"][0]["id"] == bot_b1_id
    assert list_b["bots"][0]["name"] == "Bank Portal Bot"

    # 5. User A retrieves own Bot A1
    get_a1 = client.get(f"/api/bots/{bot_a1_id}", headers=headers_a)
    assert get_a1.status_code == 200
    assert get_a1.json()["id"] == bot_a1_id

    # 6. HARD INVARIANT: User B attempts to access Bot A1 -> MUST be rejected (404)
    cross_tenant_get = client.get(f"/api/bots/{bot_a1_id}", headers=headers_b)
    assert cross_tenant_get.status_code == 404, "User B should not be able to view User A's bot!"

    # 7. HARD INVARIANT: User B attempts to update Bot A1 -> MUST be rejected (404)
    cross_tenant_patch = client.patch(
        f"/api/bots/{bot_a1_id}",
        json={"name": "Hacked Name"},
        headers=headers_b,
    )
    assert cross_tenant_patch.status_code == 404

    # 8. HARD INVARIANT: User B attempts to delete Bot A1 -> MUST be rejected (404)
    cross_tenant_delete = client.delete(f"/api/bots/{bot_a1_id}", headers=headers_b)
    assert cross_tenant_delete.status_code == 404

    # 9. User A updates own bot
    update_resp = client.patch(
        f"/api/bots/{bot_a1_id}",
        json={"name": "Doctor Clinic AI - Updated"},
        headers=headers_a,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Doctor Clinic AI - Updated"

    # 10. User A deletes own bot
    delete_resp = client.delete(f"/api/bots/{bot_a1_id}", headers=headers_a)
    assert delete_resp.status_code == 204

    # Verify bot is deleted from DB
    assert db.get(Bot, bot_a1_id) is None

    # Cleanup User A & User B
    user_a = db.query(User).filter_by(email=user_a_email).first()
    user_b = db.query(User).filter_by(email=user_b_email).first()
    if user_a:
        db.delete(user_a)
    if user_b:
        db.delete(user_b)
    db.commit()


from app.services.mail import get_last_sent_otp_for_test


def test_otp_request_and_verification(client: TestClient, db):
    email = f"otp_user_{uuid.uuid4().hex[:6]}@example.com"

    # 1. Request OTP
    req_resp = client.post("/api/auth/request-otp", json={"email": email})
    assert req_resp.status_code == 200
    otp_data = req_resp.json()
    assert "demo_otp" not in otp_data

    code = get_last_sent_otp_for_test(email)
    assert code is not None
    assert len(code) == 6

    # 2. Verify with wrong OTP -> 400
    fail_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": "000000"})
    assert fail_resp.status_code == 400

    # 3. Verify with valid OTP -> 200 with access token
    ok_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": code})
    assert ok_resp.status_code == 200
    token_data = ok_resp.json()
    assert "access_token" in token_data

    # 4. Attempt re-use of same OTP -> 400 (one-time use / invalidated)
    reuse_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": code})
    assert reuse_resp.status_code == 400

    # 5. Use token to get user profile
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email

    # Cleanup
    user = db.query(User).filter_by(email=email).first()
    if user:
        db.delete(user)
        db.commit()



