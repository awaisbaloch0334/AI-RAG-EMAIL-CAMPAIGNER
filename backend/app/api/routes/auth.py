from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.auth.schemas import (
    AuthChallengeResponse,
    OTPRequest,
    OTPResendRequest,
    OTPResponse,
    OTPVerifyRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.auth.security import create_access_token
from app.auth.service import AuthService
from app.db.database import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account and dispatch real email OTP",
)
def register(
    req: UserRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Creates user account with hashed password and dispatches a real 6-digit OTP code to the email.
    """
    user = AuthService.register_user(db, req)
    return user


@router.post(
    "/initiate-login",
    response_model=AuthChallengeResponse,
    summary="Validate credentials and send 6-digit OTP email challenge",
)
def initiate_login(
    req: UserLoginRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Validates user credentials against password hash and dispatches real OTP email.
    Returns otp_required challenge (never returns OTP in API response).
    """
    user = AuthService.initiate_login(db, req.email, req.password)
    return AuthChallengeResponse(
        status="otp_required",
        message="We sent a 6-digit verification code to your email address.",
        email=user.email,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and receive JWT token (or dispatch OTP if requested)",
)
def login(
    req: UserLoginRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Standard login endpoint. Validates password and dispatches OTP email.
    Returns access token for direct API integrations / tests.
    """
    user = AuthService.authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Also dispatch OTP email for security
    AuthService.generate_and_send_otp(user.email)

    access_token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
    )


@router.post(
    "/resend-otp",
    response_model=OTPResponse,
    summary="Resend fresh 6-digit verification code via SMTP",
)
def resend_otp(
    req: OTPResendRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Resends a fresh OTP code to the specified email address via SMTP.
    """
    AuthService.resend_otp(db, req.email)
    return OTPResponse(
        message="A new verification code has been sent to your email address.",
        email=req.email,
    )


@router.post(
    "/request-otp",
    response_model=OTPResponse,
    summary="Request a temporary OTP for email verification",
)
def request_otp(
    req: OTPRequest,
):
    """
    Dispatches a real OTP to the email address via SMTP.
    Does NOT return the OTP code in the response body.
    """
    AuthService.request_otp(req.email)
    return OTPResponse(
        message=f"A verification code has been dispatched to {req.email}.",
        email=req.email,
    )


@router.post(
    "/verify-otp",
    response_model=TokenResponse,
    summary="Verify OTP code and receive JWT access token",
)
def verify_otp(
    req: OTPVerifyRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Verifies 6-digit code.
    Expires and invalidates code immediately upon successful verification.
    """
    user = AuthService.verify_otp(db, req.email, req.otp)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code.",
        )

    access_token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get authenticated user profile",
)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user
