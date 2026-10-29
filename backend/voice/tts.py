"""Turns a chat answer into speech: clean the text, cap its length, cache the audio."""

import hashlib
import re
from pathlib import Path

from backend.config import get_settings
from backend.voice import elevenlabs

# Answers are prompted as plain speech; this is only a safety net for stray markdown
MARKDOWN = [
    (re.compile(r"```.*?```", re.S), " "),  # code blocks
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),  # links -> their text
    (re.compile(r"https?://\S+"), " "),
    (re.compile(r"^\s*(#+|[-*•>])\s+", re.M), ""),  # headings, bullets, quotes
    (re.compile(r"[*`|]"), ""),
]
# Latin, Devanagari danda and CJK sentence ends
SENTENCE_END = re.compile(r"[.!?।。](?=\s|$)")


def speech_text(text: str, max_chars: int) -> str:
    """Plain text ready to speak, cut at a sentence boundary if it is too long."""
    for pattern, repl in MARKDOWN:
        text = pattern.sub(repl, text)
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]
    ends = [m.end() for m in SENTENCE_END.finditer(cut)]
    # Prefer the last full sentence, unless that would drop most of the allowed length
    if ends and ends[-1] > max_chars // 2:
        return cut[: ends[-1]]
    return cut.rsplit(" ", 1)[0].rstrip(",;:") + "."


def _cache_path(text: str, model: str, voice_id: str) -> Path | None:
    cache_dir = get_settings().tts_cache_dir
    if not cache_dir:
        return None
    key = hashlib.sha256(f"{model}\n{voice_id}\n{text}".encode()).hexdigest()
    return Path(cache_dir) / f"{key}.mp3"


def speak(text: str, model: str, voice_id: str) -> bytes:
    """MP3 for already-cleaned text; served from the dev cache when possible."""
    path = _cache_path(text, model, voice_id)
    if path and path.exists():
        return path.read_bytes()

    audio = elevenlabs.synthesize(text, model, voice_id)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(audio)
        tmp.replace(path)
    return audio
