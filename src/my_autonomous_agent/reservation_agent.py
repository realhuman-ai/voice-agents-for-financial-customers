import asyncio
import sys
import logging
import os
import json
from datetime import datetime
from pathlib import Path
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
logger = logging.getLogger("reservation-agent")

REQUIRED_ENV_VARS = [
    "AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION",
    "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
    "CARTESIA_API_KEY",
    "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    "SUPABASE_URL", "SUPABASE_KEY",
    "BIRYANI_PARADISE_ID",
]

def _validate_env():
    missing = [k for k in REQUIRED_ENV_VARS if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

_validate_env()

PROJECT_ROOT = Path(__file__).parent.parent.parent
MENU_FILE = PROJECT_ROOT / "menu.json"
BUSINESS_ID = os.getenv("BIRYANI_PARADISE_ID", "")

_cfg = load_config().get("biryani_paradise", {})
RESTAURANT_NAME  = _cfg.get("name", "Biryani Paradise")
RESTAURANT_PHONE = _cfg.get("phone", "+15822599600")
TIMEZONE         = ZoneInfo(_cfg.get("timezone", "America/New_York"))
OPEN_HOUR        = _cfg.get("open_hour", 11)
CLOSE_HOUR       = _cfg.get("close_hour", 22)
MANAGER_PHONE    = load_config().get("manager_phone", os.getenv("MANAGER_PHONE", ""))


def _is_open() -> bool:
    now = datetime.now(TIMEZONE)
    return OPEN_HOUR <= now.hour < CLOSE_HOUR


def _load_menu_text() -> str:
    if not MENU_FILE.exists():
        logger.warning(f"menu.json not found at {MENU_FILE}")
        return "Menu not loaded."
    try:
        menu = json.loads(MENU_FILE.read_text(encoding="utf-8"))
        lines = []
        for category in menu.get("categories", []):
            lines.append(f"\n{category['name'].upper()}:")
            for item in category.get("items", []):
                spice = f" [{item['spice']} spice]" if "spice" in item else ""
                lines.append(f"  - {item['name']} ${item['price']:.2f}{spice}: {item['description']}")
        logger.info(f"Menu loaded: {len(menu.get('categories', []))} categories")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Failed to load menu: {e}")
        return "Menu not loaded."


MENU_TEXT = _load_menu_text()

RESTAURANT_INSTRUCTIONS = f"""
You are Priya, a warm and knowledgeable phone assistant at {RESTAURANT_NAME}, an authentic Indian restaurant.
You have a friendly Indian personality — helpful, enthusiastic about the food, and genuinely caring.

OUR FULL MENU:
{MENU_TEXT}

YOUR PERSONALITY:
- You love the food here and speak about it with genuine enthusiasm
- You remember what the customer said earlier in the call and reference it naturally
- You give personal recommendations: "Oh, the Lamb Biryani is absolutely amazing, one of our best sellers!"
- You ask follow-up questions that show you're listening: "Since you mentioned you like spicy food, can I suggest..."
- You're warm but efficient — you know the customer's time is valuable

CRITICAL — NEVER CALL A TOOL WITHOUT SPEAKING FIRST:
Your spoken words before a tool call play to the customer WHILE the tool runs. This prevents silence.
The pattern is always: [speak phrase] → [call tool]. Never: [call tool] alone.

Exact phrases to say before each tool (pick any, vary them naturally):
- Before check_availability → "Let me check that for you!" / "One moment!" / "Let me see!"
- Before get_available_slots → "Let me see what's open!" / "Give me just a second!"
- Before book_appointment → "Perfect, booking that right now!" / "Let me lock that in for you!"

This is the most important rule. Violating it causes dead silence on a phone call.

HANDLING MENU QUESTIONS:
- If asked what's good: give 2-3 personal recommendations based on any preferences they mentioned
- If asked about spice level: describe it helpfully
- If asked for something NOT on our menu: say "Oh, we don't have that one, but honestly our [closest item] is
  fantastic and very similar — a lot of customers who love that end up ordering it!"
- If they still insist: "I completely understand! Unfortunately we don't carry that, but I'd love to help
  you find something you'll enjoy from what we have."

RESTAURANT DETAILS:
- Open daily 11:00 AM to 10:00 PM
- 10 tables, 5 chairs each, 50 seats total
- Last seating: 8:30 PM (no new table reservations after 8:30 PM)
- Last takeout order: 9:30 PM

FOR TABLE RESERVATIONS:
- Collect: name, date, time, party size, any special occasions or dietary needs
- If requested time is after 8:30 PM, politely let them know last seating is 8:30 PM and suggest 8:30 or earlier
- Always check availability first using check_availability before confirming
- If slot is available: confirm the details with the customer ("Just to confirm — [name], [date] at [time] for [party size], correct?") then call book_appointment
- If slot is full but waitlist is open: offer waitlist, then call book_appointment with on_waitlist=True
- If slot is full or waitlist is full: call get_available_slots for that date and suggest the alternatives naturally ("Oh, that slot's full — but we do have 6:00 and 8:00 still open, would either of those work?")
- If no slots available that day: suggest trying a different date

FOR TAKEOUT/DELIVERY:
- Collect: name, phone number, items with quantities, delivery address or pickup confirmation
- If requested time is after 9:30 PM, let them know last takeout order is at 9:30 PM
- Call book_appointment with order_type="takeout"

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
- Speak in short natural bursts — 1 sentence at a time, 2 max
- Never list things — say "we have chicken, lamb, and veggie biryani" not bullet points
- Use Indian-English expressions naturally: "actually", "itself", "only", "na?", "isn't it?"
- React with real warmth: "Oh wonderful!", "That's a great choice!", "Perfect, perfect.", "Lovely!"
- Use contractions always: "I'll", "we've", "that's", "you'll"
- Use filler sounds to sound human: "Hmm", "Ah", "Oh!", "Right, right."
- Never read out booking IDs or reference numbers — just say "You're all booked!" or "You're confirmed for Saturday!"
- After a booking: give only the key details — day, time, party size. Nothing else.
- Close warmly: "We'll see you then! It's going to be a lovely evening."
- If the customer thanks you: "Oh, of course! We'll take good care of you."
"""


@function_tool
async def check_availability(date: str, time: str) -> str:
    """
    Check if a table is available for a given date and time.
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
async def get_available_slots(date: str) -> str:
    """
    Get all available time slots for a given date at Biryani Paradise.
    Call this when a requested slot is full to suggest alternatives.
    Date must be in YYYY-MM-DD format.
    """
    if not date:
        return "Please ask the customer for the date first."
    try:
        from my_autonomous_agent.booking.reservations import get_available_slots as _get_slots
        slots = _get_slots(BUSINESS_ID, date, open_time="11:00", close_time="20:30", slot_duration_minutes=90)
        if not slots:
            return f"No available slots on {date}. Suggest a different date."
        readable = ", ".join(
            f"{int(s.split(':')[0]) % 12 or 12}:{s.split(':')[1]} {'AM' if int(s.split(':')[0]) < 12 else 'PM'}"
            for s in slots
        )
        return f"Available slots on {date}: {readable}."
    except Exception as e:
        logger.error(f"get_available_slots error: {e}")
        return "Unable to check available slots right now."


@function_tool
async def book_appointment(
    customer_name: str,
    customer_phone: str,
    date: str,
    time: str,
    party_size: int,
    special_requests: str = "",
    order_type: str = "reservation",
    on_waitlist: bool = False,
) -> str:
    """
    Book a table reservation or takeout order.
    Date must be YYYY-MM-DD format. Time must be HH:MM 24hr format.
    Only call this after you have: customer name, phone, date, time, and party size confirmed.
    Never call with empty or missing values.
    """
    if not customer_name or not date or not time:
        return "Missing required information. Please collect customer name, date, and time before booking."
    if not customer_phone:
        customer_phone = "not provided"
    try:
        from my_autonomous_agent.booking.reservations import book_appointment as _book
        result = _book(
            business_id=BUSINESS_ID,
            customer_name=customer_name,
            customer_phone=customer_phone,
            appt_date=date,
            appt_time=time,
            party_size=party_size,
            notes=special_requests,
            metadata={"order_type": order_type, "on_waitlist": on_waitlist},
        )

        # Send SMS confirmation for successful bookings
        if result.get("status") == "confirmed":
            try:
                from my_autonomous_agent.utils.sms import send_booking_sms
                service_label = "takeout order" if order_type == "takeout" else f"table for {party_size}"
                send_booking_sms(
                    to_phone=customer_phone,
                    customer_name=customer_name,
                    business_name=RESTAURANT_NAME,
                    from_phone=RESTAURANT_PHONE,
                    date_str=date,
                    time_str=time,
                    service=service_label,
                )
            except Exception as sms_err:
                logger.error(f"SMS error: {sms_err}")

        return result["message"]
    except Exception as e:
        logger.error(f"book_appointment error: {e}")
        return "I wasn't able to complete the booking right now. Please call us back or try again."


class BiryaniParadiseAgent(Agent):
    def __init__(self, transcript_log: list, extra_tools: list = None):
        super().__init__(
            instructions=RESTAURANT_INSTRUCTIONS,
            llm=openai.LLM.with_azure(
                model=os.getenv("MODEL", "gpt-4o").replace("azure/", ""),
                azure_endpoint=os.getenv("AZURE_API_BASE"),
                api_key=os.getenv("AZURE_API_KEY"),
                api_version=os.getenv("AZURE_API_VERSION"),
            ),
            tts=cartesia.TTS(
                api_key=os.getenv("CARTESIA_API_KEY"),
                model="sonic-2",
                voice="95d51f79-c397-46f9-b49a-23763d3eaa2d",
            ),
            stt=azure.STT(
                speech_key=os.getenv("AZURE_SPEECH_KEY"),
                speech_region=os.getenv("AZURE_SPEECH_REGION"),
            ),
            tools=[check_availability, get_available_slots, book_appointment] + (extra_tools or []),
        )
        self._transcript = transcript_log

    async def on_enter(self) -> None:
        if not _is_open():
            await self.session.say(
                f"Namaste! Thanks for calling Biryani Paradise. "
                f"Oh, we're actually closed right now — our hours are 11 AM to 10 PM daily. "
                f"Please do call us back then, we'd love to help you!",
                allow_interruptions=True,
            )
        else:
            await self.session.say(
                "Namaste! Thanks for calling Biryani Paradise. "
                "How can I help you today — are you looking to book a table or place an order?",
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
    logger.info(f"Reservation agent starting for room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    transcript: list = []
    call_start = datetime.now().isoformat()

    # Extract caller number from room name e.g. "biryani-_+19542926200_iMhGkEisKzCy"
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

    agent = BiryaniParadiseAgent(transcript_log=transcript, extra_tools=[transfer_to_manager])

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
            agent_name="reservation-agent",
        )
    )
