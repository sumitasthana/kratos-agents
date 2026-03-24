/**
 * AgentChainMap.tsx  (enterprise dark theme)
 *
 * Industrial flow diagram â€” Bloomberg/Datadog style.
 * Spec: top-strip color bar, ALL CAPS labels, monospace metrics, no emoji.
 * Zero new npm dependencies.
 */
import React, { useState } from "react";

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Types
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface AgentChainStep {
  step:                    number;
  agent_id:                string;
  agent_label?:            string;
  agent_type:              "router" | "analyzer" | "triangulator" | "recommender";
  status:                  "completed" | "skipped" | "failed";
  decision:                string;
  health_score?:           number;
  confidence?:             number;
  findings_count?:         number;
  critical_findings?:      number;
  duration_ms:             number;
  output_summary:          string;
  correlations?:           string[];
  dominant_problem_type?:  string;
  overall_health_score?:   number;
  fixes_count?:            number;
  feedback_signal?:        string;
}

interface CrossAgentCorrelation {
  correlation_id?:      string;
  contributing_agents?: string[];
  pattern?:             string;
  severity?:            string;
  confidence?:          number;
  [key: string]: unknown;
}

interface Props {
  agentChain:   AgentChainStep[];
  correlations: CrossAgentCorrelation[];
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Dark design tokens (mirrors DemoRCA.tsx D object)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const D = {
  bgBase:    "#0f1117",
  bgCard:    "#161b25",
  border:    "#1f2937",
  textPri:   "#e5e7eb",
  textSec:   "#9ca3af",
  textMut:   "#4b5563",
  mono:      "'JetBrains Mono', 'Fira Mono', monospace",
  green:     "#22c55e",
  amber:     "#f59e0b",
  red:       "#ef4444",
  blue:      "#3b82f6",
  grey:      "#374151",
} as const;

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Helpers
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function statusColor(status: AgentChainStep["status"], agentType: AgentChainStep["agent_type"]): string {
  if (status === "failed")  return D.red;
  if (status === "skipped") return D.grey;
  if (agentType === "router")       return D.blue;
  if (agentType === "triangulator") return "#a78bfa"; // violet
  if (agentType === "recommender")  return "#2dd4bf"; // teal
  return D.green; // analyzer completed
}

function typeLabel(t: AgentChainStep["agent_type"]): string {
  if (t === "router")       return "ROUTER";
  if (t === "analyzer")     return "ANALYZER";
  if (t === "triangulator") return "TRIANGULATOR";
  if (t === "recommender")  return "RECOMMENDER";
  return (t as string).toUpperCase();
}

function healthColor(score: number): string {
  return score >= 80 ? D.green : score >= 60 ? D.amber : D.red;
}

function fmtMs(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Tooltip (dark, shown on hover)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function Tooltip({ step }: { step: AgentChainStep }) {
  return (
    <div style={{
      position: "absolute", zIndex: 200,
      top: "calc(100% + 6px)", left: "50%", transform: "translateX(-50%)",
      minWidth: 240, maxWidth: 320,
      background: "#0a0d14",
      border: `1px solid ${D.border}`,
      padding: "10px 12px",
      boxShadow: "0 4px 16px rgba(0,0,0,0.6)",
      fontSize: 10, lineHeight: 1.7, fontFamily: D.mono,
      pointerEvents: "none",
      color: D.textSec,
    }}>
      <div style={{ fontWeight: 600, color: "#c4b5fd", marginBottom: 5, letterSpacing: "0.05em" }}>
        {(step.agent_label ?? step.agent_id).toUpperCase()}
      </div>
      {step.output_summary && (
        <div style={{ marginBottom: 5, color: D.textSec, fontSize: 10 }}>{step.output_summary}</div>
      )}
      {step.findings_count != null && (
        <div>
          <span style={{ color: D.textMut }}>FINDINGS: </span>
          <span style={{ color: D.textSec }}>{step.findings_count}</span>
          {(step.critical_findings ?? 0) > 0 && (
            <span style={{ color: D.red }}> ({step.critical_findings} crit)</span>
          )}
        </div>
      )}
      {step.confidence != null && (
        <div>
          <span style={{ color: D.textMut }}>CONF: </span>
          <span style={{ color: D.textSec }}>
            {Math.round(step.confidence <= 1 ? step.confidence * 100 : step.confidence)}%
          </span>
        </div>
      )}
      {step.correlations?.length ? (
        <div style={{ marginTop: 4 }}>
          <div style={{ color: D.textMut, marginBottom: 2 }}>CORRELATIONS:</div>
          {step.correlations.map((c, i) => (
            <div key={i} style={{ color: "#c4b5fd" }}>Â· {c}</div>
          ))}
        </div>
      ) : null}
      {/* Arrow pointer */}
      <div style={{
        position: "absolute", top: -5, left: "50%", transform: "translateX(-50%)",
        width: 0, height: 0,
        borderLeft: "5px solid transparent",
        borderRight: "5px solid transparent",
        borderBottom: `5px solid ${D.border}`,
      }} />
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Node card  (140px wide, top color strip, ALL CAPS label)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const NODE_W = 140;

function NodeCard({
  step,
  isHovered,
  onMouseEnter,
  onMouseLeave,
}: {
  step:         AgentChainStep;
  isHovered:    boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) {
  const sc      = statusColor(step.status, step.agent_type);
  const isSkip  = step.status === "skipped";
  const hs      = step.health_score;

  return (
    <div
      style={{ position: "relative", cursor: "default" }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div style={{
        width: NODE_W,
        background: D.bgCard,
        border: `1px solid ${isHovered ? sc : D.border}`,
        opacity: isSkip ? 0.35 : 1,
        transition: "border-color 0.1s",
      }}>
        {/* Top status strip: 3px color bar */}
        <div style={{ height: 3, background: sc, width: "100%" }} />

        {/* Content */}
        <div style={{ padding: "7px 9px" }}>
          {/* Agent label â€” ALL CAPS */}
          <div style={{
            fontFamily: D.mono, fontSize: 11, fontWeight: 500,
            color: D.textSec, textTransform: "uppercase",
            letterSpacing: "0.04em", marginBottom: 3,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {step.agent_label ?? step.agent_id.replace(/_/g, " ")}
          </div>

          {/* Type badge */}
          <div style={{
            fontFamily: D.mono, fontSize: 8, color: D.textMut,
            letterSpacing: "0.1em", textTransform: "uppercase",
            marginBottom: 5,
          }}>
            {typeLabel(step.agent_type)}
          </div>

          {/* Decision â€” 2 lines max */}
          <div style={{
            fontSize: 10, color: D.textMut, lineHeight: 1.4,
            overflow: "hidden", textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical" as const,
            marginBottom: 6, minHeight: 28,
          }}>
            {step.decision}
          </div>

          {/* Bottom row: duration | health */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMut }}>
              {step.duration_ms > 0 ? fmtMs(step.duration_ms) : "â€”"}
            </span>
            {hs != null && !isSkip && (
              <span style={{ fontFamily: D.mono, fontSize: 10, color: healthColor(hs) }}>
                {Math.round(hs)}
              </span>
            )}
            {isSkip && (
              <span style={{ fontFamily: D.mono, fontSize: 8, color: D.grey, letterSpacing: "0.08em" }}>SKIP</span>
            )}
          </div>
        </div>
      </div>

      {isHovered && <Tooltip step={step} />}
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Arrow connectors
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const ARROW_W = 28;

function HArrow({ dashed }: { dashed?: boolean }) {
  return (
    <div style={{
      width: ARROW_W, flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 12, color: dashed ? D.grey : D.border,
      letterSpacing: -2,
    }}>
      {dashed ? "- ->" : "â†’"}
    </div>
  );
}

function VArrow() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", margin: "4px 0" }}>
      <div style={{ width: 1, height: 16, background: D.border }} />
      <span style={{ color: D.border, fontSize: 10, lineHeight: 1, marginTop: -2 }}>â–¼</span>
    </div>
  );
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// AgentChainMap â€” main component
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function AgentChainMap({ agentChain, correlations }: Props) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  if (!agentChain?.length) {
    return (
      <div style={{ fontFamily: D.mono, fontSize: 11, color: D.textMut }}>
        NO CHAIN DATA FOR THIS RUN.
      </div>
    );
  }

  const routerStep       = agentChain.find(s => s.agent_type === "router");
  const analyzerSteps    = agentChain.filter(s => s.agent_type === "analyzer");
  const triangulatorStep = agentChain.find(s => s.agent_type === "triangulator");
  const recommenderStep  = agentChain.find(s => s.agent_type === "recommender");

  const hk = (id: string, step: number) => `${id}-${step}`;
  const hover    = (id: string, step: number) => () => setHoveredKey(hk(id, step));
  const unhover  = () => setHoveredKey(null);
  const isHov    = (id: string, step: number) => hoveredKey === hk(id, step);

  return (
    <div style={{ fontSize: 12, fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* â”€â”€ Row 1: Router â†’ Analyzers â”€â”€ */}
      <div style={{ overflowX: "auto", paddingBottom: 4 }}>
        <div style={{ display: "flex", alignItems: "center", minWidth: "max-content", padding: "2px 0" }}>
          {routerStep && (
            <>
              <NodeCard
                step={routerStep}
                isHovered={isHov(routerStep.agent_id, routerStep.step)}
                onMouseEnter={hover(routerStep.agent_id, routerStep.step)}
                onMouseLeave={unhover}
              />
              {analyzerSteps.length > 0 && <HArrow />}
            </>
          )}

          {analyzerSteps.map((s, i) => (
            <React.Fragment key={`${s.agent_id}-${s.step}`}>
              <NodeCard
                step={s}
                isHovered={isHov(s.agent_id, s.step)}
                onMouseEnter={hover(s.agent_id, s.step)}
                onMouseLeave={unhover}
              />
              {i < analyzerSteps.length - 1 && (
                <HArrow dashed={analyzerSteps[i + 1].status === "skipped"} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* â”€â”€ Vertical convergence â”€â”€ */}
      {triangulatorStep && <VArrow />}

      {/* â”€â”€ Row 2: Triangulation â”€â”€ */}
      {triangulatorStep && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
          {/* Indent to align under analyzers (skip router + arrow width) */}
          <div style={{ marginLeft: routerStep ? (NODE_W + ARROW_W) : 0 }}>
            <NodeCard
              step={triangulatorStep}
              isHovered={isHov(triangulatorStep.agent_id, triangulatorStep.step)}
              onMouseEnter={hover(triangulatorStep.agent_id, triangulatorStep.step)}
              onMouseLeave={unhover}
            />
            {/* Cross-agent correlation tags */}
            {correlations?.length > 0 && (
              <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4, maxWidth: NODE_W * 2 }}>
                {correlations.slice(0, 3).map((c, i) => {
                  const agents = (c.contributing_agents ?? []).map(a => a.replace(/_/g, " ")).join(" / ");
                  return (
                    <span
                      key={c.correlation_id ?? i}
                      title={c.pattern ?? ""}
                      style={{
                        fontFamily: D.mono, fontSize: 8, color: "#a78bfa",
                        border: `1px solid #4c1d95`,
                        padding: "1px 5px",
                        letterSpacing: "0.04em", cursor: "default",
                        maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}
                    >
                      {agents}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* â”€â”€ Vertical arrow to recommender â”€â”€ */}
      {recommenderStep && (
        <div style={{ marginLeft: routerStep ? (NODE_W + ARROW_W) : 0 }}>
          <VArrow />
        </div>
      )}

      {/* â”€â”€ Row 3: Recommender â”€â”€ */}
      {recommenderStep && (
        <div style={{ marginLeft: routerStep ? (NODE_W + ARROW_W) : 0 }}>
          <NodeCard
            step={recommenderStep}
            isHovered={isHov(recommenderStep.agent_id, recommenderStep.step)}
            onMouseEnter={hover(recommenderStep.agent_id, recommenderStep.step)}
            onMouseLeave={unhover}
          />
        </div>
      )}

      {/* â”€â”€ Terminal: IssueProfile output â”€â”€ */}
      {recommenderStep && (
        <div style={{ marginLeft: routerStep ? (NODE_W + ARROW_W) : 0 }}>
          <VArrow />
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "4px 12px",
            border: `1px solid ${D.green}`,
            fontFamily: D.mono, fontSize: 10, color: D.green,
            letterSpacing: "0.06em",
          }}>
            ISSUE PROFILE
            {agentChain.find(s => s.agent_type === "triangulator")?.dominant_problem_type && (
              <span style={{ color: D.textMut }}>
                Â· {agentChain.find(s => s.agent_type === "triangulator")!.dominant_problem_type!.toUpperCase().replace(/_/g, " ")}
              </span>
            )}
            {recommenderStep.feedback_signal && (
              <span style={{
                marginLeft: 6, padding: "0 6px",
                border: `1px solid ${D.textMut}`,
                color: D.textMut, fontSize: 8, letterSpacing: "0.1em",
              }}>
                {recommenderStep.feedback_signal}
              </span>
            )}
          </div>
        </div>
      )}

      {/* â”€â”€ Legend â”€â”€ */}
      <div style={{
        marginTop: 14, display: "flex", gap: 16, flexWrap: "wrap",
        paddingTop: 10, borderTop: `1px solid ${D.border}`,
        fontFamily: D.mono, fontSize: 9, color: D.textMut, letterSpacing: "0.06em",
      }}>
        {[
          { color: D.green, label: "COMPLETED" },
          { color: D.red,   label: "FAILED"    },
          { color: D.grey,  label: "SKIPPED"   },
          { color: D.blue,  label: "ROUTER"    },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 8, height: 3, background: color }} />
            <span>{label}</span>
          </div>
        ))}
        <span style={{ color: D.textMut }}>HOVER NODE FOR DETAILS</span>
      </div>
    </div>
  );
}
