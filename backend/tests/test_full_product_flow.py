import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.security import create_access_token
from app.db.database import SessionLocal
from app.db.models import Bot, Campaign, CampaignEmail, Chunk, Contact, User
from app.embeddings.service import EmbeddingService
from app.main import app
from app.services.mail import get_last_sent_otp_for_test


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


def test_full_product_end_to_end_journey(client: TestClient, db: Session):
    # 1. User Registration & Real OTP Dispatch
    suffix = uuid.uuid4().hex[:6]
    email = f"lead_gen_{suffix}@example.com"
    pwd = "EnterprisePassword123!"

    reg_resp = client.post("/api/auth/register", json={"email": email, "password": pwd})
    assert reg_resp.status_code == 201
    assert "demo_otp" not in reg_resp.json()

    # 2. Verify OTP & Authenticate
    otp = get_last_sent_otp_for_test(email)
    assert otp is not None
    assert len(otp) == 6

    verify_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": otp})
    assert verify_resp.status_code == 200
    token = verify_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify single-use OTP invalidation
    replay_resp = client.post("/api/auth/verify-otp", json={"email": email, "otp": otp})
    assert replay_resp.status_code == 400

    # 3. Lead Source A: Real CSV Upload
    csv_content = (
        "name,email,company,role\n"
        f"Dr. Jennifer Hayes,jennifer_{suffix}@healthpartners.org,Health Partners,Chief Medical Officer\n"
        f"Marcus Vance,marcus_{suffix}@biovance.com,BioVance Health,VP Operations\n"
    )
    csv_file = io.BytesIO(csv_content.encode("utf-8"))
    csv_resp = client.post(
        "/api/contacts/import-csv",
        files={"file": ("leads.csv", csv_file, "text/csv")},
        headers=headers,
    )
    assert csv_resp.status_code == 200
    assert csv_resp.json()["imported"] == 2

    # 4. Lead Source B: Labeled HubSpot Demo Connection
    hs_resp = client.post("/api/contacts/import-hubspot", headers=headers)
    assert hs_resp.status_code == 200
    assert hs_resp.json()["imported"] >= 1
    assert hs_resp.json()["source"] == "hubspot_demo"

    contacts_list = client.get("/api/contacts", headers=headers).json()
    assert contacts_list["total"] >= 3
    all_contacts = contacts_list["contacts"]
    c1 = all_contacts[0]
    c2 = all_contacts[1]

    # 5. Website Knowledge Source & pgvector Indexing
    bot_resp = client.post(
        "/api/bots",
        json={"name": "BioVance AI Healthcare", "website_url": "https://biovance.example.com"},
        headers=headers,
    )
    assert bot_resp.status_code == 201
    bot_id = bot_resp.json()["id"]

    embed_svc = EmbeddingService()
    text = (
        "BioVance Health delivers HIPAA-compliant clinical workflow automation, "
        "AI-assisted diagnostics, and hospital EHR synchronization reducing administrative overhead by 40%."
    )
    embedding = embed_svc.embed_query(text)
    chunk = Chunk(
        bot_id=bot_id,
        content=text,
        embedding=embedding,
        chunk_index=0,
        chunk_metadata={"title": "BioVance Clinical Platform", "url": "https://biovance.example.com/platform"},
    )
    db.add(chunk)
    bot = db.get(Bot, bot_id)
    bot.status = "READY"
    db.commit()

    # 6. Verify Pages Endpoint & Alias
    pages_resp = client.get(f"/api/bots/{bot_id}/pages", headers=headers)
    assert pages_resp.status_code == 200

    pages_alias_resp = client.get(f"/api/bots/{bot_id}/knowledge/pages", headers=headers)
    assert pages_alias_resp.status_code == 200

    # 7. Create Campaign & Audience Selection
    camp_resp = client.post(
        "/api/campaigns",
        json={
            "name": "Q4 Clinical Automation Partnership",
            "bot_id": bot_id,
            "contact_ids": [c1["id"], c2["id"]],
            "campaign_goal": "Present HIPAA-compliant workflow automation and reduce administrative burden",
        },
        headers=headers,
    )
    assert camp_resp.status_code == 201
    camp = camp_resp.json()
    camp_id = camp["id"]
    assert len(camp["emails"]) == 2

    # 8. Generate Personalized RAG Emails
    gen_resp = client.post(
        f"/api/campaigns/{camp_id}/generate",
        json={"campaign_goal": "Present HIPAA-compliant workflow automation and reduce administrative burden"},
        headers=headers,
    )
    assert gen_resp.status_code == 200
    gen_camp = gen_resp.json()
    assert gen_camp["status"] == "READY"
    assert len(gen_camp["emails"]) == 2
    for em in gen_camp["emails"]:
        assert em["subject"] is not None and len(em["subject"]) > 5
        assert em["body"] is not None and len(em["body"]) > 20

    e1 = gen_camp["emails"][0]

    # 9. Single Email Review & Individual Draft Editing
    custom_subject = f"Priority partnership for {c1['company'] or 'your team'}"
    custom_body = f"Hi {c1['name']},\n\nI reviewed your operations and wanted to personally share our clinical automation report."

    upd_resp = client.put(
        f"/api/campaigns/{camp_id}/emails/{e1['id']}",
        json={"subject": custom_subject, "body": custom_body},
        headers=headers,
    )
    assert upd_resp.status_code == 200
    upd_camp = upd_resp.json()
    e1_updated = next(e for e in upd_camp["emails"] if e["id"] == e1["id"])
    assert e1_updated["subject"] == custom_subject
    assert e1_updated["body"] == custom_body

    # 10. Template Propagation across ALL Campaign Emails
    template_subject = "Transforming clinical operations at {{company}}"
    template_body = "Hi {{first_name}},\n\nWe would love to introduce our AI automation platform to {{company}}."

    apply_resp = client.post(
        f"/api/campaigns/{camp_id}/emails/apply-all",
        json={
            "subject_template": template_subject,
            "body_template": template_body,
            "source_contact_id": c1["id"],
        },
        headers=headers,
    )
    assert apply_resp.status_code == 200
    applied_camp = apply_resp.json()

    for em in applied_camp["emails"]:
        assert "{{company}}" not in em["subject"]
        assert "{{first_name}}" not in em["body"]
        assert "{{company}}" not in em["body"]
        assert "Transforming clinical operations at" in em["subject"]
        assert "We would love to introduce our AI automation platform to" in em["body"]

    # 11. Explicit User Approval & Campaign Send
    send_resp = client.post(f"/api/campaigns/{camp_id}/send", headers=headers)
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["status"] == "COMPLETED"
    assert send_data["emails_sent"] == 2

    # 12. Verify Database State
    final_camp = db.get(Campaign, camp_id)
    assert final_camp.status == "COMPLETED"
    for email_rec in final_camp.campaign_emails:
        assert email_rec.status == "SENT"
        assert email_rec.sent_at is not None

    # 13. Verify Dashboard Endpoint & Anti-Cache Headers
    dash_resp = client.get("/dashboard")
    assert dash_resp.status_code == 200
    assert "no-cache" in dash_resp.headers.get("cache-control", "").lower()
    html = dash_resp.text
    assert "STEP 5: REVIEW & PERSONALIZE" in html
    assert "Apply Changes to All Emails" in html
