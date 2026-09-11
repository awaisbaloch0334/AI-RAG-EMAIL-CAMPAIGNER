from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="Valid email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=6,
        description="Password must be at least 6 characters",
        examples=["mypassword123"],
    )


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        examples=["mypassword123"],
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional["UserResponse"] = None


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthChallengeResponse(BaseModel):
    status: str = "otp_required"
    message: str
    email: str


class OTPRequest(BaseModel):
    email: EmailStr


class OTPResponse(BaseModel):
    message: str
    email: Optional[str] = None


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


class OTPResendRequest(BaseModel):
    email: EmailStr

