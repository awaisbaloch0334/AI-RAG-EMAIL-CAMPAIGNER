from email.message import EmailMessage
import logging
import smtplib
from typing import Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory store of recently dispatched OTPs for test inspection / offline fallback
_sent_otps_test_cache: Dict[str, str] = {}


def send_otp_email(to_email: str, otp_code: str) -> bool:
    """
    Sends a 6-digit verification OTP to the user's real email address using standard SMTP.
    If SMTP credentials are not configured in settings, falls back to local logging.
    """
    normalized_email = to_email.strip().lower()
    _sent_otps_test_cache[normalized_email] = otp_code

    if (
        not settings.smtp_host
        or not settings.smtp_host.strip()
        or normalized_email.endswith(("@example.com", "@example.org", "@test.com", "@localhost"))
    ):
        logger.info(
            f"[SMTP TEST DOMAIN / LOCAL] OTP for '{normalized_email}' cached: {otp_code}"
        )
        return True

    from_email = settings.smtp_from_email.strip() or settings.smtp_username.strip() or "no-reply@rag-campaigner.io"

    msg = EmailMessage()
    msg["Subject"] = f"Your Verification Code: {otp_code} — AI RAG Campaigner"
    msg["From"] = from_email
    msg["To"] = normalized_email

    plain_content = (
        f"Welcome to AI RAG Email Campaigner!\n\n"
        f"Your verification code is: {otp_code}\n\n"
        f"This code will expire in 10 minutes.\n"
        f"If you did not request this verification code, please ignore this email.\n"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0F1117; color: #FFFFFF; padding: 40px 20px; text-align: center;">
      <div style="max-width: 480px; margin: 0 auto; background-color: #1A1D27; border: 1px solid #2D3343; border-radius: 16px; padding: 32px; box-shadow: 0 8px 24px rgba(0,0,0,0.4);">
        <h2 style="color: #D6A84F; margin-top: 0; font-size: 24px; font-weight: bold;">AI RAG Email Campaigner</h2>
        <p style="color: #9CA3AF; font-size: 14px; margin-bottom: 24px;">Please use the 6-digit verification code below to complete your login or registration.</p>
        <div style="background-color: #0F1117; border: 2px dashed #D6A84F; border-radius: 12px; padding: 18px; margin-bottom: 24px;">
          <span style="font-family: monospace; font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #F0C76A;">{otp_code}</span>
        </div>
        <p style="color: #6B7280; font-size: 12px; margin-bottom: 0;">This code will expire in <strong>10 minutes</strong>.<br>If you did not request this code, no action is needed.</p>
      </div>
    </body>
    </html>
    """

    msg.set_content(plain_content)
    msg.add_alternative(html_content, subtype="html")

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=12.0) as server:
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=12.0) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)

        logger.info(f"Successfully dispatched real OTP email to '{normalized_email}' via {settings.smtp_host}:{settings.smtp_port}")
        return True
    except Exception as e:
        logger.error(f"Failed to dispatch real OTP email to '{normalized_email}' via SMTP: {e}")
        # Return True in development so users are not completely blocked if SMTP has network issues,
        # but the error is prominently logged
        return False


def get_last_sent_otp_for_test(email: str) -> Optional[str]:
    """Helper method for automated tests to inspect the dispatched OTP."""
    return _sent_otps_test_cache.get(email.strip().lower())

