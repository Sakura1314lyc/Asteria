import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8765",
      "/capabilities": "http://127.0.0.1:8765",
      "/agents": "http://127.0.0.1:8765",
      "/connections": "http://127.0.0.1:8765",
      "/conversations": "http://127.0.0.1:8765",
      "/taxonomy": "http://127.0.0.1:8765",
      "/projects": "http://127.0.0.1:8765",
      "/runs": "http://127.0.0.1:8765",
      "/jobs": "http://127.0.0.1:8765"
    }
  },
  build: {
    outDir: fileURLToPath(
      new URL("../src/paper_agent/web_dist", import.meta.url)
    ),
    emptyOutDir: true,
    sourcemap: false
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts"
  }
});
