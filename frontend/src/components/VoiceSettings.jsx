// Choices come from GET /voice/options, so the UI only offers what the server allows.
export default function VoiceSettings({ options, error, settings, onChange }) {
  if (error) return <p className="note note-bad">Voice options unavailable: {error}</p>;
  if (!options) return <p className="muted">Loading voice options…</p>;

  const languages = [...(options.tts_models.find((m) => m.id === settings.ttsModel)?.languages || [])].sort(
    (a, b) => a.name.localeCompare(b.name)
  );
  const voices = [...options.voices].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="settings">
      <label className="toggle">
        <input
          type="checkbox"
          checked={settings.speakReplies}
          onChange={(e) => onChange({ speakReplies: e.target.checked })}
        />
        Speak replies to voice questions
      </label>

      <label className="field">
        <span>Speech-to-text model (STT)</span>
        {/* Read-only: the server offers a single STT model */}
        <select value={options.stt_models[0]?.id || ""} disabled={options.stt_models.length < 2}>
          {options.stt_models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Voice model (TTS)</span>
        <select value={settings.ttsModel || ""} onChange={(e) => onChange({ ttsModel: e.target.value })}>
          {options.tts_models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        {/* Until the ElevenLabs SDK can override the model per session (plan M5) */}
        <small className="field-note">
          Hands-free always uses {options.defaults.tts_model} for now. This choice applies to push-to-talk and Listen.
        </small>
      </label>

      <label className="field">
        <span>Voice</span>
        <select value={settings.voiceId || ""} onChange={(e) => onChange({ voiceId: e.target.value })}>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Language you speak</span>
        <select value={settings.language || ""} onChange={(e) => onChange({ language: e.target.value || null })}>
          <option value="">Auto-detect</option>
          {languages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.name}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>Answer model</span>
        <select value={settings.llmModel || ""} onChange={(e) => onChange({ llmModel: e.target.value })}>
          {options.llm_models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
