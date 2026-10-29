import { useCallback, useEffect, useRef, useState } from "react";
import { speak } from "./api.js";

// Plays spoken answers, one at a time. `playing` is { id, status: "loading" | "playing" }
// for the message being spoken; `errors` holds the last playback error per message id.
export default function usePlayer() {
  const [playing, setPlaying] = useState(null);
  const [errors, setErrors] = useState({});
  const currentRef = useRef(null);

  const stop = useCallback(() => {
    const current = currentRef.current;
    if (!current) return;
    currentRef.current = null;
    current.controller.abort();
    current.audio?.pause();
    if (current.url) URL.revokeObjectURL(current.url);
    setPlaying(null);
  }, []);

  const play = useCallback(
    async (id, text, { model, voiceId } = {}) => {
      stop();
      const current = { id, controller: new AbortController() };
      currentRef.current = current;
      setPlaying({ id, status: "loading" });
      setErrors(({ [id]: _, ...rest }) => rest);

      try {
        const blob = await speak(text, model, voiceId, current.controller.signal);
        if (currentRef.current !== current) return;
        current.url = URL.createObjectURL(blob);
        current.audio = new Audio(current.url);
        current.audio.onended = () => currentRef.current === current && stop();
        await current.audio.play();
        if (currentRef.current === current) setPlaying({ id, status: "playing" });
      } catch (e) {
        // Stopped on purpose (new question, recording, stop button)
        if (e.name === "AbortError" || currentRef.current !== current) return;
        stop();
        const message =
          e.name === "NotAllowedError" ? "The browser blocked autoplay. Click Listen to hear it." : e.message;
        setErrors((prev) => ({ ...prev, [id]: message }));
      }
    },
    [stop]
  );

  useEffect(() => stop, [stop]);

  return { playing, errors, play, stop };
}
