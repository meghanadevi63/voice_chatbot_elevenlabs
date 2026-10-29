// Same origin by default (Vite proxy in dev, FastAPI in prod).
// Set VITE_BACKEND_URL only if the API is hosted somewhere else.
const BASE = (import.meta.env.VITE_BACKEND_URL || "").replace(/\/$/, "");

// `parse` reads a successful response; JSON unless the endpoint returns e.g. audio
async function request(path, options = {}, parse = (res) => res.json()) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      // FormData sets its own multipart Content-Type (with boundary)
      headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
      ...options,
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("Can't reach the backend. Is it running?");
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // Non-JSON error body: keep the status text
    }
    throw new Error(detail);
  }
  return parse(res);
}

export const checkHealth = () => request("/health");

export const sendChat = (question, history, llmModel) =>
  request("/chat", {
    method: "POST",
    body: JSON.stringify({ question, history, llm_model: llmModel || null }),
  });

export const ingestDocs = () => request("/ingest", { method: "POST" });

// Safari records audio/mp4, Firefox audio/ogg, Chrome audio/webm
function audioExtension(type) {
  if (type.includes("mp4")) return "m4a";
  if (type.includes("ogg")) return "ogg";
  return "webm";
}

export const transcribe = (audio, language) => {
  const form = new FormData();
  form.append("file", audio, `speech.${audioExtension(audio.type)}`);
  if (language) form.append("language", language);
  return request("/voice/transcribe", { method: "POST", body: form });
};

export const getVoiceOptions = () => request("/voice/options");

// { signed_url, session_id } for one hands-free conversation with the agent
export const getHandsFreeSession = () => request("/voice/session");

// Spoken answer as an MP3 Blob. Missing model/voice use the server defaults.
export const speak = (text, model, voiceId, signal) =>
  request(
    "/voice/tts",
    { method: "POST", body: JSON.stringify({ text, model: model || null, voice_id: voiceId || null }), signal },
    (res) => res.blob()
  );
