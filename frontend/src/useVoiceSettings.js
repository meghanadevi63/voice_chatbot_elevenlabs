import { useCallback, useEffect, useState } from "react";
import { getVoiceOptions } from "./api.js";

const STORAGE_KEY = "docs-assistant-voice";
// Until the options load, null ids mean "server default"
const FALLBACK = { ttsModel: null, voiceId: null, llmModel: null, language: null, speakReplies: true };

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

// Keep only choices the server still offers; the backend owns the allow-lists
function validate(choice, options) {
  const d = options.defaults;
  const pick = (value, list, fallback) => (list.some((x) => x.id === value) ? value : fallback);
  const ttsModel = pick(choice.ttsModel, options.tts_models, d.tts_model);
  const languages = options.tts_models.find((m) => m.id === ttsModel)?.languages || [];
  return {
    ttsModel,
    voiceId: pick(choice.voiceId, options.voices, d.voice_id),
    llmModel: pick(choice.llmModel, options.llm_models, d.llm_model),
    // A language the new voice model can't speak falls back to auto-detect
    language: languages.some((l) => l.code === choice.language) ? choice.language : d.language,
    speakReplies: typeof choice.speakReplies === "boolean" ? choice.speakReplies : d.speak_replies,
  };
}

// Voice settings panel state: options from GET /voice/options, choices in localStorage.
export default function useVoiceSettings(backendOk) {
  const [options, setOptions] = useState(null);
  const [error, setError] = useState(null);
  const [settings, setSettings] = useState(() => ({
    ...FALLBACK,
    speakReplies: loadSaved().speakReplies ?? true,
  }));

  // Load once the backend is reachable (and retry after it comes back)
  useEffect(() => {
    if (!backendOk || options) return;
    let active = true;
    getVoiceOptions()
      .then((opts) => {
        if (!active) return;
        setOptions(opts);
        setError(null);
        setSettings(validate(loadSaved(), opts));
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [backendOk, options]);

  const update = useCallback(
    (patch) =>
      setSettings((prev) => {
        const next = options ? validate({ ...prev, ...patch }, options) : { ...prev, ...patch };
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          // Storage unavailable: settings last for this visit only
        }
        return next;
      }),
    [options]
  );

  return { options, error, settings, update };
}
