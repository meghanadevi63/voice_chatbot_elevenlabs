"""/voice/transcribe tests. ElevenLabs is faked, so these spend no credits."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.voice import elevenlabs, routes


class FakeResponse:
    def __init__(self, status_code=200, body=None, reason="OK"):
        self.status_code = status_code
        self.ok = status_code < 400
        self.reason = reason
        self._body = body or {}

    def json(self):
        return self._body


@pytest.fixture
def settings(monkeypatch):
    s = Settings(_env_file=None, elevenlabs_api_key="test-key", max_audio_mb=1)
    monkeypatch.setattr(elevenlabs, "get_settings", lambda: s)
    monkeypatch.setattr(routes, "get_settings", lambda: s)
    return s


class Calls(list):
    response = None


@pytest.fixture
def calls(monkeypatch):
    """Fake requests.post; tests set calls.response to control the reply."""
    recorded = Calls()

    def fake_post(url, headers, data, files, timeout):
        recorded.append({"url": url, "headers": headers, "data": data, "files": files})
        return recorded.response

    recorded.response = FakeResponse(body={"text": " hello there ", "language_code": "en"})
    monkeypatch.setattr(elevenlabs.requests, "post", fake_post)
    return recorded


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def post_audio(client, data=b"fake-audio", **form):
    return client.post(
        "/voice/transcribe",
        files={"file": ("speech.webm", data, "audio/webm")},
        data=form,
    )


def test_returns_trimmed_text_and_language(settings, calls, client):
    res = post_audio(client)
    assert res.status_code == 200
    assert res.json() == {"text": "hello there", "language": "en"}

    sent = calls[0]
    assert sent["url"].endswith("/speech-to-text")
    assert sent["headers"] == {"xi-api-key": "test-key"}
    assert sent["data"]["model_id"] == "scribe_v2"
    assert "language_code" not in sent["data"]
    assert sent["files"]["file"] == ("speech.webm", b"fake-audio", "audio/webm")


def test_passes_language(settings, calls, client):
    assert post_audio(client, language="te").status_code == 200
    assert calls[0]["data"]["language_code"] == "te"


def test_rejects_bad_language(settings, calls, client):
    assert post_audio(client, language="en-US; drop").status_code == 400
    assert calls == []


def test_rejects_empty_and_oversized(settings, calls, client):
    assert post_audio(client, data=b"").status_code == 400
    assert post_audio(client, data=b"x" * (1024 * 1024 + 1)).status_code == 413
    assert calls == []


def test_missing_key(settings, calls, client):
    settings.elevenlabs_api_key = ""
    res = post_audio(client)
    assert res.status_code == 503
    assert "ELEVENLABS_API_KEY" in res.json()["detail"]


@pytest.mark.parametrize(
    "upstream, expected",
    [(401, 502), (429, 429), (500, 502)],
)
def test_maps_upstream_errors(settings, calls, client, upstream, expected):
    calls.response = FakeResponse(
        upstream, {"detail": {"status": "x", "message": "boom"}}, reason="Err"
    )
    res = post_audio(client)
    assert res.status_code == expected
    assert "boom" in res.json()["detail"]
