import asyncio
import sys
import logging
import os
import json
from pathlib import Path

# Must be set before any livekit imports on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, JobProcess, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import azure, silero, openai, cartesia

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
RESTAURANT_NAME = "Biryani Paradise"


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

BEFORE EVERY TOOL CALL — always say a natural phrase out loud first, before checking anything:
- Before check_availability: "Oh let me check that for you!" or "One moment, let me see!"
- Before get_available_slots: "Let me see what we have open!" or "Sure, let me check what's available!"
- Before book_appointment: "Perfect, let me get that booked for you!" or "Wonderful, booking that right now!"
Never go silent — always speak first, then call the tool.

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
        return result["message"]
    except Exception as e:
        logger.error(f"book_appointment error: {e}")
        return "I wasn't able to complete the booking right now. Please call us back or try again."


class BiryaniParadiseAgent(Agent):
    def __init__(self):
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
            tools=[check_availability, get_available_slots, book_appointment],
        )

    async def on_enter(self) -> None:
        await self.session.say(
            "Namaste! Thanks for calling Biryani Paradise. "
            "How can I help you today — are you looking to book a table or place an order?",
            allow_interruptions=False,
        )


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

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        min_endpointing_delay=0.2,
        max_endpointing_delay=1.2,
        min_interruption_duration=0.6,
        allow_interruptions=True,
    )

    await session.start(room=ctx.room, agent=BiryaniParadiseAgent())


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="reservation-agent",
        )
    )
