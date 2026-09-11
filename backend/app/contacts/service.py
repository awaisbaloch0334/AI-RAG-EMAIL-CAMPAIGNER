import csv
import io
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contacts.provider import (
    ContactProvider,
    HubSpotContactProvider,
    MockContactProvider,
    MockHubSpotContactProvider,
    RawContactData,
)
from app.contacts.schemas import ContactCreateRequest, ContactUpdateRequest
from app.db.models.contact import Contact
from app.db.models.user import User


class ContactService:
    @staticmethod
    def create_contact(db: Session, user_id: str, req: ContactCreateRequest) -> Contact:
        # Determine first_name if omitted
        first_name = req.first_name
        if not first_name and req.name:
            first_name = req.name.strip().split()[0]

        contact = Contact(
            user_id=user_id,
            name=req.name.strip(),
            first_name=first_name,
            email=str(req.email).strip().lower(),
            company=req.company.strip() if req.company else None,
            role=req.role.strip() if req.role else None,
            custom_variables=req.custom_variables or {},
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return contact

    @staticmethod
    def list_contacts_for_user(db: Session, user_id: str) -> List[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.user_id == user_id)
            .order_by(Contact.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_contact_for_user(db: Session, user_id: str, contact_id: str) -> Optional[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.id == contact_id, Contact.user_id == user_id)
        )
        return db.scalars(stmt).first()

    @staticmethod
    def update_contact(
        db: Session,
        user_id: str,
        contact_id: str,
        req: ContactUpdateRequest,
    ) -> Optional[Contact]:
        contact = ContactService.get_contact_for_user(db, user_id, contact_id)
        if not contact:
            return None

        if req.name is not None:
            contact.name = req.name.strip()
        if req.first_name is not None:
            contact.first_name = req.first_name.strip()
        if req.email is not None:
            contact.email = str(req.email).strip().lower()
        if req.company is not None:
            contact.company = req.company.strip() if req.company else None
        if req.role is not None:
            contact.role = req.role.strip() if req.role else None
        if req.custom_variables is not None:
            contact.custom_variables = req.custom_variables

        db.commit()
        db.refresh(contact)
        return contact

    @staticmethod
    def delete_contact(db: Session, user_id: str, contact_id: str) -> bool:
        contact = ContactService.get_contact_for_user(db, user_id, contact_id)
        if not contact:
            return False

        db.delete(contact)
        db.commit()
        return True

    @staticmethod
    def _persist_raw_contacts(
        db: Session,
        user_id: str,
        raw_leads: List[RawContactData],
    ) -> List[Contact]:
        """Persists or updates a list of RawContactData scoped strictly to user_id."""
        imported: List[Contact] = []
        for lead in raw_leads:
            existing = db.scalars(
                select(Contact).where(
                    Contact.user_id == user_id,
                    Contact.email == str(lead.email).lower(),
                )
            ).first()

            if existing:
                existing.name = lead.name
                existing.first_name = lead.first_name or lead.name.split()[0]
                existing.company = lead.company
                existing.role = lead.role
                if lead.custom_variables:
                    existing.custom_variables = {
                        **(existing.custom_variables or {}),
                        **lead.custom_variables,
                    }
                imported.append(existing)
            else:
                contact = Contact(
                    user_id=user_id,
                    name=lead.name,
                    first_name=lead.first_name or lead.name.split()[0],
                    email=str(lead.email).lower(),
                    company=lead.company,
                    role=lead.role,
                    custom_variables=lead.custom_variables or {},
                )
                db.add(contact)
                imported.append(contact)

        db.commit()
        for c in imported:
            db.refresh(c)
        return imported

    @staticmethod
    def import_sample_contacts(
        db: Session,
        user_id: str,
        provider: Optional[ContactProvider] = None,
    ) -> List[Contact]:
        """
        Imports curated sample leads from MockContactProvider (or custom provider)
        scoped strictly to the given user_id.
        """
        if provider is None:
            provider = MockContactProvider()

        raw_leads = provider.fetch_contacts()
        return ContactService._persist_raw_contacts(db, user_id, raw_leads)

    @staticmethod
    def test_hubspot_connection(user: Optional[User] = None, db: Optional[Session] = None) -> dict:
        """Tests live connectivity to HubSpot CRM API v3 using user OAuth token or server credentials."""
        token = None
        if user and db and user.hubspot_access_token:
            from app.contacts.oauth import HubSpotOAuthService
            token = HubSpotOAuthService.get_valid_access_token(user, db)
        provider = HubSpotContactProvider(token)
        return provider.test_connection()

    @staticmethod
    def import_hubspot_contacts(
        db: Session,
        user_id: str,
        limit: int = 100,
        use_demo_fallback: bool = True,
    ) -> tuple[List[Contact], str]:
        """
        Imports real leads from HubSpot CRM API v3.
        Prioritizes user's OAuth 2.0 token (with auto-refresh), then falls back to server-side
        HUBSPOT_ACCESS_TOKEN, and lastly demo leads if use_demo_fallback=True.
        """
        import logging
        from app.config import settings

        logger = logging.getLogger(__name__)

        # 1. Check if user has an OAuth token connected
        user = db.get(User, user_id)
        effective_token = None
        is_oauth = False

        if user and user.hubspot_access_token:
            from app.contacts.oauth import HubSpotOAuthService
            effective_token = HubSpotOAuthService.get_valid_access_token(user, db)
            is_oauth = True

        # 2. Fall back to server-side private app token if no user OAuth token
        if not effective_token and settings.hubspot_access_token:
            effective_token = settings.hubspot_access_token.strip()
            is_oauth = False

        if effective_token:
            try:
                provider = HubSpotContactProvider(effective_token)
                raw_leads = provider.fetch_contacts(limit=limit)
                if raw_leads:
                    imported = ContactService._persist_raw_contacts(db, user_id, raw_leads)
                    source_label = "hubspot_oauth" if is_oauth else "hubspot_crm"
                    logger.info(f"Successfully synchronized {len(imported)} contacts from HubSpot CRM ({source_label}).")
                    return imported, source_label
                else:
                    logger.warning("HubSpot returned 0 contacts.")
            except Exception as e:
                logger.warning(f"Failed to fetch live contacts from HubSpot CRM: {e}")
                if not use_demo_fallback:
                    raise

        if use_demo_fallback:
            logger.info("Using HubSpot demo fallback connection.")
            provider = MockHubSpotContactProvider()
            raw_leads = provider.fetch_contacts()
            imported = ContactService._persist_raw_contacts(db, user_id, raw_leads)
            return imported, "hubspot_demo"
        else:
            raise ValueError("HubSpot CRM credentials are not configured on the server.")

    @staticmethod
    def import_csv_contacts(
        db: Session,
        user_id: str,
        csv_text: str,
    ) -> List[Contact]:
        """
        Imports contacts from raw CSV text content with header mapping.
        """
        reader = csv.DictReader(io.StringIO(csv_text))
        imported: List[Contact] = []

        for row in reader:
            # Normalise keys: lowercase and strip
            norm = {k.strip().lower(): v.strip() for k, v in row.items() if k}
            email = norm.get("email")
            if not email or "@" not in email:
                continue

            name = norm.get("name") or norm.get("full_name") or email.split("@")[0]
            first_name = norm.get("first_name") or name.split()[0]
            company = norm.get("company") or norm.get("organization")
            role = norm.get("role") or norm.get("title") or norm.get("job_title")

            existing = db.scalars(
                select(Contact).where(
                    Contact.user_id == user_id,
                    Contact.email == email.lower(),
                )
            ).first()

            if existing:
                existing.name = name
                existing.first_name = first_name
                existing.company = company
                existing.role = role
                imported.append(existing)
            else:
                contact = Contact(
                    user_id=user_id,
                    name=name,
                    first_name=first_name,
                    email=email.lower(),
                    company=company,
                    role=role,
                    custom_variables={},
                )
                db.add(contact)
                imported.append(contact)

        db.commit()
        for c in imported:
            db.refresh(c)
        return imported

