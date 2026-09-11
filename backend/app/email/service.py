import json
import logging
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.bot import Bot
from app.db.models.campaign import Campaign, CampaignEmail
from app.db.models.contact import Contact
from app.db.models.user import User
from app.email.schemas import EmailGenerateRequest, EmailGenerateResponse, GeneratedEmailDraft
from app.llm.client import get_llm_client
from app.rag.email_prompt import EmailPromptBuilder
from app.rag.retriever import VectorRetriever

logger = logging.getLogger(__name__)


class EmailGenerationService:
    @classmethod
    def generate_email_for_contact(
        cls,
        db: Session,
        current_user: User,
        bot_id: str,
        contact_id: str,
        req: Optional[EmailGenerateRequest] = None,
    ) -> EmailGenerateResponse:
        req = req or EmailGenerateRequest()

        # 1. Multi-tenant Authorization Boundary: Verify Bot Ownership
        bot = db.get(Bot, bot_id)
        if not bot or bot.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found",
            )

        # 2. Multi-tenant Authorization Boundary: Verify Contact Ownership
        contact = db.get(Contact, contact_id)
        if not contact or contact.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found",
            )

        # 3. If Campaign ID is specified, verify Campaign Ownership & Bot link
        campaign: Optional[Campaign] = None
        if req.campaign_id:
            campaign = db.get(Campaign, req.campaign_id)
            if not campaign or campaign.user_id != current_user.id or campaign.bot_id != bot.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Campaign not found or does not belong to this bot/user",
                )

        # 4. Formulate Retrieval Query
        query_parts = []
        if req.campaign_goal:
            query_parts.append(req.campaign_goal)
        if contact.role:
            query_parts.append(contact.role)
        if contact.company:
            query_parts.append(contact.company)
        if contact.custom_variables:
            interest = contact.custom_variables.get("interest") or contact.custom_variables.get("industry")
            if interest:
                query_parts.append(str(interest))

        retrieval_query = " ".join(query_parts).strip() or bot.name or "products services features"

        # 5. Retrieve Bot-Scoped Knowledge Chunks
        # CRITICAL INVARIANT: VectorRetriever strictly filters by bot_id == bot.id
        chunks = VectorRetriever.retrieve(
            bot_id=bot.id,
            query=retrieval_query,
            db=db,
            top_k=4,
        )

        # 6. Build Grounded and Injection-Defended Prompts
        system_prompt = EmailPromptBuilder.build_system_prompt(bot)
        user_prompt = EmailPromptBuilder.build_user_prompt(
            contact=contact,
            chunks=chunks,
            campaign_name=campaign.name if campaign else None,
            campaign_goal=req.campaign_goal,
            custom_instructions=req.custom_instructions,
        )

        # 7. Generate Response from LLM Client
        llm_client = get_llm_client()
        try:
            raw_output = llm_client.generate_response(user_prompt, system_prompt=system_prompt)
        except Exception as e:
            logger.warning(f"Email generation with {llm_client.__class__.__name__} failed: {e}. Falling back to grounded RAG generator.")
            from app.llm.client import MockLLMClient
            raw_output = MockLLMClient().generate_response(user_prompt, system_prompt=system_prompt)


        # 8. Robust Structured Parsing
        draft = cls._parse_structured_draft(raw_output, contact, bot)

        # 9. Optionally Persist as CampaignEmail Draft
        campaign_email_id: Optional[str] = None
        if campaign and req.save_draft:
            existing_email = db.scalars(
                select(CampaignEmail).where(
                    CampaignEmail.campaign_id == campaign.id,
                    CampaignEmail.contact_id == contact.id,
                )
            ).first()

            if existing_email:
                existing_email.subject = draft.subject
                existing_email.body = draft.body
                existing_email.status = "GENERATED"
                db.commit()
                db.refresh(existing_email)
                campaign_email_id = existing_email.id
            else:
                camp_email = CampaignEmail(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    subject=draft.subject,
                    body=draft.body,
                    status="GENERATED",
                )
                db.add(camp_email)
                db.commit()
                db.refresh(camp_email)
                campaign_email_id = camp_email.id

        return EmailGenerateResponse(
            subject=draft.subject,
            body=draft.body,
            contact_id=contact.id,
            bot_id=bot.id,
            campaign_id=campaign.id if campaign else None,
            campaign_email_id=campaign_email_id,
            retrieved_chunks_count=len(chunks),
            recipient_name=contact.name,
            recipient_email=contact.email,
            recipient_company=contact.company,
            status="GENERATED",
        )

    @classmethod
    def _parse_structured_draft(
        cls,
        raw_output: str,
        contact: Contact,
        bot: Bot,
    ) -> GeneratedEmailDraft:
        """
        Parses LLM output into a strict GeneratedEmailDraft schema with robust fallbacks.
        Handles raw JSON, markdown-wrapped JSON, and plain-text fallback parsing.
        """
        cleaned = raw_output.strip()

        # Remove markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        # Try direct JSON parse
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "subject" in data and "body" in data:
                return GeneratedEmailDraft(
                    subject=str(data["subject"]).strip(),
                    body=str(data["body"]).strip(),
                )
        except Exception:
            pass

        # Try regex search for JSON inside potential conversational output
        json_match = re.search(r"(\{.*?\})", cleaned, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict) and "subject" in data and "body" in data:
                    return GeneratedEmailDraft(
                        subject=str(data["subject"]).strip(),
                        body=str(data["body"]).strip(),
                    )
            except Exception:
                pass

        # Fallback: Extract Subject line from text
        subj_match = re.search(r"(?:Subject|Re):\s*(.+)", cleaned, re.IGNORECASE)
        if subj_match:
            subject = subj_match.group(1).strip()
            # Remove the subject line from the body
            body = re.sub(r"(?:Subject|Re):\s*.+\n?", "", cleaned, flags=re.IGNORECASE).strip()
            return GeneratedEmailDraft(subject=subject, body=body)

        # Fallback default
        company_ref = contact.company or "your team"
        subject = f"Accelerating growth for {company_ref} with {bot.name}"
        body = cleaned if cleaned else f"Hi {contact.first_name or contact.name},\n\nI'd love to connect regarding how we can support {company_ref}."
        return GeneratedEmailDraft(subject=subject, body=body)

