/**
 * dashboard/src/hooks/useMetrics.ts
 *
 * Polls /obs/metrics/live on a configurable interval and keeps the two most
 * recent snapshots so callers can render delta arrows.
 */

import { useEffect, useRef, useState } from "react";
import type { LiveMetrics } from "../types/observability";

export interface UseMetricsResult {
  metrics: LiveMetrics | null;
  prevMetrics: LiveMetrics | null;
  error: string | null;
}

export function useMetrics(pollIntervalMs = 2000): UseMetricsResult {
  const [metrics, setMetrics] = useState<LiveMetrics | null>(null);
  const [prevMetrics, setPrevMetrics] = useState<LiveMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchOnce(): Promise<void> {
      try {
        const res = await fetch("/obs/metrics/live");
        if (!res.ok) {
          setError(`HTTP ${res.status}`);
          return;
        }
        const data: LiveMetrics = await res.json() as LiveMetrics;
        if (!cancelled) {
          setMetrics((prev) => {
            setPrevMetrics(prev);
            return data;
          });
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    }

    void fetchOnce();
    timerRef.current = setInterval(() => { void fetchOnce(); }, pollIntervalMs);

    return () => {
      cancelled = true;
      if (timerRef.current !== null) clearInterval(timerRef.current);
    };
  }, [pollIntervalMs]);

  return { metrics, prevMetrics, error };
}
