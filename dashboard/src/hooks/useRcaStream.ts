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
  isConnected: boolean;                      // true when WS is live to backend
  currentPhase: PhaseId | null;
  connect: (incidentId: string, mode?: 'rca' | 'chat') => void;
  disconnect: () => void;
  startTrace: (incidentId: string) => void;  // alias for connect (rca mode)
  send: (query: string) => void;             // send follow-up chat query
}

export function useRcaStream(): UseRcaStreamResult {
  const [messages, setMessages] = useState<RcaMessage[]>([]);
  const [isTracing, setIsTracing] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
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

  const connect = useCallback((incidentId: string, mode: 'rca' | 'chat' = 'rca') => {
    disconnect();
    incidentIdRef.current = incidentId;
    setMessages([]);
    setCurrentPhase(null);

    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const apiHost = window.location.hostname;
    const ws = new WebSocket(`${wsScheme}://${apiHost}:8001/ws`);
    wsRef.current = ws;

    // Guard: ignore events from a stale WebSocket after a new connect() call.
    const isStale = () => wsRef.current !== ws;

    ws.onopen = () => {
      if (isStale()) return;
      setIsTracing(mode === 'rca');
      setIsConnected(true);
      setCurrentPhase(mode === 'chat' ? 'PERSIST' : null);
      ws.send(JSON.stringify({ incident_id: incidentId, mode }));
    };

    ws.onmessage = (event) => {
      if (isStale()) return;
      try {
        const msg: RcaMessage = JSON.parse(event.data as string);

        // Skip keepalive messages from the timeline — just update phase
        if (msg.type === 'system' && typeof msg.text === 'string' && msg.text.startsWith('Pipeline running')) {
          setCurrentPhase(msg.phase);
          return;
        }

        setMessages(prev => [...prev, msg]);
        setCurrentPhase(msg.phase);
        if (msg.phase === 'PERSIST' && msg.type === 'system') {
          setIsTracing(false);
        }
      } catch {
        // ignore malformed
      }
    };

    ws.onerror = () => {
      if (isStale()) return;
      wsRef.current = null;
      setIsConnected(false);
    };

    ws.onclose = (e) => {
      console.warn('[WS] onclose fired — code:', e.code, 'reason:', e.reason, 'wasClean:', e.wasClean, 'stale:', isStale());
      console.trace('[WS] close stack trace');
      // If a newer connection replaced this one, ignore entirely.
      if (isStale()) return;
      setIsConnected(false);
      setIsTracing(false);
      wsRef.current = null;
      if (e.code !== 1000) {
        setMessages(prev => {
          if (prev.length === 0) {
            console.warn('[WS] no messages — starting mock stream');
            setTimeout(() => startMockStream(), 0);
          }
          return prev;
        });
      }
    };

    // If WS doesn't open within 10s, fall back to mock.
    // Generous timeout: the real-mode orchestrator sends the first INTAKE
    // message within ~0.5s of connecting, so 10s is enough buffer.
    const timeout = setTimeout(() => {
      if (ws.readyState !== WebSocket.OPEN) {
        ws.close();
        wsRef.current = null;
        setIsConnected(false);
        startMockStream();
      }
    }, 10000);

    ws.addEventListener('open', () => clearTimeout(timeout));
  }, [disconnect, startMockStream]);

  const send = useCallback((query: string) => {
    // Append user message to the stream so it renders in the chat
    const userMsg: RcaMessage = {
      id: `user-${Date.now()}`,
      type: 'user' as const,
      phase: currentPhase ?? 'PERSIST',
      timestamp: Date.now(),
      text: query,
    };
    setMessages(prev => [...prev, userMsg]);

    // Send to backend via open WebSocket
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'chat', query }));
    } else {
      // WebSocket not connected — show offline notice and attempt reconnect
      const offlineMsg: RcaMessage = {
        id: `sys-offline-${Date.now()}`,
        type: 'agent' as const,
        phase: currentPhase ?? 'PERSIST',
        timestamp: Date.now(),
        agent: 'Kratos',
        text: 'Chat is not connected to the backend. Attempting to reconnect…',
        tag: 'info',
      };
      setMessages(prev => [...prev, offlineMsg]);

      // Attempt to reconnect and resend
      const incId = incidentIdRef.current || 'INC-UNKNOWN';
      const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const apiHost = window.location.hostname;
      const reconnectWs = new WebSocket(`${wsScheme}://${apiHost}:8001/ws`);

      reconnectWs.onopen = () => {
        wsRef.current = reconnectWs;
        // Re-initiate session then send the chat query
        reconnectWs.send(JSON.stringify({ incident_id: incId }));

        // Attach persistent message handler
        reconnectWs.onmessage = (event) => {
          try {
            const msg: RcaMessage = JSON.parse(event.data as string);

            // Skip keepalive messages from the timeline — just update phase
            if (msg.type === 'system' && typeof msg.text === 'string' && msg.text.startsWith('Pipeline running')) {
              setCurrentPhase(msg.phase);
              return;
            }

            setMessages(prev => [...prev, msg]);
            setCurrentPhase(msg.phase);
          } catch {
            // ignore malformed
          }
        };
        reconnectWs.onclose = () => { wsRef.current = null; };
        reconnectWs.onerror = () => { wsRef.current = null; };

        // Wait briefly for the pipeline to stream, then send the chat query
        setTimeout(() => {
          if (reconnectWs.readyState === WebSocket.OPEN) {
            reconnectWs.send(JSON.stringify({ type: 'chat', query }));
          }
        }, 2000);
      };

      reconnectWs.onerror = () => {
        const errMsg: RcaMessage = {
          id: `sys-err-${Date.now()}`,
          type: 'agent' as const,
          phase: currentPhase ?? 'PERSIST',
          timestamp: Date.now(),
          agent: 'Kratos',
          text: 'Could not connect to the Kratos backend on port 8001. Make sure the API server is running (.\start.ps1).',
          tag: 'info',
        };
        setMessages(prev => [...prev, errMsg]);
      };
    }
  }, [currentPhase]);

  useEffect(() => () => disconnect(), [disconnect]);

  return { messages, isTracing, isConnected, currentPhase, connect, disconnect, startTrace: connect, send };
}
