import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { BridgeProvider } from "./lib/BridgeContext";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BridgeProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </BridgeProvider>
  </StrictMode>,
);
