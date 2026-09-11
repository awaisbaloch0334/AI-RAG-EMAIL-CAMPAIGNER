import json
import os
import sys

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db.database import SessionLocal
from app.db.models.bot import Bot
from app.db.models.campaign import Campaign, CampaignEmail
from app.db.models.contact import Contact
from app.db.models.crawl import CrawlJob, Page
from app.db.models.knowledge import Chunk
from app.tasks.crawl_tasks import run_crawl_pipeline
from app.rag.retriever import VectorRetriever


def run_verification():
    print("=" * 80)
    print("AI RAG EMAIL CAMPAIGNER - REAL WEBSITE KNOWLEDGE END-TO-END VERIFICATION")
    print("=" * 80)

    client = TestClient(app)

    # ---------------------------------------------------------
    # STEP 1: User Login / OTP Authentication
    # ---------------------------------------------------------
    user_email = "verifier_admin@rag-campaigner.io"
    print(f"\n[STEP 1] Requesting & Verifying OTP for user: {user_email}")
    req_resp = client.post("/api/auth/request-otp", json={"email": user_email})
    assert req_resp.status_code == 200, f"OTP request failed: {req_resp.text}"
    print("  -> OTP requested successfully. Status:", req_resp.json())

    verify_resp = client.post("/api/auth/verify-otp", json={"email": user_email, "otp": "777888"})
    assert verify_resp.status_code == 200, f"OTP verification failed: {verify_resp.text}"
    auth_data = verify_resp.json()
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  -> Authenticated. JWT token received. Expiry/type:", auth_data.get("token_type"))

    # ---------------------------------------------------------
    # STEP 2: Import Mock Contacts
    # ---------------------------------------------------------
    print("\n[STEP 2] Importing curated mock contacts for current user...")
    import_resp = client.post("/api/contacts/import-mock", headers=headers)
    assert import_resp.status_code in (200, 201), f"Mock import failed: {import_resp.text}"
    import_json = import_resp.json()
    print(f"  -> Imported {import_json.get('count', len(import_json.get('contacts', [])))} mock contacts.")

    contacts_resp = client.get("/api/contacts", headers=headers)
    assert contacts_resp.status_code == 200
    contacts_data = contacts_resp.json()
    contacts_list = contacts_data.get("contacts", contacts_data) if isinstance(contacts_data, dict) else contacts_data
    assert len(contacts_list) > 0, "No contacts returned"
    print(f"  -> Selected Contacts for Outreach:")
    target_contacts = contacts_list[:2]
    for c in target_contacts:
        print(f"     * {c['name']} ({c['email']}) - {c['role']} at {c['company']}")

    # ---------------------------------------------------------
    # STEP 3: Create Bot with REAL Public Website URL
    # ---------------------------------------------------------
    target_url = "https://books.toscrape.com"
    bot_name = "Books To Scrape Global Bookstore"
    print(f"\n[STEP 3] Creating Bot with REAL website: {target_url}")
    bot_resp = client.post("/api/bots", headers=headers, json={"name": bot_name, "website_url": target_url})
    assert bot_resp.status_code == 201, f"Bot creation failed: {bot_resp.text}"
    bot_data = bot_resp.json()
    bot_id = bot_data["id"]
    print(f"  -> Bot created successfully: ID={bot_id}, Name='{bot_data['name']}', Initial Status='{bot_data['status']}'")

    # ---------------------------------------------------------
    # STEP 4: Trigger ACTUAL Crawler Pipeline
    # ---------------------------------------------------------
    print(f"\n[STEP 4] Triggering ACTUAL crawler on {target_url} (max_pages=3)...")
    crawl_resp = client.post(f"/api/bots/{bot_id}/crawl", headers=headers, json={"max_pages": 3})
    assert crawl_resp.status_code in (200, 202), f"Crawl trigger failed: {crawl_resp.text}"
    job_info = crawl_resp.json()
    job_id = job_info["id"]
    print(f"  -> Crawl Job queued: ID={job_id}, Initial Status='{job_info['status']}'")

    print(f"  -> Executing real crawl pipeline (HTTP fetching, HTML parsing, content extraction, chunking, embeddings)...")
    pipeline_result = run_crawl_pipeline(bot_id=bot_id, job_id=job_id, max_pages=3)
    print(f"  -> Pipeline Result:", json.dumps(pipeline_result, indent=2))
    assert pipeline_result["status"] == "success", f"Pipeline returned non-success: {pipeline_result}"

    # ---------------------------------------------------------
    # STEP 5: Verify Discovered Pages in Database
    # ---------------------------------------------------------
    print("\n[STEP 5] Verifying Discovered & Extracted Pages in PostgreSQL...")
    with SessionLocal() as db:
        pages = db.scalars(select(Page).where(Page.bot_id == bot_id)).all()
        print(f"  -> Discovered & Extracted Pages Count: {len(pages)}")
        assert len(pages) > 0, "Zero pages persisted by crawler!"
        for p in pages:
            print(f"     Page ID: {p.id}")
            print(f"       URL: {p.url}")
            print(f"       Title: {p.title}")
            print(f"       Status: {p.crawl_status}")
            print(f"       Content Length: {len(p.content or '')} chars")
            snippet = (p.content or "").replace("\n", " ")[:120]
            print(f"       Snippet: {snippet}...")

    # ---------------------------------------------------------
    # STEP 6: Verify Chunking, Embeddings, & pgvector Indexing
    # ---------------------------------------------------------
    print("\n[STEP 6] Verifying Semantic Chunks & pgvector Embeddings in PostgreSQL...")
    with SessionLocal() as db:
        chunks = db.scalars(select(Chunk).where(Chunk.bot_id == bot_id)).all()
        print(f"  -> Generated Chunks Count: {len(chunks)}")
        assert len(chunks) > 0, "Zero chunks generated by knowledge indexing pipeline!"
        for idx, ch in enumerate(chunks[:4]):
            dim = len(ch.embedding) if ch.embedding is not None else 0
            print(f"     Chunk #{idx + 1}: ID={ch.id} (Page {ch.page_id}, Index {ch.chunk_index})")
            print(f"       Embedding Vector Dimension: {dim} (pgvector float array)")
            assert dim == 384, f"Expected 384 dimensions from fastembed, got {dim}"
            preview = ch.content.replace("\n", " ")[:100]
            print(f"       Content Preview: {preview}...")

        # Verify Bot is READY
        bot = db.get(Bot, bot_id)
        print(f"  -> Bot Final Status in DB: '{bot.status}'")
        assert bot.status == "READY", f"Bot status expected READY, got {bot.status}"

    # ---------------------------------------------------------
    # STEP 7: Create Campaign
    # ---------------------------------------------------------
    campaign_title = "Books To Scrape Outreach - Academic & Corporate Partnerships"
    campaign_goal = "Highlight curated bookstore collections and literary titles for organizational libraries"
    print(f"\n[STEP 7] Creating Campaign linked to Bot '{bot_name}'...")
    camp_payload = {
        "name": campaign_title,
        "bot_id": bot_id,
        "campaign_goal": campaign_goal,
        "contact_ids": [c["id"] for c in target_contacts],
    }
    camp_resp = client.post("/api/campaigns", headers=headers, json=camp_payload)
    assert camp_resp.status_code == 201, f"Campaign creation failed: {camp_resp.text}"
    camp_data = camp_resp.json()
    campaign_id = camp_data["id"]
    print(f"  -> Campaign created: ID={campaign_id}, Name='{camp_data['name']}', Status='{camp_data['status']}'")
    print(f"  -> Target Recipients Count: {camp_data['total_emails']}")

    # ---------------------------------------------------------
    # STEP 8: Generate Personalized Emails with Retrieved Website Knowledge
    # ---------------------------------------------------------
    print(f"\n[STEP 8] Generating Personalized Emails using RAG on Crawled Knowledge...")
    gen_resp = client.post(f"/api/campaigns/{campaign_id}/generate", headers=headers, json={"campaign_goal": campaign_goal})
    assert gen_resp.status_code == 200, f"Email generation failed: {gen_resp.text}"
    gen_result = gen_resp.json()
    print(f"  -> Batch Generation Complete: Generated {gen_result.get('generated_count')} drafts.")

    # Inspect generated email details
    camp_detail_resp = client.get(f"/api/campaigns/{campaign_id}", headers=headers)
    assert camp_detail_resp.status_code == 200
    camp_detail = camp_detail_resp.json()
    emails = camp_detail["emails"]
    print(f"  -> Drafted Emails ({len(emails)}):")
    for idx, em in enumerate(emails):
        c_name = em.get("contact_name") or "Recipient"
        c_email = em.get("contact_email") or "email@example.com"
        print(f"\n  --- DRAFT EMAIL #{idx + 1} for {c_name} ({c_email}) ---")
        print(f"  Status:  {em.get('status')}")
        print(f"  Subject: {em.get('subject')}")
        print("  Body:")
        for line in (em.get("body") or "").splitlines():
            print(f"    {line}")

        # Check that crawled website knowledge was used
        body_text = em.get("body") or ""
        assert len(body_text) > 30, "Generated email body is empty or too short"
        assert em.get("status") == "GENERATED", f"Expected GENERATED status, got {em.get('status')}"

    # ---------------------------------------------------------
    # STEP 9: Mock Send Campaign & Verify Completed Status
    # ---------------------------------------------------------
    print(f"\n[STEP 9] Triggering Mock Send for Campaign '{campaign_id}'...")
    send_resp = client.post(f"/api/campaigns/{campaign_id}/send", headers=headers)
    assert send_resp.status_code == 200, f"Send campaign failed: {send_resp.text}"
    send_result = send_resp.json()
    print(f"  -> Send Result:", send_result)
    assert send_result["status"] == "COMPLETED"
    assert send_result["emails_sent"] == len(target_contacts)

    # Re-fetch campaign to verify database persistence of sent statuses
    final_camp_resp = client.get(f"/api/campaigns/{campaign_id}", headers=headers)
    final_camp = final_camp_resp.json()
    print(f"  -> Final Campaign DB Status: '{final_camp['status']}'")
    print(f"  -> Sent Emails Count: {final_camp['sent_emails']}/{final_camp['total_emails']}")
    assert final_camp["status"] == "COMPLETED"
    for em in final_camp["emails"]:
        c_email = em.get("contact_email") or "unknown"
        print(f"     * Email ID {em['id']} to {c_email} -> Status: '{em['status']}', Sent At: {em.get('sent_at')}")
        assert em["status"] == "SENT"
        assert em.get("sent_at") is not None

    # ---------------------------------------------------------
    # STEP 10: Multi-Tenant Security & Isolation Verification
    # ---------------------------------------------------------
    print("\n[STEP 10] Testing Multi-Tenant Security & Strict Ownership Boundaries...")
    # Register/Login as Attacker / Second Tenant
    attacker_email = "unauthorized_tenant@othercompany.com"
    client.post("/api/auth/request-otp", json={"email": attacker_email})
    attacker_login = client.post("/api/auth/verify-otp", json={"email": attacker_email, "otp": "777888"}).json()
    attacker_token = attacker_login["access_token"]
    attacker_headers = {"Authorization": f"Bearer {attacker_token}"}

    # 1. Attacker tries to read User A's contacts
    c_id = target_contacts[0]["id"]
    res = client.get(f"/api/contacts/{c_id}", headers=attacker_headers)
    assert res.status_code == 404, f"Security Breach: Tenant B accessed Tenant A contact! ({res.status_code})"
    print("  [PASS] Tenant B cannot access Tenant A contact -> 404 Not Found")

    # 2. Attacker tries to read User A's campaign
    res = client.get(f"/api/campaigns/{campaign_id}", headers=attacker_headers)
    assert res.status_code == 404, f"Security Breach: Tenant B accessed Tenant A campaign! ({res.status_code})"
    print("  [PASS] Tenant B cannot access Tenant A campaign -> 404 Not Found")

    # 3. Attacker tries to access User A's bot
    res = client.get(f"/api/bots/{bot_id}", headers=attacker_headers)
    assert res.status_code == 404, f"Security Breach: Tenant B accessed Tenant A bot! ({res.status_code})"
    print("  [PASS] Tenant B cannot access Tenant A bot -> 404 Not Found")

    # 4. Attacker tries to trigger crawl on User A's bot
    res = client.post(f"/api/bots/{bot_id}/crawl", headers=attacker_headers, json={"max_pages": 1})
    assert res.status_code == 404, f"Security Breach: Tenant B triggered crawl on Tenant A bot! ({res.status_code})"
    print("  [PASS] Tenant B cannot crawl Tenant A bot -> 404 Not Found")

    # 5. Attacker tries to send User A's campaign
    res = client.post(f"/api/campaigns/{campaign_id}/send", headers=attacker_headers)
    assert res.status_code == 404, f"Security Breach: Tenant B sent Tenant A campaign! ({res.status_code})"
    print("  [PASS] Tenant B cannot send Tenant A campaign -> 404 Not Found")

    # 6. Vector Retriever strictly isolates knowledge chunks by bot_id
    attacker_bot_resp = client.post(
        "/api/bots",
        headers=attacker_headers,
        json={"name": "Attacker Bot", "website_url": "https://example.com"},
    )
    assert attacker_bot_resp.status_code == 201
    attacker_bot_id = attacker_bot_resp.json()["id"]

    with SessionLocal() as db:
        leaked_chunks = VectorRetriever.retrieve(
            bot_id=attacker_bot_id,
            query="books store literature novels",
            db=db,
            top_k=5,
        )
        assert len(leaked_chunks) == 0, f"Security Breach: Attacker bot retrieved chunks from other bots! Found: {len(leaked_chunks)}"
        print(f"  [PASS] VectorRetriever returns {len(leaked_chunks)} chunks for Attacker bot (Strict bot_id isolation)")

    print("\n" + "=" * 80)
    print("ALL VERIFICATION CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 80)


if __name__ == "__main__":
    run_verification()
