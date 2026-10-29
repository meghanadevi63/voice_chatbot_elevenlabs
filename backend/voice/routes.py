import re

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.voice import elevenlabs, tts
from backend.voice.elevenlabs import ElevenLabsError

router = APIRouter(prefix="/voice")

LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")


class Transcript(BaseModel):
    text: str
    language: str | None


class SpeechRequest(BaseModel):
    # Upper bound on the raw request; the spoken text is capped by max_tts_chars
    text: str = Field(min_length=1, max_length=20_000)
    model: str | None = None
    voice_id: str | None = None


@router.get("/options")
async def options():
    """Choices for the Voice settings panel. Everything here is allow-listed by the server."""
    settings = get_settings()
    try:
        voices = await run_in_threadpool(elevenlabs.list_voices)
        languages = await run_in_threadpool(elevenlabs.model_languages)
    except ElevenLabsError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)

    tts_models = settings.tts_model_labels()
    llm_models = settings.llm_model_labels()
    return {
        # Shown for information; Scribe is the only speech-to-text model, so it isn't selectable
        "stt_models": [{"id": settings.stt_model, "label": settings.stt_model}],
        # Each TTS model lists the languages it can speak, so the UI can filter the picker
        "tts_models": [
            {"id": m, "label": label, "languages": languages.get(m, [])}
            for m, label in tts_models.items()
        ],
        "voices": voices,
        "llm_models": [{"id": m, "label": label} for m, label in llm_models.items()],
        "defaults": {
            "tts_model": next(iter(tts_models)),
            "voice_id": settings.default_voice_id,
            "llm_model": settings.groq_model,
            "language": None,  # auto-detect
            "speak_replies": True,
        },
    }


@router.post("/transcribe", response_model=Transcript)
async def transcribe(file: UploadFile, language: str | None = Form(None)):
    if language and not LANGUAGE_RE.match(language):
        raise HTTPException(status_code=400, detail="Invalid language code")

    max_bytes = get_settings().max_audio_mb * 1024 * 1024
    audio = await file.read(max_bytes + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="Recording is empty")
    if len(audio) > max_bytes:
        raise HTTPException(status_code=413, detail="Recording is too long")

    try:
        return await run_in_threadpool(
            elevenlabs.transcribe,
            audio,
            file.filename or "speech.webm",
            file.content_type or "application/octet-stream",
            language,
        )
    except ElevenLabsError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.post("/tts")
async def speak(req: SpeechRequest):
    settings = get_settings()
    models = settings.tts_model_labels()
    model = req.model or next(iter(models))
    if model not in models:
        raise HTTPException(status_code=400, detail="Voice model is not allowed")

    text = tts.speech_text(req.text, settings.max_tts_chars)
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to speak")

    voice_id = req.voice_id or settings.default_voice_id
    try:
        voices = await run_in_threadpool(elevenlabs.list_voices)
        if voice_id not in {v["id"] for v in voices}:
            raise HTTPException(status_code=400, detail="Voice is not available")
        audio = await run_in_threadpool(tts.speak, text, model, voice_id)
    except ElevenLabsError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
    return Response(content=audio, media_type="audio/mpeg")
