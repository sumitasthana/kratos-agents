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
      // ── Kratos WebSocket relay (port 5001) ──────────────────────────────
      "/ws": {
        target: "ws://127.0.0.1:5001",
        ws: true,
        changeOrigin: true,
      },
      // ── Incidents API (port 8000) ────────────────────────────────────────
      "/incidents": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
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
      // ── Demo API (port 8002) ─────────────────────────────────────────────
      // The configure hook sets headers required for SSE (text/event-stream)
      // so that Vite's proxy does not buffer the response and the browser
      // EventSource receives events in real-time.
      "/demo": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            // For SSE endpoints, signal that we accept event-stream.
            if (req.url?.includes("/stream/")) {
              proxyReq.setHeader("Accept", "text/event-stream");
              proxyReq.setHeader("Cache-Control", "no-cache");
              proxyReq.setHeader("X-Accel-Buffering", "no");
            }
          });
          proxy.on("proxyRes", (proxyRes, req) => {
            if (req.url?.includes("/stream/")) {
              // Disable buffering so chunks arrive immediately.
              proxyRes.headers["x-accel-buffering"] = "no";
              proxyRes.headers["cache-control"] = "no-cache";
            }
          });
        },
      },
      // Observability API — port 8003
      "/obs": {
        target: "http://127.0.0.1:8003",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            if (req.url?.includes("/stream")) {
              proxyReq.setHeader("Accept", "text/event-stream");
              proxyReq.setHeader("Cache-Control", "no-cache");
              proxyReq.setHeader("X-Accel-Buffering", "no");
            }
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
