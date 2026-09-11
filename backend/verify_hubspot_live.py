import requests
import uuid

BASE = "http://localhost:8000"

def verify():
    suffix = uuid.uuid4().hex[:6]
    email = f"hs_live_{suffix}@example.com"
    pwd = "EnterprisePassword123!"

    print("=" * 60)
    print("LIVE HUBSPOT CRM SYNC VERIFICATION")
    print("=" * 60)

    # 1. Register & Login
    print("[1] Registering & authenticating test user...")
    reg = requests.post(f"{BASE}/api/auth/register", json={"email": email, "password": pwd})
    assert reg.status_code == 201, reg.text

    login = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("    -> Authenticated.")

    # 2. Test Connection
    print("[2] Testing server-side HubSpot API v3 connection...")
    test_res = requests.get(f"{BASE}/api/contacts/hubspot/test-connection", headers=headers)
    assert test_res.status_code == 200, test_res.text
    test_data = test_res.json()
    print("    -> Result:", test_data)
    assert test_data["success"] is True
    assert test_data["configured"] is True

    # 3. Live Sync Contacts
    print("[3] Synchronizing contacts from live HubSpot portal...")
    sync_res = requests.post(f"{BASE}/api/contacts/import-hubspot", headers=headers)
    assert sync_res.status_code == 200, sync_res.text
    sync_data = sync_res.json()
    print(f"    -> Synced {sync_data['imported']} contacts from source: '{sync_data['source']}'")
    assert sync_data["source"] == "hubspot_crm"
    assert sync_data["imported"] >= 1

    print("\n[4] Sample Synchronized Contacts:")
    for c in sync_data["contacts"][:5]:
        print(f"    • {c['name']} <{c['email']}> | Company: {c.get('company')} | Role: {c.get('role')}")

    print("\n" + "=" * 60)
    print(">>> HUBSPOT LIVE API SYNCHRONIZATION 100% VERIFIED! <<<")
    print("=" * 60)

if __name__ == "__main__":
    verify()

