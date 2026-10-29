"""Create or update the hands-free ElevenLabs agent from code (plan decision D8).

    python -m backend.voice.setup_agents

Run again after changing PUBLIC_BASE_URL, CUSTOM_LLM_SECRET or the settings below. Creating and
updating an agent costs no credits; only live conversations do.
"""

import requests

from backend.config import get_settings
from backend.voice.elevenlabs import API_BASE, TIMEOUT_S, _headers, _raise_for_status

AGENT_NAME = "Docs Assistant (hands-free)"
SECRET_NAME = "docs-assistant-custom-llm"
# Free-tier guards: agent minutes are the most expensive part of voice
MAX_DURATION_S = 300
SILENCE_END_S = 20
# Events the browser needs: audio, both transcripts, and barge-in (also enables interruptions)
CLIENT_EVENTS = ["audio", "interruption", "user_transcript", "agent_response", "agent_response_correction"]


def _call(method: str, path: str, **kwargs) -> dict:
    res = requests.request(method, f"{API_BASE}{path}", headers=_headers(), timeout=TIMEOUT_S, **kwargs)
    _raise_for_status(res)
    return res.json() if res.content else {}


def upsert_secret(value: str) -> str:
    """Store the Custom LLM bearer secret in the workspace; agents can only reference secrets by id."""
    existing = next(
        (s for s in _call("GET", "/convai/secrets")["secrets"] if s["name"] == SECRET_NAME), None
    )
    if existing:
        _call("PATCH", f"/convai/secrets/{existing['secret_id']}",
              json={"type": "update", "name": SECRET_NAME, "value": value})
        return existing["secret_id"]
    return _call("POST", "/convai/secrets", json={"type": "new", "name": SECRET_NAME, "value": value})[
        "secret_id"
    ]


def agent_config(secret_id: str) -> dict:
    settings = get_settings()
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                # Empty: the agent waits for the user to speak first (no greeting credits)
                "first_message": "",
                "language": "en",
                "prompt": {
                    # Ignored by our endpoint (it drops system messages and uses the RAG prompts)
                    "prompt": "You are the Docs Assistant. Answers come from the custom LLM.",
                    "llm": "custom-llm",
                    "custom_llm": {
                        # ElevenLabs appends /chat/completions
                        "url": f"{settings.public_base_url.rstrip('/')}/v1",
                        "api_key": {"secret_id": secret_id},
                    },
                },
            },
            "asr": {"provider": "scribe_realtime", "quality": "high"},
            "tts": {
                "model_id": next(iter(settings.tts_model_labels())),
                "voice_id": settings.default_voice_id,
                # Audio tags are for ElevenLabs' own LLM prompt; our answers don't use them
                "expressive_mode": False,
            },
            "turn": {
                "turn_eagerness": "normal",
                # Same as the silence end: otherwise ElevenLabs re-engages a silent user by sending
                # us "..." as a question after 7 s, and the answer is spoken (credits)
                "turn_timeout": SILENCE_END_S,
                "silence_end_call_timeout": SILENCE_END_S,
            },
            "conversation": {"max_duration_seconds": MAX_DURATION_S, "client_events": CLIENT_EVENTS},
        },
        "platform_settings": {
            # Private: sessions need a signed URL from our backend (D6)
            "auth": {"enable_auth": True},
            "overrides": {
                "custom_llm_extra_body": True,
                "conversation_config_override": {
                    "tts": {"model_id": True, "voice_id": True},
                    "agent": {"language": True},
                },
            },
        },
    }


def find_agent_id() -> str | None:
    configured = get_settings().elevenlabs_agent_id
    if configured:
        return configured
    agents = _call("GET", "/convai/agents", params={"search": AGENT_NAME})["agents"]
    return next((a["agent_id"] for a in agents if a["name"] == AGENT_NAME), None)


def main():
    settings = get_settings()
    if not settings.public_base_url or not settings.custom_llm_secret:
        raise SystemExit("Set PUBLIC_BASE_URL and CUSTOM_LLM_SECRET in .env first.")

    config = agent_config(upsert_secret(settings.custom_llm_secret))
    agent_id = find_agent_id()
    if agent_id:
        _call("PATCH", f"/convai/agents/{agent_id}", json=config)
        print(f"Updated agent {agent_id}")
    else:
        agent_id = _call("POST", "/convai/agents/create", json=config)["agent_id"]
        print(f"Created agent {agent_id}")

    print(f"Custom LLM URL: {config['conversation_config']['agent']['prompt']['custom_llm']['url']}")
    if not settings.elevenlabs_agent_id:
        print(f"Add to .env: ELEVENLABS_AGENT_ID={agent_id}")


if __name__ == "__main__":
    main()
