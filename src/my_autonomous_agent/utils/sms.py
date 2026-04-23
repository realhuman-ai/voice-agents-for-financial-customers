"""
SMS utility — sends booking confirmation texts via Twilio.
Failures are logged and never raise, so a broken SMS never crashes the agent.
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _normalize_phone(phone: str) -> str:
    """Best-effort E.164 normalization (assumes US if no country code)."""
    cleaned = phone.strip()
    for ch in (" ", "-", "(", ")", ".", "\u2011"):
        cleaned = cleaned.replace(ch, "")
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("1") and len(cleaned) == 11:
        return "+" + cleaned
    if len(cleaned) == 10:
        return "+1" + cleaned
    return cleaned  # pass through and let Twilio reject with a clear error


def send_booking_sms(
    to_phone: str,
    customer_name: str,
    business_name: str,
    from_phone: str,
    date_str: str,
    time_str: str,
    service: str,
) -> bool:
    """
    Send a booking confirmation SMS.
    Returns True on success, False on any failure (never raises).
    """
    if not to_phone or to_phone.strip().lower() in ("", "not provided", "n/a"):
        logger.info("SMS skipped: no customer phone")
        return False

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not account_sid or not auth_token:
        logger.warning("SMS skipped: TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set")
        return False

    to_e164 = _normalize_phone(to_phone)

    try:
        # Human-readable date/time
        try:
            t = datetime.strptime(time_str, "%H:%M")
            display_time = t.strftime("%I:%M %p").lstrip("0")
            d = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = d.strftime("%A, %b %-d")
        except Exception:
            display_time = time_str
            display_date = date_str

        body = (
            f"Hi {customer_name}! Your {service} at {business_name} is confirmed "
            f"for {display_date} at {display_time}. See you then! "
            f"Reply STOP to opt out."
        )

        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(body=body, from_=from_phone, to=to_e164)
        logger.info(f"SMS sent | to={to_e164} | sid={msg.sid}")
        return True

    except Exception as e:
        logger.error(f"SMS failed | to={to_e164} | error={e}")
        return False
