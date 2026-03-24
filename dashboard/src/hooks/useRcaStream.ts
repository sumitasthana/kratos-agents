import { useState, useCallback, useRef } from 'react';
import type { HopEvent, RcaResult, PhaseStep, HopNode, RemAction, ChatMsg } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8002';

const PHASE_AGENTS: Record<string, string> = {
  INTAKE:        'IntakeAgent',
  LOGS_FIRST:    'EvidenceAgent',
  ROUTE:         'RoutingAgent',
  BACKTRACK:     'BacktrackAgent',
  INCIDENT_CARD: 'IncidentAgent',
  RECOMMEND:     'RecommendAgent',
  PERSIST:       'RankerAgent',
};

export function useRcaStream() {
  // Legacy — kept for backward compat with RcaTracePanel/ConfidenceGauge
  const [hops,    setHops]    = useState<HopEvent[]>([]);
  const [result,  setResult]  = useState<RcaResult | null>(null);
  // New structured state
  const [phases,     setPhases]     = useState<PhaseStep[]>([]);
  const [hopNodes,   setHopNodes]   = useState<HopNode[]>([]);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);

  const [tracing, setTracing] = useState(false);
  const [syncPct, setSyncPct] = useState(100);
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const abortRef     = useRef<AbortController | null>(null);
  const incidentRef  = useRef<string | null>(null);
  const scenarioRef  = useRef<string | null>(null);
  const recsRef      = useRef<RemAction[]>([]);
  // Refs so ask() can read current result/phases without stale closures
  const resultRef    = useRef<RcaResult | null>(null);
  const phasesRef    = useRef<PhaseStep[]>([]);

  const trace = useCallback(async (text: string) => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    // Reset all state
    setHops([]);
    setResult(null);
    setPhases([]);
    setHopNodes([]);
    setScenarioId(null);
    setIncidentId(null);
    setChatMessages([]);
    incidentRef.current  = null;
    scenarioRef.current  = null;
    recsRef.current      = [];
    resultRef.current    = null;
    phasesRef.current    = [];
    setTracing(true);
    setSyncPct(0);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ text }),
        signal:  abortRef.current.signal,
      });

      if (!res.body) throw new Error('No stream body');
      const reader = res.body.getReader();
      const dec    = new TextDecoder();
      let   buf    = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });

        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (raw === '[DONE]') { setTracing(false); setSyncPct(100); break; }

          try {
            const evt = JSON.parse(raw) as Record<string, unknown>;
            const evtType = (evt.type as string) ?? '';

            // ── SKILL_RESOLVED: first event from /api/chat ─────────────
            if (evtType === 'SKILL_RESOLVED') {
              const sid = evt.scenario_id as string | null;
              if (sid) { setScenarioId(sid); scenarioRef.current = sid; }
              continue;
            }

            // ── Grab scenario_id from any PhaseEvent field ──────────────
            if (!scenarioRef.current && evt.scenario_id) {
              const sid = evt.scenario_id as string;
              setScenarioId(sid);
              scenarioRef.current = sid;
            }

            // ── PHASE_COMPLETE ──────────────────────────────────────────
            if (evtType === 'PHASE_COMPLETE') {
              const phase   = (evt.phase as string) ?? '';
              const details = (evt.details as Record<string, unknown>) ?? {};

              // Extract incident_id from INTAKE phase
              if (phase === 'INTAKE') {
                const iid = details.incident_id as string | undefined;
                if (iid) { setIncidentId(iid); incidentRef.current = iid; }
              }

              // Build RcaResult from PERSIST phase confidence breakdown
              if (phase === 'PERSIST') {
                const bd = (details.confidence_breakdown as Record<string, number>) ?? {};
                const composite = bd.composite_score ?? 0;
                const built: RcaResult = {
                  incident_id:          incidentRef.current ?? '',
                  root_cause_final:     (details.root_cause_node_id as string) ?? null,
                  defect_id:            null,
                  confidence: {
                    composite,
                    tier: composite >= 0.70 ? 'CONFIRMED' : composite >= 0.40 ? 'HIGH' : 'MEDIUM',
                    E: bd.evidence_score            ?? 0,
                    T: bd.temporal_score            ?? 0,
                    D: bd.depth_score               ?? 0,
                    H: bd.hypothesis_alignment_score ?? 0,
                  },
                  regulation_citations: [],
                  remediation:          recsRef.current,
                  audit_trace:          [],
                };
                resultRef.current = built;
                setResult(built);
                setSyncPct(100);
              }

              // Capture recommendations from RECOMMEND phase
              if (phase === 'RECOMMEND') {
                const recs = details.recommendations as RemAction[] | undefined;
                if (recs?.length) recsRef.current = recs;
              }

              setPhases(prev => {
                const next = [...prev, {
                  phase,
                  phase_number: (evt.phase_number as number) ?? 0,
                  status:       (evt.status  as string) ?? '',
                  summary:      (evt.summary as string) ?? '',
                  agent:        PHASE_AGENTS[phase] ?? 'DemoRcaService',
                  details,
                }];
                phasesRef.current = next;
                return next;
              });

              setSyncPct(prev => Math.max(prev, Math.round(
                (((evt.phase_number as number) ?? 0) / 7) * 80
              )));
            }

            // ── HOP_REVEALED — one per causal edge during BACKTRACK ─────
            if (evtType === 'HOP_REVEALED') {
              const details = (evt.details as Record<string, unknown>) ?? {};
              const hopIdx  = (details.hop_index as number) ?? 0;
              setHopNodes(prev => [...prev, {
                from_node_id: (details.from_node_id as string) ?? '',
                to_node_id:   (details.to_node_id   as string) ?? '',
                rel_type:     (details.rel_type      as string) ?? '',
                hop_index:    hopIdx,
                status:       (details.status        as string) ?? 'confirmed',
              }]);
              setSyncPct(Math.min(90, 40 + hopIdx * 12));
            }

            // ── INVESTIGATION_COMPLETE — all 7 phases done ──────────────
            if (evtType === 'INVESTIGATION_COMPLETE') {
              setTracing(false);
              setSyncPct(100);
            }

            // ── Legacy: hop / result events (pre-demo API) ──────────────
            if (evtType === 'hop') {
              setHops(prev => [...prev, evt as unknown as HopEvent]);
            }
            if (evtType === 'result') {
              setResult(evt.data as RcaResult);
              setTracing(false);
              setSyncPct(100);
            }

          } catch { /* malformed SSE — skip */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') setTracing(false);
    }
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setTracing(false);
  }, []);

  // ── ask(): follow-up question — does NOT reset RCA state ────────────────
  const ask = useCallback(async (text: string) => {
    const userMsg: ChatMsg = { role: 'user', content: text, ts: new Date().toISOString() };
    setChatMessages(prev => [...prev, userMsg]);

    // Append a placeholder assistant message we'll fill in token-by-token
    const assistantTs = new Date().toISOString();
    setChatMessages(prev => [...prev, { role: 'assistant', content: '', ts: assistantTs }]);

    try {
      const res = await fetch(`${API_BASE}/api/ask`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question:    text,
          scenario_id: scenarioRef.current ?? undefined,
          investigation_context: {
            root_cause_final: resultRef.current?.root_cause_final ?? null,
            confidence:       resultRef.current?.confidence ?? null,
            remediation:      resultRef.current?.remediation ?? [],
            phases: phasesRef.current.map(p => ({
              phase:   p.phase,
              status:  p.status,
              summary: p.summary,
            })),
          },
        }),
      });
      if (!res.ok || !res.body) {
        const errText = res.body
          ? await res.text().catch(() => `HTTP ${res.status}`)
          : `HTTP ${res.status}`;
        setChatMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant') {
            updated[updated.length - 1] = { ...last, content: `Error: ${errText.slice(0, 200)}` };
          }
          return updated;
        });
        return;
      }

      const reader = res.body.getReader();
      const dec    = new TextDecoder();
      let   buf    = '';

      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() ?? '';
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          const raw = line.slice(5).trim();
          if (raw === '[DONE]') break outer;
          try {
            const evt = JSON.parse(raw) as Record<string, unknown>;
            if (evt.type === 'TOKEN') {
              const token = (evt.text as string) ?? '';
              // Append token to the last (placeholder) assistant message
              setChatMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'assistant') {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + token,
                  };
                }
                return updated;
              });
            }
            if (evt.type === 'DONE' || evt.type === 'ERROR') {
              if (evt.type === 'ERROR') {
                setChatMessages(prev => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last?.role === 'assistant' && last.content === '') {
                    updated[updated.length - 1] = {
                      ...last,
                      content: `Error: ${(evt.message as string) ?? 'Server error.'}`,
                    };
                  }
                  return updated;
                });
              }
              break outer;
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setChatMessages(prev => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === 'assistant' && last.content === '') {
            updated[updated.length - 1] = {
              ...last,
              content: 'Unable to reach the analysis server. Check your connection.',
            };
          }
          return updated;
        });
      }
    }
  }, []);

  return {
    hops, result, tracing, syncPct, trace, abort,
    phases, hopNodes, scenarioId, incidentId,
    chatMessages, ask,
  };
}
