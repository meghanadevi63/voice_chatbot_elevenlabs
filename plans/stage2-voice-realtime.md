# Stage 2 — Hands-free with Eleven Realtime (Mini / Max)

Status: **Parked — revisit after Stage 1 is done** · Depends on: [Stage 1](stage1-voice-custom-llm.md)

## Goal

Offer **Eleven Realtime** as an alternative engine for **hands-free** mode, compare it against
the Stage 1 Custom-LLM agent on grounding, latency and cost, and decide which one becomes the
default.

Push-to-talk is **unchanged** in Stage 2 (Scribe v2 → `/chat` → TTS).

## What changes vs. Stage 1

| | Stage 1 (Custom mode) | Stage 2 (Realtime mode) |
|---|---|---|
| Brain | Our Groq RAG, every turn | `eleven_realtime_v1_mini` or `_max` |
| Document access | Retrieval on every turn (guaranteed) | Model calls our **`search_documents`** server tool when it decides to |
| LLM / TTS / ASR choice | User selectable | Managed by ElevenLabs (only voice, language, prompt, tools, KB, turn settings) |
| Our endpoint | `/v1/chat/completions` (SSE) | `/tools/search` (JSON) |
| Billing | Agent minutes + Groq | Agent minutes + Realtime token rates |

## Design

```
Browser ──GET /voice/session?engine=realtime-mini──▶ backend ──▶ signed URL (Realtime agent)
Browser ◀══ audio ══▶ Eleven Realtime agent (hears, reasons, speaks)
                              │ tool call: search_documents(query)
                              ▼
          POST {public-url}/tools/search  (secret header, session_id dynamic variable)
                              │
                     Milvus retrieve top-k → chunks + source/page
                              │
                     sources stored by session id → GET /voice/sources (reused from Stage 1)
```

### Engine selector

Voice settings gets **Hands-free engine**:
- `Custom — our RAG` (Stage 1, default until evaluation says otherwise)
- `Realtime Mini` — fastest, cheapest
- `Realtime Max` — better instruction following / tool use, higher cost

When a Realtime engine is chosen, the TTS-model and LLM pickers are hidden for hands-free
(they don't apply); voice and language remain.

### Grounding strategy

- System prompt (adapted from `SYSTEM_PROMPT` in `backend/rag.py`): "For any question about
  the company or its documents, **always call `search_documents` first** and answer only from
  its results. If nothing relevant is returned, say you couldn't find it. Small talk needs no
  search."
- Tool returns compact text: up to `top_k` chunks with `source` and `page`, trimmed to keep
  token cost down.
- Do **not** upload PDFs to the ElevenLabs knowledge base by default — Milvus stays the single
  source of truth and ingestion stays in one place. (Knowledge base is a fallback option if the
  tool approach underperforms.)

## Work breakdown

### 0. Spikes

- **S1** — Confirm Realtime model ids, regional/residency availability for our account, and
  current per-token pricing for Mini and Max.
- **S2** — Confirm server tool config: secret headers, passing `{{session_id}}` as a dynamic
  variable, timeout behaviour, and what the agent says while the tool runs.

### 1. Backend

- `POST /tools/search` — body `{ query, session_id }`, header secret check, returns
  `{ results: [{ source, page, content }] }`; stores sources for `/voice/sources`.
- Refactor: expose retrieval from `RAGChain` (`retrieve(query)`) so `/chat`, the Custom LLM
  endpoint and the tool share it.
- `setup_agents.py`: add Realtime Mini and Max agents (Max: max tokens ≥ 1,024), with the
  `search_documents` tool, interruptions on, same turn settings as Stage 1.
- `/voice/options` and `/voice/session`: add the `engine` option.

### 2. Frontend

- Engine selector in Voice settings; hide non-applicable pickers.
- Same hands-free UI and transcript handling as Stage 1 (pass `session_id` as a dynamic
  variable instead of extra body).
- Show an "engine" tag on hands-free assistant messages during evaluation.

### 3. Evaluation (decides the default engine)

Build `eval/voice_questions.md` with ~30 questions:
- 15 answerable from the documents (incl. follow-ups like "what about the second one?"),
- 10 not in the documents (must decline),
- 5 small talk.

Measure for each engine (Custom, Mini, Max):

| Metric | How |
|---|---|
| Grounded accuracy | % correct answers on the 15 answerable |
| Hallucination rate | % of the 10 out-of-scope that were answered anyway |
| Search-skip rate (Realtime) | answerable questions where no tool call happened |
| Latency | end of speech → first audio (median, p90) |
| Cost per 10-minute conversation | from ElevenLabs + Groq usage |

Decision rule (proposal): Realtime becomes default only if hallucination rate is **no worse**
than Custom and median latency is clearly better. Otherwise keep Custom as default and offer
Realtime as an option.

## Milestones

1. **M1** — `/tools/search` + Realtime Mini agent working end to end.
2. **M2** — Engine selector in UI; sources shown for Realtime answers.
3. **M3** — Realtime Max agent.
4. **M4** — Evaluation run + written recommendation; set default engine.

## Risks

- Model may skip the search tool and answer from general knowledge → mitigate with prompt,
  Max, or eval-driven decision to stay on Custom.
- Max not available with India/Singapore data residency; Mini not available with
  zero-retention/HIPAA — check account settings first (Spike S1).
- Very new models (released Oct 2026): APIs and pricing may still change.

## Definition of done

- User can choose Custom / Realtime Mini / Realtime Max for hands-free.
- Realtime answers show sources when a search was made.
- Evaluation results recorded and the default engine chosen based on them.
