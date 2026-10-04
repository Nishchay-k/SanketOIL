import { useEffect } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function SanketApp() {
  useEffect(() => {
    void (async () => {
      try {
        const response = await fetch("/runtime-config", { cache: "no-store" });
        if (response.ok) window.__SANKET_CONFIG__ = await response.json();
      } catch {
        // Vite can still run with its local VITE_* fallbacks while the API is stopped.
      }
      await import("./legacy/app");
    })().catch((error: unknown) => {
      console.error("SANKET failed to start", error);
      const root = document.getElementById("app");
      if (root) {
        root.innerHTML = '<main class="boot-screen"><strong>SANKET could not start</strong><span>Check the server configuration and refresh this page.</span></main>';
      }
    });
  }, []);

  return (
    <div className="min-h-screen">
      <div id="app">
        <div className="boot-screen">
          <img className="brand-emblem boot-emblem" src="/branding/sanket-mark.png" alt="SANKET mark" />
          <strong>SANKET</strong>
          <span>Nearby Wells Intelligence System</span>
        </div>
      </div>
      <div id="dialog-root" />
    </div>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("Missing React application root.");
createRoot(root).render(<SanketApp />);
