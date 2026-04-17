# Voice Agents Platform — Architecture

A multi-tenant AI voice agent platform where businesses receive phone calls handled by intelligent voice agents. Each agent books appointments, answers questions, and manages waitlists — all backed by a shared Supabase database.

## System Architecture

```mermaid
graph TD
    Caller["📞 Caller"] -->|dials Twilio number| Twilio["Twilio\nPhone Numbers"]

    Twilio -->|POST webhook| ngrok["ngrok\nHTTPS Tunnel"]
    ngrok --> API["API Server\nStarlette / uvicorn\nport 8000"]

    API -->|TwiML: dial SIP URI| Twilio
    Twilio -->|SIP INVITE| LiveKitSIP["LiveKit SIP Gateway\n23kaxjikuwa.sip.livekit.cloud"]

    LiveKitSIP -->|match trunk + dispatch rule| Router{"LiveKit\nDispatch Rules"}

    Router -->|+1 582 259 9600| ResvAgent["reservation-agent\n🍛 Biryani Paradise"]
    Router -->|+1 218 396 2707| LubeAgent["oilchange-agent\n🔧 Golden Wrench Auto"]

    ResvAgent --> Pipeline1["Voice Pipeline\nSTT → LLM → TTS"]
    LubeAgent --> Pipeline2["Voice Pipeline\nSTT → LLM → TTS"]

    Pipeline1 --> STT1["Azure Speech STT"]
    Pipeline1 --> LLM1["Azure OpenAI\nGPT-4o"]
    Pipeline1 --> TTS1["Cartesia TTS\nPriya — Indian English"]

    Pipeline2 --> STT2["Azure Speech STT"]
    Pipeline2 --> LLM2["Azure OpenAI\nGPT-4o"]
    Pipeline2 --> TTS2["Cartesia TTS\nMike — Casual English"]

    ResvAgent -->|check_availability\nget_available_slots\nbook_appointment| Supabase["Supabase\nPostgreSQL"]
    LubeAgent -->|check_availability\nbook_appointment| Supabase

    Supabase --> T1["businesses"]
    Supabase --> T2["appointments"]
    Supabase --> T3["waitlist"]

    VAD["Silero VAD\nVoice Activity Detection"] --> ResvAgent
    VAD --> LubeAgent
```

## Call Flow

```
1. Customer dials Twilio number
2. Twilio hits webhook → API server returns TwiML with SIP URI
3. Twilio bridges call into LiveKit SIP Gateway
4. LiveKit matches inbound number to dispatch rule → assigns agent
5. Agent joins room: STT transcribes speech → GPT-4o generates response → Cartesia speaks
6. Agent calls tools (check availability, book appointment) against Supabase
7. Booking confirmed — customer receives verbal confirmation
```

## Businesses

| Business | Phone | Agent | Persona | Capacity |
|---|---|---|---|---|
| Biryani Paradise | +1 582 259 9600 | reservation-agent | Priya | 10 tables, 50 seats |
| Golden Wrench Auto | +1 218 396 2707 | oilchange-agent | Mike | 3 bays |
| City Clinic | TBD | clinic-agent | Sarah | 1 slot / 30 min |

## Tech Stack

| Layer | Technology |
|---|---|
| Phone / PSTN | Twilio |
| SIP / WebRTC | LiveKit Cloud |
| Voice Activity Detection | Silero VAD |
| Speech-to-Text | Azure Speech Services |
| Language Model | Azure OpenAI GPT-4o |
| Text-to-Speech | Cartesia Sonic-2 |
| Database | Supabase (PostgreSQL) |
| Webhook Server | Starlette + uvicorn |
| Tunnel (dev) | ngrok |

## Project Structure

```
my_autonomous_agent/
├── src/my_autonomous_agent/
│   ├── reservation_agent.py      # Biryani Paradise — Priya
│   ├── oilchange_agent.py        # Golden Wrench Auto — Mike
│   ├── api.py                    # Twilio webhook + web UI
│   ├── booking/
│   │   ├── reservations.py       # Shared booking logic
│   │   └── supabase_client.py    # Supabase singleton
│   └── config/
│       ├── biryani_paradise.json
│       ├── quick_lube.json
│       └── city_clinic.json
├── menu.json                     # Biryani Paradise menu
├── schema.sql                    # Supabase schema + seed data
└── .env                          # API keys and credentials
```
