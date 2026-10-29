import { useCallback, useEffect, useRef, useState } from "react";
import { checkHealth, ingestDocs, sendChat } from "./api.js";
import ChatMessage from "./components/ChatMessage.jsx";
import Composer from "./components/Composer.jsx";
import EmptyState from "./components/EmptyState.jsx";
import Sidebar from "./components/Sidebar.jsx";
import { MenuIcon } from "./components/icons.jsx";
import usePlayer from "./usePlayer.js";
import useVoiceSettings from "./useVoiceSettings.js";

const STORAGE_KEY = "docs-assistant-messages";
const HEALTH_INTERVAL_MS = 15000;

let nextId = 0;
const newId = () => `${Date.now()}-${nextId++}`;

function loadMessages() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

// History sent to the backend: skip failed replies and the question that caused them.
function toHistory(messages) {
  return messages
    .filter((m, i) => !m.error && !messages[i + 1]?.error)
    .map(({ role, content }) => ({ role, content }));
}

export default function App() {
  const [messages, setMessages] = useState(loadMessages);
  const [pending, setPending] = useState(false);
  const [backend, setBackend] = useState("checking");
  const [ingest, setIngest] = useState({ status: "idle" });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef(null);
  const voice = useVoiceSettings(backend === "ok");
  const player = usePlayer();
  const { ttsModel, voiceId, llmModel, speakReplies } = voice.settings;
  const { play, stop } = player;

  const speakAnswer = useCallback(
    (message) => play(message.id, message.content, { model: ttsModel, voiceId }),
    [play, ttsModel, voiceId]
  );

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // Storage unavailable (private mode etc.): chat still works, just isn't kept
    }
  }, [messages]);

  useEffect(() => {
    let active = true;
    const check = () =>
      checkHealth()
        .then(() => active && setBackend("ok"))
        .catch(() => active && setBackend("down"));
    check();
    const timer = setInterval(check, HEALTH_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  const ask = useCallback(
    async (question, { spoken = false } = {}) => {
      // A new question interrupts the answer being read aloud
      stop();
      const history = toHistory(messages);
      setMessages((prev) => [...prev, { id: newId(), role: "user", content: question }]);
      setPending(true);
      try {
        const { answer, sources } = await sendChat(question, history, llmModel);
        const reply = { id: newId(), role: "assistant", content: answer, sources };
        setMessages((prev) => [...prev, reply]);
        // Typed questions stay silent; Listen still reads any answer on demand
        if (speakReplies && spoken) speakAnswer(reply);
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          { id: newId(), role: "assistant", content: e.message, error: true },
        ]);
      } finally {
        setPending(false);
      }
    },
    [messages, stop, llmModel, speakReplies, speakAnswer]
  );

  const reingest = useCallback(async () => {
    setIngest({ status: "running" });
    try {
      setIngest({ status: "done", result: await ingestDocs() });
    } catch (e) {
      setIngest({ status: "error", message: e.message });
    }
  }, []);

  const clearChat = useCallback(() => {
    stop();
    setMessages([]);
    setSidebarOpen(false);
  }, [stop]);

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        backend={backend}
        ingest={ingest}
        onIngest={reingest}
        onClear={clearChat}
        canClear={messages.length > 0 && !pending}
        voice={voice}
      />

      <main className="main">
        <header className="topbar">
          <button className="icon-btn" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <MenuIcon />
          </button>
          <span className="topbar-title">Docs Assistant</span>
        </header>

        <div className="messages">
          <div className="messages-inner">
            {messages.length === 0 ? (
              <EmptyState onPick={ask} disabled={pending} />
            ) : (
              messages.map((m) => (
                <ChatMessage
                  key={m.id}
                  message={m}
                  playStatus={player.playing?.id === m.id ? player.playing.status : undefined}
                  playError={player.errors[m.id]}
                  onPlay={m.role === "assistant" ? () => speakAnswer(m) : undefined}
                  onStop={stop}
                />
              ))
            )}
            {pending && <ChatMessage message={{ role: "assistant", typing: true }} />}
            <div ref={bottomRef} />
          </div>
        </div>

        <Composer onSend={ask} disabled={pending} language={voice.settings.language} onRecordStart={stop} />
      </main>
    </div>
  );
}
