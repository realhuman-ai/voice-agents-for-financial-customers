"""
Twilio webhook server — handles inbound call routing to LiveKit SIP.
Run this as a standalone server for production deployments.
"""
import os
import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response
from twilio.request_validator import RequestValidator

load_dotenv()

_twilio_validator = RequestValidator(os.getenv("TWILIO_AUTH_TOKEN", ""))

# Phone number → LiveKit SIP number mapping
PHONE_ROUTES = {
    "+12183962707": "+12183962707",   # Quick Lube → oilchange-agent
    "+15822599600": "+15822599600",   # Biryani Paradise → reservation-agent
}


async def voice_webhook(request: Request):
    """
    Twilio POSTs here when any configured number receives a call.
    Validates the request, then returns TwiML to bridge the call into LiveKit SIP.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    form_data = dict(await request.form())

    if not _twilio_validator.validate(url, form_data, signature):
        return Response(content="Forbidden", status_code=403)

    to_number = form_data.get("To", "").replace(" ", "").replace("-", "")
    sip_domain = os.getenv("LIVEKIT_SIP_TRUNK_URI", "").replace("sip:", "")
    sip_phone = PHONE_ROUTES.get(to_number, os.getenv("TWILIO_PHONE_NUMBER", ""))
    sip_uri = f"sip:{sip_phone}@{sip_domain};transport=tcp"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
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
