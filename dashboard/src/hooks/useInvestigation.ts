/**
 * useInvestigation.ts  FULL REWRITE
 *
 * Starts a demo RCA investigation via POST /demo/investigations,
 * then consumes the SSE phase stream from GET /demo/stream/{id}.
 *
 * Every SSE event is merged into InvestigationState  never replaced wholesale.
 * The hook derives StatusBarState as a side-effect of state changes.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ScenarioId, StatusBarState } from "../types/demo";
import type {
  AgentThought,
  BacktrackHop,
  CanonGraph,
  ConfidenceBreakdown,
  ControlFinding,
  IncidentCard,
  InvestigationState,
  InvestigationStatus,
  PhaseId,
  PhaseResult,
  Recommendation,
  RejectedAlternative,
  SSEEvent,
  ThoughtType,
} from "../types/causelink";
import { PHASE_ORDER, TOTAL_PHASES } from "../constants/scenarios";

// Backwards-compat re-exports used by legacy components
export type {
  ConfidenceBreakdown,
  InvestigationState,
  PhaseResult as PhaseEvent,
  BacktrackHop,
  ControlFinding,
};
export type { RejectedAlternative, Recommendation };
// Legacy per-field types that existing components reference
export interface CausalEdge {
  edge_id: string;
  cause_node_id: string;
  effect_node_id: string;
  mechanism: string;
  confidence: number;
  status: string;
}
export interface RootCauseCandidate {
  candidate_id: string;
  node_id: string;
  description: string;
  composite_score: number;
  evidence_score: number;
  temporal_score: number;
  structural_depth_score: number;
  hypothesis_alignment_score: number;
  status: string;
  hypothesis_ids: string[];
  causal_edge_ids: string[];
  ranked_at: string;
}
export interface AuditTraceEntry {
  step_id: string;
  timestamp: string;
  agent_type: string;
  action: string;
  inputs_summary: Record<string, unknown>;
  outputs_summary: Record<string, unknown>;
  decision: string | null;
}
export interface EvidenceObject {
  evidence_id: string;
  type: string;
  source_system: string;
  summary: string;
  reliability: number;
  reliability_tier: string;
  collected_at: string;
  collected_by: string;
}
export interface Hypothesis {
  hypothesis_id: string;
  description: string;
  status: string;
  confidence: number;
  pattern_id: string | null;
  generated_by: string;
  involved_node_ids: string[];
}

//  Helpers 

function buildStatusBar(state: InvestigationState | null): Partial<StatusBarState> {
  if (!state) return {};
  return {
    confidence: state.confidence?.composite ?? state.confidence?.composite_score ?? undefined,
  };
}

function deriveLabel(nodeId: string): string {
  const id = nodeId.toLowerCase();
  if (id.includes("inc")) return "Incident";
  if (id.includes("ctl")) return "ControlObjective";
  if (id.includes("rul")) return "Rule";
  if (id.includes("pip")) return "Pipeline";
  if (id.includes("stp") || id.includes("mod")) return "Job";
  if (id.includes("art") || id.includes("cob") || id.includes("bcj") || id.includes("swp")) return "Script";
  return "Node";
}

function formatNodeId(nodeId: string): string {
  return nodeId.split("-").slice(2).join("-").toUpperCase();
}

function buildHopsFromPhase(ev: PhaseResult, graph: CanonGraph, existing: BacktrackHop[]): BacktrackHop[] {
  const details = ev.details ?? {};
  const chain = (details.causal_chain ?? []) as string[];
  const edgeTypes = (details.rel_types ?? details.causal_edges ?? []) as string[];
  if (chain.length === 0) return existing;
  if (existing.length > 0 && chain.length <= existing.length) return existing;

  const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]));
  return chain.map((nodeId, i) => {
    const node = nodeMap.get(nodeId);
    const isLast = i === chain.length - 1;
    return {
      hopIndex: i,
      fromNodeId: i < chain.length - 1 ? nodeId : chain[chain.length - 2] ?? nodeId,
      toNodeId: i < chain.length - 1 ? chain[i + 1] : nodeId,
      relType: edgeTypes[i] ?? "",
      status: (isLast ? "ROOT_CAUSE" : "CONFIRMED_FAILED") as BacktrackHop["status"],
      evidenceIds: [],
      nodeLabel: node?.label ?? deriveLabel(nodeId),
      nodeName: (node?.props?.name as string) ?? formatNodeId(nodeId),
    };
  });
}

function buildConfidence(details: Record<string, unknown>): ConfidenceBreakdown | null {
  const cb = (details.confidence_breakdown ?? details) as Record<string, unknown>;
  if (!cb || typeof cb !== "object") return null;
  const ev = (cb.evidence_score ?? cb.evidenceScore ?? 0) as number;
  const tmp = (cb.temporal_score ?? cb.temporalScore ?? 0) as number;
  const dep = (cb.depth_score ?? cb.depthScore ?? 0) as number;
  const hyp = (cb.hypothesis_alignment_score ?? cb.hypothesisScore ?? 0) as number;
  const comp = (cb.composite_score ?? cb.composite ?? 0) as number;
  if (comp === 0 && ev === 0) return null;
  return {
    evidenceScore: ev,
    temporalScore: tmp,
    depthScore: dep,
    hypothesisScore: hyp,
    composite: comp,
    composite_score: comp,
    threshold: (cb.threshold as number) ?? 0.70,
    confirmed: comp >= 0.70,
    evidence_score: ev,
    temporal_score: tmp,
    depth_score: dep,
    hypothesis_alignment_score: hyp,
    weights: cb.weights as ConfidenceBreakdown["weights"],
    validationGates: cb.validation_gates as Record<string, "PASS" | "FAIL"> | undefined,
  };
}

//  Reducer 

interface SliceState {
  state: InvestigationState | null;
  loading: boolean;
  error: string | null;
  statusBarState: Partial<StatusBarState>;
  thoughts: AgentThought[];
}

type SliceAction =
  | { type: "RESET" }
  | { type: "STARTED"; investigationId: string; scenarioId: ScenarioId; jobId: string }
  | { type: "PHASE"; event: PhaseResult }
  | { type: "HOP_REVEALED"; hop: BacktrackHop }
  | { type: "DONE"; finalStatus: InvestigationStatus }
  | { type: "ERROR"; message: string }
  | { type: "THOUGHT"; thought: AgentThought };

const EMPTY: InvestigationState = {
  investigationId: "", scenarioId: "", jobId: "", status: "STARTED",
  currentPhase: "INTAKE", phases: {}, canonGraph: { nodes: [], edges: [] },
  backtrackChain: [], controls: [], incidentCard: null, recommendations: [],
  rejectedAlternatives: [], confidence: null, auditTrace: [], startedAt: "",
  completedAt: null, validationGates: {}, rawPhaseEvents: [], thoughts: [],
};

function reducer(prev: SliceState, action: SliceAction): SliceState {
  switch (action.type) {
    case "RESET":
      return { state: null, loading: false, error: null, statusBarState: {}, thoughts: [] };

    case "STARTED": {
      const s: InvestigationState = {
        ...EMPTY,
        investigationId: action.investigationId,
        scenarioId: action.scenarioId,
        jobId: action.jobId,
        startedAt: new Date().toISOString(),
        status: "RUNNING",
      };
      return { state: s, loading: true, error: null, statusBarState: buildStatusBar(s), thoughts: [] };
    }

    case "PHASE": {
      if (!prev.state) return prev;
      const ev = action.event;
      const phaseId = ev.phase as PhaseId;
      const details = ev.details ?? {};
      let g = prev.state.canonGraph;
      let hops = prev.state.backtrackChain;
      let controls = prev.state.controls;
      let incident = prev.state.incidentCard;
      let recs = prev.state.recommendations;
      let conf = prev.state.confidence;

      if (phaseId === "BACKTRACK") {
        const cg = details.canon_graph as CanonGraph | undefined;
        if (cg?.nodes?.length) g = cg;
        const newHops = buildHopsFromPhase(ev, g, hops);
        if (newHops.length > 0) hops = newHops;
      }
      if (phaseId === "INCIDENT_CARD") {
        const card = details.incident_card as IncidentCard | undefined;
        if (card) incident = card;
        const rawCtrl = (details.controls ?? details.failed_controls) as ControlFinding[] | undefined;
        if (rawCtrl?.length) controls = rawCtrl;
      }
      if (phaseId === "RECOMMEND") {
        const r = details.recommendations as Recommendation[] | undefined;
        if (r?.length) recs = r;
      }
      if (phaseId === "PERSIST") {
        conf = buildConfidence(details);
        const r = details.recommendations as Recommendation[] | undefined;
        if (r?.length) recs = r;
      }

      const next: InvestigationState = {
        ...prev.state,
        currentPhase: phaseId,
        phases: { ...prev.state.phases, [phaseId]: { ...ev, uiStatus: "PASS" } },
        canonGraph: g,
        backtrackChain: hops,
        controls,
        incidentCard: incident,
        recommendations: recs,
        confidence: conf,
        rawPhaseEvents: [...prev.state.rawPhaseEvents, ev],
      };
      return { state: next, loading: true, error: null, statusBarState: { ...prev.statusBarState, ...buildStatusBar(next) }, thoughts: prev.thoughts };
    }

    case "HOP_REVEALED": {
      if (!prev.state) return prev;
      const hop = action.hop;
      const already = prev.state.backtrackChain.some((h) => h.hopIndex === hop.hopIndex && h.fromNodeId === hop.fromNodeId);
      if (already) return prev;
      const next: InvestigationState = { ...prev.state, backtrackChain: [...prev.state.backtrackChain, hop] };
      return { ...prev, state: next, statusBarState: { ...prev.statusBarState } };
    }

    case "DONE": {
      if (!prev.state) return prev;
      const next: InvestigationState = { ...prev.state, status: action.finalStatus, completedAt: new Date().toISOString() };
      return { state: next, loading: false, error: null, statusBarState: { ...prev.statusBarState, ...buildStatusBar(next) }, thoughts: prev.thoughts };
    }

    case "ERROR":
      return { ...prev, loading: false, error: action.message, state: prev.state ? { ...prev.state, status: "ERROR" } : null };

    case "THOUGHT": {
      const t = action.thought;
      const lastIdx = prev.thoughts.findIndex(
        (x) => x.step_index === t.step_index && x.agent === t.agent,
      );
      if (lastIdx >= 0) {
        const updated = [...prev.thoughts];
        updated[lastIdx] = { ...updated[lastIdx], content: updated[lastIdx].content + t.content };
        return { ...prev, thoughts: updated };
      }
      return { ...prev, thoughts: [...prev.thoughts, t] };
    }

    default:
      return prev;
  }
}

//  Hook 

export function useInvestigation(): {
  state: InvestigationState | null;
  statusBarState: Partial<StatusBarState>;
  loading: boolean;
  error: string | null;
  thoughts: AgentThought[];
  startInvestigation: (scenarioId: ScenarioId, jobId: string) => Promise<void>;
  reset: () => void;
} {
  const [{ state, loading, error, statusBarState, thoughts }, dispatch] = useReducer(reducer, {
    state: null, loading: false, error: null, statusBarState: {}, thoughts: [],
  });
  const esRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    dispatch({ type: "RESET" });
  }, []);

  const startInvestigation = useCallback(async (scenarioId: ScenarioId, jobId: string) => {
    esRef.current?.close();
    esRef.current = null;
    dispatch({ type: "RESET" });

    const t0 = Date.now();
    let investigationId: string;

    try {
      const res = await fetch("/demo/investigations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: scenarioId, job_id: jobId }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as Record<string, unknown>;
        throw new Error((body.message as string) ?? `HTTP ${res.status}`);
      }
      const data = await res.json() as { investigation_id: string };
      investigationId = data.investigation_id;
    } catch (err) {
      dispatch({ type: "ERROR", message: err instanceof Error ? err.message : String(err) });
      return;
    }

    dispatch({ type: "STARTED", investigationId, scenarioId, jobId });

    const es = new EventSource(`/demo/stream/${investigationId}`);
    esRef.current = es;

    es.onmessage = (event: MessageEvent<string>) => {
      let raw: SSEEvent;
      try { raw = JSON.parse(event.data) as SSEEvent; }
      catch { return; }

      if (raw.type === "KEEPALIVE") return;

      if (raw.type === "AGENT_THOUGHT") {
        const d = (raw.details ?? {}) as Record<string, unknown>;
        const thought: AgentThought = {
          agent:            (d.agent as string) ?? "",
          step_index:       (d.step_index as number) ?? 0,
          thought_type:     (d.thought_type as ThoughtType) ?? "OBSERVING",
          content:          (d.content as string) ?? "",
          evidence_refs:    (d.evidence_refs as string[]) ?? [],
          node_refs:        (d.node_refs as string[]) ?? [],
          confidence_delta: (d.confidence_delta as number) ?? 0,
          phase:            (raw.phase as string) ?? "",
          timestamp:        raw.emitted_at,
        };
        dispatch({ type: "THOUGHT", thought });
        return;
      }

      if (raw.type === "HOP_REVEALED") {
        const hops = (raw.data?.hops ?? []) as BacktrackHop[];
        hops.forEach((h) => dispatch({ type: "HOP_REVEALED", hop: h }));
        return;
      }

      if (raw.type === "INVESTIGATION_COMPLETE") {
        const s = ((raw.data?.status as string) ?? "COMPLETED") as InvestigationStatus;
        es.close(); esRef.current = null;
        dispatch({ type: "DONE", finalStatus: s });
        return;
      }

      if (raw.type === "ERROR") {
        const msg = (raw.data?.message as string) ?? (raw.summary ?? "Unknown error");
        es.close(); esRef.current = null;
        dispatch({ type: "ERROR", message: msg });
        return;
      }

      // PHASE_COMPLETE or legacy PhaseEvent (no type field)
      const phaseEvent: PhaseResult = {
        phase: (raw.phase ?? "UNKNOWN") as PhaseId,
        phaseNumber: raw.phase_number ?? 0,
        investigationId: raw.investigation_id ?? investigationId,
        scenarioId: raw.scenario_id ?? scenarioId,
        status: raw.status ?? "",
        summary: raw.summary ?? "",
        details: raw.details ?? (raw.data as Record<string, unknown>) ?? {},
        emittedAt: raw.emitted_at ?? raw.timestamp ?? new Date().toISOString(),
        durationMs: Date.now() - t0,
      };
      dispatch({ type: "PHASE", event: phaseEvent });

      if (phaseEvent.phase === "PERSIST") {
        setTimeout(() => dispatch({ type: "DONE", finalStatus: "CONFIRMED" }), 800);
      }
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;
      dispatch({ type: "ERROR", message: "SSE connection lost" });
    };
  }, []);

  useEffect(() => () => { esRef.current?.close(); }, []);

  return { state, statusBarState, loading, error, thoughts, startInvestigation, reset };
}
