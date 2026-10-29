import { ConversationProvider } from "@elevenlabs/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    {/* Hands-free conversation state (useHandsFree) */}
    <ConversationProvider>
      <App />
    </ConversationProvider>
  </StrictMode>
);
