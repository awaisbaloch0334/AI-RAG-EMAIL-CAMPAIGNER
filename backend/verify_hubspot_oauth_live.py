import uuid
import httpx
from urllib.parse import parse_qs, urlparse

API_BASE = "http://localhost:8000"

def run_live_verification():
    print("=" * 60)
    print("HUBSPOT OAUTH 2.0 LIVE VERIFICATION ON ACTIVE UVICORN SERVER")
    print("=" * 60)

    client = httpx.Client(base_url=API_BASE, timeout=15.0)

    # 1. Health check
    print("\n[1] Checking Server Health...")
    r = client.get("/health")
    assert r.status_code == 200, f"Health failed: {r.status_code}"
    print("    -> Server is HEALTHY (200 OK)")

    # 2. Register & Login
    suffix = uuid.uuid4().hex[:6]
    email = f"oauth_live_{suffix}@example.com"
    pwd = "StrongPassword123!"

    print(f"\n[2] Registering User: {email}...")
    r = client.post("/api/auth/register", json={"email": email, "password": pwd})
    assert r.status_code == 201, f"Registration failed: {r.text}"
    user_id = r.json()["id"]
    print(f"    -> Registered User ID: {user_id}")

    r = client.post("/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("    -> Logged in, JWT token acquired.")

    # 3. Test /api/auth/hubspot/authorize
    print("\n[3] Testing GET /api/auth/hubspot/authorize...")
    r = client.get("/api/auth/hubspot/authorize", headers=headers)
    assert r.status_code == 200, f"Authorize failed: {r.text}"
    auth_url = r.json().get("url", "")
    print(f"    -> Generated URL: {auth_url[:80]}...")

    parsed = urlparse(auth_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "app.hubspot.com"
    assert parsed.path == "/oauth/authorize"

    qs = parse_qs(parsed.query)
    assert "client_id" in qs, "client_id missing"
    assert qs["client_id"][0] == "cc22ec21-1050-42e9-a72e-64547c887ecb"
    assert "redirect_uri" in qs, "redirect_uri missing"
    assert qs["redirect_uri"][0] == "http://localhost:8000/api/auth/hubspot/callback"
    assert "scope" in qs, "scope missing"
    assert "crm.objects.contacts.read" in qs["scope"][0]
    assert "state" in qs, "state parameter missing"
    print("    -> All OAuth parameters validated: client_id, redirect_uri, scope, and state.")

    # 4. Test /api/auth/hubspot/status
    print("\n[4] Testing GET /api/auth/hubspot/status...")
    r = client.get("/api/auth/hubspot/status", headers=headers)
    assert r.status_code == 200, f"Status failed: {r.text}"
    status_data = r.json()
    assert status_data["connected"] is False
    print(f"    -> Connection Status: connected={status_data['connected']}, auth_type={status_data['auth_type']}")

    # 5. Test /api/contacts/hubspot/test-connection diagnostics endpoint
    print("\n[5] Testing GET /api/contacts/hubspot/test-connection...")
    r = client.get("/api/contacts/hubspot/test-connection", headers=headers)
    assert r.status_code == 200, f"Test-connection failed: {r.text}"
    diag = r.json()
    print(f"    -> Diagnostics endpoint returned 200 OK: configured={diag.get('configured')}, msg={diag.get('message')}")

    # 6. Test setting user OAuth token and checking status & disconnect
    print("\n[6] Testing User OAuth Status & Disconnect...")
    from app.db.database import SessionLocal
    from app.db.models.user import User
    with SessionLocal() as db:
        u = db.get(User, user_id)
        u.hubspot_access_token = "mock_active_oauth_token"
        u.hubspot_portal_id = "247349614"
        db.commit()

    r = client.get("/api/auth/hubspot/status", headers=headers)
    assert r.status_code == 200
    status_active = r.json()
    assert status_active["connected"] is True
    assert status_active["portal_id"] == "247349614"
    print(f"    -> User OAuth status verified: connected=True, portal_id={status_active['portal_id']}")

    r = client.post("/api/auth/hubspot/disconnect", headers=headers)
    assert r.status_code == 200
    assert r.json()["success"] is True

    r = client.get("/api/auth/hubspot/status", headers=headers)
    assert r.json()["connected"] is False
    print("    -> Disconnect verified: status now connected=False.")

    # 7. Check Dashboard HTML for OAuth components
    print("\n[7] Verifying Dashboard SPA contains OAuth 2.0 UI components...")
    r = client.get("/dashboard")
    assert r.status_code == 200, f"Dashboard failed: {r.status_code}"
    html = r.text
    assert "Connect with HubSpot" in html, "Connect with HubSpot button missing"
    assert "checkHubSpotOAuthStatus" in html, "OAuth status checker missing"
    assert "handleConnectHubSpotOAuth" in html, "OAuth connect handler missing"
    print("    -> Dashboard SPA contains 1-click 'Connect with HubSpot' button & OAuth handlers.")

    print("\n" + "=" * 60)
    print(">>> ALL 7 HUBSPOT OAUTH LIVE VERIFICATION CHECKS PASSED (100%) <<<")
    print("=" * 60)

if __name__ == "__main__":
    run_live_verification()
