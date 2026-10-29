# Stage 1 — Voice with ElevenLabs Agents + our RAG (Custom LLM)

Status: **In progress (M1–M2 done; next M3)** · Branch: `voicefeature` · Later: [Stage 2](stage2-voice-realtime.md) (parked)

## Goal

Add voice to the Docs Assistant in two modes. Our existing RAG pipeline
(intent router → Milvus retrieval → Groq answer) stays the only source of answers.
Voice works in every language the selected ElevenLabs models support.

| Mode | User experience |
|---|---|
| **Push-to-talk (PTT)** | Click mic → speak → click stop → transcript appears in the chat box → user can edit → clicks **Send** → answer is shown **and read aloud**. |
| **Hands-free** | Turn mic on → just talk. ElevenLabs detects when the user finished, our RAG answers, the answer is spoken. The user can interrupt (barge-in). Both sides of the conversation appear in the chat. |

Both modes write into the same chat thread; the user can switch modes mid-conversation.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **PTT does not use an ElevenLabs Agent.** It is: Scribe v2 (speech→text) → existing `/chat` → ElevenLabs TTS. | An Agent answers automatically when the user stops talking; PTT needs "review, then Send". Also cheaper (no per-minute agent charge) and every model is selectable. |
| D2 | **Hands-free uses ElevenLabs Agents (Custom mode)** with our backend as the **Custom LLM**. | ElevenLabs handles voice detection, end-of-turn detection, barge-in, echo cancellation and audio streaming. We only provide the answers. |
| D3 | **PTT reads answers aloud by default.** A "Speak replies" toggle turns it off. | Decided in discussion. |
| D4 | **Multilingual by default.** Speech-to-text auto-detects the language; answers come back in the user's language; TTS default is a multilingual model. | Decided in discussion. |
| D5 | **Turn eagerness is fixed** at `normal` (not user-selectable). | Decided in discussion; keeps one agent per TTS model. |
| D6 | API keys stay on the server. The browser gets only a short-lived signed URL (hands-free) or talks to our backend (PTT). | Security. |
| D7 | Model choices are **allow-listed by the backend**; the UI shows what `GET /voice/options` returns. | Users can't pick arbitrary/expensive models. |
| D8 | Agent configuration lives in code (`backend/voice/setup_agents.py`), not edited by hand in the dashboard. | Reviewable and reproducible. |

## Why hands-free needs a public URL

```
Browser ──audio──▶ ElevenLabs cloud (listens, detects end of turn)
                          │  server-to-server call
                          ▼
                  OUR backend  POST /v1/chat/completions
```

In hands-free mode **ElevenLabs' servers** call our backend for every answer. `localhost:8002`
is not reachable from the internet, so:

- **Development:** `ngrok http 8002` gives a public HTTPS URL that forwards to the local backend.
  A free reserved ngrok domain keeps the URL stable across restarts (otherwise re-run
  `setup_agents` after each restart).
- **Production:** the backend's real domain.

The endpoint is protected by a secret bearer token that only our agent knows.
PTT does **not** need a public URL (our backend calls ElevenLabs, not the other way round).

## Architecture

```
PUSH-TO-TALK
Mic ──MediaRecorder──▶ POST /voice/transcribe ──▶ ElevenLabs Scribe v2 ──▶ text into chat box
User clicks Send ──▶ POST /chat (RAG) ──▶ answer + sources shown
                 └──▶ POST /voice/tts ──▶ ElevenLabs TTS ──▶ played aloud

HANDS-FREE
Browser ──GET /voice/session──▶ backend ──▶ signed URL for the agent
Browser ◀══ live audio (@elevenlabs/react) ══▶ ElevenLabs Agent (ASR + turn-taking + TTS)
                                                     │ each user turn
                                                     ▼
                         {public URL}/v1/chat/completions  (secret token, streamed)
                                                     │
                                   RAG: router → Milvus → Groq (streamed tokens)
                                                     │
                                   sources saved per session → GET /voice/sources
```

## Multilingual design

**Problem found:** the embedding model `all-MiniLM-L6-v2` is English-only and the documents are
English. A Hindi/Telugu question would retrieve the wrong passages.

**Fix (no re-ingestion needed):**
1. Router prompt: `search_query` is **always written in English** (translate if needed).
2. Answer prompt: "Reply in the same language the user used."
3. Small-talk replies also in the user's language.

**Language support per model** (the UI only offers combinations that work):

| Model | Used for | Languages |
|---|---|---|
| `scribe_v2` | PTT speech-to-text | 90+, auto-detect |
| Scribe v2 Realtime | Hands-free speech-to-text (built into Agents) | 90+ |
| `eleven_v4_turbo` | TTS "Natural" (default), ~100 ms | 94, all major Indian languages |
| `eleven_v3_conversational` | TTS "Expressive", ~280 ms | 74, all major Indian languages |

**Default TTS:** `eleven_v4_turbo` ("Natural"); `eleven_v3_conversational` ("Expressive") is the
alternative. Both 0.5 credit/char on the free key. `eleven_flash_v2_5` was dropped: same price,
lacks te/kn/ml/mr/bn/gu. Spike S1 still checks both work as Agent TTS models (hands-free).

**Hands-free language:** Agents need a configured language. Spike S2 checks how
ElevenLabs' language detection works in Agents (switching mid-conversation), so the user does
not have to pick a language first.

## What the user can choose (Voice settings panel)

Saved in `localStorage`, validated by the backend.

| Setting | Options | PTT | Hands-free |
|---|---|---|---|
| Language | Auto-detect (default) or a specific language | ✅ | ✅ |
| Answer LLM (Groq) | allow-list from config, default `openai/gpt-oss-20b` | ✅ | ✅ |
| TTS model | table above | ✅ | ✅ (one agent per model) |
| Voice | multilingual voices from ElevenLabs | ✅ | ✅ |
| Speak replies | on (default) / off | ✅ | always on |

Not selectable: speech-to-text model (Scribe v2 is the only current option), turn eagerness (D5).

**Why one agent per TTS model:** per-session overrides are documented for voice, language and
prompt but not clearly for the TTS *model*, and changing the shared agent would affect every
user. If spike S1 shows the model can be overridden per session, we use a single agent.

## Work plan

### Progress

Legend: `[x]` done · `[ ]` to do · ⏳ in progress

| # | Milestone | Status |
|---|---|---|
| S | Spikes (S1–S4) | ⏳ S1 partly answered |
| M1 | PTT transcription | ✅ Done (2026-10-29) |
| M2 | PTT spoken replies + Voice settings | ✅ Done (2026-10-29) |
| M3 | Multilingual RAG | Not started |
| M4 | Streaming RAG + Custom LLM endpoint | Not started |
| M5 | Hands-free end to end | Not started |
| M6 | Sources + model choice in hands-free | Not started |
| M7 | Hardening | Not started |

### Spikes

Run each spike just before the milestone that needs it (S1–S3 before M5, S4 before M4).

- [ ] **S1 — TTS models in Agents.**
  - [x] Free key can use `eleven_v4_turbo` and `eleven_v3_conversational` via the TTS API (`GET /v1/models`, 2026-10-29; both 0.5 credit/char).
  - [ ] Check that both can be selected as an Agent's TTS model.
  - [ ] Check whether the TTS model can be overridden per session (if yes: one agent instead of one per model).
- [ ] **S2 — Languages in Agents.** How language detection / switching works mid-conversation; which setting lets the user speak any language without choosing first.
- [ ] **S3 — Custom LLM request shape.** Does `customLlmExtraBody` reach our endpoint? What `messages` contains after a barge-in (full generated text or only what was heard)? How the request is cancelled on interruption.
- [ ] **S4 — Tunnel.** ngrok installed, authtoken set, free static domain claimed, `PUBLIC_BASE_URL` in `.env`; a stub endpoint reachable from outside.

### M1 — PTT transcription ✅

Plan: mic button in the composer → record in the browser → `POST /voice/transcribe` →
ElevenLabs Scribe v2 → text appended to the chat box → user edits and clicks Send.

- [x] Config: `ELEVENLABS_API_KEY`, `STT_MODEL` (`scribe_v2`), `MAX_AUDIO_MB` in `backend/config.py` and `.env.example`.
- [x] API key created with minimal permissions, saved in `.env`, verified (free tier, 10,000 credits).
- [x] `backend/voice/elevenlabs.py`: Scribe client — auto language detect, no audio-event tags, clear errors (bad key → 502, quota → 429, missing key → 503).
- [x] `POST /voice/transcribe` (`backend/voice/routes.py`): rejects empty, > 10 MB, invalid language code.
- [x] `python-multipart` added to `requirements.txt`; `requirements-dev.txt` with `pytest`.
- [x] Frontend `useRecorder.js`: MediaRecorder (webm / ogg / mp4), echo cancellation, auto-stop at 2 min, releases the mic.
- [x] Composer: mic button (idle → red recording with timer → "Transcribing…"), transcript appended, Send disabled while busy, clicks < 0.7 s ignored, double-click guard, mic/permission error messages.
- [x] `/voice` added to the Vite proxy.
- [x] Unit tests with a fake ElevenLabs client (8 passing, no credits used).
- [x] Frontend builds.
- [x] Browser test: restart backend, record an English question, transcript appears, Send works
  (confirmed 2026-10-29).
- [x] Browser test: Hindi/Telugu transcription moved to the M3 voice test (needs M3's prompts to be useful end to end).
- [x] Commit M1 (combined with M2: the files mix both milestones).

### M2 — PTT spoken replies + Voice settings ✅

Plan: after each answer in PTT/text mode, the backend turns the answer into speech with the
selected model and voice, and the browser plays it automatically (D3). A Voice settings panel
lets the user pick model, voice, language and the Groq LLM.

- [x] Config: TTS model allow-list (`TTS_MODELS`: `eleven_v4_turbo` default, `eleven_v3_conversational`; the UI shows the real model ids, optional `id:Label` for display names), `DEFAULT_VOICE_ID` (premade "Matilda", provisional), `MAX_TTS_CHARS` (800), `TTS_CACHE_DIR`.
- [x] Config: Groq LLM allow-list (`LLM_MODELS`: `openai/gpt-oss-20b` default, `openai/gpt-oss-120b`, shown by model id; checked against the key's Groq model list 2026-10-29. `qwen/qwen3.8-27b` left out: untested with the structured-output router).
- [x] `GET /voice/options`: STT model (`scribe_v2`, shown read-only in the panel), TTS models (each with its language list from `/v1/models`), voices from `/v1/voices`, answer LLMs, defaults. ElevenLabs listings cached for an hour.
- [x] `POST /voice/tts`: `{ text, model, voice_id }` → whole `audio/mpeg` (not streamed: answers are short and the cache needs the whole file); rejects models not in the allow-list and voices not on the account; strips stray markdown; cuts long text at a sentence end (incl. `।`); logs billed characters per call.
- [x] Dev-only audio cache keyed by (text, model, voice) so replays cost nothing (`data/tts_cache/`, disabled when `TTS_CACHE_DIR` is empty).
- [x] `/chat` accepts an optional `llm_model` (validated); `RAGChain` keeps one `ChatGroq` per allowed model. The router model stays fixed (`ROUTER_MODEL`).
- [x] Frontend (`usePlayer.js`): auto-play the answer when "Speak replies" is on; Listen / Stop button on every answer (Listen also replays, free from the dev cache); a new recording, new question or New chat stops playback; autoplay blocked by the browser → message says to click Listen.
- [x] Voice settings panel in the Sidebar (`VoiceSettings.jsx`, `useVoiceSettings.js`: voice model, voice, language, answer model, speak replies), saved in `localStorage`; saved choices the server no longer offers fall back to defaults; language list follows the selected voice model.
- [x] Language picker sends `language` to `/voice/transcribe` (default auto-detect); `/chat` gets the chosen answer model.
- [x] Frontend builds.
- [x] Browser test: settings panel loads; a typed question is read aloud (`eleven_v4_turbo`, then `eleven_v3_conversational`); Stop works; Speak replies off → silent; answer model switch works (confirmed 2026-10-29).
- [x] Pick the default voice: Matilda kept as default (`DEFAULT_VOICE_ID`; change in `.env` to switch).
- [x] Unit tests with fakes for `/voice/tts`, `/voice/options`, `/chat` model choice (18 new, 26 total, no credits).
- [x] Manual test of both voice models (1–2 short sentences each).
- [x] Commit M2 (one commit together with M1).

### M3 — Multilingual RAG

Plan: make non-English questions retrieve the right passages from the English documents and
get answers in the user's language — prompt changes only, no re-ingestion.

- [ ] Router prompt: `search_query` always written in English (translate if needed).
- [ ] Answer prompt: reply in the language the user used; small-talk replies too.
- [ ] Test with 2–3 Hindi and Telugu questions (text first, then voice): right sources retrieved, answer language correct, read aloud correctly. Includes the Hindi/Telugu transcription check moved from M1.
- [ ] Commit M3.

### M4 — Streaming RAG + Custom LLM endpoint

Plan: build the endpoint ElevenLabs will call in hands-free mode. It speaks the OpenAI
chat-completions format and streams tokens so the agent can start talking early.

- [ ] Spike S4 done (ngrok + static domain).
- [ ] Config: `CUSTOM_LLM_SECRET`, `PUBLIC_BASE_URL`.
- [ ] `RAGChain.astream_answer(question, history, model)`: route → retrieve → stream Groq tokens; small talk as one chunk; returns sources.
- [ ] `POST /v1/chat/completions`: bearer-secret check, `stream=true` only, maps `messages` to question + history, reads `session_id` / `llm_model` / prior history from the extra body, SSE `chat.completion.chunk` events ending in `[DONE]`, stops when the client disconnects.
- [ ] Sources store per session (in memory, with TTL).
- [ ] Unit tests: SSE format, auth rejection, message mapping.
- [ ] curl test through the ngrok URL.
- [ ] Commit M4.

### M5 — Hands-free end to end

Plan: create the ElevenLabs agent from code and connect the browser to it, so the user can
talk continuously and hear answers from our RAG.

- [ ] Spikes S1 (Agents part), S2 and S3 done.
- [ ] `python -m backend.voice.setup_agents`: creates/updates private agents (Custom LLM → `{PUBLIC_BASE_URL}/v1`, Scribe v2 Realtime, interruptions on, turn eagerness `normal`, auto-end on long silence); saves agent ids.
- [ ] `GET /voice/session`: signed URL for the right agent.
- [ ] Frontend: `@elevenlabs/react`; hands-free toggle next to the mic; status listening / thinking / speaking; end button; textarea disabled while active.
- [ ] User transcripts and agent replies appear as chat messages; interrupted replies marked.
- [ ] Manual test: a few short sessions incl. barge-in and a follow-up question.
- [ ] Commit M5.

### M6 — Sources + model choice in hands-free

Plan: bring hands-free to parity with PTT: show sources, respect the user's settings, and
continue the existing conversation.

- [ ] `GET /voice/sources?session_id=…`; frontend attaches sources to each hands-free answer.
- [ ] Session start passes `session_id`, selected LLM and the last 6 chat turns (extra body).
- [ ] Voice and language passed as session overrides; TTS model selects the agent.
- [ ] Manual test: switch modes mid-conversation; out-of-document question is declined.
- [ ] Commit M6.

### M7 — Hardening

Plan: make it safe and pleasant to use and document it.

- [ ] Limits: TTS text length, upload size, request size on the Custom LLM endpoint.
- [ ] Clear error messages for quota reached, key missing, tunnel down.
- [ ] Latency + credit logging per turn; check target end of speech → first audio < ~1.5 s.
- [ ] Browser matrix: Chrome, Firefox, Safari, phone over LAN.
- [ ] README: ElevenLabs key permissions, ngrok setup, `setup_agents`, voice settings.
- [ ] Rotate the ElevenLabs API key (the current one was shared in chat).
- [ ] Commit M7 — Stage 1 done.

### Files touched

| Area | Files |
|---|---|
| Config | `backend/config.py`, `.env.example` (`ELEVENLABS_API_KEY`, `CUSTOM_LLM_SECRET`, `PUBLIC_BASE_URL`, model allow-lists, default voice) |
| RAG | `backend/rag.py` (multilingual prompts, streaming, per-request LLM) |
| Voice backend | new `backend/voice/` (ElevenLabs client, routes, `setup_agents.py`, sources store) |
| API | `backend/main.py` (include voice router) |
| Frontend | `frontend/src/api.js`, `Composer.jsx`, `Sidebar.jsx`, `App.jsx`, new `VoiceSettings.jsx` / `HandsFree.jsx`, `vite.config.js` (proxy paths), `package.json` (`@elevenlabs/react`) |
| Deps | `requirements.txt` (`python-multipart`, `httpx`) |

### Guards

- Custom LLM endpoint: secret token check, `stream=true` only, request size limit.
- `/voice/tts`: max text length; `/voice/transcribe`: max file size / duration.
- Hands-free: auto-end after long silence to stop per-minute billing.
- Never log API keys; log model choice + latency per turn.

## Testing

- Unit: SSE format of `/v1/chat/completions`, token rejection, history mapping, allow-list validation.
- Manual: PTT on Chrome/Firefox/Safari/phone; hands-free with barge-in; follow-up after an
  interruption; switching modes mid-chat; English, Hindi, Telugu questions.
- Target: end of speech → first audio under ~1.5 s in hands-free.

## Definition of done

- Both modes work in Chrome and on a phone over the LAN (HTTPS).
- PTT answers are read aloud by default; can be turned off.
- Questions in Hindi/Telugu retrieve the right passages and are answered in that language.
- Hands-free answers come only from our RAG (out-of-document question is declined).
- User can choose language, LLM, TTS model and voice; invalid choices rejected by the backend.
- Sources shown for voice answers in both modes.
- README documents ElevenLabs setup, ngrok and `setup_agents`.

## Free-tier budget (development)

We develop on the ElevenLabs **free plan**: 10,000 credits/month shared by STT, TTS and Agents,
non-commercial use with attribution (production needs a paid plan).

| Item | Approx. cost |
|---|---|
| One spoken answer (~300 chars), Flash v2.5 (0.5 credit/char) | ~150 credits |
| One spoken answer, full-price model (~1 credit/char) | ~300 credits |
| Hands-free | most expensive; free plan reportedly ~15 min/month (unverified) |

Rules:
- Unit tests use a **fake ElevenLabs client** — zero credits.
- Real calls only in planned manual checks (a few STT clips, 1–2 short sentences per TTS model).
- Dev-only **audio cache** keyed by (text, model, voice) so replays are free.
- Hands-free tests: few short sessions, auto-end on silence.
- Log the credit cost reported by ElevenLabs for each call.

## M2 TTS choice (confirmed)

PTT TTS uses the same API for every model (only `model_id` changes), so the user picks one of two:

| UI name | Model | Notes |
|---|---|---|
| **Natural** (default) | `eleven_v4_turbo` | Best quality, 94 languages (all major Indian languages), ~100 ms. |
| **Expressive** | `eleven_v3_conversational` | More emotion, 74 languages (all major Indian languages), ~280 ms. |

Verified with the free key via `GET /v1/models` (2026-10-29): both available, both 0.5
credit/char. `eleven_flash_v2_5` is also 0.5 credit/char but lacks te/kn/ml/mr/bn/gu, so it
offers no saving and is dropped. Voice: a premade voice from the account's default voices.

## Still open

Nothing. ngrok confirmed for development; M2 TTS choice confirmed (Natural / Expressive).
