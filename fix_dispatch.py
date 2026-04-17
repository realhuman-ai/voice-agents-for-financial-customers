import requests, jwt, time

API_KEY = "APIKN8vN34cS38W"
API_SECRET = "W3YixXBIem9p9wcjPYdDWg850thmzodT240kG8rWtRX"
HOST = "https://financial-voice-agents-yj4rwp22.livekit.cloud"

token = jwt.encode(
    {"iss": API_KEY, "sub": API_KEY, "exp": int(time.time()) + 600,
     "nbf": int(time.time()), "video": {}, "sip": {"admin": True}},
    API_SECRET, algorithm="HS256"
)
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Delete current Quick Lube rule
r = requests.post(f"{HOST}/twirp/livekit.SIP/DeleteSIPDispatchRule",
    headers=headers, json={"sip_dispatch_rule_id": "SDR_cWcPzLe9XMV3"})
print("Delete Quick Lube rule:", r.status_code)

# Recreate with no inbound_numbers filter - trunk ST_R3AkiS4kcWbj only handles +12183962707
r = requests.post(f"{HOST}/twirp/livekit.SIP/CreateSIPDispatchRule",
    headers=headers,
    json={
        "name": "Quick Lube Dispatch",
        "trunk_ids": ["ST_R3AkiS4kcWbj"],
        "inbound_numbers": [],
        "rule": {"dispatchRuleIndividual": {"roomPrefix": "lube-"}},
        "room_config": {
            "agents": [{"agent_name": "oilchange-agent"}]
        }
    })
print("Create Quick Lube rule:", r.status_code, r.text)
