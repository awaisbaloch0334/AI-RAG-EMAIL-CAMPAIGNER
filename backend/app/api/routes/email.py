from typing import Annotated, Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models.campaign import Campaign
from app.db.models.user import User
from app.email.schemas import EmailGenerateRequest, EmailGenerateResponse
from app.email.service import EmailGenerationService

router = APIRouter(tags=["email"])


@router.post(
    "/api/bots/{bot_id}/contacts/{contact_id}/generate-email",
    response_model=EmailGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate personalized RAG email draft for a contact using bot knowledge",
)
def generate_email_for_bot_contact(
    bot_id: str,
    contact_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    req: Optional[EmailGenerateRequest] = None,
):
    """
    RAG-driven personalized email generation:
    1. Authenticates current user.
    2. Enforces ownership of both Bot and Contact.
    3. Retrieves website knowledge strictly scoped by bot_id.
    4. Constructs injection-defended prompt with contact attributes.
    5. Returns structured JSON with subject and body.
    """
    return EmailGenerationService.generate_email_for_contact(
        db=db,
        current_user=current_user,
        bot_id=bot_id,
        contact_id=contact_id,
        req=req,
    )


@router.post(
    "/api/campaigns/{campaign_id}/contacts/{contact_id}/generate-email",
    response_model=EmailGenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate personalized RAG email draft within a campaign context",
)
def generate_email_for_campaign_contact(
    campaign_id: str,
    contact_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    req: Optional[EmailGenerateRequest] = None,
):
    """
    Campaign-scoped personalized email generation:
    Retrieves the campaign's associated bot and automatically links the resulting draft.
    """
    req = req or EmailGenerateRequest()
    req.campaign_id = campaign_id

    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.user_id != current_user.id:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return EmailGenerationService.generate_email_for_contact(
        db=db,
        current_user=current_user,
        bot_id=campaign.bot_id,
        contact_id=contact_id,
        req=req,
    )

