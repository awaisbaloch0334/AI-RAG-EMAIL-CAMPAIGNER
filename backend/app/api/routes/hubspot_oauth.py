from typing import Annotated, Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.contacts.oauth import HubSpotOAuthService
from app.db.database import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/auth/hubspot", tags=["hubspot_oauth"])


@router.get(
    "/authorize",
    summary="Initiate HubSpot OAuth 2.0 authorization",
)
def authorize_hubspot(
    current_user: Annotated[User, Depends(get_current_user)],
) -> Dict[str, str]:
    """
    Returns the official HubSpot OAuth URL with a signed CSRF state token.
    """
    url = HubSpotOAuthService.generate_authorization_url(current_user.id)
    return {"url": url}


@router.get(
    "/callback",
    summary="Handle HubSpot OAuth 2.0 redirect callback",
)
def hubspot_callback(
    code: str = Query(..., description="Authorization code from HubSpot"),
    state: Optional[str] = Query(None, description="Signed CSRF state parameter"),
    db: Session = Depends(get_db),
):
    """
    Exchanges authorization code for access and refresh tokens, updates user in DB,
    and redirects the browser back to the dashboard.
    """
    try:
        HubSpotOAuthService.exchange_code_for_tokens(code, state, db)
        return RedirectResponse(url="/dashboard?hubspot=connected", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        error_msg = quote(str(e))
        return RedirectResponse(url=f"/dashboard?hubspot_error={error_msg}", status_code=status.HTTP_303_SEE_OTHER)


@router.get(
    "/status",
    summary="Retrieve current user's HubSpot connection status",
)
def get_hubspot_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> Dict[str, Any]:
    """
    Returns the current user's HubSpot connection status and portal ID.
    """
    return HubSpotOAuthService.get_connection_status(current_user)


@router.post(
    "/disconnect",
    summary="Disconnect current user's HubSpot portal",
)
def disconnect_hubspot(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Clears stored OAuth tokens and portal metadata for the user.
    """
    HubSpotOAuthService.disconnect_user(current_user, db)
    return {"success": True, "message": "HubSpot disconnected successfully."}

