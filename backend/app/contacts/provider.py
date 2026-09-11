from abc import ABC, abstractmethod
import csv
import io
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr


class RawContactData(BaseModel):
    name: str
    first_name: Optional[str] = None
    email: EmailStr
    company: Optional[str] = None
    role: Optional[str] = None
    custom_variables: Optional[Dict[str, Any]] = None


class ContactProvider(ABC):
    """
    Abstract contact provider.
    Enables pluggable data sources: CSVContactProvider (Real)
    and MockHubSpotContactProvider (Mocked demo connection).
    """
    @abstractmethod
    def fetch_contacts(self) -> List[RawContactData]:
        pass


class CSVContactProvider(ContactProvider):
    """
    Real CSV contact provider that receives, parses, and normalizes uploaded CSV files.
    """
    def __init__(self, csv_text: str):
        self.csv_text = csv_text

    def fetch_contacts(self) -> List[RawContactData]:
        reader = csv.DictReader(io.StringIO(self.csv_text))
        contacts: List[RawContactData] = []
        for row in reader:
            norm = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}
            email = norm.get("email")
            if not email or "@" not in email:
                continue

            name = norm.get("name") or norm.get("full_name") or email.split("@")[0]
            first_name = norm.get("first_name") or name.split()[0]
            company = norm.get("company") or norm.get("organization")
            role = norm.get("role") or norm.get("title") or norm.get("job_title")

            contacts.append(
                RawContactData(
                    name=name,
                    first_name=first_name,
                    email=email,
                    company=company,
                    role=role,
                )
            )
        return contacts


class MockHubSpotContactProvider(ContactProvider):
    """
    Simulates a connected HubSpot CRM lead source for demo purposes.
    Explicitly labeled as 'HubSpot Demo Connection'.
    """
    provider_name: str = "HubSpot Demo Connection"

    def fetch_contacts(self) -> List[RawContactData]:
        return [
            RawContactData(
                name="Sarah Connor",
                first_name="Sarah",
                email="sarah.connor@cyberdyne.example.com",
                company="Cyberdyne Systems",
                role="Chief Security Officer",
                custom_variables={
                    "hubspot_source": "Enterprise Inbound Form",
                    "lifecycle_stage": "Sales Qualified Lead",
                    "lead_score": 95,
                },
            ),
            RawContactData(
                name="Alexander Wright",
                first_name="Alex",
                email="a.wright@novatech.example.com",
                company="NovaTech Solutions",
                role="Head of Growth & Marketing",
                custom_variables={
                    "hubspot_source": "Product Webinar 2026",
                    "lifecycle_stage": "Opportunity",
                    "lead_score": 88,
                },
            ),
            RawContactData(
                name="Elena Rostova",
                first_name="Elena",
                email="elena.r@biovance.example.com",
                company="BioVance Health",
                role="VP of Clinical Operations",
                custom_variables={
                    "hubspot_source": "Organic Search",
                    "lifecycle_stage": "Marketing Qualified Lead",
                    "lead_score": 91,
                },
            ),
            RawContactData(
                name="Marcus Vance",
                first_name="Marcus",
                email="marcus.v@apexlogistics.example.com",
                company="Apex Global Logistics",
                role="Director of Operations",
                custom_variables={
                    "hubspot_source": "Cold Outreach Follow-up",
                    "lifecycle_stage": "Lead",
                    "lead_score": 84,
                },
            ),
        ]


class HubSpotContactProvider(ContactProvider):
    """
    Real HubSpot CRM contact provider connecting to HubSpot CRM API v3.
    Uses server-side Private App Token configured in environment.
    """
    provider_name: str = "HubSpot CRM"

    def __init__(self, access_token: Optional[str] = None, base_url: Optional[str] = None):
        import logging
        from app.config import settings

        if access_token is not None:
            self.access_token = access_token.strip()
        else:
            self.access_token = (settings.hubspot_access_token or "").strip()
        self.base_url = (base_url or settings.hubspot_api_base_url or "https://api.hubapi.com").rstrip("/")

    def test_connection(self) -> Dict[str, Any]:
        """Validates token and connectivity against HubSpot API v3."""
        import httpx

        if not self.access_token:
            return {
                "success": False,
                "configured": False,
                "message": "HUBSPOT_ACCESS_TOKEN is not configured on the server (.env).",
                "contact_count": 0,
            }

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{self.base_url}/crm/v3/objects/contacts",
                    headers=headers,
                    params={"limit": 1, "archived": "false"},
                )

                if resp.status_code == 200:
                    data = resp.json()
                    # Determine estimate of contacts
                    total = data.get("total")
                    results = data.get("results", [])
                    count = total if total is not None else len(results)
                    return {
                        "success": True,
                        "configured": True,
                        "message": "Successfully connected to HubSpot CRM API v3.",
                        "contact_count": count,
                    }
                elif resp.status_code == 401:
                    return {
                        "success": False,
                        "configured": True,
                        "message": "Invalid or expired HubSpot Private App Token.",
                        "contact_count": 0,
                    }
                elif resp.status_code == 403:
                    return {
                        "success": False,
                        "configured": True,
                        "message": "Missing permissions. Please ensure your HubSpot Private App includes the 'crm.objects.contacts.read' scope.",
                        "contact_count": 0,
                    }
                else:
                    return {
                        "success": False,
                        "configured": True,
                        "message": f"HubSpot API error (HTTP {resp.status_code}): {resp.text[:200]}",
                        "contact_count": 0,
                    }
        except Exception as e:
            return {
                "success": False,
                "configured": True,
                "message": f"Failed to connect to HubSpot API: {str(e)}",
                "contact_count": 0,
            }

    def fetch_contacts(self, limit: int = 100) -> List[RawContactData]:
        """
        Fetches contacts from HubSpot CRM API v3.
        If credentials are not configured or invalid, raises ValueError or returns fallback.
        """
        import httpx

        if not self.access_token:
            raise ValueError(
                "HubSpot CRM access token is not configured on the server. "
                "Please set HUBSPOT_ACCESS_TOKEN in .env or use demo leads."
            )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        properties = [
            "firstname",
            "lastname",
            "email",
            "company",
            "jobtitle",
            "phone",
            "lifecyclestage",
            "hs_lead_status",
        ]

        contacts: List[RawContactData] = []
        next_after: Optional[str] = None
        max_to_fetch = min(max(limit, 1), 250)

        with httpx.Client(timeout=20.0) as client:
            while len(contacts) < max_to_fetch:
                fetch_batch = min(100, max_to_fetch - len(contacts))
                params: Dict[str, Any] = {
                    "limit": fetch_batch,
                    "properties": ",".join(properties),
                    "archived": "false",
                }
                if next_after:
                    params["after"] = next_after

                resp = client.get(
                    f"{self.base_url}/crm/v3/objects/contacts",
                    headers=headers,
                    params=params,
                )

                if resp.status_code != 200:
                    self.logger.error(f"HubSpot API returned status {resp.status_code}: {resp.text}")
                    if resp.status_code == 401:
                        raise ValueError("HubSpot authentication failed. Check your Private App Token.")
                    elif resp.status_code == 403:
                        raise ValueError("HubSpot access denied. Verify 'crm.objects.contacts.read' scope.")
                    raise ValueError(f"HubSpot API returned error {resp.status_code}")

                data = resp.json()
                results = data.get("results", [])

                for item in results:
                    props = item.get("properties", {})
                    email = props.get("email")
                    if not email or "@" not in email:
                        continue

                    first_name = props.get("firstname")
                    last_name = props.get("lastname")
                    
                    if first_name and last_name:
                        name = f"{first_name} {last_name}".strip()
                    elif first_name:
                        name = first_name
                    elif last_name:
                        name = last_name
                    else:
                        name = email.split("@")[0]

                    company = props.get("company")
                    role = props.get("jobtitle")
                    
                    custom_vars = {
                        "hubspot_id": item.get("id"),
                        "hubspot_source": "HubSpot CRM v3",
                    }
                    if props.get("phone"):
                        custom_vars["phone"] = props.get("phone")
                    if props.get("lifecyclestage"):
                        custom_vars["lifecycle_stage"] = props.get("lifecyclestage")
                    if props.get("hs_lead_status"):
                        custom_vars["lead_status"] = props.get("hs_lead_status")

                    contacts.append(
                        RawContactData(
                            name=name,
                            first_name=first_name or name.split()[0],
                            email=email.strip().lower(),
                            company=company,
                            role=role,
                            custom_variables=custom_vars,
                        )
                    )

                paging = data.get("paging", {})
                next_page = paging.get("next", {})
                next_after = next_page.get("after")
                if not next_after or not results:
                    break

        return contacts


# Backward compatibility alias
MockContactProvider = MockHubSpotContactProvider

