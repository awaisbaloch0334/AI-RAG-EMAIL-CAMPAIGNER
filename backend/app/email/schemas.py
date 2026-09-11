from typing import Optional
from pydantic import BaseModel, Field


class EmailGenerateRequest(BaseModel):
    campaign_id: Optional[str] = Field(None, description="Optional Campaign ID to link and save this email under")
    campaign_goal: Optional[str] = Field(None, description="Target objective or call-to-action for the email")
    custom_instructions: Optional[str] = Field(None, description="Special copywriting instructions or constraints")
    save_draft: bool = Field(True, description="Whether to persist generated email into CampaignEmail record if campaign_id provided")


class GeneratedEmailDraft(BaseModel):
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Personalized body of the email")


class EmailGenerateResponse(BaseModel):
    subject: str
    body: str
    contact_id: str
    bot_id: str
    campaign_id: Optional[str] = None
    campaign_email_id: Optional[str] = None
    retrieved_chunks_count: int
    recipient_name: str
    recipient_email: str
    recipient_company: Optional[str] = None
    status: str = "GENERATED"

