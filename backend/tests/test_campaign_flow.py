import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Bot, Campaign, CampaignEmail, Chunk, Contact
from app.embeddings.service import EmbeddingService
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
    email = f"camp_flow_{suffix}@example.com"
    password = "SecurePassword123!"

    client.post("/api/auth/register", json={"email": email, "password": password})
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return login.json(), headers


def test_complete_campaign_flow(client: TestClient, db: Session):
    user, headers = create_authenticated_user(client)

    # 1. Create a Bot (Knowledge Source)
    bot_resp = client.post(
        "/api/bots",
        json={"name": "CloudNova Enterprise", "website_url": "https://cloudnova.example.com"},
        headers=headers,
    )
    assert bot_resp.status_code == 201
    bot_id = bot_resp.json()["id"]

    # 2. Seed knowledge chunk
    chunk_text = "CloudNova automates multi-cloud disaster recovery with zero data loss."
    chunk = Chunk(
        bot_id=bot_id,
        content=chunk_text,
        embedding=EmbeddingService.embed_query(chunk_text),
        chunk_index=0,
        chunk_metadata={"source_url": "https://cloudnova.example.com/dr", "page_title": "Disaster Recovery"},
    )
    db.add(chunk)
    db.commit()

    # 3. Create two Contacts
    c1_resp = client.post(
        "/api/contacts",
        json={
            "name": "David Wallace",
            "first_name": "David",
            "email": "dwallace@dundermifflin.example.com",
            "company": "Dunder Mifflin",
            "role": "CFO",
            "custom_variables": {"interest": "Disaster Recovery"},
        },
        headers=headers,
    )
    c2_resp = client.post(
        "/api/contacts",
        json={
            "name": "Jim Halpert",
            "first_name": "Jim",
            "email": "jhalpert@dundermifflin.example.com",
            "company": "Athlead",
            "role": "Marketing VP",
        },
        headers=headers,
    )
    c1_id = c1_resp.json()["id"]
    c2_id = c2_resp.json()["id"]

    # 4. Create Campaign with initial contact c1
    camp_create_resp = client.post(
        "/api/campaigns",
        json={
            "name": "Q4 Enterprise DR Outreach",
            "bot_id": bot_id,
            "contact_ids": [c1_id],
            "campaign_goal": "Demonstrate zero data loss recovery",
        },
        headers=headers,
    )
    assert camp_create_resp.status_code == 201, camp_create_resp.text
    camp_data = camp_create_resp.json()
    campaign_id = camp_data["id"]

    assert camp_data["status"] == "DRAFT"
    assert camp_data["total_emails"] == 1
    assert camp_data["sent_emails"] == 0
    assert len(camp_data["emails"]) == 1
    assert camp_data["emails"][0]["contact_id"] == c1_id
    assert camp_data["emails"][0]["status"] == "PENDING"

    # 5. Attach contact c2 to existing campaign
    attach_resp = client.post(
        f"/api/campaigns/{campaign_id}/contacts",
        json={"contact_ids": [c2_id]},
        headers=headers,
    )
    assert attach_resp.status_code == 200
    assert attach_resp.json()["total_emails"] == 2

    # 6. Generate Emails for all contacts in Campaign
    gen_resp = client.post(
        f"/api/campaigns/{campaign_id}/generate",
        json={"campaign_goal": "Disaster recovery cost optimization"},
        headers=headers,
    )
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()

    assert gen_data["status"] == "READY"
    assert gen_data["total_emails"] == 2
    for email_draft in gen_data["emails"]:
        assert email_draft["status"] == "GENERATED"
        assert email_draft["subject"] is not None and len(email_draft["subject"]) > 0
        assert email_draft["body"] is not None and len(email_draft["body"]) > 0

    # 7. Mock Send Campaign
    send_resp = client.post(f"/api/campaigns/{campaign_id}/send", headers=headers)
    assert send_resp.status_code == 200
    send_result = send_resp.json()

    assert send_result["status"] == "COMPLETED"
    assert send_result["emails_sent"] == 2

    # 8. Verify campaign state in detail query
    detail_resp = client.get(f"/api/campaigns/{campaign_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "COMPLETED"
    assert detail["sent_emails"] == 2

    for email_record in detail["emails"]:
        assert email_record["status"] == "SENT"
        assert email_record["sent_at"] is not None

    # 9. List Campaigns
    list_resp = client.get("/api/campaigns", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["campaigns"][0]["id"] == campaign_id


def test_campaign_multi_tenant_isolation(client: TestClient, db: Session):
    # Setup User A and User B
    user_a, headers_a = create_authenticated_user(client)
    user_b, headers_b = create_authenticated_user(client)

    # User A creates Bot A, Contact A, Campaign A
    bot_a = client.post(
        "/api/bots",
        json={"name": "Bot Alpha", "website_url": "https://alpha.example.com"},
        headers=headers_a,
    ).json()["id"]

    contact_a = client.post(
        "/api/contacts",
        json={"name": "Contact Alpha", "email": "alpha@example.com"},
        headers=headers_a,
    ).json()["id"]

    camp_a = client.post(
        "/api/campaigns",
        json={"name": "Campaign Alpha", "bot_id": bot_a, "contact_ids": [contact_a]},
        headers=headers_a,
    ).json()["id"]

    # User B creates Bot B and Contact B
    bot_b = client.post(
        "/api/bots",
        json={"name": "Bot Beta", "website_url": "https://beta.example.com"},
        headers=headers_b,
    ).json()["id"]

    contact_b = client.post(
        "/api/contacts",
        json={"name": "Contact Beta", "email": "beta@example.com"},
        headers=headers_b,
    ).json()["id"]

    # 1. User B cannot access User A's campaign
    assert client.get(f"/api/campaigns/{camp_a}", headers=headers_b).status_code == 404

    # 2. User B cannot see User A's campaign in their list
    b_list = client.get("/api/campaigns", headers=headers_b).json()
    assert b_list["total"] == 0

    # 3. User B cannot add contacts to User A's campaign
    assert (
        client.post(
            f"/api/campaigns/{camp_a}/contacts",
            json={"contact_ids": [contact_b]},
            headers=headers_b,
        ).status_code
        == 404
    )

    # 4. User B cannot trigger email generation for User A's campaign
    assert client.post(f"/api/campaigns/{camp_a}/generate", json={}, headers=headers_b).status_code == 404

    # 5. User B cannot send User A's campaign
    assert client.post(f"/api/campaigns/{camp_a}/send", headers=headers_b).status_code == 404

    # 6. User B cannot delete User A's campaign
    assert client.delete(f"/api/campaigns/{camp_a}", headers=headers_b).status_code == 404

    # 7. User A cannot create a campaign referencing User B's Bot
    fail_create = client.post(
        "/api/campaigns",
        json={"name": "Unauthorized Bot Link", "bot_id": bot_b},
        headers=headers_a,
    )
    assert fail_create.status_code == 404

    # 8. User A cannot add User B's Contact to User A's Campaign
    fail_attach = client.post(
        f"/api/campaigns/{camp_a}/contacts",
        json={"contact_ids": [contact_b]},
        headers=headers_a,
    )
    assert fail_attach.status_code == 404


def test_campaign_deletion_cascade(client: TestClient, db: Session):
    _, headers = create_authenticated_user(client)

    bot_id = client.post(
        "/api/bots",
        json={"name": "Cascade Bot", "website_url": "https://cascade.example.com"},
        headers=headers,
    ).json()["id"]

    contact_id = client.post(
        "/api/contacts",
        json={"name": "Cascade Contact", "email": "cascade@example.com"},
        headers=headers,
    ).json()["id"]

    camp_id = client.post(
        "/api/campaigns",
        json={"name": "Campaign to Delete", "bot_id": bot_id, "contact_ids": [contact_id]},
        headers=headers,
    ).json()["id"]

    # Verify Campaign and CampaignEmail exist in DB
    assert db.get(Campaign, camp_id) is not None
    assert db.get(Contact, contact_id) is not None
    assert db.get(Bot, bot_id) is not None

    # Delete Campaign
    del_resp = client.delete(f"/api/campaigns/{camp_id}", headers=headers)
    assert del_resp.status_code == 204

    # Campaign is gone from DB, but Contact and Bot remain
    assert db.get(Campaign, camp_id) is None
    assert db.get(Contact, contact_id) is not None
    assert db.get(Bot, bot_id) is not None


def test_update_and_apply_all_campaign_emails(client: TestClient, db: Session):
    _, headers = create_authenticated_user(client)

    bot_id = client.post(
        "/api/bots",
        json={"name": "Outreach Bot", "website_url": "https://outreach.example.com"},
        headers=headers,
    ).json()["id"]

    c1 = client.post(
        "/api/contacts",
        json={"name": "Alice Wonderland", "email": "alice@wonder.com", "company": "Wonder Corp", "role": "Director"},
        headers=headers,
    ).json()["id"]

    c2 = client.post(
        "/api/contacts",
        json={"name": "Bob Builder", "email": "bob@build.com", "company": "Build Inc", "role": "Manager"},
        headers=headers,
    ).json()["id"]

    camp = client.post(
        "/api/campaigns",
        json={"name": "Template Test", "bot_id": bot_id, "contact_ids": [c1, c2]},
        headers=headers,
    ).json()
    camp_id = camp["id"]
    email_1 = camp["emails"][0]

    # 1. Update single email draft
    upd_resp = client.put(
        f"/api/campaigns/{camp_id}/emails/{email_1['id']}",
        json={"subject": "Custom subject for Alice", "body": "Hi Alice, custom personal note."},
        headers=headers,
    )
    assert upd_resp.status_code == 200
    updated_camp = upd_resp.json()
    e1_updated = next(e for e in updated_camp["emails"] if e["id"] == email_1["id"])
    assert e1_updated["subject"] == "Custom subject for Alice"
    assert e1_updated["body"] == "Hi Alice, custom personal note."

    # 2. Apply template across all emails
    apply_resp = client.post(
        f"/api/campaigns/{camp_id}/emails/apply-all",
        json={
            "subject_template": "Special opportunity for {{company}}",
            "body_template": "Hello {{name}}, we are excited to partner with {{company}}!",
            "source_contact_id": c1,
        },
        headers=headers,
    )
    assert apply_resp.status_code == 200
    applied_camp = apply_resp.json()

    alice_email = next(e for e in applied_camp["emails"] if e["contact_id"] == c1)
    bob_email = next(e for e in applied_camp["emails"] if e["contact_id"] == c2)

    assert alice_email["subject"] == "Special opportunity for Wonder Corp"
    assert "Hello Alice Wonderland, we are excited to partner with Wonder Corp!" in alice_email["body"]

    assert bob_email["subject"] == "Special opportunity for Build Inc"
    assert "Hello Bob Builder, we are excited to partner with Build Inc!" in bob_email["body"]


