from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.contacts.schemas import (
    ContactCreateRequest,
    ContactImportResponse,
    ContactListResponse,
    ContactResponse,
    ContactUpdateRequest,
    HubSpotImportRequest,
    HubSpotTestConnectionResponse,
)
from app.contacts.service import ContactService
from app.db.database import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.post(
    "",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contact",
)
def create_contact(
    req: ContactCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Creates a new contact associated with the authenticated user.
    Enforces user_id = current_user.id boundary.
    """
    contact = ContactService.create_contact(db, current_user.id, req)
    return contact


@router.get(
    "",
    response_model=ContactListResponse,
    summary="List all contacts owned by the current user",
)
def list_contacts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Returns only contacts owned by the authenticated user.
    """
    contacts = ContactService.list_contacts_for_user(db, current_user.id)
    return ContactListResponse(contacts=contacts, total=len(contacts))


@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Retrieve a single contact by ID",
)
def get_contact(
    contact_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Returns the contact if owned by the authenticated user; otherwise 404.
    """
    contact = ContactService.get_contact_for_user(db, current_user.id, contact_id)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    return contact


@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    summary="Update an existing contact",
)
def update_contact(
    contact_id: str,
    req: ContactUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Updates the contact fields if owned by authenticated user; otherwise 404.
    """
    contact = ContactService.update_contact(db, current_user.id, contact_id, req)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    return contact


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a contact",
)
def delete_contact(
    contact_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Deletes the contact if owned by authenticated user; otherwise 404.
    """
    success = ContactService.delete_contact(db, current_user.id, contact_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    return None


@router.post(
    "/import-mock",
    response_model=ContactImportResponse,
    summary="Import mock sample leads for demo",
)
def import_mock_contacts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Populates sample leads into the user's account using MockContactProvider.
    """
    contacts = ContactService.import_sample_contacts(db, current_user.id)
    return ContactImportResponse(
        imported=len(contacts),
        contacts=contacts,
        source="mock",
    )


@router.get(
    "/hubspot/test-connection",
    response_model=HubSpotTestConnectionResponse,
    summary="Test server-side HubSpot CRM connectivity",
)
def test_hubspot_connection(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Tests live connectivity to HubSpot CRM API v3 using user OAuth or server-side credentials.
    Does not expose the token to the client.
    """
    res = ContactService.test_hubspot_connection(current_user, db)
    return HubSpotTestConnectionResponse(**res)


@router.post(
    "/import-hubspot",
    response_model=ContactImportResponse,
    summary="Connect HubSpot CRM Integration (Real API with graceful demo fallback)",
)
def import_hubspot_contacts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    req: Optional[HubSpotImportRequest] = None,
):
    """
    Imports real contacts from HubSpot CRM API v3 using server-side credentials.
    If unconfigured or if network issues arise, gracefully falls back to demo leads
    so the campaign flow is never blocked.
    """
    limit = req.limit if req else 100
    use_fallback = req.use_demo_fallback if req else True
    contacts, source = ContactService.import_hubspot_contacts(
        db,
        current_user.id,
        limit=limit,
        use_demo_fallback=use_fallback,
    )
    return ContactImportResponse(
        imported=len(contacts),
        contacts=contacts,
        source=source,
    )


@router.post(
    "/import-csv",
    response_model=ContactImportResponse,
    summary="Import contacts from uploaded CSV file",
)
async def import_csv_contacts(
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_current_user)] = None,
    db: Annotated[Session, Depends(get_db)] = None,
):
    """
    Parses a CSV file containing columns: name, email, company, role.
    """
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("latin-1")

    contacts = ContactService.import_csv_contacts(db, current_user.id, csv_text)
    return ContactImportResponse(
        imported=len(contacts),
        contacts=contacts,
        source="csv",
    )

