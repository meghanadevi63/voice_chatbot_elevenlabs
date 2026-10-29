"""/v1/chat/completions (hands-free Custom LLM). The RAG chain is faked: no Groq, no Milvus."""

import json

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.config import Settings
from backend.voice import custom_llm

SECRET = "test-secret"
AUTH = {"Authorization": f"Bearer {SECRET}"}


class FakeRAG:
    def __init__(self):
        self.calls = []

    def stream_answer(self, question, history, model=None):
        self.calls.append((question, history, model))
        return [{"source": "hr.pdf", "page": 2, "content": "..."}], iter(["Leave ", "", "is 20 days."])


@pytest.fixture
def rag(monkeypatch):
    fake = FakeRAG()
    monkeypatch.setattr(main.app.state, "rag", fake, raising=False)
    s = Settings(_env_file=None, custom_llm_secret=SECRET)
    monkeypatch.setattr(custom_llm, "get_settings", lambda: s)
    return fake


@pytest.fixture
def client():
    # No `with`: the lifespan would build the real RAGChain
    return TestClient(main.app)


def body(**extra):
    return {
        "stream": True,
        "messages": [
            {"role": "system", "content": "agent prompt"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How many leave days?"},
        ],
        **extra,
    }


def test_streams_openai_chunks_and_saves_sources(rag, client):
    res = client.post(
        "/v1/chat/completions", headers=AUTH, json=body(elevenlabs_extra_body={"session_id": "s1"})
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = [line.removeprefix("data: ") for line in res.text.split("\n\n") if line]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert {c["object"] for c in chunks} == {"chat.completion.chunk"}
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    # Empty tokens are skipped
    assert [c["choices"][0]["delta"]["content"] for c in chunks[1:-1]] == ["Leave ", "is 20 days."]
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert custom_llm.latest_sources("s1")[0]["source"] == "hr.pdf"


def test_maps_messages_to_question_and_history(rag, client):
    extra = {
        "llm_model": "openai/gpt-oss-120b",
        "history": [{"role": "user", "content": "earlier typed question"}],
    }
    client.post("/v1/chat/completions", headers=AUTH, json=body(elevenlabs_extra_body=extra))
    question, history, model = rag.calls[0]
    assert question == "How many leave days?"
    # System prompt dropped; chat history from before hands-free comes first
    assert [t["content"] for t in history] == ["earlier typed question", "hi", "Hello!"]
    assert model == "openai/gpt-oss-120b"


@pytest.mark.parametrize(
    "headers, expected", [({}, 401), ({"Authorization": "Bearer wrong"}, 401)]
)
def test_rejects_bad_token(rag, client, headers, expected):
    assert client.post("/v1/chat/completions", headers=headers, json=body()).status_code == expected
    assert rag.calls == []


def test_disabled_without_secret(rag, client, monkeypatch):
    s = Settings(_env_file=None, custom_llm_secret="")
    monkeypatch.setattr(custom_llm, "get_settings", lambda: s)
    assert client.post("/v1/chat/completions", headers=AUTH, json=body()).status_code == 503


@pytest.mark.parametrize(
    "override",
    [
        {"stream": False},
        {"elevenlabs_extra_body": {"llm_model": "qwen/qwen3.8-27b"}},
        {"messages": [{"role": "system", "content": "agent prompt"}]},
    ],
)
def test_rejects_bad_requests(rag, client, override):
    assert client.post("/v1/chat/completions", headers=AUTH, json=body(**override)).status_code == 400
    assert rag.calls == []
