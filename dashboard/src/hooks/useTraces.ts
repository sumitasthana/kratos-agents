/**
 * dashboard/src/hooks/useTraces.ts
 *
 * Fetches OTel spans for a given investigation from /obs/traces/{id}.
 * Re-fetches whenever investigationId changes.
 */

import { useEffect, useState } from "react";
import type { ObsSpan } from "../types/observability";

export interface UseTracesResult {
  spans: ObsSpan[];
  loading: boolean;
  error: string | null;
}

export function useTraces(investigationId: string | null): UseTracesResult {
  const [spans, setSpans] = useState<ObsSpan[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (investigationId === null) {
      setSpans([]);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/obs/traces/${encodeURIComponent(investigationId)}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json() as { spans: ObsSpan[] };
        if (!cancelled) {
          setSpans(data.spans ?? []);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [investigationId]);

  return { spans, loading, error };
}
