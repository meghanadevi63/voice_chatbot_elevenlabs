"""/chat answer-model selection. The RAG chain is faked: no Groq calls, no Milvus."""

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.config import Settings


class FakeRAG:
    def __init__(self):
        self.calls = []

    def answer(self, question, history, model=None):
        self.calls.append(model)
        return {"answer": "ok", "sources": []}


@pytest.fixture
def rag(monkeypatch):
    fake = FakeRAG()
    monkeypatch.setitem(main.state, "rag", fake)
    s = Settings(_env_file=None)
    monkeypatch.setattr(main, "get_settings", lambda: s)
    return fake


@pytest.fixture
def client():
    # No `with`: the lifespan would build the real RAGChain
    return TestClient(main.app)


def test_default_model_when_not_given(rag, client):
    assert client.post("/chat", json={"question": "hi"}).status_code == 200
    assert rag.calls == [None]


def test_passes_allowed_model(rag, client):
    res = client.post("/chat", json={"question": "hi", "llm_model": "openai/gpt-oss-120b"})
    assert res.status_code == 200
    assert rag.calls == ["openai/gpt-oss-120b"]


def test_rejects_model_not_in_allow_list(rag, client):
    res = client.post("/chat", json={"question": "hi", "llm_model": "qwen/qwen3.8-27b"})
    assert res.status_code == 400
    assert rag.calls == []


def test_default_model_is_always_allowed():
    s = Settings(_env_file=None, groq_model="custom/model", llm_models="a:A")
    assert s.llm_model_labels() == {"custom/model": "custom/model", "a": "A"}
