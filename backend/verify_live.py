import requests
import uuid

BASE = "http://localhost:8000"

def run_live_verification():
    print("=" * 60)
    print("LIVE END-TO-END VERIFICATION ON RUNNING SERVER")
    print("=" * 60)

    # 1. User Register & Login
    suffix = uuid.uuid4().hex[:6]
    email = f"live_verify_{suffix}@example.com"
    pwd = "EnterprisePassword123!"

    print(f"[1] Registering user: {email}...")
    reg = requests.post(f"{BASE}/api/auth/register", json={"email": email, "password": pwd})
    assert reg.status_code == 201, f"Register failed: {reg.text}"
    print("    -> User registered successfully (201).")

    print("[2] Logging in...")
    login_res = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("    -> JWT token received.")

    # 2. Import Contacts
    print("[3] Importing sample leads (mock CRM)...")
    mock_res = requests.post(f"{BASE}/api/contacts/import-mock", headers=headers)
    assert mock_res.status_code == 200, mock_res.text
    contacts = mock_res.json()["contacts"]
    assert len(contacts) >= 2
    c1, c2 = contacts[0], contacts[1]
    print(f"    -> Imported {len(contacts)} contacts. Selected: {c1['name']} ({c1['company']}) and {c2['name']} ({c2['company']}).")

    # 3. Create Bot & Verify Knowledge alias
    print("[4] Creating Knowledge Bot & testing knowledge alias...")
    bot_res = requests.post(f"{BASE}/api/bots", json={"name": "Live Verification Bot", "website_url": "https://example.com"}, headers=headers)
    assert bot_res.status_code == 201, bot_res.text
    bot_id = bot_res.json()["id"]

    pages_res = requests.get(f"{BASE}/api/bots/{bot_id}/knowledge/pages", headers=headers)
    assert pages_res.status_code == 200, pages_res.text
    print("    -> /knowledge/pages endpoint returned 200 OK.")

    # 4. Create Campaign
    print("[5] Creating campaign with 2 recipients...")
    camp_res = requests.post(f"{BASE}/api/campaigns", json={
        "name": "Live Test Partnership Campaign",
        "bot_id": bot_id,
        "contact_ids": [c1["id"], c2["id"]],
        "campaign_goal": "Schedule a product demo and clinical workflow overview",
    }, headers=headers)
    assert camp_res.status_code == 201, camp_res.text
    camp_id = camp_res.json()["id"]
    print(f"    -> Campaign created: {camp_id}")

    # 5. Generate Emails
    print("[6] Generating personalized RAG email drafts...")
    gen_res = requests.post(f"{BASE}/api/campaigns/{camp_id}/generate", json={"campaign_goal": "Schedule a product demo"}, headers=headers)
    assert gen_res.status_code == 200, gen_res.text
    emails = gen_res.json()["emails"]
    assert len(emails) == 2
    e1 = emails[0]
    safe_subj = e1["subject"].encode("ascii", "replace").decode("ascii")
    print(f"    -> Generated drafts. Draft 1 subject: '{safe_subj}'")

    # 6. Single Email Edit (Save this email)
    print(f"[7] Editing draft for individual contact: {c1['name']}...")
    custom_sub = f"Personalized proposal for {c1['company']}"
    custom_body = f"Hello {c1['name']},\n\nI customized this specifically for your team at {c1['company']}."
    upd_res = requests.put(f"{BASE}/api/campaigns/{camp_id}/emails/{e1['id']}", json={
        "subject": custom_sub,
        "body": custom_body,
    }, headers=headers)
    assert upd_res.status_code == 200, upd_res.text
    e1_updated = [e for e in upd_res.json()["emails"] if e["id"] == e1["id"]][0]
    assert e1_updated["subject"] == custom_sub
    print(f"    -> Successfully saved individual email edit: '{e1_updated['subject']}'")

    # 7. Apply Changes to All Emails
    print("[8] Testing 'Apply Changes to All Emails' template propagation...")
    apply_res = requests.post(f"{BASE}/api/campaigns/{camp_id}/emails/apply-all", json={
        "subject_template": "Exclusive opportunity for {{company}}",
        "body_template": "Hi {{first_name}},\n\nWe would love to collaborate with {{company}}.",
        "source_contact_id": c1["id"],
    }, headers=headers)
    assert apply_res.status_code == 200, apply_res.text
    applied_emails = apply_res.json()["emails"]
    assert len(applied_emails) == 2
    for em in applied_emails:
        assert "{{company}}" not in em["subject"]
        assert "{{first_name}}" not in em["body"]
        assert "{{company}}" not in em["body"]
        assert "Exclusive opportunity for" in em["subject"]
        print(f"    -> Prepared for: {em['contact_email']} ({em.get('contact_name')}) | Subject: {em['subject']}")

    # 8. User Approval & Send
    print("[9] Simulating user explicit approval & send...")
    send_res = requests.post(f"{BASE}/api/campaigns/{camp_id}/send", headers=headers)
    assert send_res.status_code == 200, send_res.text
    send_json = send_res.json()
    assert send_json["status"] == "COMPLETED"
    assert send_json["emails_sent"] == 2
    print(f"    -> Campaign status: {send_json['status']} | Emails sent: {send_json['emails_sent']}")

    # 9. Verify Dashboard UI Serving
    print("[10] Verifying Dashboard SPA & anti-caching headers...")
    dash_res = requests.get(f"{BASE}/dashboard")
    assert dash_res.status_code == 200
    assert "no-cache" in dash_res.headers.get("Cache-Control", "").lower()
    html = dash_res.text
    assert "STEP 5: REVIEW & PERSONALIZE" in html
    assert "Apply Changes to All Emails" in html
    # 10. Verify HubSpot CRM Live Endpoints
    print("[11] Verifying HubSpot CRM live endpoints & UI components...")
    hs_test = requests.get(f"{BASE}/api/contacts/hubspot/test-connection", headers=headers)
    assert hs_test.status_code == 200, hs_test.text
    hs_data = hs_test.json()
    assert "success" in hs_data
    print(f"    -> /hubspot/test-connection returned 200 (configured: {hs_data.get('configured')}).")

    hs_import = requests.post(f"{BASE}/api/contacts/import-hubspot", json={"limit": 50, "use_demo_fallback": True}, headers=headers)
    assert hs_import.status_code == 200, hs_import.text
    hs_imp_data = hs_import.json()
    assert hs_imp_data["imported"] >= 1
    assert hs_imp_data["source"] in ("hubspot_crm", "hubspot_demo")
    print(f"    -> /import-hubspot returned 200 (imported: {hs_imp_data['imported']}, source: {hs_imp_data['source']}).")

    assert "Connect HubSpot CRM" in html
    assert "OAuth" in html
    assert "Private App" in html
    print("    -> Dashboard DOM verified: 'Connect HubSpot CRM' and 'OAuth / Private App' rendered.")

    print("\n" + "=" * 60)
    print(">>> ALL 11 END-TO-END CHECKS PASSED WITH 100% SUCCESS! <<<")
    print("=" * 60)

if __name__ == "__main__":
    run_live_verification()

