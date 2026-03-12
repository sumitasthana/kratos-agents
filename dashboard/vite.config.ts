import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy RCA endpoints to the FastAPI backend during `npm run dev`.
    // Use 127.0.0.1 (not localhost) to avoid IPv6 / ::1 resolution failures
    // on Windows where localhost may resolve to ::1 but uvicorn listens on
    // 127.0.0.1 only.
    // The more-specific path (/api/run_rca_from_logs) is listed first so it
    // wins before the shorter /api/run_rca prefix rule.
    proxy: {
      // ── FastAPI RCA backend (port 8000) ─────────────────────────────────
      // More-specific paths are listed first so they win before shorter prefixes.
      "/api/run_rca_from_logs": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api/run_rca_from_file": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api/logs": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api/run_rca": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },      // ── CauseLink RCA workspace API (port 8001) ───────────────────────────────────
      // Must be listed before /api/runs to avoid prefix clash.
      "/api/rca": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api/, ""),
      },      // ── Express artifact / history server (port 4173) ────────────────────
      // Routes served by `npm run server` (dashboard/server.js).
      // In dev mode Vite would otherwise fall back to serving index.html for
      // these paths, causing res.json() to receive <!doctype HTML.
      "/api/runs": {
        target: "http://127.0.0.1:4173",
        changeOrigin: true,
      },
      "/api/latest": {
        target: "http://127.0.0.1:4173",
        changeOrigin: true,
      },
      "/api/file": {
        target: "http://127.0.0.1:4173",
        changeOrigin: true,
      },
      "/api/clear-history": {
        target: "http://127.0.0.1:4173",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
