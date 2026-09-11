import uuid
import pytest
from fastapi.testclient import TestClient

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


def create_authenticated_user(client: TestClient):
    suffix = uuid.uuid4().hex[:8]
    email = f"leaduser_{suffix}@example.com"
    password = "SecretPassword123!"

    reg = client.post("/api/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201
    user_data = reg.json()

    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    return user_data, headers


def test_contact_crud_lifecycle(client: TestClient, db):
    user, headers = create_authenticated_user(client)

    # 1. Create Contact
    contact_data = {
        "name": "Bruce Wayne",
        "first_name": "Bruce",
        "email": "bruce@wayneenterprises.example.com",
        "company": "Wayne Enterprises",
        "role": "CEO",
        "custom_variables": {"tier": "Enterprise", "region": "Gotham"},
    }
    create_resp = client.post("/api/contacts", json=contact_data, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    res_data = create_resp.json()
    contact_id = res_data["id"]

    assert res_data["name"] == "Bruce Wayne"
    assert res_data["first_name"] == "Bruce"
    assert res_data["email"] == "bruce@wayneenterprises.example.com"
    assert res_data["company"] == "Wayne Enterprises"
    assert res_data["role"] == "CEO"
    assert res_data["custom_variables"]["tier"] == "Enterprise"
    assert res_data["user_id"] == user["id"]

    # 2. Get Contact by ID
    get_resp = client.get(f"/api/contacts/{contact_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == contact_id

    # 3. List Contacts
    list_resp = client.get("/api/contacts", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] == 1
    assert list_data["contacts"][0]["id"] == contact_id

    # 4. Update Contact
    update_resp = client.patch(
        f"/api/contacts/{contact_id}",
        json={"role": "Chairman & CEO", "company": "Wayne Global"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["role"] == "Chairman & CEO"
    assert updated_data["company"] == "Wayne Global"
    assert updated_data["name"] == "Bruce Wayne"

    # 5. Delete Contact
    del_resp = client.delete(f"/api/contacts/{contact_id}", headers=headers)
    assert del_resp.status_code == 204

    # 6. Verify Deletion
    get_del_resp = client.get(f"/api/contacts/{contact_id}", headers=headers)
    assert get_del_resp.status_code == 404

    list_after_del = client.get("/api/contacts", headers=headers)
    assert list_after_del.status_code == 200
    assert list_after_del.json()["total"] == 0


def test_contact_tenant_isolation(client: TestClient, db):
    # Setup User A and User B
    user_a, headers_a = create_authenticated_user(client)
    user_b, headers_b = create_authenticated_user(client)

    # User A creates a contact
    create_resp = client.post(
        "/api/contacts",
        json={
            "name": "Secret Contact A",
            "email": "secret.a@example.com",
            "company": "Company A",
        },
        headers=headers_a,
    )
    assert create_resp.status_code == 201
    contact_a_id = create_resp.json()["id"]

    # User B must NOT see User A's contact in their list
    list_b_resp = client.get("/api/contacts", headers=headers_b)
    assert list_b_resp.status_code == 200
    assert list_b_resp.json()["total"] == 0

    # User B must NOT be able to get User A's contact
    get_b_resp = client.get(f"/api/contacts/{contact_a_id}", headers=headers_b)
    assert get_b_resp.status_code == 404

    # User B must NOT be able to update User A's contact
    patch_b_resp = client.patch(
        f"/api/contacts/{contact_a_id}",
        json={"name": "Hacked Name"},
        headers=headers_b,
    )
    assert patch_b_resp.status_code == 404

    # User B must NOT be able to delete User A's contact
    del_b_resp = client.delete(f"/api/contacts/{contact_a_id}", headers=headers_b)
    assert del_b_resp.status_code == 404

    # User A's contact must still exist untouched
    verify_resp = client.get(f"/api/contacts/{contact_a_id}", headers=headers_a)
    assert verify_resp.status_code == 200
    assert verify_resp.json()["name"] == "Secret Contact A"


def test_unauthorized_access(client: TestClient):
    # No auth header -> 401
    resp = client.get("/api/contacts")
    assert resp.status_code == 401

    resp_create = client.post(
        "/api/contacts",
        json={"name": "Anonymous", "email": "anon@example.com"},
    )
    assert resp_create.status_code == 401


def test_mock_contacts_import(client: TestClient, db):
    user, headers = create_authenticated_user(client)

    # Call import-mock endpoint
    import_resp = client.post("/api/contacts/import-mock", headers=headers)
    assert import_resp.status_code == 200
    import_data = import_resp.json()

    assert import_data["imported"] >= 4
    assert import_data["source"] == "mock"

    # Verify contacts exist in user's list
    list_resp = client.get("/api/contacts", headers=headers)
    assert list_resp.status_code == 200
    contacts = list_resp.json()["contacts"]
    assert len(contacts) >= 4

    names = [c["name"] for c in contacts]
    assert "Sarah Connor" in names
    assert "Alexander Wright" in names

    # Re-running mock import should update rather than duplicate
    reimport_resp = client.post("/api/contacts/import-mock", headers=headers)
    assert reimport_resp.status_code == 200
    list_resp_again = client.get("/api/contacts", headers=headers)
    assert list_resp_again.json()["total"] == len(contacts)


def test_csv_contacts_import(client: TestClient, db):
    user, headers = create_authenticated_user(client)

    csv_payload = (
        "name,email,company,role\n"
        "Diana Prince,diana@themyscira.example.com,Themyscira Embassy,Ambassador\n"
        "Barry Allen,barry@centralcitypd.example.com,CCPD,Forensic Scientist\n"
    )

    files = {"file": ("contacts.csv", csv_payload.encode("utf-8"), "text/csv")}
    resp = client.post("/api/contacts/import-csv", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 2
    assert data["source"] == "csv"

    # Verify contacts in database
    list_resp = client.get("/api/contacts", headers=headers)
    assert list_resp.status_code == 200
    contacts = list_resp.json()["contacts"]
    assert len(contacts) == 2
    names = [c["name"] for c in contacts]
    assert "Diana Prince" in names
    assert "Barry Allen" in names

