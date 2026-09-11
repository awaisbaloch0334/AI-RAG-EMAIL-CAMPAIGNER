from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.auth.service import AuthService
from app.db.database import get_db
from app.db.models.bot import Bot
from app.db.models.user import User

security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Authenticate request via JWT Bearer token and return the User instance.
    Never trusts client-supplied user_id.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Click the green 'Authorize' button at the top of Swagger UI and paste your token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = credentials.credentials.strip().strip('"').strip("'")
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[7:].strip()

    payload = decode_access_token(raw_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token. Please log in again to get a fresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_bot(
    bot_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Bot:
    """
    Load a Bot and verify that the authenticated user is the legitimate owner.
    Hard invariant: A user cannot access or manage another tenant's bot.
    """
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )
    return bot

