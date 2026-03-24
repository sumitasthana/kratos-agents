/**
 * useScenarios.ts
 *
 * Fetches the list of available demo scenarios from GET /demo/scenarios.
 * Returns { scenarios, loading, error }.
 */

import { useEffect, useState } from 'react';
import type { ScenarioSummary } from '../types/demo';

export type { ScenarioSummary };

interface UseScenarioOptions {
  enabled?: boolean;
}

interface UseScenarioResult {
  scenarios: ScenarioSummary[];
  loading: boolean;
  error: string | null;
}

export function useScenarios(options?: UseScenarioOptions): UseScenarioResult {
  const enabled = options?.enabled ?? true;
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading]     = useState(enabled);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch('/demo/scenarios')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<{ items: ScenarioSummary[]; total: number }>;
      })
      .then((data) => {
        if (!cancelled) {
          setScenarios(data.items);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { scenarios, loading, error };
}
