from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
from typing import Optional

from app.db.models.campaign import CampaignEmail

logger = logging.getLogger(__name__)


class EmailSenderProvider(ABC):
    """
    Abstract Email Provider interface.
    Supports pluggable sending backends: MockEmailSenderProvider (default/demo)
    and future SMTP/SendGrid/Postmark providers.
    """
    @abstractmethod
    def send_email(self, email_record: CampaignEmail, recipient_email: str) -> bool:
        pass


class MockEmailSenderProvider(EmailSenderProvider):
    """
    Simulates email dispatch for demo and testing without external SMTP dependencies.
    Records delivery timestamp and transitions status to SENT.
    """
    def send_email(self, email_record: CampaignEmail, recipient_email: str) -> bool:
        logger.info(
            f"[MockEmailSender] Dispatched email '{email_record.subject}' to <{recipient_email}> "
            f"(Email ID: {email_record.id})"
        )
        email_record.status = "SENT"
        email_record.sent_at = datetime.now(timezone.utc)
        return True

