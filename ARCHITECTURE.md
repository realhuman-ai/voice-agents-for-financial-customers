# Voice Agent Platform — Architecture

Multi-tenant AI voice agent platform built on LiveKit, Twilio, and Azure. Each business gets its own phone number, persona, and booking database. All operational settings (hours, manager number, rate limits) are driven by `business_config.json` — no code changes required.

---

## System Overview

```mermaid
flowchart TD
    caller(["📞 Caller"])

    subgraph twilio["Twilio"]
        tn1["+1 218 396 2707\nQuick Lube"]
        tn2["+1 582 259 9600\nBiryani Paradise"]
        sms["SMS Confirmations"]
    end

    subgraph security["Webhook Server :8001"]
        wh["voice_webhook()"]
        rl["Rate Limiter\n≤5 calls/hr per number"]
        bl["Blocklist\nbusiness_config.json"]
        anon["Anonymous Rejection"]
    end

    subgraph livekit["LiveKit Cloud"]
        sip["SIP Trunk"]
        disp["Dispatcher\nroom prefix routing"]
    end

    subgraph agents["Agent Workers"]
        ql["oilchange-agent\nMike 🔧"]
        bp["reservation-agent\nPriya 🍛"]
    end

    subgraph ai["AI Services"]
        llm["Azure OpenAI\nGPT-4o"]
        tts["Cartesia\nSonic-2 TTS"]
        stt["Azure Speech\nSTT"]
    end

    subgraph db["Supabase (PostgreSQL)"]
        appt[("appointments")]
        wait[("waitlist")]
        trans[("call_transcripts")]
    end

    manager(["👤 Manager\n+1 832 330 3619"])

    caller --> tn1 & tn2
    tn1 & tn2 --> wh
    wh --> anon & rl & bl
    anon & rl & bl -->|"pass"| sip
    anon & rl & bl -->|"fail → hangup TwiML"| caller

    sip --> disp
    disp -->|"lube-* room"| ql
    disp -->|"biryani-* room"| bp

    ql & bp <--> llm
    ql & bp <--> tts
    ql & bp <--> stt

    ql & bp -->|"book_appointment\ncheck_availability"| appt & wait
    ql & bp -->|"on disconnect"| trans
    ql & bp -->|"confirmed booking"| sms

    ql & bp -->|"transfer_to_manager\n(SIP REFER)"| manager
```

---

## Call Flow

```mermaid
sequenceDiagram
    actor Caller
    participant Twilio
    participant Webhook
    participant LiveKit
    participant Agent
    participant Supabase
    participant SMS

    Caller->>Twilio: Dials business number
    Twilio->>Webhook: POST /twilio/voice
    Webhook->>Webhook: Check: anonymous? blocked? rate limit?
    alt rejected
        Webhook-->>Twilio: TwiML Hangup
        Twilio-->>Caller: Call ended
    else accepted
        Webhook-->>Twilio: TwiML Dial Sip
        Twilio->>LiveKit: SIP INVITE
        LiveKit->>Agent: Dispatch job to worker
        Agent-->>Caller: Greeting (Cartesia TTS)
        Caller-->>Agent: Speech (Azure STT)
        Agent->>Agent: LLM inference (Azure GPT-4o)

        opt Booking requested
            Agent->>Supabase: check_availability()
            Supabase-->>Agent: slots_left
            Agent->>Supabase: book_appointment()
            Supabase-->>Agent: confirmed
            Agent->>SMS: Send confirmation text
            SMS-->>Caller: "Your booking is confirmed..."
        end

        opt Escalation requested
            Agent-->>Caller: "Let me get our manager..."
            Agent->>LiveKit: SIP REFER to manager phone
            LiveKit->>Twilio: Transfer call
        end

        Caller->>Twilio: Hangs up
        Twilio->>LiveKit: BYE
        LiveKit->>Agent: Room disconnected
        Agent->>Supabase: save_transcript()
    end
```

---

## Component Map

| Component | Technology | Purpose |
|---|---|---|
| Phone numbers | Twilio | Public PSTN entry points |
| Webhook server | Starlette + uvicorn :8001 | Twilio routing, spam protection |
| Voice infrastructure | LiveKit Cloud | SIP, real-time audio, dispatch |
| LLM | Azure OpenAI GPT-4o | Conversation, tool calling |
| TTS | Cartesia Sonic-2 | Natural-sounding speech output |
| STT | Azure Speech | Transcription of caller audio |
| VAD | Silero | Voice activity detection |
| Database | Supabase (PostgreSQL) | Bookings, waitlist, transcripts |
| SMS | Twilio Messaging | Booking confirmations |
| Config | `business_config.json` | Runtime settings, no deploy needed |

---

## Security Layers

```
Caller → [Anonymous check] → [Blocklist] → [Rate limit 5/hr] → Agent
                ↓                  ↓               ↓
            Hangup             Hangup           Hangup
```

- **Anonymous rejection** — calls with no caller ID are refused
- **Blocklist** — add a number to `business_config.json → security.blocked_numbers`, restart webhook
- **Rate limiting** — in-memory, per-number, per-hour (configurable)
- **Max call duration** — hard cap via TwiML `callTimeout` (default 10 min)

---

## Configuration — `business_config.json`

Operational settings that can be changed **without touching code** — edit the file, restart workers:

```jsonc
{
  "manager_phone": "+18323303619",      // escalation target

  "security": {
    "reject_anonymous_calls": true,
    "max_call_duration_seconds": 600,   // 10 min hard cap
    "rate_limit_calls_per_hour": 5,
    "blocked_numbers": []               // add spammers here
  },

  "quick_lube": {
    "name": "Golden Wrench Auto services",
    "phone": "+12183962707",
    "timezone": "America/New_York",
    "open_days": [0,1,2,3,4,5],        // Mon-Sat
    "open_hour": 8,
    "close_hour": 18
  },

  "biryani_paradise": {
    "name": "Biryani Paradise",
    "phone": "+15822599600",
    "timezone": "America/New_York",
    "open_hour": 11,
    "close_hour": 22
  }
}
```

---

## Repository Structure

```
my_autonomous_agent/
├── business_config.json          # Operational config (edit without code changes)
├── menu.json                     # Biryani Paradise menu
├── ARCHITECTURE.md               # This file
│
└── src/my_autonomous_agent/
    ├── oilchange_agent.py        # Mike — Golden Wrench Auto
    ├── reservation_agent.py      # Priya — Biryani Paradise
    ├── webhook.py                # Twilio routing + spam protection
    ├── api.py                    # CrewAI task UI (:8000)
    ├── config.py                 # business_config.json loader
    │
    ├── booking/
    │   ├── reservations.py       # Shared booking logic (all business types)
    │   └── supabase_client.py    # DB client
    │
    └── utils/
        └── sms.py                # Twilio SMS confirmations
```
