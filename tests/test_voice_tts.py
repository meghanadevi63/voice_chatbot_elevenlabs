"""/voice/tts tests. ElevenLabs is faked, so these spend no credits."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.voice import elevenlabs, routes, tts

VOICE = "voice-a"
MODELS = [
    {"model_id": "eleven_v4_turbo", "languages": [{"language_id": "te", "name": "Telugu"}]},
    {"model_id": "eleven_flash_v2_5", "languages": [{"language_id": "en", "name": "English"}]},
]


class FakeResponse:
    def __init__(self, status_code=200, body=None, content=b"", headers=None, reason="OK"):
        self.status_code = status_code
        self.ok = status_code < 400
        self.reason = reason
        self.content = content
        self.headers = headers or {}
        self._body = body or {}

    def json(self):
        return self._body


@pytest.fixture
def settings(monkeypatch, tmp_path):
    s = Settings(
        _env_file=None,
        elevenlabs_api_key="test-key",
        default_voice_id=VOICE,
        max_tts_chars=60,
        tts_cache_dir=str(tmp_path / "tts"),
    )
    for module in (elevenlabs, routes, tts):
        monkeypatch.setattr(module, "get_settings", lambda: s)
    monkeypatch.setattr(elevenlabs, "_list_cache", {})
    return s


class Calls(list):
    response = None


@pytest.fixture
def calls(monkeypatch):
    """Fake requests.get (voices) and requests.post (TTS); records every call."""
    recorded = Calls()

    def fake_get(url, headers, timeout):
        recorded.append({"method": "GET", "url": url})
        if url.endswith("/models"):
            return FakeResponse(body=MODELS)
        return FakeResponse(body={"voices": [{"voice_id": VOICE, "name": "A"}]})

    def fake_post(url, headers, params, json, timeout):
        recorded.append({"method": "POST", "url": url, "params": params, "json": json})
        return recorded.response

    recorded.response = FakeResponse(content=b"mp3-bytes", headers={"character-cost": "11"})
    monkeypatch.setattr(elevenlabs.requests, "get", fake_get)
    monkeypatch.setattr(elevenlabs.requests, "post", fake_post)
    return recorded


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def tts_posts(calls):
    return [c for c in calls if c["method"] == "POST"]


def test_returns_mp3_with_default_model_and_voice(settings, calls, client):
    res = client.post("/voice/tts", json={"text": "Hello there."})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.content == b"mp3-bytes"

    sent = tts_posts(calls)[0]
    assert sent["url"].endswith(f"/text-to-speech/{VOICE}")
    assert sent["json"] == {"text": "Hello there.", "model_id": "eleven_v4_turbo"}
    assert sent["params"] == {"output_format": "mp3_44100_128"}


def test_accepts_expressive_model(settings, calls, client):
    res = client.post("/voice/tts", json={"text": "Hi.", "model": "eleven_v3_conversational"})
    assert res.status_code == 200
    assert tts_posts(calls)[0]["json"]["model_id"] == "eleven_v3_conversational"


def test_rejects_model_not_in_allow_list(settings, calls, client):
    res = client.post("/voice/tts", json={"text": "Hi.", "model": "eleven_multilingual_v2"})
    assert res.status_code == 400
    assert calls == []


def test_rejects_unknown_voice(settings, calls, client):
    res = client.post("/voice/tts", json={"text": "Hi.", "voice_id": "someone-else"})
    assert res.status_code == 400
    assert tts_posts(calls) == []


def test_rejects_text_with_nothing_to_speak(settings, calls, client):
    assert client.post("/voice/tts", json={"text": ""}).status_code == 422
    assert client.post("/voice/tts", json={"text": "** ``` ```"}).status_code == 400
    assert calls == []


def test_cache_makes_replays_free(settings, calls, client):
    for _ in range(2):
        assert client.post("/voice/tts", json={"text": "Same answer."}).content == b"mp3-bytes"
    assert len(tts_posts(calls)) == 1
    # Voices are fetched once and reused too
    assert len([c for c in calls if c["method"] == "GET"]) == 1


def test_no_cache_when_disabled(settings, calls, client):
    settings.tts_cache_dir = ""
    for _ in range(2):
        client.post("/voice/tts", json={"text": "Same answer."})
    assert len(tts_posts(calls)) == 2


@pytest.mark.parametrize("upstream, expected", [(401, 502), (429, 429), (500, 502)])
def test_maps_upstream_errors(settings, calls, client, upstream, expected):
    calls.response = FakeResponse(upstream, {"detail": {"message": "boom"}}, reason="Err")
    res = client.post("/voice/tts", json={"text": "Hi."})
    assert res.status_code == expected
    assert "boom" in res.json()["detail"]


def test_speech_text_strips_markdown():
    text = "## Leave\n- **Annual** leave: see [policy](https://x.y/p).\n- Sick `leave`."
    assert tts.speech_text(text, 800) == "Leave Annual leave: see policy. Sick leave."


def test_speech_text_cuts_at_sentence_end():
    text = "First sentence is here. Second one is a bit longer and goes past the limit."
    assert tts.speech_text(text, 40) == "First sentence is here."


def test_speech_text_handles_danda_and_long_sentences():
    assert tts.speech_text("छुट्टी बारह दिन है। बाकी नियम बाद में।", 25) == "छुट्टी बारह दिन है।"
    # No sentence end in range: cut at a word and close the sentence
    assert tts.speech_text("one two three four five six", 15) == "one two three."


def test_options_lists_only_allowed_choices(settings, calls, client):
    res = client.get("/voice/options")
    assert res.status_code == 200
    body = res.json()
    assert body["stt_models"] == [{"id": "scribe_v2", "label": "scribe_v2"}]
    assert body["tts_models"] == [
        {"id": "eleven_v4_turbo", "label": "eleven_v4_turbo", "languages": [{"code": "te", "name": "Telugu"}]},
        {"id": "eleven_v3_conversational", "label": "eleven_v3_conversational", "languages": []},
    ]
    assert body["voices"] == [{"id": VOICE, "name": "A", "labels": {}}]
    assert [m["id"] for m in body["llm_models"]] == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert body["defaults"] == {
        "tts_model": "eleven_v4_turbo",
        "voice_id": VOICE,
        "llm_model": "openai/gpt-oss-20b",
        "language": None,
        "speak_replies": True,
    }
    # Listings are free, but still cached
    client.get("/voice/options")
    assert len(calls) == 2
