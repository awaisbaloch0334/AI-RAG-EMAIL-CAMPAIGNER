from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Full name of contact")
    first_name: Optional[str] = Field(None, max_length=128, description="First name for personalization")
    email: EmailStr = Field(..., description="Valid contact email address")
    company: Optional[str] = Field(None, max_length=255, description="Company or organization name")
    role: Optional[str] = Field(None, max_length=255, description="Job title / role")
    custom_variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom personalization key-values")


class ContactUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    first_name: Optional[str] = Field(None, max_length=128)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, max_length=255)
    custom_variables: Optional[Dict[str, Any]] = None


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    first_name: Optional[str] = None
    email: str
    company: Optional[str] = None
    role: Optional[str] = None
    custom_variables: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    contacts: List[ContactResponse]
    total: int


class ContactImportResponse(BaseModel):
    imported: int
    contacts: List[ContactResponse]
    source: str = "mock"


class HubSpotTestConnectionResponse(BaseModel):
    success: bool
    configured: bool
    message: str
    contact_count: Optional[int] = 0


class HubSpotImportRequest(BaseModel):
    limit: Optional[int] = Field(100, ge=1, le=250, description="Max contacts to import")
    use_demo_fallback: Optional[bool] = Field(True, description="Fallback to demo leads if HubSpot token is not configured")


