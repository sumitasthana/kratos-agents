/**
 * BootScreen.tsx
 *
 * Full-screen overlay shown during the BOOT runtime state.
 * Displays boot stages with progress bar and per-stage timing.
 * Fades out and unmounts on READY. Shows retry button on FAILED.
 */

import React, { useEffect, useState } from "react";
import type { BootState } from "../types/demo";

interface BootScreenProps {
  bootState: BootState;
  onRetry: () => void;
}

const STAGE_ORDER: BootState["stage"][] = [
  "CONNECTING",
  "LOADING_SCENARIOS",
  "LOADING_CSV",
  "SEEDING_ONTOLOGY",
  "READY",
];

const STAGE_LABELS: Record<BootState["stage"], string> = {
  CONNECTING:       "Connecting to CauseLink engine",
  LOADING_SCENARIOS: "Loading 3 scenario packs",
  LOADING_CSV:      "Indexing 6,006 account records",
  SEEDING_ONTOLOGY: "Seeding CanonGraph (19 labels, 26 rel-types)",
  READY:            "Platform ready",
  FAILED:           "Boot failed",
};

function stageStatus(
  stage: BootState["stage"],
  current: BootState["stage"],
  completedCount: number,
  currentIndex: number,
  timings: BootState["stageTimings"]
): { icon: string; color: string; timing: string } {
  const stageIdx = STAGE_ORDER.indexOf(stage);
  if (current === "FAILED") {
    if (stageIdx < currentIndex) return { icon: "✓", color: "#4ade80", timing: `${timings[stage] ?? 0}ms` };
    if (stageIdx === currentIndex) return { icon: "✕", color: "#f87171", timing: "failed" };
    return { icon: "○", color: "#374151", timing: "—" };
  }
  if (stageIdx < completedCount) {
    return { icon: "✓", color: "#4ade80", timing: `${timings[stage] ?? 0}ms` };
  }
  if (stage === current && current !== "READY") {
    return { icon: "◌", color: "#3b82f6", timing: "running" };
  }
  return { icon: "○", color: "#374151", timing: "—" };
}

export default function BootScreen({ bootState, onRetry }: BootScreenProps) {
  const [visible, setVisible] = useState(true);
  const [fading, setFading] = useState(false);

  const { stage, completedStages, message, error, stageTimings, elapsed } = bootState;

  const totalStages = STAGE_ORDER.length;
  const progressPct = Math.min(100, (completedStages / totalStages) * 100);
  const currentIndex = STAGE_ORDER.indexOf(stage as BootState["stage"]);

  useEffect(() => {
    if (stage === "READY") {
      setFading(true);
      const t = setTimeout(() => setVisible(false), 420);
      return () => clearTimeout(t);
    }
  }, [stage]);

  if (!visible) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "#090b10",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        transition: "opacity 0.42s ease",
        opacity: fading ? 0 : 1,
        fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
      }}
      role="status"
      aria-live="polite"
    >
      {/* Logo */}
      <div style={{ marginBottom: 32, textAlign: "center" }}>
        <div style={{ fontSize: 32, fontWeight: 800, letterSpacing: "0.15em", color: "#e2e8f0", marginBottom: 4 }}>
          KRATOS
        </div>
        <div style={{ fontSize: 15, color: "#64748b", letterSpacing: "0.06em" }}>
          Intelligence Platform
        </div>
      </div>

      {/* Progress bar */}
      <div
        style={{
          width: 480,
          height: 4,
          background: "#1f2937",
          borderRadius: 2,
          overflow: "hidden",
          marginBottom: 8,
        }}
      >
        <div
          style={{
            height: "100%",
            background: stage === "FAILED" ? "#f87171" : "#3b82f6",
            borderRadius: 2,
            width: `${progressPct}%`,
            transition: "width 0.5s ease",
          }}
        />
      </div>

      {/* Stage message */}
      <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 28, letterSpacing: "0.04em" }}>
        {message}
      </div>

      {/* Stage list */}
      <div
        style={{
          width: 480,
          background: "#0f1117",
          border: "1px solid #1f2937",
          borderRadius: 8,
          padding: "16px 20px",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        {STAGE_ORDER.filter((s) => s !== "FAILED").map((s) => {
          const { icon, color, timing } = stageStatus(
            s, stage as BootState["stage"], completedStages, currentIndex, stageTimings
          );
          const isRunning = icon === "◌";
          return (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span
                style={{
                  color,
                  fontSize: 13,
                  width: 16,
                  display: "inline-block",
                  animation: isRunning ? "spin 1.2s linear infinite" : "none",
                }}
              >
                {icon}
              </span>
              <span style={{ color: icon === "✓" ? "#e2e8f0" : icon === "◌" ? "#93c5fd" : "#4b5563", fontSize: 12, flex: 1 }}>
                {STAGE_LABELS[s]}
              </span>
              <span style={{ color: icon === "✓" ? "#4b5563" : icon === "◌" ? "#3b82f6" : "#1f2937", fontSize: 11, fontFamily: "monospace" }}>
                {timing}
              </span>
            </div>
          );
        })}
      </div>

      {/* Error box */}
      {stage === "FAILED" && error && (
        <div
          style={{
            marginTop: 20,
            width: 480,
            background: "#1c0808",
            border: "1px solid #7f1d1d",
            borderRadius: 6,
            padding: "12px 16px",
            color: "#fca5a5",
            fontSize: 12,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Boot failed</div>
          <div style={{ fontFamily: "monospace", wordBreak: "break-all" }}>{error}</div>
          <button
            onClick={onRetry}
            style={{
              marginTop: 12,
              background: "#991b1b",
              border: "none",
              borderRadius: 4,
              color: "#fef2f2",
              padding: "6px 14px",
              fontSize: 12,
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          marginTop: 28,
          color: "#374151",
          fontSize: 10,
          letterSpacing: "0.08em",
          textAlign: "center",
        }}
      >
        legacy_deposit_system · trust_custody_system · wire_transfer_system · kratos-data · kratos-agents
        {elapsed > 0 && (
          <span style={{ marginLeft: 12 }}>{elapsed}ms</span>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
