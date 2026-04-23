import asyncio
import sys
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Must be set before any livekit imports on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import azure, silero, openai, cartesia
from my_autonomous_agent.config import load_config

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oilchange-agent")

REQUIRED_ENV_VARS = [
    "AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION",
    "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
    "CARTESIA_API_KEY",
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    "SUPABASE_URL", "SUPABASE_KEY",
    "QUICK_LUBE_ID",
]

def _validate_env():
    missing = [k for k in REQUIRED_ENV_VARS if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

_validate_env()

BUSINESS_ID = os.getenv("QUICK_LUBE_ID", "")

_cfg = load_config().get("quick_lube", {})
SHOP_NAME   = _cfg.get("name", "Golden Wrench Auto services")
SHOP_PHONE  = _cfg.get("phone", "+12183962707")
TIMEZONE    = ZoneInfo(_cfg.get("timezone", "America/New_York"))
OPEN_DAYS   = set(_cfg.get("open_days", [0, 1, 2, 3, 4, 5]))
OPEN_HOUR   = _cfg.get("open_hour", 8)
CLOSE_HOUR  = _cfg.get("close_hour", 18)
MANAGER_PHONE = load_config().get("manager_phone", os.getenv("MANAGER_PHONE", ""))


def _is_open() -> bool:
    now = datetime.now(TIMEZONE)
    return now.weekday() in OPEN_DAYS and OPEN_HOUR <= now.hour < CLOSE_HOUR


AGENT_INSTRUCTIONS = f"""
You are Mike, a friendly and efficient phone assistant at {SHOP_NAME}, a fast oil change and auto service shop.
You're knowledgeable about cars, approachable, and get to the point — customers usually call on the go.

YOUR SERVICES & PRICING:
- Standard Oil Change (conventional): $29.99 — up to 5 quarts, filter included
- Synthetic Oil Change: $59.99 — full synthetic, up to 5 quarts, filter included
- Full-Synthetic High Mileage (75k+ miles): $69.99
- Tire Rotation: $19.99 (free with any oil change)
- Air Filter Replacement: $24.99
- Cabin Filter Replacement: $29.99
- Multi-Point Inspection: FREE with every service

HOURS: Monday–Saturday 8:00 AM – 6:00 PM, Closed Sunday
AVERAGE WAIT TIME: 30–45 minutes, no appointment needed (but appointments get priority)

YOUR PERSONALITY:
- Friendly and no-nonsense — customers want quick answers
- Give honest recommendations: "With 80k miles on it, I'd go synthetic high-mileage, it's worth it"
- Don't oversell — if they just need a basic oil change, say so
- Use casual, confident tone: "Yeah, absolutely", "No problem at all", "We can take care of that"

HANDLING SERVICE QUESTIONS:
- If they ask what oil is best: ask mileage, then recommend accordingly
- If they ask about wait times: "Usually 30–45 minutes, and if you book ahead you get priority lane"
- If they just want to drop in: "Yeah, walk-ins are always welcome — appointments just skip the line"

HANDLING CAR DIAGNOSTIC / ERROR CODES (OBD-II / DTC codes):
You are knowledgeable about car diagnostic codes. When a customer mentions a code like P0420, P0171, P0300 etc:
- Explain what the code means in plain, simple English — no jargon
- Say how serious it is: minor, moderate, or urgent
- Tell them whether it's something we can help with at Golden Wrench (oil, filters, fluids) or if they need a specialist mechanic
- Always recommend they come in for our FREE multi-point inspection if there's any doubt

COMMON CODE EXAMPLES TO GUIDE YOUR ANSWERS:
- P0171 / P0174 (System Too Lean): Often a dirty MAF sensor, vacuum leak, or clogged fuel injector. Moderate — come in for inspection.
- P0300–P0308 (Misfire): Could be spark plugs, ignition coils, or bad fuel. Moderate to urgent depending on severity.
- P0420 / P0430 (Catalyst Efficiency): Catalytic converter issue. Needs a specialist — we can't fix this but can inspect and refer.
- P0401 (EGR Flow Insufficient): EGR valve issue, needs a specialist mechanic.
- P0113 (IAT Sensor High): Air intake temp sensor — usually minor, sometimes just a loose connector.
- P0507 (Idle Control High): Idle air control valve. Moderate — come in for inspection.
- B-codes (Body), C-codes (Chassis), U-codes (Network): These are typically electrical/sensor issues. Refer to a specialist.

ACCURACY RULE: If you're not fully confident about a specific code, say "That one's a bit unusual — I'd recommend having a mechanic scan it properly, but here's what I know about it..." Never guess or make up information. It's okay to say you're not sure and recommend a full diagnostic scan.

FOR APPOINTMENTS:
- Collect: customer name, phone number, vehicle (year, make, model), service needed, preferred date and time
- Always check availability first using check_availability before confirming
- If slot available: call book_appointment to confirm
- If slot full but waitlist open: offer waitlist, call book_appointment with on_waitlist=True
- If waitlist full: suggest next available time

BEFORE EVERY TOOL CALL — always say something natural first before checking anything:
- Before check_availability: "Let me check that for you!" or "One sec, let me look!"
- Before book_appointment: "Perfect, getting that booked right now!" or "Let me lock that in!"
Never go silent — always speak first, then call the tool.

ESCALATION / CALL TRANSFER:
You can transfer the call to a manager using the transfer_to_manager tool.
When to escalate:
- Customer explicitly asks for a manager or supervisor
- Customer is frustrated and two attempts to resolve haven't helped
- The issue is outside your scope (refund, complaint, dispute, pricing exception)

Before calling transfer_to_manager, always say something like:
"Of course, let me get our manager on the line for you. Just one moment!"

If the transfer fails, say:
"I'm sorry, our manager isn't available right now. Can I take your name and number and have them call you right back?"

VOICE RULES:
- Short, natural sentences — 1 to 2 at a time
- No bullet points or lists — speak it out
- Use filler sounds: "Hmm", "Yeah", "Sure thing", "Alright"
- React naturally: "Oh nice!", "Good choice!", "Yeah absolutely."
- Never read out booking IDs — just say "You're all set!" or "You're booked for Thursday!"
- After booking: just say the day, time, and service. Nothing else.
- Close with: "See you then — we'll get you in and out quick!"
- If they thank you: "Of course! See you soon."
"""


@function_tool
async def check_availability(date: str, time: str) -> str:
    """
    Check if an appointment slot is available for a given date and time.
    Date must be in YYYY-MM-DD format. Time must be in HH:MM 24hr format.
    Only call this once you have confirmed the exact date and time from the customer.
    """
    if not date or not time:
        return "Please ask the customer for the date and time before checking availability."
    try:
        from my_autonomous_agent.booking.reservations import check_availability as _check
        result = _check(BUSINESS_ID, date, time)
        if result["available"]:
            return f"Available! {result['slots_left']} slot(s) open for {date} at {time}."
        elif not result["waitlist_full"]:
            return f"Fully booked for {date} at {time}. Waitlist has {result['waitlist_count']} of 5 spots taken — I can add them to the waitlist."
        else:
            return f"Fully booked for {date} at {time} and waitlist is full. Please suggest a different time."
    except Exception as e:
        logger.error(f"check_availability error: {e}")
        return "Unable to check availability right now. Please proceed with the booking."


@function_tool
async def book_appointment(
    customer_name: str,
    customer_phone: str,
    date: str,
    time: str,
    vehicle: str,
    service_requested: str = "oil change",
    on_waitlist: bool = False,
) -> str:
    """
    Book a service appointment.
    Date must be YYYY-MM-DD format. Time must be HH:MM 24hr format.
    Vehicle should be formatted as 'YEAR MAKE MODEL' e.g. '2019 Toyota Camry'.
    Only call this after you have: customer name, phone, date, time, and vehicle confirmed.
    Never call with empty or missing values.
    """
    if not customer_name or not date or not time:
        return "Missing required information. Please collect customer name, date, and time before booking."
    if not customer_phone:
        customer_phone = "not provided"
    if not vehicle:
        vehicle = "not provided"
    try:
        from my_autonomous_agent.booking.reservations import book_appointment as _book
        result = _book(
            business_id=BUSINESS_ID,
            customer_name=customer_name,
            customer_phone=customer_phone,
            appt_date=date,
            appt_time=time,
            party_size=1,
            notes=f"Vehicle: {vehicle} | Service: {service_requested}",
            metadata={"vehicle": vehicle, "service": service_requested, "on_waitlist": on_waitlist},
        )

        # Send SMS confirmation for successful bookings
        if result.get("status") == "confirmed":
            try:
                from my_autonomous_agent.utils.sms import send_booking_sms
                send_booking_sms(
                    to_phone=customer_phone,
                    customer_name=customer_name,
                    business_name=SHOP_NAME,
                    from_phone=SHOP_PHONE,
                    date_str=date,
                    time_str=time,
                    service=service_requested,
                )
            except Exception as sms_err:
                logger.error(f"SMS error: {sms_err}")

        return result["message"]
    except Exception as e:
        logger.error(f"book_appointment error: {e}")
        return "I wasn't able to complete the booking. Please try again."


class QuickLubeAgent(Agent):
    def __init__(self, transcript_log: list, extra_tools: list = None):
        super().__init__(
            instructions=AGENT_INSTRUCTIONS,
            llm=openai.LLM.with_azure(
                model=os.getenv("MODEL", "gpt-4o").replace("azure/", ""),
                azure_endpoint=os.getenv("AZURE_API_BASE"),
                api_key=os.getenv("AZURE_API_KEY"),
                api_version=os.getenv("AZURE_API_VERSION"),
            ),
            tts=cartesia.TTS(
                api_key=os.getenv("CARTESIA_API_KEY"),
                model="sonic-2",
                voice="a5136bf9-224c-4d76-b823-52bd5efcffcc",
            ),
            stt=azure.STT(
                speech_key=os.getenv("AZURE_SPEECH_KEY"),
                speech_region=os.getenv("AZURE_SPEECH_REGION"),
            ),
            tools=[check_availability, book_appointment] + (extra_tools or []),
        )
        self._transcript = transcript_log

    async def on_enter(self) -> None:
        if not _is_open():
            now = datetime.now(TIMEZONE)
            day_name = now.strftime("%A")
            await self.session.say(
                f"Hey, thanks for calling Golden Wrench! Unfortunately we're closed right now — "
                f"it's {day_name} and our hours are Monday through Saturday, 8 AM to 6 PM. "
                f"Give us a call back then, or I can take your name and number and we'll reach out first thing!",
                allow_interruptions=True,
            )
        else:
            await self.session.say(
                "Hey, thanks for calling Quick Lube! This is Mike. "
                "Are you looking to book an appointment or do you have a question about our services?",
                allow_interruptions=True,
            )

    async def on_user_turn_completed(self, turn_ctx=None, new_message=None) -> None:
        """Capture user turns for transcript."""
        if new_message and hasattr(new_message, "content"):
            content = new_message.content
            if isinstance(content, list):
                text = " ".join(getattr(c, "text", "") for c in content if hasattr(c, "text"))
            else:
                text = str(content)
            if text.strip():
                self._transcript.append({
                    "role": "user",
                    "text": text.strip(),
                    "ts": datetime.now().isoformat(),
                })


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load(
        activation_threshold=0.7,
        min_speech_duration=0.2,
        min_silence_duration=0.8,
        prefix_padding_duration=0.3,
    )


async def entrypoint(ctx: JobContext):
    logger.info(f"Oil change agent starting for room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    transcript: list = []
    call_start = datetime.now().isoformat()

    # Extract caller number from room name e.g. "lube-_+19542926200_iMhGkEisKzCy"
    caller_number = ""
    room_name = ctx.room.name
    if "_+" in room_name:
        parts = room_name.split("_+")
        if len(parts) > 1:
            caller_number = "+" + parts[1].split("_")[0]

    @function_tool
    async def transfer_to_manager() -> str:
        """
        Transfer the call to a manager or supervisor.
        Only call this when the customer requests a manager, or after two failed
        attempts to resolve a complaint/dispute yourself.
        Always say a handoff phrase out loud before calling this tool.
        """
        if not MANAGER_PHONE:
            return "Manager phone not configured. Take a message and promise a callback."

        sip_participant = next(iter(ctx.room.remote_participants.values()), None)
        if not sip_participant:
            return "No active caller found to transfer."

        try:
            from livekit import api as lk_api
            lk = lk_api.LiveKitAPI(
                url=os.getenv("LIVEKIT_URL"),
                api_key=os.getenv("LIVEKIT_API_KEY"),
                api_secret=os.getenv("LIVEKIT_API_SECRET"),
            )
            await lk.sip.transfer_sip_participant(
                lk_api.TransferSIPParticipantRequest(
                    room_name=ctx.room.name,
                    participant_identity=sip_participant.identity,
                    transfer_to=f"tel:{MANAGER_PHONE}",
                )
            )
            await lk.aclose()
            logger.info(f"SIP transfer initiated to {MANAGER_PHONE}")
            return "Transfer initiated. The call is being connected to the manager."
        except Exception as e:
            logger.error(f"SIP transfer failed: {e}")
            return "Transfer failed. Please take the customer's name and number and promise a callback."

    agent = QuickLubeAgent(transcript_log=transcript, extra_tools=[transfer_to_manager])

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        min_endpointing_delay=0.2,
        max_endpointing_delay=1.2,
        min_interruption_duration=0.3,
        allow_interruptions=True,
    )

    @ctx.room.on("disconnected")
    def on_room_disconnected(*_args):
        ended_at = datetime.now().isoformat()
        logger.info(f"Room disconnected — saving transcript ({len(transcript)} turns)")
        try:
            from my_autonomous_agent.booking.reservations import save_transcript as _save
            _save(
                business_id=BUSINESS_ID,
                room_name=room_name,
                caller_number=caller_number,
                transcript=transcript,
                started_at=call_start,
                ended_at=ended_at,
            )
        except Exception as e:
            logger.error(f"Transcript save error: {e}")

    await session.start(room=ctx.room, agent=agent)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="oilchange-agent",
        )
    )
