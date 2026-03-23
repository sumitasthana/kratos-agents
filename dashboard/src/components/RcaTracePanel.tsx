/**
 * RcaTracePanel.tsx
 *
 * Live causal trace viewer — shows:
 *  1. Live agent banner (current agent + latest thought) while running
 *  2. Phase timeline (one row per completed phase with agent + summary)
 *  3. Hop-by-hop backtracking chain (fade-in per hop)
 *  4. "Next:" indicator for the upcoming phase
 */

import React, { useEffect, useRef } from "react";
import type { AgentThought, BacktrackHop, PhaseId, PhaseResult } from "../types/causelink";
import { PHASE_LABELS, PHASE_ORDER } from "../constants/scenarios";

interface Props {
  hops:          BacktrackHop[];
  isRunning?:    boolean;
  currentPhase?: PhaseId | null;
  thoughts?:     AgentThought[];
  phases?:       Partial<Record<PhaseId, PhaseResult>>;
}

// Maps each phase to the primary agent name displayed in the timeline
const PHASE_AGENT: Record<string, string> = {
  INTAKE:        "DemoIntakeAgent",
  LOGS_FIRST:    "DemoEvidenceAgent",
  ROUTE:         "DemoRoutingAgent",
  BACKTRACK:     "DemoBacktrackingAgent",
  INCIDENT_CARD: "DemoIncidentAgent",
  RECOMMEND:     "DemoRecommendAgent",
  PERSIST:       "DemoRankerAgent",
};

// Short sentence describing what each phase does
const PHASE_DESCRIPTION: Record<string, string> = {
  INTAKE:        "Validating scenario inputs and seeding investigation state",
  LOGS_FIRST:    "Scanning job logs for anomaly signals",
  ROUTE:         "Matching log signal to hypothesis pattern library",
  BACKTRACK:     "Walking the causal ontology graph hop-by-hop",
  INCIDENT_CARD: "Synthesising structured incident summary",
  RECOMMEND:     "Generating ranked remediation actions from defect catalog",
  PERSIST:       "Computing confidence score and confirming root cause",
};

// Brief one-liner for what comes NEXT after each phase
const NEXT_DESCRIPTION: Record<string, string> = {
  INTAKE:        "scanning batch job logs for failure signals",
  LOGS_FIRST:    "routing the detected signal to a hypothesis pattern",
  ROUTE:         "backtracking the causal graph from the anchor incident",
  BACKTRACK:     "building the structured incident card",
  INCIDENT_CARD: "generating ranked remediation recommendations",
  RECOMMEND:     "computing composite confidence and confirming root cause",
  PERSIST:       "investigation complete",
};

// ── Thought-type display config ──────────────────────────────────────────────
const THOUGHT_STYLE: Record<string, { icon: string; color: string }> = {
  OBSERVING:     { icon: "◎", color: "#94a3b8" },
  HYPOTHESISING: { icon: "◈", color: "#a78bfa" },
  TESTING:       { icon: "◇", color: "#60a5fa" },
  REJECTING:     { icon: "✕", color: "#f87171" },
  ACCEPTING:     { icon: "✓", color: "#4ade80" },
  CONCLUDING:    { icon: "★", color: "#f59e0b" },
  WARNING:       { icon: "!", color: "#fb923c" },
};

const BADGE_FALLBACK = { label: "UNKNOWN", color: "#6b7280" };

const BADGE_MAP: Partial<Record<string, { label: string; color: string }>> = {
  // Canonical HopStatus values (from types/causelink.ts)
  UNKNOWN:          { label: "UNKNOWN",          color: "#6b7280" },
  CONFIRMED_FAILED: { label: "CONFIRMED FAILED", color: "#f87171" },
  PASSING:          { label: "PASSING",          color: "#22c55e" },
  ROOT_CAUSE:       { label: "ROOT CAUSE",       color: "#f59e0b" },
  // Legacy / backend variant spellings — kept for backwards compat
  pending:          { label: "PENDING",          color: "#6b7280" },
  confirmed:        { label: "CONFIRMED FAILED", color: "#f87171" },
  root_cause:       { label: "ROOT CAUSE",       color: "#f59e0b" },
  artifact_defect:  { label: "CONFIRMED DEFECT", color: "#f87171" },
};

function inferLabel(nodeId: string): string {
  const l = nodeId.toLowerCase();
  if (l.includes("inc")) return "Incident";
  if (l.includes("ctl")) return "Control";
  if (l.includes("rul")) return "Rule";
  if (l.includes("pip")) return "Pipeline";
  if (l.includes("stp")) return "JobStep";
  if (l.includes("mod")) return "Module";
  if (l.includes("art") || l.includes("cob") || l.includes("bcj") || l.includes("swp")) return "Artifact";
  return "Node";
}

// ── Injected CSS (keyframes for hop fade-in + agent pulse) ───────────────────
const TRACE_CSS = `
  @keyframes rca-hop-in {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0);    }
  }
  @keyframes rca-agent-dot {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.25; }
  }
  .rca-hop-row {
    animation: rca-hop-in 0.35s ease both;
  }
  .rca-agent-dot {
    animation: rca-agent-dot 1.1s ease-in-out infinite;
  }
`;

const S = {
  container: {
    background: "#0d1117",
    border: "1px solid #1e293b",
    borderRadius: 10,
    overflow: "hidden" as const,
  },
  header: {
    padding: "14px 18px 12px",
    borderBottom: "1px solid #1e293b",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: {
    color: "#e2e8f0",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase" as const,
  },
  body: {
    padding: "16px 18px",
  },
  nodeRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    padding: "5px 0",
  },
  bullet: (isRoot: boolean): React.CSSProperties => ({
    color: isRoot ? "#f59e0b" : "#f87171",
    fontSize: 15,
    lineHeight: 1.3,
    flexShrink: 0,
    marginTop: 1,
  }),
  nodeId: {
    color: "#e2e8f0",
    fontWeight: 700,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: 11,
    minWidth: 160,
  },
  nodeLabel: {
    color: "#64748b",
    fontSize: 11,
    minWidth: 100,
  },
  nodeDesc: {
    color: "#475569",
    fontSize: 11,
    flex: 1,
  },
  badge: (color: string): React.CSSProperties => ({
    background: color + "20",
    color,
    borderRadius: 4,
    padding: "1px 8px",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.05em",
    whiteSpace: "nowrap",
  }),
  edgeRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "1px 0 1px 25px",
    color: "#1e293b",
    fontSize: 11,
    fontFamily: "'JetBrains Mono', monospace",
  },
  empty: {
    color: "#334155",
    fontSize: 13,
    padding: "32px 0",
    textAlign: "center" as const,
  },
};

// ── Sub-components ────────────────────────────────────────────────────────────

/** Pulsing banner: current agent + latest thought content */
function LiveAgentBanner({
  currentPhase,
  thoughts,
}: {
  currentPhase: PhaseId;
  thoughts: AgentThought[];
}) {
  const agent = PHASE_AGENT[currentPhase] ?? "Analyzer";
  const latest = thoughts.length > 0 ? thoughts[thoughts.length - 1] : null;
  const typeStyle = latest ? (THOUGHT_STYLE[latest.thought_type] ?? THOUGHT_STYLE.OBSERVING) : THOUGHT_STYLE.OBSERVING;

  return (
    <div
      style={{
        background: "#0f172a",
        border: "1px solid #1e3a5f",
        borderRadius: 8,
        padding: "12px 14px",
        marginBottom: 14,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {/* Top row: agent name + phase + pulsing dot */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="rca-agent-dot" style={{ width: 7, height: 7, borderRadius: "50%", background: "#3b82f6", flexShrink: 0 }} />
        <span style={{ color: "#60a5fa", fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace" }}>
          {agent}
        </span>
        <span style={{ color: "#1e293b", fontSize: 12 }}>|</span>
        <span style={{ color: "#334155", fontSize: 11 }}>{PHASE_LABELS[currentPhase] ?? currentPhase}</span>
        <span style={{ color: "#1e293b", fontSize: 12 }}>|</span>
        <span style={{ color: "#6366f1", fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" as const }}>ANALYZING</span>
      </div>

      {/* Current phase description */}
      <div style={{ color: "#475569", fontSize: 11, lineHeight: 1.5 }}>
        {PHASE_DESCRIPTION[currentPhase] ?? "Processing…"}
      </div>

      {/* Latest thought */}
      {latest && (
        <div
          style={{
            background: "#0a0f1a",
            border: `1px solid ${typeStyle.color}30`,
            borderLeft: `3px solid ${typeStyle.color}`,
            borderRadius: 4,
            padding: "7px 10px",
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <span style={{ color: typeStyle.color, fontSize: 12, flexShrink: 0, marginTop: 1 }}>{typeStyle.icon}</span>
          <span style={{ color: "#94a3b8", fontSize: 11, lineHeight: 1.5 }}>
            {latest.content.length > 160 ? latest.content.slice(0, 160) + "…" : latest.content}
          </span>
        </div>
      )}
    </div>
  );
}

/** One row per completed phase — agent, summary, hop count */
function PhaseTimelineRow({
  phase,
  result,
  hopCount,
}: {
  phase: PhaseId;
  result: PhaseResult;
  hopCount: number;
}) {
  const agent = PHASE_AGENT[phase] ?? "Agent";
  const isOk  = result.status === "OK" || result.status === "CONFIRMED" || result.status === "PASS";
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        padding: "6px 10px",
        background: "#0a0f1a",
        border: "1px solid #1e293b",
        borderRadius: 6,
        marginBottom: 4,
        alignItems: "flex-start",
      }}
    >
      {/* Status dot */}
      <span style={{ color: isOk ? "#22c55e" : "#f87171", fontSize: 13, marginTop: 1, flexShrink: 0 }}>
        {isOk ? "✓" : "✕"}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Phase label + agent */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" as const }}>
          <span style={{ color: "#64748b", fontSize: 10, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "0.07em" }}>
            {PHASE_LABELS[phase] ?? phase}
          </span>
          <span style={{
            background: "#1e293b",
            color: "#475569",
            borderRadius: 3,
            padding: "1px 5px",
            fontSize: 9,
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            {agent}
          </span>
          {hopCount > 0 && (
            <span style={{ color: "#334155", fontSize: 9 }}>{hopCount} hop{hopCount !== 1 ? "s" : ""} revealed</span>
          )}
        </div>
        {/* Summary text */}
        <div style={{ color: "#334155", fontSize: 11, marginTop: 2, lineHeight: 1.4 }}>
          {result.summary}
        </div>
      </div>
    </div>
  );
}

/** Hop rows with fade-in animation */
function HopChain({ hops }: { hops: BacktrackHop[] }) {
  if (hops.length === 0) return null;
  const lastHop = hops[hops.length - 1];

  return (
    <div style={{ marginTop: 12 }}>
      {/* Section label */}
      <div style={{ color: "#1e293b", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" as const, marginBottom: 8 }}>
        Causal Chain
      </div>

      {hops.map((hop, i) => {
        const badge    = BADGE_MAP[hop.status] ?? BADGE_FALLBACK;
        const isRoot   = hop.status === "ROOT_CAUSE";
        const isSpec   = isRoot || hop.status === "CONFIRMED_FAILED";
        const delay    = `${i * 60}ms`;
        return (
          <React.Fragment key={`${hop.fromNodeId}-${hop.hopIndex}`}>
            <div
              className="rca-hop-row"
              style={{ ...S.nodeRow, animationDelay: delay }}
            >
              <span style={S.bullet(isSpec)}>{isSpec ? "◉" : "●"}</span>
              <span style={S.nodeId}>{hop.fromNodeId}</span>
              <span style={S.nodeLabel}>{hop.nodeLabel || inferLabel(hop.fromNodeId)}</span>
              <span style={S.nodeDesc}>{hop.nodeName}</span>
              <span style={S.badge(badge.color)}>{badge.label}</span>
            </div>
            <div style={S.edgeRow}>↓ {hop.relType}</div>
          </React.Fragment>
        );
      })}

      {/* Final destination node */}
      <div
        className="rca-hop-row"
        style={{ ...S.nodeRow, animationDelay: `${hops.length * 60}ms` }}
      >
        <span style={S.bullet(true)}>◉</span>
        <span style={S.nodeId}>{lastHop.toNodeId}</span>
        <span style={S.nodeLabel}>{inferLabel(lastHop.toNodeId)}</span>
        <span style={S.nodeDesc} />
        <span style={S.badge((BADGE_MAP["CONFIRMED_FAILED"] ?? BADGE_FALLBACK).color)}>
          CONFIRMED DEFECT
        </span>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function RcaTracePanel({
  hops,
  isRunning = false,
  currentPhase,
  thoughts = [],
  phases = {},
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when new hops arrive while running
  useEffect(() => {
    if (isRunning) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [hops.length, isRunning]);

  // Determine completed phases in order
  const completedPhases = (PHASE_ORDER as readonly PhaseId[]).filter((p) => !!phases[p]);

  // Compute next phase
  const phaseList = PHASE_ORDER as readonly PhaseId[];
  const curIdx    = currentPhase ? phaseList.indexOf(currentPhase) : -1;
  const nextPhase = isRunning && curIdx >= 0 && curIdx < phaseList.length - 1
    ? phaseList[curIdx + 1]
    : null;

  const isEmpty = hops.length === 0 && completedPhases.length === 0 && !isRunning;

  return (
    <>
      <style>{TRACE_CSS}</style>

      <div style={S.container}>
        {/* Header */}
        <div style={S.header}>
          <span style={S.title}>RCA Trace — Causal Backtracking</span>
          {hops.length > 0 && (
            <span style={{ color: "#334155", fontSize: 11 }}>
              {hops.length} hop{hops.length !== 1 ? "s" : ""} traced
            </span>
          )}
        </div>

        <div style={S.body}>
          {/* ── Idle / empty state ─────────────────────────────── */}
          {isEmpty && (
            <div style={S.empty}>
              Select a scenario and run RCA Analysis to start tracing
            </div>
          )}

          {/* ── Live agent banner (while running) ──────────────── */}
          {isRunning && currentPhase && (
            <LiveAgentBanner
              currentPhase={currentPhase}
              thoughts={thoughts}
            />
          )}

          {/* ── Phase timeline ─────────────────────────────────── */}
          {completedPhases.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ color: "#1e293b", fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" as const, marginBottom: 6 }}>
                Phase Log
              </div>
              {completedPhases.map((phase) => (
                <PhaseTimelineRow
                  key={phase}
                  phase={phase}
                  result={phases[phase]!}
                  hopCount={
                    phase === "BACKTRACK"
                      ? hops.length
                      : 0
                  }
                />
              ))}
            </div>
          )}

          {/* ── Hop chain ──────────────────────────────────────── */}
          <HopChain hops={hops} />

          {/* ── Next step indicator ────────────────────────────── */}
          {isRunning && nextPhase && (
            <div
              style={{
                marginTop: 14,
                padding: "8px 12px",
                background: "#0a0f1a",
                border: "1px dashed #1e3a5f",
                borderRadius: 6,
                display: "flex",
                gap: 8,
                alignItems: "center",
              }}
            >
              <span style={{ color: "#1e3a8a", fontSize: 12 }}>→</span>
              <span style={{ color: "#1e3a8a", fontSize: 11 }}>
                Next: <strong style={{ color: "#3b82f6" }}>{PHASE_LABELS[nextPhase] ?? nextPhase}</strong>
                {" — "}{NEXT_DESCRIPTION[currentPhase ?? ""] ?? "continuing investigation"}
              </span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>
    </>
  );
}
