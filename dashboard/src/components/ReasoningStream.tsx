/**
 * ReasoningStream.tsx
 *
 * Renders the live chain-of-thought AGENT_THOUGHT SSE events that arrive
 * before each RCA phase. Thoughts are grouped by phase, with a pulsing
 * indicator while the investigation is still running.
 */

import { useEffect, useRef } from "react";
import type { AgentThought, ThoughtType } from "../types/causelink";

// ─── Thought-type colour + icon map ────────────────────────────────────────
const THOUGHT_STYLE: Record<
  ThoughtType,
  { label: string; colour: string; icon: string }
> = {
  OBSERVING:     { label: "Observing",     colour: "#3b82f6", icon: "◉" },
  HYPOTHESISING: { label: "Hypothesising", colour: "#6366f1", icon: "⬡" },
  TESTING:       { label: "Testing",       colour: "#f59e0b", icon: "▷" },
  REJECTING:     { label: "Rejecting",     colour: "#ef4444", icon: "✕" },
  ACCEPTING:     { label: "Accepting",     colour: "#22c55e", icon: "✓" },
  CONCLUDING:    { label: "Concluding",    colour: "#a855f7", icon: "★" },
  WARNING:       { label: "Warning",       colour: "#f97316", icon: "⚠" },
};

// ─── Types ──────────────────────────────────────────────────────────────────
interface Props {
  thoughts: AgentThought[];
  isRunning: boolean;
}

// Group thoughts by phase label for display
interface PhaseGroup {
  phase: string;
  items: AgentThought[];
}

function groupByPhase(thoughts: AgentThought[]): PhaseGroup[] {
  const groups: PhaseGroup[] = [];
  const seen = new Map<string, PhaseGroup>();
  for (const t of thoughts) {
    const key = t.phase || "INTAKE";
    if (!seen.has(key)) {
      const g: PhaseGroup = { phase: key, items: [] };
      groups.push(g);
      seen.set(key, g);
    }
    seen.get(key)!.items.push(t);
  }
  return groups;
}

// ─── Component ──────────────────────────────────────────────────────────────
export function ReasoningStream({ thoughts, isRunning }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to latest thought
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thoughts.length]);

  if (thoughts.length === 0 && !isRunning) {
    return (
      <div style={styles.empty}>
        No reasoning trace yet. Start an RCA investigation to see
        live chain-of-thought.
      </div>
    );
  }

  const groups = groupByPhase(thoughts);

  return (
    <div style={styles.container}>
      {groups.map((group) => (
        <div key={group.phase} style={styles.phaseGroup}>
          <div style={styles.phaseHeader}>
            <span style={styles.phaseBadge}>{group.phase}</span>
          </div>
          {group.items.map((t, idx) => {
            const style = THOUGHT_STYLE[t.thought_type] ?? THOUGHT_STYLE.OBSERVING;
            return (
              <div key={`${t.agent}-${t.step_index}-${idx}`} style={styles.thoughtRow}>
                <span
                  style={{ ...styles.thoughtIcon, color: style.colour }}
                  title={style.label}
                >
                  {style.icon}
                </span>
                <div style={styles.thoughtBody}>
                  <span style={{ ...styles.thoughtType, color: style.colour }}>
                    {style.label}
                  </span>
                  <span style={styles.agentLabel}>{t.agent}</span>
                  <p style={styles.thoughtContent}>{t.content}</p>
                  {t.evidence_refs.length > 0 && (
                    <div style={styles.refs}>
                      {t.evidence_refs.map((r) => (
                        <span key={r} style={styles.refBadge}>{r}</span>
                      ))}
                    </div>
                  )}
                  {t.node_refs.length > 0 && (
                    <div style={styles.refs}>
                      {t.node_refs.map((r) => (
                        <span key={r} style={{ ...styles.refBadge, background: "#1e293b", color: "#94a3b8" }}>
                          {r}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {t.confidence_delta !== 0 && (
                  <span
                    style={{
                      ...styles.deltaBadge,
                      color: t.confidence_delta > 0 ? "#22c55e" : "#ef4444",
                    }}
                  >
                    {t.confidence_delta > 0 ? "+" : ""}
                    {(t.confidence_delta * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            );
          })}
        </div>
      ))}

      {isRunning && (
        <div style={styles.pulsingRow}>
          <span style={styles.pulseDot} />
          <span style={styles.pulseLabel}>Agent reasoning in progress…</span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}

// ─── Inline styles (no external deps) ───────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  container: {
    fontFamily: "monospace",
    fontSize: "13px",
    lineHeight: "1.5",
    overflowY: "auto",
    maxHeight: "100%",
    padding: "12px 0",
  },
  empty: {
    color: "#64748b",
    fontStyle: "italic",
    padding: "24px 16px",
    textAlign: "center",
  },
  phaseGroup: {
    marginBottom: "12px",
  },
  phaseHeader: {
    padding: "4px 12px",
    marginBottom: "4px",
  },
  phaseBadge: {
    background: "#1e293b",
    color: "#94a3b8",
    borderRadius: "4px",
    padding: "2px 8px",
    fontSize: "11px",
    fontWeight: 700,
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
  },
  thoughtRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: "8px",
    padding: "6px 12px",
    borderLeft: "2px solid transparent",
  },
  thoughtIcon: {
    fontSize: "16px",
    lineHeight: "1",
    marginTop: "2px",
    flexShrink: 0,
  },
  thoughtBody: {
    flex: 1,
    minWidth: 0,
  },
  thoughtType: {
    fontWeight: 700,
    marginRight: "6px",
    fontSize: "11px",
    textTransform: "uppercase" as const,
  },
  agentLabel: {
    color: "#64748b",
    fontSize: "11px",
  },
  thoughtContent: {
    margin: "2px 0 0 0",
    color: "#cbd5e1",
    wordBreak: "break-word",
  },
  refs: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "4px",
    marginTop: "4px",
  },
  refBadge: {
    background: "#1d4ed8",
    color: "#bfdbfe",
    borderRadius: "3px",
    padding: "1px 5px",
    fontSize: "10px",
  },
  deltaBadge: {
    fontSize: "11px",
    fontWeight: 600,
    flexShrink: 0,
    marginTop: "2px",
  },
  pulsingRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 12px",
    color: "#94a3b8",
    fontSize: "12px",
  },
  pulseDot: {
    display: "inline-block",
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "#3b82f6",
    animation: "pulse 1.5s infinite",
  },
  pulseLabel: {
    fontStyle: "italic",
  },
};
