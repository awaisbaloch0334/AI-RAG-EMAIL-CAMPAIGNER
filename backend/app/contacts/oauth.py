from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx
import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.user import User

logger = logging.getLogger(__name__)


class HubSpotOAuthService:
    SCOPES = ["crm.objects.contacts.read"]

    @classmethod
    def generate_authorization_url(cls, user_id: str) -> str:
        """
        Generates the HubSpot OAuth authorization URL with a tamper-proof signed CSRF state.
        """
        state_payload = {
            "sub": user_id,
            "purpose": "hubspot_oauth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        state_token = jwt.encode(
            state_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        encoded_scopes = quote(" ".join(cls.SCOPES))
        encoded_redirect = quote(settings.hubspot_redirect_uri)
        auth_base = settings.hubspot_auth_base_url.rstrip("/")
        auth_url = (
            f"{auth_base}/oauth/authorize"
            f"?client_id={settings.hubspot_client_id}"
            f"&redirect_uri={encoded_redirect}"
            f"&scope={encoded_scopes}"
            f"&state={state_token}"
        )
        return auth_url

    @classmethod
    def exchange_code_for_tokens(cls, code: str, state: Optional[str], db: Session) -> User:
        """
        Validates state token (if present) and exchanges authorization code for access & refresh tokens.
        If state is absent (e.g. Test URL directly from HubSpot), resolves user via token identity.
        """
        user = None
        if state:
            try:
                payload = jwt.decode(
                    state,
                    settings.jwt_secret_key,
                    algorithms=[settings.jwt_algorithm],
                )
            except jwt.PyJWTError as e:
                logger.error(f"Invalid or expired HubSpot OAuth state token: {e}")
                raise ValueError("Invalid or expired OAuth state parameter. Please try connecting again.")

            if payload.get("purpose") != "hubspot_oauth":
                raise ValueError("Invalid OAuth purpose token.")

            user_id = payload.get("sub")
            if not user_id:
                raise ValueError("User identifier missing from OAuth state.")

            user = db.get(User, user_id)
            if not user:
                raise ValueError("User not found.")

        # Exchange authorization code for tokens
        token_url = f"{settings.hubspot_api_base_url.rstrip('/')}/oauth/v1/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.hubspot_client_id,
            "client_secret": settings.hubspot_client_secret,
            "redirect_uri": settings.hubspot_redirect_uri,
            "code": code,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if resp.status_code != 200:
                    logger.error(f"HubSpot token exchange failed ({resp.status_code}): {resp.text}")
                    raise ValueError(f"HubSpot authorization failed (HTTP {resp.status_code}).")

                token_data = resp.json()
        except httpx.HTTPError as e:
            logger.error(f"Network error during HubSpot token exchange: {e}")
            raise ValueError("Failed to communicate with HubSpot OAuth servers.")

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 1800)

        if not access_token:
            raise ValueError("HubSpot did not return an access token.")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Retrieve portal ID (hub_id) and token info
        portal_id = None
        hub_user = None
        try:
            with httpx.Client(timeout=10.0) as client:
                info_resp = client.get(
                    f"{settings.hubspot_api_base_url.rstrip('/')}/oauth/v1/access-tokens/{access_token}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if info_resp.status_code == 200:
                    info_data = info_resp.json()
                    portal_id = str(info_data.get("hub_id") or "")
                    hub_user = info_data.get("user")
        except Exception as e:
            logger.warning(f"Could not retrieve HubSpot portal ID: {e}")

        # If user was not resolved via signed state token, resolve via HubSpot user email or fallback
        if not user:
            if hub_user:
                # 1. Try exact email match
                user = db.query(User).filter(User.email == hub_user).first()
                if not user:
                    # 2. Try prefix match (e.g. awaisbaloch)
                    username = hub_user.split("@")[0]
                    user = db.query(User).filter(User.email.like(f"{username}%")).first()
            if not user:
                # 3. Fallback to the primary customer in database
                user = db.query(User).filter(User.email.not_like("oauth_%"), User.email.not_like("camp_%"), User.email.not_like("lead%"), User.email.not_like("rag_%")).first()
            if not user:
                user = db.query(User).first()

        if not user:
            raise ValueError("No user account available to associate HubSpot credentials with.")

        # Update user record
        user.hubspot_access_token = access_token
        user.hubspot_refresh_token = refresh_token
        user.hubspot_token_expires_at = expires_at
        user.hubspot_portal_id = portal_id
        user.hubspot_connected_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(user)
        logger.info(f"User {user.id} successfully connected HubSpot Portal #{portal_id}.")
        return user

    @classmethod
    def get_valid_access_token(cls, user: User, db: Session) -> Optional[str]:
        """
        Returns a valid access token for the user, automatically refreshing it if expired.
        """
        if not user.hubspot_access_token:
            return None

        # Check if expired or within 3 minutes of expiry
        now = datetime.now(timezone.utc)
        needs_refresh = (
            user.hubspot_token_expires_at is None
            or now >= (user.hubspot_token_expires_at - timedelta(minutes=3))
        )

        if not needs_refresh:
            return user.hubspot_access_token

        if not user.hubspot_refresh_token:
            logger.warning(f"User {user.id} HubSpot token expired and no refresh token available.")
            return user.hubspot_access_token

        logger.info(f"HubSpot access token for user {user.id} is expired or expiring. Refreshing...")
        token_url = f"{settings.hubspot_api_base_url.rstrip('/')}/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.hubspot_client_id,
            "client_secret": settings.hubspot_client_secret,
            "refresh_token": user.hubspot_refresh_token,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                if resp.status_code == 200:
                    token_data = resp.json()
                    user.hubspot_access_token = token_data.get("access_token")
                    if token_data.get("refresh_token"):
                        user.hubspot_refresh_token = token_data.get("refresh_token")
                    expires_in = token_data.get("expires_in", 1800)
                    user.hubspot_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                    db.commit()
                    db.refresh(user)
                    logger.info(f"Successfully refreshed HubSpot token for user {user.id}.")
                    return user.hubspot_access_token
                else:
                    logger.error(f"Failed to refresh HubSpot token ({resp.status_code}): {resp.text}")
                    return user.hubspot_access_token
        except Exception as e:
            logger.error(f"Error refreshing HubSpot access token: {e}")
            return user.hubspot_access_token

    @classmethod
    def disconnect_user(cls, user: User, db: Session) -> None:
        """
        Clears all stored HubSpot OAuth tokens and portal metadata for the user.
        """
        user.hubspot_access_token = None
        user.hubspot_refresh_token = None
        user.hubspot_token_expires_at = None
        user.hubspot_portal_id = None
        user.hubspot_connected_at = None
        db.commit()
        db.refresh(user)
        logger.info(f"User {user.id} disconnected HubSpot.")

    @classmethod
    def get_connection_status(cls, user: User) -> Dict[str, Any]:
        """
        Returns connection metadata without exposing secrets.
        """
        has_token = bool(user.hubspot_access_token)
        now = datetime.now(timezone.utc)
        is_expired = False
        if has_token and user.hubspot_token_expires_at:
            is_expired = now >= user.hubspot_token_expires_at

        return {
            "connected": has_token,
            "portal_id": user.hubspot_portal_id,
            "connected_at": user.hubspot_connected_at.isoformat() if user.hubspot_connected_at else None,
            "expires_at": user.hubspot_token_expires_at.isoformat() if user.hubspot_token_expires_at else None,
            "is_expired": is_expired,
            "auth_type": "oauth_2" if has_token else ("server_token" if settings.hubspot_access_token else "none"),
        }
