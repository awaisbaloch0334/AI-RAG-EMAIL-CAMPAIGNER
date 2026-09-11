from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the campaign")
    bot_id: str = Field(..., description="Knowledge source bot ID owned by the user")
    contact_ids: Optional[List[str]] = Field(default_factory=list, description="Initial contacts to include")
    campaign_goal: Optional[str] = Field(None, description="Campaign objective or value proposition")


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = Field(None, max_length=50)


class CampaignAddContactsRequest(BaseModel):
    contact_ids: List[str] = Field(..., min_length=1, description="List of owned contact IDs to add")



class CampaignGenerateAllRequest(BaseModel):
    campaign_goal: Optional[str] = Field(None, description="Objective or angle for email generation")
    custom_instructions: Optional[str] = Field(None, description="Special instructions for the copywriter")


class CampaignEmailUpdateRequest(BaseModel):
    subject: str = Field(..., min_length=1, description="Updated subject line")
    body: str = Field(..., min_length=1, description="Updated email body")


class CampaignApplyAllEmailsRequest(BaseModel):
    subject_template: str = Field(..., min_length=1, description="Subject template to apply across all emails")
    body_template: str = Field(..., min_length=1, description="Body template to apply across all emails")
    source_contact_id: Optional[str] = Field(None, description="Contact ID whose details were used to produce the template")



class CampaignEmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    contact_id: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_company: Optional[str] = None
    contact_role: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None


class CampaignSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    bot_id: str
    bot_name: Optional[str] = None
    name: str
    status: str
    total_emails: int = 0
    sent_emails: int = 0
    created_at: datetime
    updated_at: datetime


class CampaignDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    bot_id: str
    bot_name: Optional[str] = None
    name: str
    status: str
    total_emails: int = 0
    sent_emails: int = 0
    created_at: datetime
    updated_at: datetime
    emails: List[CampaignEmailResponse] = []


class CampaignListResponse(BaseModel):
    campaigns: List[CampaignSummaryResponse]
    total: int


class CampaignSendResponse(BaseModel):
    campaign_id: str
    status: str
    emails_sent: int
    message: str
