# Stage 1 — Voice with ElevenLabs Agents + our RAG (Custom LLM)

Status: **In progress (M1–M2, M4 done; M3 awaiting browser test; M5 coded, manual test next)** · Branches: `voicefeature` (M1–M2), `voicefeature-m3-multilingual` (M3, PRs target `voicefeature`), `voicefeature-m4-custom-llm` (M4, PRs target the M3 branch) · Later: [Stage 2](stage2-voice-realtime.md) (parked)

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
| D3 | **PTT reads answers aloud by default — only for questions asked with the mic.** Typed questions stay silent (Listen button reads any answer). A "Speak replies to voice questions" toggle turns it off. | Decided in discussion; typed-only auto-play dropped 2026-10-29 (typing means the user is reading). |
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
| TTS model | table above | ✅ | ✅ (session override) |
| Voice | multilingual voices from ElevenLabs | ✅ | ✅ |
| Speak replies | on (default) / off | ✅ | always on |

Not selectable: speech-to-text model (Scribe v2 is the only current option), turn eagerness (D5).

**One agent for all TTS models:** spike S1 showed the TTS *model* can be overridden per session
(like voice and language), so a single agent serves both models; the browser passes the chosen
model as a session override. (Earlier plan: one agent per model, in case it couldn't.)

## Work plan

### Progress

Legend: `[x]` done · `[ ]` to do · ⏳ in progress

| # | Milestone | Status |
|---|---|---|
| S | Spikes (S1–S4) | ⏳ S1, S2, S4 ✅; S3: only the slow-answer failure left (parked) |
| M1 | PTT transcription | ✅ Done (2026-10-29) |
| M2 | PTT spoken replies + Voice settings | ✅ Done (2026-10-29) |
| M3 | Multilingual RAG | ⏳ Prompts committed; browser test pending |
| M4 | Streaming RAG + Custom LLM endpoint | ✅ Done (2026-10-29) |
| M5 | Hands-free end to end | ⏳ Agent, `/voice/session`, hands-free button, chat messages coded; first session worked; next: M5 manual test, commit |
| M6 | Sources + model choice in hands-free | Not started |
| M7 | Hardening | Not started |

### Spikes

Run each spike just before the milestone that needs it (S1–S3 before M5, S4 before M4).

- [x] **S1 — TTS models in Agents.** (2026-10-29, no credits: OpenAPI schema + a temporary agent, created and deleted)
  - [x] Free key can use `eleven_v4_turbo` and `eleven_v3_conversational` via the TTS API (`GET /v1/models`, 2026-10-29; both 0.5 credit/char).
  - [x] Both can be selected as an Agent's TTS model: both in `TTSConversationalModel`; a test agent was created with `eleven_v4_turbo` and switched to `eleven_v3_conversational`.
  - [x] TTS model can be overridden per session: `tts.model_id` is client-overridable once `platform_settings.overrides.conversation_config_override.tts.model_id = true` (accepted by the API). **→ One agent, not one per model.** First live session (S2/S3) confirms the override takes effect.
  - Also found: Custom LLM `api_key` must be a workspace-secret reference (`ConvAISecretLocator`), so `setup_agents` stores `CUSTOM_LLM_SECRET` as an ElevenLabs workspace secret first. Extra body is enabled with `platform_settings.overrides.custom_llm_extra_body = true` and sent by the client as `custom_llm_extra_body`.
- [x] **S2 — Languages in Agents.** How language detection / switching works mid-conversation; which setting lets the user speak any language without choosing first.
  - [x] Live test (2026-10-29, 703 credits): with agent language `en` and **no extra setting**, Scribe Realtime auto-detects per turn: Telugu and Hindi arrived in their own scripts, switching en → te → en → hi mid-session worked, and our RAG answered in the same language; `eleven_v4_turbo` spoke them. No language picker needed for hands-free; the Voice-settings language can still be passed as an override.
  - Very short Hindi phrases sometimes arrive romanized ("Aapke paas kya document"); the router/answer handle it.
- [ ] **S3 — Custom LLM request shape.** Does `customLlmExtraBody` reach our endpoint, and under which field name (endpoint assumes `elevenlabs_extra_body`)? What `messages` contains after a barge-in (full generated text or only what was heard)? How the request is cancelled on interruption.
  - [x] Live test via dashboard "Test AI agent" (2026-10-29, 2 sessions, 152 s, **845 credits ≈ 330 credits/min**); requests read in the ngrok inspector. All 15 calls 200, answers from the documents, declined an out-of-document question.
  - [x] Request: `messages` (ElevenLabs' own system prompt first, then the full conversation), `model: "custom-llm"`, `temperature: 0`, `max_tokens: 8192`, `stream: true`, `stream_options.include_usage`; `Authorization: Bearer <workspace secret>`; path `/v1/chat/completions`. Extra fields are ignored by our endpoint.
  - [x] After a barge-in, `messages` holds **only what was heard**, cut off and ending in `...`. A reply interrupted before it was spoken is dropped; the user's continued speech is merged into one user turn and the request is re-sent.
  - [x] **Silence re-engagement:** after `turn_timeout` (default 7 s) of silence ElevenLabs calls us with the user message `"..."`; our RAG answers it (Groq + TTS credits, repeats itself). Fixed in `setup_agents` (`turn_timeout` = 20 s, see M5).
  - [ ] ⚠️ **Slow answers end the session** (S2 session, 15:25): for one question ElevenLabs hung up on our request after ~3.5 s with no content yet, re-sent it (several in parallel), and after repeated failures ended the call with `custom_llm generation failed`. Our endpoint sends nothing until router (Groq) + retrieval finish, and aborted requests keep running in the thread pool (more Groq load). Root cause to confirm from the backend log (Groq 429?).
  - Echo: with laptop speakers the agent's own reply was once transcribed as the user's turn ("I couldn't find that in the documents."); use headphones for tests; our frontend keeps echo cancellation on.
    Also seen from our own frontend (15:52): a 4.0 s small-talk reply was re-sent by ElevenLabs after ~4 s (duplicate request, both 200).
  - [x] Extra body field name: arrives as **`elevenlabs_extra_body`** with our `{session_id, llm_model, history}` (ngrok inspector, first session from our frontend, 2026-10-29). Endpoint unchanged.
  - [x] ElevenLabs closes the HTTP stream when it gives up: the 15:25 requests were cut at ~3.5 s with no `[DONE]`. For barge-in it rarely matters: our answers finish streaming in ~0.5–2 s, before the user can interrupt the spoken reply.
- [x] **S4 — Tunnel.** ngrok installed, authtoken set, free static domain claimed, `PUBLIC_BASE_URL` in `.env`; a stub endpoint reachable from outside.
  - [x] ngrok installed without sudo via `pyngrok` (in `requirements-dev.txt`); `.venv/bin/ngrok` → ngrok 3.39.13 in `~/.config/ngrok/` (2026-10-29).
  - [x] Authtoken set (`.venv/bin/ngrok config add-authtoken …`, stored in `~/.config/ngrok/ngrok.yml`, 2026-10-29).
  - [x] Free static domain claimed (`clean-backless-graceful.ngrok-free.dev`); `PUBLIC_BASE_URL` in `.env`.
  - [x] `GET /health` reachable through the tunnel (existing endpoint is the stub): 200 `{"status":"ok"}` via the public URL (2026-10-29).
  - Run the tunnel by hand only while testing: it makes the whole backend public.

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
- [x] Follow-up: auto-play only for questions asked with the mic (typed questions silent; D3 updated).
- [x] Browser test of the follow-up: typed question → silent; mic question → read aloud; Listen still works (2026-10-29).
- [x] Commit the follow-up.

### M3 — Multilingual RAG

Plan: make non-English questions retrieve the right passages from the English documents and
get answers in the user's language — prompt changes only, no re-ingestion.

- [x] Router prompt: `search_query` always written in English (translate if needed).
- [x] Answer prompt: reply in the language the user used; small-talk replies too.
- [ ] Test with 2–3 Hindi and Telugu questions (text first, then voice): right sources retrieved, answer language correct, read aloud correctly. Includes the Hindi/Telugu transcription check moved from M1.
- [x] Commit M3 (prompt changes committed before the browser test, on `voicefeature-m3-multilingual`).

### M4 — Streaming RAG + Custom LLM endpoint

Plan: build the endpoint ElevenLabs will call in hands-free mode. It speaks the OpenAI
chat-completions format and streams tokens so the agent can start talking early.

- [x] Spike S4 done (ngrok + static domain).
- [x] Config: `CUSTOM_LLM_SECRET` (empty disables the endpoint; generated into `.env`), `PUBLIC_BASE_URL` (in `config.py` and `.env.example`).
- [x] `RAGChain.stream_answer(question, history, model)` (sync, consumed with `iterate_in_threadpool`): route → retrieve run up front and return `(sources, token iterator)`; Groq is called only while the iterator is read; small talk as one chunk. Shared `_prepare()` keeps `/chat` unchanged.
- [x] `POST /v1/chat/completions` (`backend/voice/custom_llm.py`): bearer-secret check (401; 503 when no secret), `stream=true` only, maps `messages` to question + history (system/tool messages dropped), reads `session_id` / `llm_model` / prior history from `elevenlabs_extra_body` (field name to confirm in S3), SSE `chat.completion.chunk` events ending in `[DONE]`, stops when the client disconnects (Starlette cancels the stream). The chain is reached via `app.state.rag`.
- [x] Sources store per session (in memory, 30 min TTL; `latest_sources()` for M6's `GET /voice/sources`).
- [x] Unit tests: SSE format, auth rejection, message mapping, bad requests (`tests/test_custom_llm.py`, 8 new, 34 total, no credits).
- [x] curl test through the ngrok URL: streamed chunks ending in `[DONE]`; no token → 401 (2026-10-29).
- [x] Commit M4 (`21214dd` on `voicefeature-m4-custom-llm`).

### M5 — Hands-free end to end

Plan: create the ElevenLabs agent from code and connect the browser to it, so the user can
talk continuously and hear answers from our RAG.

- [ ] Spikes S1 (Agents part), S2 and S3 done.
- [x] `python -m backend.voice.setup_agents`: stores `CUSTOM_LLM_SECRET` as a workspace secret, then creates/updates one private agent (Custom LLM → `{PUBLIC_BASE_URL}/v1`, Scribe v2 Realtime, interruptions on, turn eagerness `normal`, auto-end after 20 s silence, max 5 min, no greeting, overrides allowed for TTS model / voice / language, custom LLM extra body on); agent id in `.env` as `ELEVENLABS_AGENT_ID`. Created `agent_5701m63fxktzevdam47efgfst83r` and read back (2026-10-29, no credits); re-run updates in place.
- [x] No silence re-engagement (S3): `turn.turn_timeout` = `SILENCE_END_S` in `setup_agents`, so a silent user gets no `"..."` turn; the session just ends after 20 s. Applied and read back (2026-10-29); confirm in the S2 session.
- [x] `GET /voice/session`: `{signed_url, session_id}` for the agent (503 when `ELEVENLABS_AGENT_ID` is empty); `elevenlabs.signed_url()` uses `get-signed-url` (free). 2 unit tests (36 total); real signed URL fetched (2026-10-29). Test fixture pins `elevenlabs_agent_id=""` because importing pymilvus loads `.env` into `os.environ`.
- [ ] Frontend: `@elevenlabs/react`; hands-free toggle next to the mic; status listening / thinking / speaking; end button; textarea disabled while active.
  - [x] Code (2026-10-29): `@elevenlabs/react` **1.18.0** pinned (client 1.28.0; newest release ≥ 2 weeks old); `ConversationProvider` in `main.jsx`; `useHandsFree.js` (mic check → `/voice/session` → `startSession` with signed URL over WebSocket, voice + language overrides, extra body `{session_id, llm_model, history}`); wave button in the Composer (stop while active), status dot + label, mic / Send / textarea disabled while active; error and "ended" notices. Frontend builds.
  - SDK 1.28.0 can't override the **TTS model** (`modelId` arrives in client 1.32.0, too new): hands-free uses the agent's default `eleven_v4_turbo` for now. Upgrade once a release with `modelId` is ≥ 2 weeks old (~2026-11-09), then remove the note under "Voice model (TTS)" in `VoiceSettings.jsx` ("Hands-free always uses … for now").
  - [ ] Browser test (credits). First session from our app (2026-10-29 15:52) connected and answered one turn with the extra body; status labels, stop button and the 20 s silence end still to confirm (folded into the M5 manual test).
- [ ] User transcripts and agent replies appear as chat messages; interrupted replies marked.
  - [x] Code (2026-10-29): `useHandsFree({ onMessage, onCorrection })` passes each finished turn (SDK `onMessage`, turn id = session id + `event_id`) to `App.jsx`, which appends it to the chat; `onAgentResponseCorrection` replaces the reply with the part that was spoken and marks it "Interrupted" (`ChatMessage.jsx`). Typing dots while hands-free is thinking. Hands-free turns are normal chat messages, so later typed questions get them as history. Frontend builds.
  - [ ] Browser test (credits, in the M5 manual test).
- [ ] Manual test: a few short sessions incl. barge-in and a follow-up question.
- [ ] Commit M5.

### M6 — Sources + model choice in hands-free

Plan: bring hands-free to parity with PTT: show sources, respect the user's settings, and
continue the existing conversation.

- [ ] `GET /voice/sources?session_id=…`; frontend attaches sources to each hands-free answer.
- [ ] Session start passes `session_id`, selected LLM and the last 6 chat turns (extra body).
- [ ] Voice, language and TTS model passed as session overrides.
- [ ] Manual test: switch modes mid-conversation; out-of-document question is declined.
- [ ] Commit M6.

### M7 — Hardening

Plan: make it safe and pleasant to use and document it.

- [ ] Limits: TTS text length, upload size, request size on the Custom LLM endpoint.
- [ ] Clear error messages for quota reached, key missing, tunnel down.
- [ ] Latency + credit logging per turn; check target end of speech → first audio < ~1.5 s.
- [ ] Bundle: load `@elevenlabs/react` only when hands-free starts (bundle went from small to 840 kB / 232 kB gzip with the SDK).
- [ ] Browser matrix: Chrome, Firefox, Safari, phone over LAN.
- [ ] README: ElevenLabs key permissions, ngrok setup, `setup_agents`, voice settings.
- [ ] Rotate the ElevenLabs API key (the current one was shared in chat).
- [ ] Rotate the Groq API key (it was visible in a screenshot).
- [ ] Reset the ngrok authtoken (the current one was shared in chat), then re-run `ngrok config add-authtoken`.
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
| Hands-free | measured ≈ 330 credits/min (S3, 2026-10-29) → ~25 min/month on the free plan |

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
