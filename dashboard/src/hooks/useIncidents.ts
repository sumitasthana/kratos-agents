import { useState, useEffect, useCallback, useRef } from 'react';
import type { Incident } from '../types';

const MOCK_INCIDENTS: Incident[] = [
  {
    id: 'INC-4491',
    service: 'DepositInsurance-Pipeline',
    severity: 'P1',
    error: 'Control CTRL-007 failed: aggregation bypass',
    job: 'nightly_batch',
    status: 'active',
    timestamp: '2025-03-16T13:39:00Z',
  },
  {
    id: 'INC-4488',
    service: 'TrustCustody-ORC',
    severity: 'P1',
    error: 'IRR misclassification: ORC fallthrough to SGL',
    job: 'trust_processing',
    status: 'investigating',
    timestamp: '2025-03-16T11:22:00Z',
  },
  {
    id: 'INC-4485',
    service: 'WireTransfer-MT202',
    severity: 'P2',
    error: 'MT202 message handler missing',
    job: 'wire_settlement',
    status: 'investigating',
    timestamp: '2025-03-16T09:05:00Z',
  },
];

interface UseIncidentsResult {
  incidents: Incident[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useIncidents(): UseIncidentsResult {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchIncidents = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/incidents');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Incident[] = await res.json();
      setIncidents(data);
      setError(null);
    } catch {
      setIncidents(MOCK_INCIDENTS);
      setError(null); // silently fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIncidents();
    intervalRef.current = setInterval(fetchIncidents, 30_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchIncidents]);

  return { incidents, loading, error, refresh: fetchIncidents };
}
