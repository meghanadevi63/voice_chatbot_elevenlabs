import Sources from "./Sources.jsx";
import { SpeakerIcon, StopIcon } from "./icons.jsx";

// Listen / stop control under an answer. `playStatus` is "loading", "playing" or undefined.
function SpeakButton({ playStatus, onPlay, onStop }) {
  if (playStatus) {
    return (
      <button className="speak-btn active" onClick={onStop} aria-label="Stop speaking">
        <StopIcon /> {playStatus === "loading" ? "Preparing audio…" : "Stop"}
      </button>
    );
  }
  return (
    <button className="speak-btn" onClick={onPlay} aria-label="Read this answer aloud">
      <SpeakerIcon /> Listen
    </button>
  );
}

export default function ChatMessage({ message, playStatus, playError, onPlay, onStop }) {
  const { role, content, sources, error, typing, interrupted } = message;

  if (role === "user") {
    return (
      <div className="msg msg-user">
        <div className="bubble">{content}</div>
      </div>
    );
  }

  return (
    <div className={`msg msg-assistant ${error ? "msg-error" : ""}`}>
      {typing ? (
        <div className="typing" aria-label="Assistant is thinking">
          <span />
          <span />
          <span />
        </div>
      ) : (
        <>
          <div className="answer">{error ? `Something went wrong: ${content}` : content}</div>
          {interrupted && <p className="interrupted-note">Interrupted</p>}
          {!error && onPlay && <SpeakButton playStatus={playStatus} onPlay={onPlay} onStop={onStop} />}
          {playError && <p className="play-error">{playError}</p>}
          {sources?.length > 0 && <Sources sources={sources} />}
        </>
      )}
    </div>
  );
}
