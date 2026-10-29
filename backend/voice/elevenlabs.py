"""Minimal client for the ElevenLabs REST API (only the endpoints we use)."""

import logging
import time

import requests

from backend.config import get_settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.elevenlabs.io/v1"
TIMEOUT_S = 60
# 128 kbps is the highest MP3 quality on the free plan
TTS_FORMAT = "mp3_44100_128"
# Voice and model lists rarely change; refetch at most hourly
LIST_TTL_S = 3600

_list_cache: dict[str, tuple[float, object]] = {}


class ElevenLabsError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _headers() -> dict:
    key = get_settings().elevenlabs_api_key
    if not key:
        raise ElevenLabsError(503, "ELEVENLABS_API_KEY is not set on the server")
    return {"xi-api-key": key}


def _raise_for_status(res: requests.Response) -> None:
    if res.ok:
        return
    # Errors look like {"detail": {"status": "...", "message": "..."}} or {"detail": "..."}
    try:
        detail = res.json().get("detail")
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("status")
    except ValueError:
        detail = None
    detail = detail or res.reason
    logger.warning("ElevenLabs %s: %s", res.status_code, detail)

    if res.status_code in (401, 403):
        raise ElevenLabsError(502, f"ElevenLabs rejected the API key: {detail}")
    if res.status_code == 429:
        raise ElevenLabsError(429, f"ElevenLabs rate limit or credit quota reached: {detail}")
    raise ElevenLabsError(502, f"ElevenLabs error: {detail}")


def transcribe(audio: bytes, filename: str, content_type: str, language: str | None = None) -> dict:
    """Speech to text with Scribe. Language is auto-detected unless given (ISO 639 code)."""
    data = {
        "model_id": get_settings().stt_model,
        # Keep the transcript clean for the chat box: no "(laughter)" style tags
        "tag_audio_events": "false",
    }
    if language:
        data["language_code"] = language

    try:
        res = requests.post(
            f"{API_BASE}/speech-to-text",
            headers=_headers(),
            data=data,
            files={"file": (filename, audio, content_type)},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise ElevenLabsError(502, f"Can't reach ElevenLabs: {e}") from e
    _raise_for_status(res)

    body = res.json()
    return {"text": (body.get("text") or "").strip(), "language": body.get("language_code")}


def _get_cached(path: str):
    """GET a free listing endpoint, cached for LIST_TTL_S."""
    hit = _list_cache.get(path)
    if hit and time.monotonic() - hit[0] < LIST_TTL_S:
        return hit[1]

    try:
        res = requests.get(f"{API_BASE}{path}", headers=_headers(), timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise ElevenLabsError(502, f"Can't reach ElevenLabs: {e}") from e
    _raise_for_status(res)

    body = res.json()
    _list_cache[path] = (time.monotonic(), body)
    return body


def list_voices() -> list[dict]:
    """Voices available to the account (premade on the free plan)."""
    return [
        {"id": v["voice_id"], "name": v["name"], "labels": v.get("labels") or {}}
        for v in _get_cached("/voices").get("voices", [])
    ]


def model_languages() -> dict[str, list[dict]]:
    """{model_id: [{"code", "name"}]} for every model on the account."""
    return {
        m["model_id"]: [{"code": l["language_id"], "name": l["name"]} for l in m.get("languages", [])]
        for m in _get_cached("/models")
    }


def synthesize(text: str, model: str, voice_id: str) -> bytes:
    """Text to speech. Returns the whole MP3 (answers are short, and the cache needs it whole)."""
    try:
        res = requests.post(
            f"{API_BASE}/text-to-speech/{voice_id}",
            headers=_headers(),
            params={"output_format": TTS_FORMAT},
            json={"text": text, "model_id": model},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise ElevenLabsError(502, f"Can't reach ElevenLabs: {e}") from e
    _raise_for_status(res)

    # ElevenLabs reports the characters it billed; fall back to what we sent
    cost = res.headers.get("character-cost") or len(text)
    logger.info("TTS %s voice=%s chars=%d billed=%s", model, voice_id, len(text), cost)
    return res.content
