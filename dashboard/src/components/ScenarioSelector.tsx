/**
 * ScenarioSelector.tsx
 *
 * Left-panel scenario picker and job-id input.
 * Calls onStart(scenarioId, jobId) when the user clicks "Run RCA Analysis".
 */

import React, { useState } from "react";
import { useScenarios } from "../hooks/useScenarios";
import { SCENARIO_META } from "../constants/scenarios";
import type { RuntimeState, ScenarioId } from "../types/demo";

interface ScenarioSelectorProps {
  onStart: (scenarioId: ScenarioId, jobId: string) => void;
  disabled?: boolean;
  runtimeState: RuntimeState;
}

const styles = {
  panel: {
    background: "#111318",
    border: "1px solid #1f2937",
    borderRadius: 8,
    padding: "20px 18px",
    minWidth: 240,
    maxWidth: 280,
    display: "flex",
    flexDirection: "column" as const,
    gap: 16,
  },
  title: {
    color: "#e2e8f0",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
    marginBottom: 4,
  },
  radioRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    cursor: "pointer",
    padding: "5px 4px",
    borderRadius: 4,
    transition: "background 0.15s",
  },
  radioLabel: {
    color: "#94a3b8",
    fontSize: 13,
  },
  radioLabelSelected: {
    color: "#e2e8f0",
    fontWeight: 600,
  },
  divider: {
    borderTop: "1px solid #1f2937",
    margin: "0 -4px",
  },
  inputLabel: {
    color: "#64748b",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: "0.07em",
    textTransform: "uppercase" as const,
    marginBottom: 4,
  },
  input: {
    background: "#0f1117",
    border: "1px solid #1f2937",
    borderRadius: 5,
    color: "#e2e8f0",
    fontSize: 12,
    padding: "7px 10px",
    width: "100%",
    fontFamily: "'JetBrains Mono', monospace",
    boxSizing: "border-box" as const,
    outline: "none",
  },
  button: {
    background: "#2563eb",
    border: "none",
    borderRadius: 6,
    color: "#fff",
    cursor: "pointer",
    fontWeight: 700,
    fontSize: 13,
    padding: "10px 0",
    width: "100%",
    letterSpacing: "0.04em",
    transition: "background 0.15s",
  },
  buttonDisabled: {
    background: "#1e3a5f",
    cursor: "not-allowed",
    color: "#64748b",
  },
  loadingText: {
    color: "#64748b",
    fontSize: 12,
    textAlign: "center" as const,
  },
  errorText: {
    color: "#f87171",
    fontSize: 12,
  },
};

export default function ScenarioSelector({ onStart, disabled = false, runtimeState }: ScenarioSelectorProps) {
  const { scenarios, loading, error } = useScenarios({ enabled: runtimeState !== "BOOT" });
  const [selected, setSelected] = useState<ScenarioId | "">("");
  const [jobId, setJobId]       = useState("");

  // Merge API scenarios with static metadata for display
  const displayScenarios = scenarios.length > 0
    ? scenarios
    : SCENARIO_META.map((m) => ({ scenario_id: m.id, job_id: m.defaultJobId, title: m.title }));

  const handleSelect = (id: ScenarioId) => {
    setSelected(id);
    const found = displayScenarios.find((s) => s.scenario_id === id);
    if (found) setJobId(found.job_id ?? "");
    else {
      const meta = SCENARIO_META.find((m) => m.id === id);
      if (meta) setJobId(meta.defaultJobId);
    }
  };

  const handleRun = () => {
    if (selected && jobId) onStart(selected as ScenarioId, jobId);
  };

  const isDisabled = !selected || !jobId || disabled || runtimeState === "BOOT" || runtimeState === "RUNNING";

  return (
    <div style={styles.panel}>
      <div>
        <div style={styles.title}>Select Scenario</div>

        {loading && <div style={styles.loadingText}>Loading scenarios…</div>}
        {error && <div style={styles.errorText}>Error: {error}</div>}

        {displayScenarios.map((s) => (
          <div
            key={s.scenario_id}
            style={{
              ...styles.radioRow,
              background: selected === s.scenario_id ? "#161b25" : "transparent",
            }}
            onClick={() => handleSelect(s.scenario_id as ScenarioId)}
          >
            <input
              type="radio"
              name="scenario"
              value={s.scenario_id}
              checked={selected === s.scenario_id}
              onChange={() => handleSelect(s.scenario_id as ScenarioId)}
              style={{ accentColor: "#2563eb", cursor: "pointer" }}
            />
            <span
              style={
                selected === s.scenario_id
                  ? { ...styles.radioLabel, ...styles.radioLabelSelected }
                  : styles.radioLabel
              }
            >
              {s.title ?? SCENARIO_META.find((m) => m.id === s.scenario_id)?.title ?? s.scenario_id}
            </span>
          </div>
        ))}
      </div>

      <div style={styles.divider} />

      <div>
        <div style={styles.inputLabel}>Job ID</div>
        <input
          style={styles.input}
          type="text"
          value={jobId}
          onChange={(e) => setJobId(e.target.value)}
          placeholder="e.g. DAILY-INSURANCE-JOB-20260316"
          spellCheck={false}
          disabled={runtimeState === "BOOT"}
        />
      </div>

      <button
        style={isDisabled ? { ...styles.button, ...styles.buttonDisabled } : styles.button}
        onClick={handleRun}
        disabled={isDisabled}
        type="button"
      >
        {runtimeState === "RUNNING" ? "Running…" : "Run RCA Analysis ↗"}
      </button>
    </div>
  );
}
