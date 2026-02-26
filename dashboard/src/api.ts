export type RunManifest = {
  run_id: string;
  created_at: string;
  command: string;
  inputs?: Record<string, any>;
  artifacts?: Record<string, string | null>;
  summary?: {
    success?: boolean;
    highlights?: string[];
  };
};

/**
 * Safely parse a Response as JSON.
 * Throws a readable error when the server returns HTML (e.g. the Vite SPA
 * fallback when the Express artifact server is not running).
 */
async function safeJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    const preview = text.slice(0, 120).replace(/\n/g, " ");
    const hint = text.trimStart().startsWith("<")
      ? " (HTML received — is the artifact server running? Start it with: npm run server)"
      : "";
    throw new Error(`API response is not valid JSON${hint}: ${preview}`);
  }
}

export async function fetchRuns(): Promise<RunManifest[]> {
  const res = await fetch("/api/runs");
  if (!res.ok) throw new Error(`Failed to load runs: ${res.status}`);
  return safeJson<RunManifest[]>(res);
}

export async function fetchRun(runId: string): Promise<RunManifest> {
  const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(`Failed to load run: ${res.status}`);
  return safeJson<RunManifest>(res);
}

export async function fetchLatest(): Promise<{ run_id: string; manifest_path: string } | null> {
  const res = await fetch("/api/latest");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load latest: ${res.status}`);
  return safeJson(res);
}
