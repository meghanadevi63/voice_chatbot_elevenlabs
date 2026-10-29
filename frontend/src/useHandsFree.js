import { useConversation } from "@elevenlabs/react";
import { useCallback, useRef, useState } from "react";
import { getHandsFreeSession } from "./api.js";
import { micErrorMessage } from "./useRecorder.js";

// Chat turns from before the session, so the agent can follow up on them
const HISTORY_TURNS = 6;

// Hands-free conversation with our ElevenLabs agent. ElevenLabs listens, detects the end of
// each turn and speaks; our backend (/v1/chat/completions) writes every answer.
// status: "off" | "connecting" | "listening" | "thinking" | "speaking"
// onMessage({ turnId, role, content }) for each finished turn; onCorrection({ turnId, content })
// when the user interrupts a reply (content = the part that was spoken).
export default function useHandsFree({ onMessage, onCorrection }) {
  const [starting, setStarting] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  // Event ids restart in every session, so turn ids include the session id
  const sessionRef = useRef(null);

  const conversation = useConversation({
    onMessage: ({ role, message, event_id }) => {
      // A finished user turn means our backend is working on the answer
      setThinking(role === "user");
      const turnId = `${sessionRef.current}:${event_id}`;
      onMessage({ turnId, role: role === "user" ? "user" : "assistant", content: message });
    },
    onAgentResponseCorrection: ({ corrected_agent_response, event_id }) =>
      onCorrection({ turnId: `${sessionRef.current}:${event_id}`, content: corrected_agent_response }),
    onModeChange: ({ mode }) => mode === "speaking" && setThinking(false),
    onError: (message) => setError(message || "Hands-free conversation failed."),
    onDisconnect: (details) => {
      setThinking(false);
      if (details.reason === "error") setError(details.message || "Hands-free conversation stopped.");
      // The agent hangs up after 20 s of silence or 5 min (setup_agents)
      else if (details.reason === "agent") setNotice("Hands-free ended. Click the wave button to talk again.");
    },
  });

  const start = useCallback(
    async ({ history, voiceId, language, llmModel }) => {
      setError(null);
      setNotice(null);
      setStarting(true);
      try {
        // Ask for the mic first so a blocked mic gets a clear message
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("Microphone needs a secure page (HTTPS or localhost).");
        }
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          stream.getTracks().forEach((t) => t.stop());
        } catch (e) {
          throw new Error(micErrorMessage(e));
        }

        const { signed_url, session_id } = await getHandsFreeSession();
        sessionRef.current = session_id;
        conversation.startSession({
          signedUrl: signed_url,
          connectionType: "websocket",
          // TTS model stays the agent's default until the SDK can override it (needs client >= 1.32)
          overrides: {
            tts: voiceId ? { voiceId } : undefined,
            // No language = Scribe auto-detects every turn
            agent: language ? { language } : undefined,
          },
          customLlmExtraBody: { session_id, llm_model: llmModel || null, history: history.slice(-HISTORY_TURNS) },
        });
      } catch (e) {
        setError(e.message);
      } finally {
        setStarting(false);
      }
    },
    [conversation]
  );

  const end = useCallback(() => conversation.endSession(), [conversation]);

  let status = "off";
  if (starting || conversation.status === "connecting") status = "connecting";
  else if (conversation.status === "connected") {
    if (conversation.isSpeaking) status = "speaking";
    else status = thinking ? "thinking" : "listening";
  }

  return { status, active: status !== "off", error, notice, start, end };
}
