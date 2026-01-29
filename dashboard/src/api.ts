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

export async function fetchRuns(): Promise<RunManifest[]> {
  const res = await fetch("/api/runs");
  if (!res.ok) throw new Error(`Failed to load runs: ${res.status}`);
  return res.json();
}

export async function fetchRun(runId: string): Promise<RunManifest> {
  const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(`Failed to load run: ${res.status}`);
  return res.json();
}

export async function fetchLatest(): Promise<{ run_id: string; manifest_path: string } | null> {
  const res = await fetch("/api/latest");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load latest: ${res.status}`);
  return res.json();
}
