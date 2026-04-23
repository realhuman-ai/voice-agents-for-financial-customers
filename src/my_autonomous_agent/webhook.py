"""
Twilio webhook server — handles inbound call routing to LiveKit SIP.
Includes spam/abuse protection: anonymous rejection, rate limiting, blocklist.
"""
import os
import time
import logging
import uvicorn
from collections import defaultdict
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response
from twilio.request_validator import RequestValidator

load_dotenv()

logger = logging.getLogger("webhook")

_twilio_validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN", ""))

# Phone number → LiveKit SIP number mapping
PHONE_ROUTES = {
    "+12183962707": "+12183962707",   # Quick Lube → oilchange-agent
    "+15822599600": "+15822599600",   # Biryani Paradise → reservation-agent
}

# ---------------------------------------------------------------------------
# Rate limiter — in-memory (resets on restart; use Redis for production)
# ---------------------------------------------------------------------------
_call_log: dict = defaultdict(list)   # caller → [timestamp, ...]


def _load_security_cfg() -> dict:
    try:
        from my_autonomous_agent.config import load_config
        return load_config().get("security", {})
    except Exception:
        return {}


def _twiml_reject(message: str = "This call cannot be completed.") -> Response:
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{message}</Say>
    <Hangup/>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


def _is_rate_limited(caller: str, max_calls: int, window_seconds: int = 3600) -> bool:
    now = time.time()
    cutoff = now - window_seconds
    recent = [t for t in _call_log[caller] if t > cutoff]
    _call_log[caller] = recent
    if len(recent) >= max_calls:
        return True
    _call_log[caller].append(now)
    return False


async def voice_webhook(request: Request):
    form_data = dict(await request.form())

    # --- Twilio signature validation ---
    if os.getenv("TWILIO_VALIDATE_SIGNATURES", "true").lower() != "false":
        signature = request.headers.get("X-Twilio-Signature", "")
        url = os.getenv("TWILIO_WEBHOOK_URL", str(request.url))
        if not _twilio_validator.validate(url, form_data, signature):
            logger.warning(f"Twilio signature validation failed | url={url}")
            return Response(content="Forbidden", status_code=403)

    caller = form_data.get("From", "").strip()
    to_number = form_data.get("To", "").replace(" ", "").replace("-", "")
    sec = _load_security_cfg()

    # --- Reject anonymous / unknown callers ---
    if sec.get("reject_anonymous_calls", True):
        if not caller or caller.lower() in ("anonymous", "unknown", "restricted", ""):
            logger.warning("Rejected anonymous call")
            return _twiml_reject("Sorry, we are unable to accept calls from anonymous numbers.")

    # --- Blocked number list ---
    blocked: list = sec.get("blocked_numbers", [])
    if caller in blocked:
        logger.warning(f"Rejected blocked number: {caller}")
        return _twiml_reject("This number has been blocked.")

    # --- Rate limiting ---
    max_calls = sec.get("rate_limit_calls_per_hour", 5)
    if _is_rate_limited(caller, max_calls=max_calls):
        logger.warning(f"Rate limit hit for {caller} (>{max_calls}/hr)")
        return _twiml_reject(
            "You have reached the maximum number of calls allowed per hour. Please try again later."
        )

    # --- Route to LiveKit SIP ---
    max_duration = sec.get("max_call_duration_seconds", 600)
    sip_domain = os.getenv("LIVEKIT_SIP_TRUNK_URI", "").replace("sip:", "")
    sip_phone = PHONE_ROUTES.get(to_number, os.getenv("TWILIO_PHONE_NUMBER", ""))
    sip_uri = f"sip:{sip_phone}@{sip_domain};transport=tcp"

    logger.info(f"Routing call | from={caller} | to={to_number} | sip={sip_uri} | max={max_duration}s")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial timeout="30" callTimeout="{max_duration}">
        <Sip>{sip_uri}</Sip>
    </Dial>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


async def health(_request: Request):
    return Response(content="ok", status_code=200)


app = Starlette(
    routes=[
        Route("/twilio/voice", voice_webhook, methods=["POST"]),
        Route("/health", health),
    ]
)


def serve():
    port = int(os.getenv("WEBHOOK_PORT", "8001"))
    print(f"Starting Twilio webhook server at http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    serve()
