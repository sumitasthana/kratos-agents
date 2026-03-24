import express from "express";
import fs from "fs";
import http from "http";
import path from "path";
import url from "url";

const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = 4173;
// FastAPI RCA backend (POST /api/run_rca and /api/run_rca_from_logs).
// Use 127.0.0.1 explicitly — "localhost" can resolve to ::1 (IPv6) on
// Windows, causing ECONNREFUSED when uvicorn listens on 127.0.0.1 only.
const FASTAPI_HOST = "127.0.0.1";
const FASTAPI_PORT = 8000;

const repoRoot = path.resolve(__dirname, "..");
const runsRoot = path.resolve(repoRoot, "runs");
const manifestsDir = path.resolve(runsRoot, "run_manifests");
const latestPath = path.resolve(runsRoot, "latest.json");

function safeResolveRunsPath(p) {
  const abs = path.resolve(repoRoot, p);
  const rel = path.relative(repoRoot, abs);
  if (rel.startsWith("..") || path.isAbsolute(rel) && rel.startsWith("..")) {
    throw new Error("Path escapes repo root");
  }
  const relRuns = path.relative(runsRoot, abs);
  if (relRuns.startsWith("..")) {
    throw new Error("Only paths under runs/ are allowed");
  }
  return abs;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf-8"));
}

const app = express();

// API
app.get("/api/runs", (req, res) => {
  if (!fs.existsSync(manifestsDir)) {
    return res.json([]);
  }

  const files = fs
    .readdirSync(manifestsDir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => path.resolve(manifestsDir, f));

  const manifests = [];
  for (const fp of files) {
    try {
      manifests.push(readJson(fp));
    } catch {
      // ignore malformed
    }
  }

  manifests.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  res.json(manifests);
});

app.get("/api/runs/:runId", (req, res) => {
  const runId = req.params.runId;
  const manifestPath = path.resolve(manifestsDir, `${runId}.json`);
  if (!fs.existsSync(manifestPath)) {
    return res.status(404).json({ error: "Run not found" });
  }
  res.json(readJson(manifestPath));
});

app.get("/api/latest", (req, res) => {
  if (!fs.existsSync(latestPath)) {
    return res.status(404).json({ error: "No latest run" });
  }
  res.json(readJson(latestPath));
});

app.get("/api/file", (req, res) => {
  const p = String(req.query.path || "");
  if (!p) return res.status(400).json({ error: "Missing path" });

  try {
    const abs = safeResolveRunsPath(p);
    if (!fs.existsSync(abs)) return res.status(404).json({ error: "Not found" });
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.send(fs.readFileSync(abs, "utf-8"));
  } catch (e) {
    res.status(400).json({ error: String(e?.message || e) });
  }
});

// Clear all run history: removes every manifest and resets latest.json
app.delete("/api/clear-history", (req, res) => {
  try {
    let deleted = 0;

    // Remove all run manifests
    if (fs.existsSync(manifestsDir)) {
      const files = fs
        .readdirSync(manifestsDir)
        .filter((f) => f.endsWith(".json"));
      for (const f of files) {
        fs.rmSync(path.resolve(manifestsDir, f), { force: true });
        deleted++;
      }
    }

    // Remove latest.json pointer
    if (fs.existsSync(latestPath)) {
      fs.rmSync(latestPath, { force: true });
    }

    console.log(`[dashboard] Clear-history: removed ${deleted} manifest(s)`);
    res.json({ ok: true, deleted });
  } catch (e) {
    console.error("[dashboard] Clear-history error:", e);
    res.status(500).json({ error: String(e?.message || e) });
  }
});

// ── Proxy /api/run_rca* → FastAPI on port 8000 ───────────────────────────────
// Used when the dashboard Express server is the public entry point (production
// mode or `npm run server`).  In `npm run dev` mode Vite's proxy handles this.
function proxyToFastAPI(req, res) {
  const body = [];
  req.on("data", (chunk) => body.push(chunk));
  req.on("end", () => {
    const data = Buffer.concat(body);
    const options = {
      hostname: FASTAPI_HOST,
      port:     FASTAPI_PORT,
      path:     req.url,
      method:   req.method,
      headers:  {
        ...req.headers,
        host:             `${FASTAPI_HOST}:${FASTAPI_PORT}`,
        "content-length": data.length,
      },
    };
    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });
    proxyReq.on("error", (err) => {
      console.error("[dashboard] FastAPI proxy error:", err.message);
      if (!res.headersSent) {
        res.status(502).json({ error: `FastAPI proxy error: ${err.message}` });
      }
    });
    proxyReq.end(data);
  });
}

app.post("/api/run_rca", proxyToFastAPI);
app.post("/api/run_rca_from_logs", proxyToFastAPI);
app.post("/api/run_rca_from_file", proxyToFastAPI);
app.get("/api/logs/browse", proxyToFastAPI);

// ── Proxy /api/rca/* → CauseLink RCA API on port 8001 ─────────────────────────────────
// Handles: GET /api/rca/scenarios, POST /api/rca/chat/investigate,
//           GET /api/rca/sessions/:id, GET /api/rca/jobs/:id/dashboard, etc.
const CAUSELINK_PORT = 8001;

function proxyToCauseLink(req, res) {
  const body = [];
  req.on("data", (chunk) => body.push(chunk));
  req.on("end", () => {
    const data = Buffer.concat(body);
    const options = {
      hostname: FASTAPI_HOST,
      port:     CAUSELINK_PORT,
      // app.use('/api/rca') strips '/api/rca' from req.url, so restore '/rca'
      // to match CauseLink's actual route prefix (e.g. /rca/scenarios)
      path:     "/rca" + req.url,
      method:   req.method,
      headers:  {
        ...req.headers,
        host:             `${FASTAPI_HOST}:${CAUSELINK_PORT}`,
        "content-length": data.length,
      },
    };
    const proxyReq = http.request(options, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });
    proxyReq.on("error", (err) => {
      console.error("[dashboard] CauseLink proxy error:", err.message);
      if (!res.headersSent) {
        res.status(502).json({ error: `CauseLink proxy error: ${err.message}` });
      }
    });
    proxyReq.end(data);
  });
}

app.use("/api/rca", (req, res) => proxyToCauseLink(req, res));

// ── Proxy /demo/* → Demo API on port 8002 ────────────────────────────────────
// Handles DemoPage endpoints: /demo/scenarios, /demo/investigations, /demo/stream/{id}, etc.
const DEMO_API_PORT = 8002;

function proxyToDemo(req, res) {
  const body = [];
  req.on("data", (chunk) => body.push(chunk));
  req.on("end", () => {
    const data = Buffer.concat(body);
    // app.use('/demo') strips '/demo' from req.url; restore it
    const targetPath = "/demo" + req.url;
    const isSSE = targetPath.includes("/stream/");
    const options = {
      hostname: FASTAPI_HOST,
      port:     DEMO_API_PORT,
      path:     targetPath,
      method:   req.method,
      headers:  {
        ...req.headers,
        host:             `${FASTAPI_HOST}:${DEMO_API_PORT}`,
        "content-length": data.length,
        ...(isSSE ? { accept: "text/event-stream", "cache-control": "no-cache" } : {}),
      },
    };
    const proxyReq = http.request(options, (proxyRes) => {
      if (isSSE) {
        proxyRes.headers["x-accel-buffering"] = "no";
        proxyRes.headers["cache-control"] = "no-cache";
      }
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });
    proxyReq.on("error", (err) => {
      console.error("[dashboard] Demo API proxy error:", err.message);
      if (!res.headersSent) {
        res.status(502).json({ error: `Demo API proxy error: ${err.message}` });
      }
    });
    proxyReq.end(data);
  });
}

app.use("/demo", (req, res) => proxyToDemo(req, res));

// Static UI (built)
const distDir = path.resolve(__dirname, "dist");
if (fs.existsSync(distDir)) {
  app.use(express.static(distDir));

  app.get("*", (req, res) => {
    res.sendFile(path.join(distDir, "index.html"));
  });
} else {
  app.get("/", (req, res) => {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.send(
      "Dashboard not built yet.\n\n" +
        "From the dashboard/ folder run:\n" +
        "  npm install\n" +
        "  npm run build\n" +
        "Then start the server:\n" +
        "  npm run server\n"
    );
  });
}

app.listen(PORT, () => {
  console.log(`[dashboard] Server running at http://localhost:${PORT}`);
  console.log(`[dashboard] Reading artifacts from: ${runsRoot}`);
});
