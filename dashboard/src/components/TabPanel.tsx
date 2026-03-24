/**
 * TabPanel.tsx
 *
 * Horizontal tab strip + content switcher for the main right panel.
 * Tabs: trace | controls | incident | recommendations | confidence | data | observability
 * Children must be in the same order as TAB_IDS.
 */

import React from "react";
import type { RuntimeState } from "../types/demo";

export type TabId = "trace" | "controls" | "incident" | "recommendations" | "confidence" | "data" | "observability" | "reasoning";

export const TAB_IDS: TabId[] = [
  "trace",
  "controls",
  "incident",
  "recommendations",
  "confidence",
  "data",
  "observability",
  "reasoning",
];

const TAB_LABELS: Record<TabId, string> = {
  trace:           "RCA Trace",
  controls:        "Controls",
  incident:        "Incident",
  recommendations: "Recommendations",
  confidence:      "Confidence",
  data:            "Sample Data",
  observability:   "Observability",
  reasoning:       "Reasoning",
};

interface TabPanelProps {
  activeTab: TabId;
  onTabChange: (t: TabId) => void;
  runtimeState: RuntimeState;
  children: React.ReactNode[];
}

export default function TabPanel({
  activeTab,
  onTabChange,
  runtimeState: _runtimeState,
  children,
}: TabPanelProps) {
  const activeIndex = TAB_IDS.indexOf(activeTab);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Tab strip */}
      <div
        role="tablist"
        style={{
          display: "flex",
          borderBottom: "1px solid #1f2937",
          background: "#0a0c10",
          flexShrink: 0,
          overflowX: "auto",
        }}
      >
        {TAB_IDS.map((tab) => {
          const isActive = tab === activeTab;
          return (
            <button
              key={tab}
              role="tab"
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab}`}
              id={`tab-${tab}`}
              onClick={() => onTabChange(tab)}
              style={{
                background: "none",
                border: "none",
                borderBottom: isActive ? "2px solid #3b82f6" : "2px solid transparent",
                color: isActive ? "#e2e8f0" : "#6b7280",
                padding: "9px 16px",
                fontSize: 12,
                fontWeight: isActive ? 600 : 400,
                cursor: "pointer",
                whiteSpace: "nowrap",
                fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
                transition: "color 0.15s, border-color 0.15s",
                letterSpacing: "0.02em",
              }}
            >
              {TAB_LABELS[tab]}
            </button>
          );
        })}
      </div>

      {/* Tab content — render only active child */}
      <div
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
        style={{ flex: 1, minHeight: 0, overflow: "auto" }}
      >
        {children[activeIndex] ?? null}
      </div>
    </div>
  );
}
