/**
 * hooks/useControlScan.ts
 *
 * Fetches control scan results from GET /demo/controls/{scenarioId}.
 * Returns { result, loading, error, refetch }.
 */

import { useCallback, useEffect, useState } from 'react';
import type { ControlFinding } from '../types/causelink';

export interface ControlScanResult {
  scenario_id: string;
  incident_id: string;
  scanned_at: string;
  total_controls: number;
  passed: number;
  failed: number;
  warnings: number;
  critical_failures: number;
  has_critical_failure: boolean;
  findings: ControlFinding[];
}

interface UseControlScanResult {
  result: ControlScanResult | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useControlScan(scenarioId: string | null): UseControlScanResult {
  const [result, setResult] = useState<ControlScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!scenarioId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/demo/controls/${scenarioId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<ControlScanResult>;
      })
      .then((data) => {
        if (!cancelled) {
          setResult(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, tick]);

  return { result, loading, error, refetch };
}
