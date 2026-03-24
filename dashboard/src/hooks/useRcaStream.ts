import { useState, useEffect, useCallback, useRef } from 'react';
import type { RcaMessage, PhaseId } from '../types';

// ── Mock data ────────────────────────────────────────────────────────────────

const MOCK_MESSAGES: RcaMessage[] = [
  {
    id: 'm1',
    type: 'system',
    phase: 'INTAKE',
    timestamp: Date.now(),
    text: 'Incident INC-4491 loaded. 2 of 21 controls failed.',
  },
  {
    id: 'm2',
    type: 'agent',
    phase: 'INTAKE',
    timestamp: Date.now(),
    agent: 'Orchestrator',
    text: 'Seeding ontology graph. CTRL-007 failed on nightly_batch run. Regulation: 12 CFR §330.1(b). Starting trace.',
  },
  {
    id: 'm3',
    type: 'hop',
    phase: 'INTAKE',
    timestamp: Date.now(),
    hops: [
      { from: 'System:legacy_deposit', edge: 'RUNS_JOB', to: 'Job:nightly_batch' },
      { from: 'Job:nightly_batch', edge: 'EXECUTES', to: 'Pipeline:deposit_insurance' },
      { from: 'Pipeline:deposit_insurance', edge: 'GOVERNED_BY', to: 'Regulation:12CFR330' },
      { from: 'Regulation:12CFR330', edge: 'MANDATES', to: 'ControlObjective:CTRL-007' },
    ],
  },
  {
    id: 'm4',
    type: 'agent',
    phase: 'LOGS_FIRST',
    timestamp: Date.now(),
    agent: 'SparkLogTool',
    tag: 'evidence',
    text: 'Aggregation stage: 0 records output. Insurance calc consumed raw_deposits directly — 847,231 rows bypassed aggregation.',
  },
  {
    id: 'm5',
    type: 'agent',
    phase: 'LOGS_FIRST',
    timestamp: Date.now(),
    agent: 'AirflowLogTool',
    tag: 'evidence',
    text: "Task 'run_aggregation' SKIPPED — JCL flag check resolved WS-SKIP-AGG=Y. Downstream tasks proceeded without aggregated input.",
  },
  {
    id: 'm6',
    type: 'agent',
    phase: 'ROUTE',
    timestamp: Date.now(),
    agent: 'RoutingAgent',
    text: 'Pattern identified: configuration_bypass (confidence 0.92). Dispatching: GitDiffTool, DataProfiler, DDLDiffTool.',
  },
  {
    id: 'm7',
    type: 'evidence',
    phase: 'BACKTRACK',
    timestamp: Date.now(),
    source: 'GitDiffTool',
    filename: 'deposit_agg.cbl',
    language: 'COBOL',
    defect: 'DEF-AGG-001',
    code: `000142* AGGREGATION CONTROL FLAG
000143  05 WS-SKIP-AGG PIC X(1) VALUE 'Y'. *> CHANGED
000144* Commit: a3f7c2 by ops-automation
000145* "disable aggregation for performance testing"`,
  },
  {
    id: 'm8',
    type: 'hop',
    phase: 'BACKTRACK',
    timestamp: Date.now(),
    hops: [
      { from: 'Pipeline:deposit_insurance', edge: 'USES_SCRIPT', to: 'Script:deposit_agg.cbl' },
      { from: 'Script:deposit_agg.cbl', edge: 'CHANGED_BY', to: 'CodeEvent:commit_a3f7c2' },
      { from: 'Script:deposit_agg.cbl', edge: 'TYPICALLY_IMPLEMENTS', to: 'Transformation:deposit_aggregation' },
      { from: 'Rule:AGG_RULE_001', edge: 'ENFORCED_BY', to: 'Transformation:deposit_aggregation' },
    ],
  },
  {
    id: 'm9',
    type: 'agent',
    phase: 'BACKTRACK',
    timestamp: Date.now(),
    agent: 'DataProfiler',
    tag: 'finding',
    text: 'aggregated_deposits = 847,231 rows (expected ~312K). 147,892 depositors affected. Estimated excess FDIC coverage: ~$12.3B.',
  },
  {
    id: 'm10',
    type: 'triangulation',
    phase: 'INCIDENT_CARD',
    timestamp: Date.now(),
    confidence: 0.97,
    rootCause: 'CodeEvent commit_a3f7c2 set WS-SKIP-AGG=Y in deposit_agg.cbl, disabling deposit aggregation. Insurance calculated on raw deposits — 847K rows vs expected 312K.',
    regulation: '12 CFR §330.1(b)',
    defect: 'DEF-AGG-001',
  },
  {
    id: 'm11',
    type: 'recommendation',
    phase: 'RECOMMEND',
    timestamp: Date.now(),
    items: [
      {
        priority: 'P1',
        action: 'Revert WS-SKIP-AGG=Y to N in deposit_agg.cbl and rerun nightly_batch',
        owner: 'John Chen',
        effort: '2 hr',
        regulation: '§330.1(b)',
      },
      {
        priority: 'P1',
        action: 'Reprocess 147,892 depositor records and recalculate FDIC coverage',
        owner: 'Maria Santos',
        effort: '4 hr',
        regulation: '§330.1(b)',
      },
      {
        priority: 'P2',
        action: 'Add pre-production gate blocking JCL changes to controls marked blocking',
        owner: 'Alex Kim',
        effort: '2 days',
      },
    ],
  },
  {
    id: 'm12',
    type: 'system',
    phase: 'PERSIST',
    timestamp: Date.now(),
    text: 'RCA complete. 7 phases, 47s elapsed, 15 ontology nodes traversed, 5 evidence objects, 3 recommendations.',
  },
];

// ── Hook ────────────────────────────────────────────────────────────────────

interface UseRcaStreamResult {
  messages: RcaMessage[];
  isTracing: boolean;
  currentPhase: PhaseId | null;
  connect: (incidentId: string) => void;
  disconnect: () => void;
}

export function useRcaStream(): UseRcaStreamResult {
  const [messages, setMessages] = useState<RcaMessage[]>([]);
  const [isTracing, setIsTracing] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<PhaseId | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const mockTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mockIndexRef = useRef(0);
  const incidentIdRef = useRef<string>('');

  const clearMockTimer = () => {
    if (mockTimerRef.current) {
      clearTimeout(mockTimerRef.current);
      mockTimerRef.current = null;
    }
  };

  const playNextMock = useCallback(() => {
    const idx = mockIndexRef.current;
    if (idx >= MOCK_MESSAGES.length) {
      setIsTracing(false);
      return;
    }
    const msg = { ...MOCK_MESSAGES[idx], id: `${incidentIdRef.current}-${idx}`, timestamp: Date.now() };
    setMessages(prev => [...prev, msg]);
    setCurrentPhase(msg.phase);
    mockIndexRef.current = idx + 1;

    const delay = idx === MOCK_MESSAGES.length - 1 ? 0 : 900;
    if (delay > 0) {
      mockTimerRef.current = setTimeout(playNextMock, delay);
    } else {
      setIsTracing(false);
    }
  }, []);

  const startMockStream = useCallback(() => {
    mockIndexRef.current = 0;
    setMessages([]);
    setIsTracing(true);
    setCurrentPhase('INTAKE');
    mockTimerRef.current = setTimeout(playNextMock, 400);
  }, [playNextMock]);

  const disconnect = useCallback(() => {
    clearMockTimer();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsTracing(false);
  }, []);

  const connect = useCallback((incidentId: string) => {
    disconnect();
    incidentIdRef.current = incidentId;
    setMessages([]);
    setCurrentPhase(null);

    const ws = new WebSocket('ws://localhost:5001/ws');
    wsRef.current = ws;

    ws.onopen = () => {
      setIsTracing(true);
      ws.send(JSON.stringify({ type: 'start_trace', incident_id: incidentId }));
    };

    ws.onmessage = (event) => {
      try {
        const msg: RcaMessage = JSON.parse(event.data as string);
        setMessages(prev => [...prev, msg]);
        setCurrentPhase(msg.phase);
      } catch {
        // ignore malformed
      }
    };

    ws.onerror = () => {
      wsRef.current = null;
      startMockStream();
    };

    ws.onclose = (e) => {
      if (e.code !== 1000) {
        wsRef.current = null;
        startMockStream();
      } else {
        setIsTracing(false);
      }
    };

    // If WS doesn't open within 1.5s, fall back to mock
    const timeout = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        ws.close();
        wsRef.current = null;
        startMockStream();
      }
    }, 1500);

    ws.addEventListener('open', () => clearTimeout(timeout));
  }, [disconnect, startMockStream]);

  useEffect(() => () => disconnect(), [disconnect]);

  return { messages, isTracing, currentPhase, connect, disconnect };
}
