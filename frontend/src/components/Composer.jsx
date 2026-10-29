import { useEffect, useRef, useState } from "react";
import { transcribe } from "../api.js";
import useRecorder, { micErrorMessage } from "../useRecorder.js";
import { MicIcon, SendIcon, StopIcon, WaveIcon } from "./icons.jsx";

const MAX_HEIGHT = 200;
// Shorter clips are almost always accidental clicks; skip them to save STT credits
const MIN_RECORDING_MS = 700;

const HANDS_FREE_LABELS = {
  connecting: "Connecting…",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

const formatTime = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export default function Composer({ onSend, disabled, language, onRecordStart, handsFree, onHandsFreeStart }) {
  const [text, setText] = useState("");
  const [transcribing, setTranscribing] = useState(false);
  const [micError, setMicError] = useState(null);
  const { recording, seconds, record, stop } = useRecorder();
  const ref = useRef(null);
  const micBusyRef = useRef(false);
  // True once the mic added text to the box; only spoken questions get spoken answers
  const spokenRef = useRef(false);

  // Grow the textarea with its content, up to MAX_HEIGHT
  useEffect(() => {
    const el = ref.current;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [text]);

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  const busy = recording || transcribing || handsFree.active;

  const submit = () => {
    const question = text.trim();
    if (!question || disabled || busy) return;
    onSend(question, { spoken: spokenRef.current });
    spokenRef.current = false;
    setText("");
  };

  // Push-to-talk: click to start, click again to stop. The transcript is added to
  // the text box so the user can check or edit it before sending.
  const toggleMic = async () => {
    if (recording) {
      stop();
      return;
    }
    // Ignore clicks while the browser's permission prompt is still open
    if (micBusyRef.current) return;
    micBusyRef.current = true;
    try {
      await dictate();
    } finally {
      micBusyRef.current = false;
    }
  };

  const dictate = async () => {
    setMicError(null);
    // Don't record the assistant's own voice
    onRecordStart?.();

    let audio;
    const startedAt = Date.now();
    try {
      audio = await record();
    } catch (e) {
      setMicError(micErrorMessage(e));
      return;
    }
    if (Date.now() - startedAt < MIN_RECORDING_MS) {
      setMicError("Recording was too short. Click the mic, speak, then click stop.");
      return;
    }

    setTranscribing(true);
    try {
      const { text: spoken } = await transcribe(audio, language);
      if (spoken) {
        spokenRef.current = true;
        setText((prev) => (prev.trim() ? `${prev.trimEnd()} ${spoken}` : spoken));
      } else {
        setMicError("Didn't catch any speech. Please try again.");
      }
    } catch (e) {
      setMicError(e.message);
    } finally {
      setTranscribing(false);
      ref.current?.focus();
    }
  };

  let placeholder = "Ask a question about your documents";
  if (handsFree.active) placeholder = "Hands-free: just talk. Click stop to end.";
  else if (recording) placeholder = "Listening… click stop when you're done";
  else if (transcribing) placeholder = "Transcribing…";

  const handsFreeMessage = handsFree.error || handsFree.notice;

  return (
    <div className="composer-wrap">
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={ref}
          rows={1}
          value={text}
          placeholder={placeholder}
          disabled={handsFree.active}
          onChange={(e) => {
            // Clearing the box drops the transcript, so the next question counts as typed
            if (!e.target.value.trim()) spokenRef.current = false;
            setText(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {recording && (
          <span className="rec-status" aria-live="polite">
            <span className="rec-dot" />
            {formatTime(seconds)}
          </span>
        )}
        {transcribing && <span className="rec-status">Transcribing…</span>}
        {handsFree.active && (
          <span className={`rec-status hf-${handsFree.status}`} aria-live="polite">
            <span className="rec-dot" />
            {HANDS_FREE_LABELS[handsFree.status]}
          </span>
        )}
        {!handsFree.active && (
          <button
            className={`mic-btn${recording ? " recording" : ""}`}
            type="button"
            onClick={toggleMic}
            disabled={transcribing}
            aria-label={recording ? "Stop recording" : "Speak your question"}
            title={recording ? "Stop recording" : "Speak your question"}
          >
            {recording ? <StopIcon /> : <MicIcon />}
          </button>
        )}
        {!recording && !transcribing && (
          <button
            className={`mic-btn${handsFree.active ? " hands-free" : ""}`}
            type="button"
            onClick={handsFree.active ? handsFree.end : onHandsFreeStart}
            disabled={disabled || handsFree.status === "connecting"}
            aria-label={handsFree.active ? "End hands-free conversation" : "Start hands-free conversation"}
            title={handsFree.active ? "End hands-free conversation" : "Hands-free: talk without clicking"}
          >
            {handsFree.active ? <StopIcon /> : <WaveIcon />}
          </button>
        )}
        <button className="send-btn" type="submit" disabled={disabled || busy || !text.trim()} aria-label="Send">
          <SendIcon />
        </button>
      </form>
      {micError && (
        <p className="composer-error" role="alert">
          {micError}
        </p>
      )}
      {handsFreeMessage && (
        <p className={handsFree.error ? "composer-error" : "composer-note"} role={handsFree.error ? "alert" : "status"}>
          {handsFreeMessage}
        </p>
      )}
      <p className="hint">
        Answers come only from your indexed documents. Enter to send, Shift+Enter for a new line, click the mic to
        speak, or the wave button to talk hands-free.
      </p>
    </div>
  );
}
