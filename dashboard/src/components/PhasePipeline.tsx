/**
 * PhasePipeline.tsx
 *
 * 7-pill horizontal strip showing the 7-phase RCA pipeline status.
 * Clicking a completed/failed phase fires onPhaseClick.
 */

import React from "react";
import { PHASE_ORDER, PHASE_LABELS } from "../constants/scenarios";
import type { PhaseId, PhaseResult } from "../types/causelink";
import type { RuntimeState } from "../types/demo";

interface PhasePipelineProps {
  phases: Partial<Record<PhaseId, PhaseResult>>;
  currentPhase: PhaseId | null;
  runtimeState: RuntimeState;
  onPhaseClick: (phase: PhaseId) => void;
}

type PillStatus = "pending" | "running" | "pass" | "fail";

function getPillStatus(
  phase: PhaseId,
  phases: Partial<Record<PhaseId, PhaseResult>>,
  currentPhase: PhaseId | null,
  runtimeState: RuntimeState
): PillStatus {
  const result = phases[phase];
  if (result) {
    return result.status === "PASS" ? "pass" : "fail";
  }
  if (currentPhase === phase && runtimeState === "RUNNING") {
    return "running";
  }
  return "pending";
}

const PILL_COLORS: Record<PillStatus, { bg: string; border: string; text: string }> = {
  pending: { bg: "#111827", border: "#1f2937", text: "#4b5563" },
  running: { bg: "#1e3a5f", border: "#3b82f6", text: "#93c5fd" },
  pass:    { bg: "#052e16", border: "#16a34a", text: "#4ade80" },
  fail:    { bg: "#2c0a0a", border: "#dc2626", text: "#f87171" },
};

export default function PhasePipeline({
  phases,
  currentPhase,
  runtimeState,
  onPhaseClick,
}: PhasePipelineProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 2,
        padding: "10px 16px",
        background: "#0a0c10",
        borderBottom: "1px solid #1f2937",
        overflowX: "auto",
        flexShrink: 0,
      }}
    >
      {PHASE_ORDER.map((phase, idx) => {
        const status = getPillStatus(phase, phases, currentPhase, runtimeState);
        const colors = PILL_COLORS[status];
        const isClickable = status === "pass" || status === "fail";
        return (
          <React.Fragment key={phase}>
            {idx > 0 && (
              <div
                style={{
                  width: 18,
                  height: 1,
                  background: status !== "pending" ? "#374151" : "#1f2937",
                  flexShrink: 0,
                }}
              />
            )}
            <button
              onClick={() => isClickable && onPhaseClick(phase)}
              disabled={!isClickable}
              title={PHASE_LABELS[phase]}
              aria-current={currentPhase === phase ? "step" : undefined}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                width: 88,
                height: 32,
                background: colors.bg,
                border: `1px solid ${colors.border}`,
                borderRadius: 5,
                color: colors.text,
                fontSize: 10,
                fontWeight: status === "running" ? 700 : 500,
                fontFamily: "monospace",
                cursor: isClickable ? "pointer" : "default",
                flexShrink: 0,
                padding: 0,
                letterSpacing: "0.03em",
                animation: status === "running" ? "phasePulse 1.4s ease-in-out infinite" : "none",
                transition: "border-color 0.2s",
              }}
            >
              <span style={{ fontSize: 8, color: "#6b7280", fontFamily: "sans-serif", marginBottom: 1 }}>
                {(idx + 1).toString().padStart(2, "0")}
              </span>
              {phase}
            </button>
          </React.Fragment>
        );
      })}

      <style>{`
        @keyframes phasePulse {
          0%,100% { box-shadow: 0 0 0 0   #3b82f640; }
          50%      { box-shadow: 0 0 0 5px #3b82f620; }
        }
      `}</style>
    </div>
  );
}
