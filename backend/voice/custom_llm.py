"""OpenAI-compatible chat-completions endpoint that ElevenLabs Agents call in hands-free mode.

ElevenLabs does speech recognition, turn-taking and TTS; for every user turn it POSTs the
conversation here (via the public ngrok URL) and speaks the streamed tokens.
"""

import json
import logging
import secrets
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

# Sources of the latest answer per hands-free session, read later by the browser
SOURCES_TTL_SECONDS = 30 * 60
_sources: dict[str, tuple[float, list[dict]]] = {}


class Message(BaseModel):
    role: str
    # OpenAI allows a list of content parts; ElevenLabs sends plain strings
    content: str | list[dict] | None = None


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ExtraBody(BaseModel):
    """Set by our browser when the session starts (customLlmExtraBody)."""

    session_id: str | None = None
    llm_model: str | None = None
    # Chat turns from before hands-free started
    history: list[Turn] = []


class CompletionRequest(BaseModel):
    messages: list[Message]
    stream: bool = False
    model: str | None = None
    elevenlabs_extra_body: ExtraBody = ExtraBody()


def save_sources(session_id: str, sources: list[dict]):
    now = time.monotonic()
    for sid in [s for s, (t, _) in _sources.items() if now - t > SOURCES_TTL_SECONDS]:
        del _sources[sid]
    _sources[session_id] = (now, sources)


def latest_sources(session_id: str) -> list[dict]:
    saved = _sources.get(session_id)
    if not saved or time.monotonic() - saved[0] > SOURCES_TTL_SECONDS:
        return []
    return saved[1]


def text_of(message: Message) -> str:
    if isinstance(message.content, list):
        return " ".join(p.get("text", "") for p in message.content if p.get("type") == "text")
    return message.content or ""


def to_question_and_history(messages: list[Message]) -> tuple[str, list[dict]]:
    """Last user message is the question; earlier user/assistant turns are the history.

    System messages (the agent's prompt) and tool messages are dropped: our own prompts apply.
    """
    turns = [
        {"role": m.role, "content": text_of(m).strip()}
        for m in messages
        if m.role in ("user", "assistant") and text_of(m).strip()
    ]
    if not turns or turns[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="No user message to answer")
    return turns[-1]["content"], turns[:-1]


def check_secret(authorization: str | None):
    secret = get_settings().custom_llm_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Hands-free is not configured")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Invalid token")


def chunk(completion_id: str, model: str, delta: dict, finish_reason: str | None = None) -> str:
    data = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/completions")
async def chat_completions(
    req: CompletionRequest, request: Request, authorization: str | None = Header(None)
):
    check_secret(authorization)
    if not req.stream:
        raise HTTPException(status_code=400, detail="Only stream=true is supported")

    settings = get_settings()
    extra = req.elevenlabs_extra_body
    model = extra.llm_model or settings.groq_model
    if model not in settings.llm_model_labels():
        raise HTTPException(status_code=400, detail="Answer model is not allowed")

    question, history = to_question_and_history(req.messages)
    history = [t.model_dump() for t in extra.history] + history
    try:
        sources, tokens = await run_in_threadpool(
            request.app.state.rag.stream_answer, question, history, model
        )
    except Exception as e:
        logger.exception("Custom LLM: routing/retrieval failed")
        raise HTTPException(status_code=500, detail=str(e))
    if extra.session_id:
        save_sources(extra.session_id, sources)

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"

    # Starlette stops this generator when ElevenLabs disconnects (e.g. the user interrupts)
    async def events():
        yield chunk(completion_id, model, {"role": "assistant"})
        try:
            async for token in iterate_in_threadpool(tokens):
                if token:
                    yield chunk(completion_id, model, {"content": token})
        except Exception:
            logger.exception("Custom LLM: answer stream failed")
        yield chunk(completion_id, model, {}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
