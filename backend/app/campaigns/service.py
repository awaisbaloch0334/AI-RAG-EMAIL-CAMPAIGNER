import logging
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.campaigns.provider import EmailSenderProvider, MockEmailSenderProvider
from app.campaigns.schemas import (
    CampaignAddContactsRequest,
    CampaignCreateRequest,
    CampaignDetailResponse,
    CampaignEmailResponse,
    CampaignGenerateAllRequest,
    CampaignSendResponse,
    CampaignSummaryResponse,
    CampaignUpdateRequest,
)
from app.db.models.bot import Bot
from app.db.models.campaign import Campaign, CampaignEmail
from app.db.models.contact import Contact
from app.db.models.user import User
from app.email.schemas import EmailGenerateRequest
from app.email.service import EmailGenerationService

logger = logging.getLogger(__name__)


class CampaignService:
    @staticmethod
    def create_campaign(
        db: Session,
        current_user: User,
        req: CampaignCreateRequest,
    ) -> Campaign:
        # 1. Authorization: Verify user owns the knowledge bot
        bot = db.get(Bot, req.bot_id)
        if not bot or bot.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found or not owned by user",
            )

        # 2. Create campaign
        campaign = Campaign(
            user_id=current_user.id,
            bot_id=bot.id,
            name=req.name.strip(),
            status="DRAFT",
        )
        db.add(campaign)
        db.flush()

        # 3. Add initial contacts if requested
        if req.contact_ids:
            for cid in req.contact_ids:
                contact = db.get(Contact, cid)
                if not contact or contact.user_id != current_user.id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Contact '{cid}' not found or not owned by user",
                    )
                email_record = CampaignEmail(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    status="PENDING",
                )
                db.add(email_record)

        db.commit()
        db.refresh(campaign)
        return campaign

    @staticmethod
    def list_campaigns_for_user(
        db: Session,
        user_id: str,
    ) -> List[CampaignSummaryResponse]:
        stmt = (
            select(Campaign)
            .where(Campaign.user_id == user_id)
            .order_by(Campaign.created_at.desc())
        )
        campaigns = db.scalars(stmt).all()
        summaries: List[CampaignSummaryResponse] = []

        for camp in campaigns:
            total = len(camp.campaign_emails)
            sent = sum(1 for e in camp.campaign_emails if e.status == "SENT")
            summaries.append(
                CampaignSummaryResponse(
                    id=camp.id,
                    user_id=camp.user_id,
                    bot_id=camp.bot_id,
                    bot_name=camp.bot.name if camp.bot else None,
                    name=camp.name,
                    status=camp.status,
                    total_emails=total,
                    sent_emails=sent,
                    created_at=camp.created_at,
                    updated_at=camp.updated_at,
                )
            )
        return summaries

    @staticmethod
    def get_campaign_detail(
        db: Session,
        user_id: str,
        campaign_id: str,
    ) -> Optional[CampaignDetailResponse]:
        stmt = (
            select(Campaign)
            .where(Campaign.id == campaign_id, Campaign.user_id == user_id)
        )
        camp = db.scalars(stmt).first()
        if not camp:
            return None

        total = len(camp.campaign_emails)
        sent = sum(1 for e in camp.campaign_emails if e.status == "SENT")

        emails: List[CampaignEmailResponse] = []
        for e in camp.campaign_emails:
            contact = e.contact
            emails.append(
                CampaignEmailResponse(
                    id=e.id,
                    campaign_id=e.campaign_id,
                    contact_id=e.contact_id,
                    contact_name=contact.name if contact else None,
                    contact_email=contact.email if contact else None,
                    contact_company=contact.company if contact else None,
                    contact_role=contact.role if contact else None,
                    subject=e.subject,
                    body=e.body,
                    status=e.status,
                    created_at=e.created_at,
                    sent_at=e.sent_at,
                )
            )

        return CampaignDetailResponse(
            id=camp.id,
            user_id=camp.user_id,
            bot_id=camp.bot_id,
            bot_name=camp.bot.name if camp.bot else None,
            name=camp.name,
            status=camp.status,
            total_emails=total,
            sent_emails=sent,
            created_at=camp.created_at,
            updated_at=camp.updated_at,
            emails=emails,
        )

    @staticmethod
    def add_contacts_to_campaign(
        db: Session,
        current_user: User,
        campaign_id: str,
        req: CampaignAddContactsRequest,
    ) -> CampaignDetailResponse:
        camp = db.get(Campaign, campaign_id)
        if not camp or camp.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        existing_cids = {e.contact_id for e in camp.campaign_emails}

        for cid in req.contact_ids:
            if cid in existing_cids:
                continue
            contact = db.get(Contact, cid)
            if not contact or contact.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Contact '{cid}' not found or not owned by user",
                )
            new_email = CampaignEmail(
                campaign_id=camp.id,
                contact_id=contact.id,
                status="PENDING",
            )
            db.add(new_email)

        db.commit()
        db.refresh(camp)
        return CampaignService.get_campaign_detail(db, current_user.id, camp.id)

    @staticmethod
    def generate_all_emails(
        db: Session,
        current_user: User,
        campaign_id: str,
        req: Optional[CampaignGenerateAllRequest] = None,
    ) -> CampaignDetailResponse:
        camp = db.get(Campaign, campaign_id)
        if not camp or camp.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        camp.status = "GENERATING"
        db.commit()

        for email_record in camp.campaign_emails:
            gen_req = EmailGenerateRequest(
                campaign_id=camp.id,
                campaign_goal=req.campaign_goal if req else None,
                custom_instructions=req.custom_instructions if req else None,
                save_draft=True,
            )
            try:
                # Invoke RAG email generator for this contact
                EmailGenerationService.generate_email_for_contact(
                    db=db,
                    current_user=current_user,
                    bot_id=camp.bot_id,
                    contact_id=email_record.contact_id,
                    req=gen_req,
                )
            except Exception as e:
                logger.error(f"Failed to generate draft for contact {email_record.contact_id}: {e}")

        camp.status = "READY"

        db.commit()
        db.refresh(camp)
        return CampaignService.get_campaign_detail(db, current_user.id, camp.id)

    @staticmethod
    def send_campaign(
        db: Session,
        current_user: User,
        campaign_id: str,
        provider: Optional[EmailSenderProvider] = None,
    ) -> CampaignSendResponse:
        camp = db.get(Campaign, campaign_id)
        if not camp or camp.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        if provider is None:
            provider = MockEmailSenderProvider()

        camp.status = "SENDING"
        db.commit()

        sent_count = 0
        for email_record in camp.campaign_emails:
            # Auto-generate if still pending
            if not email_record.subject or not email_record.body:
                gen_req = EmailGenerateRequest(
                    campaign_id=camp.id,
                    save_draft=True,
                )
                EmailGenerationService.generate_email_for_contact(
                    db=db,
                    current_user=current_user,
                    bot_id=camp.bot_id,
                    contact_id=email_record.contact_id,
                    req=gen_req,
                )

            recipient_email = email_record.contact.email if email_record.contact else "unknown@example.com"
            success = provider.send_email(email_record, recipient_email)
            if success:
                sent_count += 1

        camp.status = "COMPLETED"
        db.commit()

        return CampaignSendResponse(
            campaign_id=camp.id,
            status="COMPLETED",
            emails_sent=sent_count,
            message=f"Campaign '{camp.name}' dispatched. {sent_count} emails marked as SENT.",
        )

    @staticmethod
    def delete_campaign(
        db: Session,
        user_id: str,
        campaign_id: str,
    ) -> bool:
        camp = db.scalars(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.user_id == user_id,
            )
        ).first()
        if not camp:
            return False

        db.delete(camp)
        db.commit()
        return True

    @staticmethod
    def update_campaign_email(
        db: Session,
        current_user: User,
        campaign_id: str,
        email_id: str,
        subject: str,
        body: str,
    ) -> CampaignDetailResponse:
        camp = db.get(Campaign, campaign_id)
        if not camp or camp.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        email = db.get(CampaignEmail, email_id)
        if not email or email.campaign_id != camp.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign email not found",
            )

        email.subject = subject.strip()
        email.body = body.strip()
        email.status = "GENERATED"
        db.commit()
        db.refresh(email)
        return CampaignService.get_campaign_detail(db, current_user.id, camp.id)

    @staticmethod
    def apply_template_to_all_emails(
        db: Session,
        current_user: User,
        campaign_id: str,
        subject_template: str,
        body_template: str,
        source_contact_id: Optional[str] = None,
    ) -> CampaignDetailResponse:
        camp = db.get(Campaign, campaign_id)
        if not camp or camp.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found",
            )

        source_contact = db.get(Contact, source_contact_id) if source_contact_id else None

        for email in camp.campaign_emails:
            contact = email.contact
            if not contact:
                continue

            s = subject_template
            b = body_template

            if source_contact:
                if source_contact.name:
                    s = s.replace(source_contact.name, "{{name}}")
                    b = b.replace(source_contact.name, "{{name}}")
                if source_contact.first_name:
                    s = s.replace(source_contact.first_name, "{{first_name}}")
                    b = b.replace(source_contact.first_name, "{{first_name}}")
                if source_contact.company:
                    s = s.replace(source_contact.company, "{{company}}")
                    b = b.replace(source_contact.company, "{{company}}")
                if source_contact.role:
                    s = s.replace(source_contact.role, "{{role}}")
                    b = b.replace(source_contact.role, "{{role}}")

            rec_name = contact.name or contact.email or "Colleague"
            rec_first = contact.first_name or (contact.name.split()[0] if contact.name else "there")
            rec_comp = contact.company or "your company"
            rec_role = contact.role or "team"

            final_s = (
                s.replace("{{name}}", rec_name)
                .replace("{name}", rec_name)
                .replace("{{first_name}}", rec_first)
                .replace("{first_name}", rec_first)
                .replace("{{company}}", rec_comp)
                .replace("{company}", rec_comp)
                .replace("{{role}}", rec_role)
                .replace("{role}", rec_role)
            )

            final_b = (
                b.replace("{{name}}", rec_name)
                .replace("{name}", rec_name)
                .replace("{{first_name}}", rec_first)
                .replace("{first_name}", rec_first)
                .replace("{{company}}", rec_comp)
                .replace("{company}", rec_comp)
                .replace("{{role}}", rec_role)
                .replace("{role}", rec_role)
            )

            email.subject = final_s.strip()
            email.body = final_b.strip()
            email.status = "GENERATED"

        db.commit()
        return CampaignService.get_campaign_detail(db, current_user.id, camp.id)


