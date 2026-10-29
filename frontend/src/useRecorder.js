import { useCallback, useEffect, useRef, useState } from "react";

// Hard stop so a forgotten recording can't grow without bound (and burn STT credits)
const MAX_SECONDS = 120;

export function micErrorMessage(e) {
  if (e?.name === "NotAllowedError") return "Microphone access is blocked. Allow it in the browser's site settings.";
  if (e?.name === "NotFoundError") return "No microphone found.";
  return e?.message || "Couldn't start the microphone.";
}

// Records microphone audio. record() resolves with the audio Blob once stop() is
// called or MAX_SECONDS is reached.
export default function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recorderRef = useRef(null);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }, []);

  const record = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Microphone needs a secure page (HTTPS or localhost).");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });

    return new Promise((resolve, reject) => {
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      const started = Date.now();
      const timer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - started) / 1000);
        setSeconds(elapsed);
        if (elapsed >= MAX_SECONDS) stop();
      }, 250);

      const finish = () => {
        clearInterval(timer);
        stream.getTracks().forEach((t) => t.stop());
        recorderRef.current = null;
        setRecording(false);
      };

      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        finish();
        resolve(new Blob(chunks, { type: recorder.mimeType }));
      };
      recorder.onerror = (e) => {
        finish();
        reject(e.error || new Error("Recording failed."));
      };

      recorderRef.current = recorder;
      setSeconds(0);
      setRecording(true);
      recorder.start();
    });
  }, [stop]);

  // Release the microphone if the component goes away mid-recording
  useEffect(() => stop, [stop]);

  return { recording, seconds, record, stop };
}
