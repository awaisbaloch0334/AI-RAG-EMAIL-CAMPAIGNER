from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.campaigns.schemas import (
    CampaignAddContactsRequest,
    CampaignApplyAllEmailsRequest,
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignEmailUpdateRequest,
    CampaignGenerateAllRequest,
    CampaignListResponse,
    CampaignSendResponse,
    CampaignSummaryResponse,
)

from app.campaigns.service import CampaignService
from app.db.database import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.post(
    "",
    response_model=CampaignDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new email campaign",
)
def create_campaign(
    req: CampaignCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    campaign = CampaignService.create_campaign(db, current_user, req)
    detail = CampaignService.get_campaign_detail(db, current_user.id, campaign.id)
    return detail


@router.get(
    "",
    response_model=CampaignListResponse,
    summary="List all campaigns owned by the current user",
)
def list_campaigns(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    campaigns = CampaignService.list_campaigns_for_user(db, current_user.id)
    return CampaignListResponse(campaigns=campaigns, total=len(campaigns))


@router.get(
    "/{campaign_id}",
    response_model=CampaignDetailResponse,
    summary="Retrieve full campaign details with all targeted contacts and email drafts",
)
def get_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    camp = CampaignService.get_campaign_detail(db, current_user.id, campaign_id)
    if not camp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return camp


@router.post(
    "/{campaign_id}/contacts",
    response_model=CampaignDetailResponse,
    summary="Attach contacts to an existing campaign",
)
def add_contacts_to_campaign(
    campaign_id: str,
    req: CampaignAddContactsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return CampaignService.add_contacts_to_campaign(db, current_user, campaign_id, req)


@router.post(
    "/{campaign_id}/generate",
    response_model=CampaignDetailResponse,
    summary="Generate personalized RAG emails for all contacts in this campaign",
)
def generate_all_emails(
    campaign_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    req: Optional[CampaignGenerateAllRequest] = None,
):
    return CampaignService.generate_all_emails(db, current_user, campaign_id, req)


@router.post(
    "/{campaign_id}/send",
    response_model=CampaignSendResponse,
    summary="Trigger campaign dispatch via Mock Email Provider",
)
def send_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return CampaignService.send_campaign(db, current_user, campaign_id)


@router.put(
    "/{campaign_id}/emails/{email_id}",
    response_model=CampaignDetailResponse,
    summary="Update subject or body of a single campaign email draft",
)
def update_campaign_email(
    campaign_id: str,
    email_id: str,
    req: CampaignEmailUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return CampaignService.update_campaign_email(
        db=db,
        current_user=current_user,
        campaign_id=campaign_id,
        email_id=email_id,
        subject=req.subject,
        body=req.body,
    )


@router.post(
    "/{campaign_id}/emails/apply-all",
    response_model=CampaignDetailResponse,
    summary="Apply an email template across all contacts in this campaign",
)
def apply_template_to_all_emails(
    campaign_id: str,
    req: CampaignApplyAllEmailsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return CampaignService.apply_template_to_all_emails(
        db=db,
        current_user=current_user,
        campaign_id=campaign_id,
        subject_template=req.subject_template,
        body_template=req.body_template,
        source_contact_id=req.source_contact_id,
    )



@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a campaign",
)
def delete_campaign(
    campaign_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    success = CampaignService.delete_campaign(db, current_user.id, campaign_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return None

