import asyncio
import sys
import logging
import os

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
SHOP_NAME = "Golden Wrench Auto services"

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
        return result["message"]
    except Exception as e:
        logger.error(f"book_appointment error: {e}")
        return "I wasn't able to complete the booking. Please try again."


class QuickLubeAgent(Agent):
    def __init__(self):
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
            tools=[check_availability, book_appointment],
        )

    async def on_enter(self) -> None:
        await self.session.say(
            "Hey, thanks for calling Quick Lube! This is Mike. "
            "Are you looking to book an appointment or do you have a question about our services?",
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
    logger.info(f"Oil change agent starting for room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        min_endpointing_delay=0.2,
        max_endpointing_delay=1.2,
        min_interruption_duration=0.6,
        allow_interruptions=True,
    )

    await session.start(room=ctx.room, agent=QuickLubeAgent())


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="oilchange-agent",
        )
    )
