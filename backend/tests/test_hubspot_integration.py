from unittest.mock import patch, MagicMock
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.contacts.provider import HubSpotContactProvider, RawContactData
from app.contacts.service import ContactService
from app.db.database import SessionLocal
from app.db.models.contact import Contact
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



def test_hubspot_test_connection_unconfigured():
    provider = HubSpotContactProvider(access_token="")
    res = provider.test_connection()
    assert res["success"] is False
    assert res["configured"] is False
    assert "not configured" in res["message"]


def test_hubspot_test_connection_success():
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 42,
            "results": [{"id": "1", "properties": {"email": "test@example.com"}}],
        }
        mock_get.return_value = mock_resp

        provider = HubSpotContactProvider(access_token="pat-test-token-1234")
        res = provider.test_connection()
        assert res["success"] is True
        assert res["configured"] is True
        assert res["contact_count"] == 42


def test_hubspot_test_connection_invalid_token():
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        provider = HubSpotContactProvider(access_token="pat-invalid")
        res = provider.test_connection()
        assert res["success"] is False
        assert "Invalid or expired" in res["message"]


def test_hubspot_test_connection_missing_scope():
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        provider = HubSpotContactProvider(access_token="pat-no-scope")
        res = provider.test_connection()
        assert res["success"] is False
        assert "Missing permissions" in res["message"]


def test_hubspot_fetch_contacts_parsing():
    sample_hubspot_response = {
        "results": [
            {
                "id": "hs_101",
                "properties": {
                    "email": "richard.hendricks@piedpiper.com",
                    "firstname": "Richard",
                    "lastname": "Hendricks",
                    "company": "Pied Piper",
                    "jobtitle": "Founder & CEO",
                    "phone": "+1-555-0199",
                    "lifecyclestage": "opportunity",
                    "hs_lead_status": "OPEN",
                },
            },
            {
                "id": "hs_102",
                "properties": {
                    "email": "jared.dunn@piedpiper.com",
                    "firstname": "Jared",
                    "lastname": "Dunn",
                    "company": "Pied Piper",
                    "jobtitle": "Chief Operating Officer",
                },
            },
        ],
        "paging": {},
    }

    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_hubspot_response
        mock_get.return_value = mock_resp

        provider = HubSpotContactProvider(access_token="pat-valid-token")
        contacts = provider.fetch_contacts()

        assert len(contacts) == 2
        c1 = contacts[0]
        assert c1.email == "richard.hendricks@piedpiper.com"
        assert c1.name == "Richard Hendricks"
        assert c1.first_name == "Richard"
        assert c1.company == "Pied Piper"
        assert c1.role == "Founder & CEO"
        assert c1.custom_variables["hubspot_id"] == "hs_101"
        assert c1.custom_variables["phone"] == "+1-555-0199"
        assert c1.custom_variables["lifecycle_stage"] == "opportunity"


def test_hubspot_api_endpoints_and_tenant_isolation(client: TestClient, db: Session):
    # Setup User A
    suffix_a = uuid.uuid4().hex[:6]
    email_a = f"hubspot_user_a_{suffix_a}@example.com"
    pwd = "EnterprisePassword123!"

    reg_a = client.post("/api/auth/register", json={"email": email_a, "password": pwd})
    assert reg_a.status_code == 201
    user_a_id = reg_a.json()["id"]

    login_a = client.post("/api/auth/login", json={"email": email_a, "password": pwd})
    token_a = login_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Setup User B
    suffix_b = uuid.uuid4().hex[:6]
    email_b = f"hubspot_user_b_{suffix_b}@example.com"
    reg_b = client.post("/api/auth/register", json={"email": email_b, "password": pwd})
    assert reg_b.status_code == 201
    user_b_id = reg_b.json()["id"]

    login_b = client.post("/api/auth/login", json={"email": email_b, "password": pwd})
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. Test test-connection endpoint
    test_res = client.get("/api/contacts/hubspot/test-connection", headers=headers_a)
    assert test_res.status_code == 200
    assert "success" in test_res.json()

    # 2. Test import-hubspot endpoint with live response mock
    sample_hubspot_response = {
        "results": [
            {
                "id": "hs_tenant_1",
                "properties": {
                    "email": f"erlich_{suffix_a}@aviato.com",
                    "firstname": "Erlich",
                    "lastname": "Bachman",
                    "company": "Aviato",
                    "jobtitle": "Managing Partner",
                },
            }
        ],
        "paging": {},
    }

    with patch("app.config.settings.hubspot_access_token", "pat-test-valid"):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = sample_hubspot_response
            mock_get.return_value = mock_resp

            import_res = client.post("/api/contacts/import-hubspot", headers=headers_a)
            assert import_res.status_code == 200
            import_data = import_res.json()
            assert import_data["source"] == "hubspot_crm"
            assert import_data["imported"] == 1
            assert import_data["contacts"][0]["company"] == "Aviato"

    # 3. Verify Tenant Isolation: User A sees Aviato contact, User B sees 0 contacts
    list_a = client.get("/api/contacts", headers=headers_a).json()
    assert list_a["total"] == 1
    assert list_a["contacts"][0]["company"] == "Aviato"

    list_b = client.get("/api/contacts", headers=headers_b).json()
    assert list_b["total"] == 0

    # 4. Fallback Resilience: when unconfigured or offline, doesn't break campaign flow
    with patch("app.config.settings.hubspot_access_token", ""):
        fallback_res = client.post("/api/contacts/import-hubspot", headers=headers_b)
        assert fallback_res.status_code == 200
        fallback_data = fallback_res.json()
        assert fallback_data["source"] == "hubspot_demo"
        assert fallback_data["imported"] >= 1
