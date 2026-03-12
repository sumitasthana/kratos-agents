/**
 * DemoRCA.tsx
 *
 * Full-featured Demo RCA page.
 * Calls POST /api/run_rca_from_logs and renders the result in the same style
 * as the existing "RCA Findings" screen (HealthGaugeCard, LogStatusCard,
 * per-analyzer AnalyzerStrip, PrioritizedFixes, ExecutiveSummary).
 *
 * Accessible at hash #demo-rca.
 */
import React, { useState } from "react";
import AgentChainMap, { AgentChainStep } from "./AgentChainMap";

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens — enterprise dark theme (Bloomberg / Datadog / PagerDuty)
// ─────────────────────────────────────────────────────────────────────────────

const D = {
  bgBase:      "#0f1117",
  bgSurface:   "#111318",
  bgCard:      "#161b25",
  border:      "#1f2937",
  textPrimary: "#e5e7eb",
  textSecond:  "#9ca3af",
  textMuted:   "#4b5563",
  mono:        "'JetBrains Mono', 'Fira Mono', monospace" as const,
  green:       "#22c55e",
  amber:       "#f59e0b",
  red:         "#ef4444",
  blue:        "#3b82f6",
  grey:        "#374151",
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Types  (mirrors backend schemas.py shapes)
// ─────────────────────────────────────────────────────────────────────────────

interface IncludeFlags {
  spark:   boolean;
  airflow: boolean;
  data:    boolean;
  infra:   boolean;
  change:  boolean;
}

interface Finding {
  title?:          string;
  description?:    string;
  severity?:       string;
  recommendation?: string;
  finding_type?:   string;
}

interface AnalysisResult {
  problem_type?:      string;
  health_score?:      number;
  confidence?:        number;
  findings?:          Finding[];
  recommendations?:   string[];
  executive_summary?: string;
}

interface IssueProfile {
  dominant_problem_type?:   string;
  overall_health_score?:    number;
  overall_confidence?:      number;
  agents_invoked?:          string[];
  log_analysis?:            AnalysisResult | null;
  code_analysis?:           AnalysisResult | null;
  data_analysis?:           AnalysisResult | null;
  infra_analysis?:          AnalysisResult | null;
  change_analysis?:         AnalysisResult | null;
  total_findings_count?:    number;
  critical_findings_count?: number;
  [key: string]: unknown;
}

interface Fix {
  fix_id?:            string;
  title?:             string;
  description?:       string;
  priority?:          number;
  effort?:            string;
  applies_to_agents?: string[];
  code_snippet?:      string | null;
  severity?:          string;
}

interface RCAReport {
  job_id?:            string;
  generated_at?:      string;
  executive_summary?: string;
  issue_profile?:     IssueProfile;
  prioritized_fixes?: Fix[];
  recommendations?:   string[];
  agent_chain?:       AgentChainStep[];
  [key: string]: unknown;
}

// ─────────────────────────────────────────────────────────────────────────────
// Pure helpers
// ─────────────────────────────────────────────────────────────────────────────

const GENERIC_TITLES = new Set(["issue", "analysis", "observation", "note", "finding"]);
const TRUE_CRITICAL_WORDS = ["crash", "oom", "out of memory", "job failed", "aborted", "killed"];

function resolvedSeverity(f: Finding): string {
  const sev   = (f.severity || "info").toLowerCase();
  const title = (f.title    || "").toLowerCase().trim();
  if (sev === "critical" && GENERIC_TITLES.has(title)) {
    return TRUE_CRITICAL_WORDS.some(w => (f.description || "").toLowerCase().includes(w))
      ? "critical" : "high";
  }
  return sev;
}

function severityColor(s: string): string {
  switch (s?.toLowerCase()) {
    case "critical": case "high": return D.red;
    case "medium":                return D.amber;
    case "low":                   return D.green;
    default:                      return D.grey;
  }
}

function healthColor(score: number): string {
  return score >= 80 ? D.green : score >= 60 ? D.amber : D.red;
}

function healthStatus(score: number): string {
  return score >= 80 ? "HEALTHY" : score >= 60 ? "WARNING" : "CRITICAL";
}

function getLogStatusMeta(t: string) {
  switch (t?.toLowerCase()) {
    case "healthy":           return { color: D.green,      label: "HEALTHY",           category: "NO ISSUES"        };
    case "execution_failure": return { color: D.red,        label: "EXECUTION FAILURE", category: "JOB FAILED"       };
    case "memory_pressure":   return { color: D.red,        label: "MEMORY PRESSURE",   category: "RESOURCE ISSUE"   };
    case "shuffle_overhead":  return { color: D.amber,      label: "SHUFFLE OVERHEAD",  category: "NETWORK I/O"      };
    case "data_skew":         return { color: D.amber,      label: "DATA SKEW",         category: "PARTITION ISSUE"  };
    case "performance":       return { color: D.amber,      label: "PERFORMANCE",       category: "OPTIMIZATION"     };
    case "general":           return { color: D.textSecond, label: "GENERAL",           category: "GENERAL ANALYSIS" };
    default:                   return { color: D.textSecond, label: (t || "unknown").toUpperCase(), category: "UNKNOWN" };
  }
}

function confidenceLabel(v: number): string {
  return v >= 80 ? "HIGH CONFIDENCE" : v >= 60 ? "MODERATE CONFIDENCE" : "LOW CONFIDENCE";
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared UI atoms
// ─────────────────────────────────────────────────────────────────────────────

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: D.bgCard,
      border: `1px solid ${D.border}`,
      borderRadius: 2,
      ...style,
    }}>
      {children}
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 600, color: D.textMuted,
      textTransform: "uppercase", letterSpacing: "0.12em",
      marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const c = severityColor(severity);
  return (
    <span style={{
      padding: "1px 6px", fontSize: 9, fontWeight: 700,
      border: `1px solid ${c}`, color: c,
      textTransform: "uppercase", letterSpacing: "0.08em",
      fontFamily: D.mono, flexShrink: 0,
    }}>
      {severity || "INFO"}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Overall Assessment — Health Score block  (big number, no SVG gauge)
// ─────────────────────────────────────────────────────────────────────────────

function HealthScoreBlock({ score }: { score: number }) {
  const c      = healthColor(score);
  const status = healthStatus(score);
  return (
    <div style={{
      background: D.bgCard, border: `1px solid ${D.border}`,
      padding: "16px 20px", minWidth: 120,
    }}>
      <SectionHeader>Health Score</SectionHeader>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span style={{ fontFamily: D.mono, fontSize: 48, fontWeight: 400, lineHeight: 1, color: c }}>
          {Math.round(score)}
        </span>
        <span style={{ fontFamily: D.mono, fontSize: 20, color: D.textMuted, lineHeight: 1 }}>/100</span>
      </div>
      <div style={{ marginTop: 4, fontFamily: D.mono, fontSize: 10, color: c, letterSpacing: "0.08em" }}>
        {status}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Log Status block  (dominant problem type — text only, no icon div)
// ─────────────────────────────────────────────────────────────────────────────

function LogStatusBlock({ problemType }: { problemType: string }) {
  const m = getLogStatusMeta(problemType);
  return (
    <div style={{
      background: D.bgCard, border: `1px solid ${D.border}`,
      padding: "16px 20px", flex: 1,
    }}>
      <SectionHeader>Log Status</SectionHeader>
      <div style={{ fontSize: 20, fontWeight: 600, color: m.color, letterSpacing: "0.02em", marginBottom: 8 }}>
        {m.label}
      </div>
      <span style={{
        display: "inline-block",
        padding: "2px 8px", fontSize: 10, fontWeight: 600,
        border: `1px solid ${m.color}`, color: m.color,
        textTransform: "uppercase", letterSpacing: "0.08em",
      }}>
        {m.category}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Confidence block  (number + 3 px flat bar)
// ─────────────────────────────────────────────────────────────────────────────

function ConfidenceBlock({ value }: { value: number }) {
  const pct = value <= 1.0 ? Math.round(value * 100) : Math.round(value);
  const c   = healthColor(pct);
  return (
    <div style={{
      background: D.bgCard, border: `1px solid ${D.border}`,
      padding: "16px 20px", flex: 1,
    }}>
      <SectionHeader>Confidence</SectionHeader>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 10 }}>
        <span style={{ fontFamily: D.mono, fontSize: 36, fontWeight: 400, lineHeight: 1, color: D.textPrimary }}>
          {pct}%
        </span>
      </div>
      <div style={{ background: D.border, height: 3, width: "100%", marginBottom: 6 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: c, transition: "width 0.7s ease" }} />
      </div>
      <div style={{ fontSize: 9, color: D.textMuted, letterSpacing: "0.1em", fontFamily: D.mono }}>
        {confidenceLabel(pct)}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Markdown renderer
// ─────────────────────────────────────────────────────────────────────────────

function renderInline(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/).map((part, j) => {
    if (/^\*\*(.+)\*\*$/.test(part)) return <strong key={j}>{part.slice(2, -2)}</strong>;
    if (/^\*(.+)\*$/.test(part))     return <em      key={j}>{part.slice(1, -1)}</em>;
    return part;
  });
}

function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null;
  return (
    <div>
      {text.split(/\n/).map((line, i) => {
        const isBullet = /^\s*[-*]\s+/.test(line);
        const cleaned  = line.replace(/^\s*[-*]\s+/, "");
        return isBullet ? (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4 }}>
            <span style={{ color: D.textMuted, flexShrink: 0, marginTop: 1 }}>·</span>
            <span>{renderInline(cleaned)}</span>
          </div>
        ) : (
          <div key={i} style={{ marginBottom: line.trim() ? 4 : 8 }}>{renderInline(cleaned)}</div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Summary block  (left blue border, no icon)
// ─────────────────────────────────────────────────────────────────────────────

function ExecutiveSummaryCard({ text }: { text: string }) {
  return (
    <div style={{
      borderLeft: `3px solid ${D.blue}`,
      background: D.bgCard,
      border: `1px solid ${D.border}`,
      borderLeftWidth: 3,
      borderLeftColor: D.blue,
      padding: "14px 16px",
    }}>
      <p style={{ margin: 0, lineHeight: 1.7, fontSize: 13, color: D.textPrimary, whiteSpace: "pre-wrap" }}>
        {text}
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Metadata strip  (monospace single-row: invoked agents | findings | generated)
// ─────────────────────────────────────────────────────────────────────────────

function MetadataStrip({
  agents, totalFindings, criticalFindings, generatedAt,
}: {
  agents:           string[];
  totalFindings?:   number;
  criticalFindings?: number;
  generatedAt?:     string;
}) {
  const parts: React.ReactNode[] = [];
  const sep = <span key={`sep-${parts.length}`} style={{ color: D.border, margin: "0 10px" }}>|</span>;

  if (agents?.length) {
    parts.push(
      <span key="agents">
        <span style={{ color: D.textMuted, marginRight: 6 }}>INVOKED:</span>
        {agents.map((a, i) => (
          <React.Fragment key={a}>
            <span style={{ color: D.textSecond }}>{a}</span>
            {i < agents.length - 1 && <span style={{ color: D.border, margin: "0 4px" }}>·</span>}
          </React.Fragment>
        ))}
      </span>
    );
  }
  if (totalFindings != null) {
    if (parts.length) parts.push(sep);
    parts.push(
      <span key="findings">
        <span style={{ color: D.textMuted, marginRight: 4 }}>FINDINGS:</span>
        <span style={{ color: D.textSecond }}>{totalFindings}</span>
        {(criticalFindings ?? 0) > 0 && (
          <>
            <span style={{ color: D.border, margin: "0 6px" }}>·</span>
            <span style={{ color: D.textMuted, marginRight: 4 }}>CRITICAL:</span>
            <span style={{ color: D.red, fontWeight: 600 }}>{criticalFindings}</span>
          </>
        )}
      </span>
    );
  }
  if (generatedAt) {
    if (parts.length) parts.push(sep);
    parts.push(
      <span key="gen">
        <span style={{ color: D.textMuted, marginRight: 4 }}>GENERATED:</span>
        <span style={{ color: D.textSecond }}>
          {new Date(generatedAt).toLocaleTimeString()}
        </span>
      </span>
    );
  }

  if (!parts.length) return null;
  return (
    <div style={{
      background: D.bgCard, border: `1px solid ${D.border}`,
      padding: "7px 14px",
      fontFamily: D.mono, fontSize: 11, color: D.textMuted,
      marginBottom: 12, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0,
    }}>
      {parts}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Analyzer Table  (data-dense rows, click to expand)
// ─────────────────────────────────────────────────────────────────────────────

const ANALYZER_LABEL: Record<string, string> = {
  log_analysis:    "SPARK / LOG",
  code_analysis:   "CODE ANALYZER",
  data_analysis:   "DATA PROFILER",
  change_analysis: "CHANGE ANALYZER",
  infra_analysis:  "INFRA ANALYZER",
};

function AnalyzerTable({ issueProfile }: { issueProfile: IssueProfile }) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const analyzers = (
    [
      { key: "log_analysis",    result: issueProfile.log_analysis    },
      { key: "code_analysis",   result: issueProfile.code_analysis   },
      { key: "data_analysis",   result: issueProfile.data_analysis   },
      { key: "change_analysis", result: issueProfile.change_analysis },
      { key: "infra_analysis",  result: issueProfile.infra_analysis  },
    ] as { key: string; result: AnalysisResult | null | undefined }[]
  ).filter((a): a is { key: string; result: AnalysisResult } => a.result != null);

  if (analyzers.length === 0) return null;

  const colStyle: React.CSSProperties = {
    padding: "7px 12px", fontSize: 11, borderBottom: `1px solid ${D.border}`,
    verticalAlign: "middle",
  };

  return (
    <div style={{ border: `1px solid ${D.border}`, marginBottom: 16 }}>
      {/* Table header */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "160px 1fr 80px 72px 72px 1fr",
        background: D.bgBase,
        borderBottom: `1px solid ${D.border}`,
      }}>
        {["ANALYZER", "PROBLEM TYPE", "HEALTH", "FINDINGS", "CRITICAL", "SUMMARY"].map(h => (
          <div key={h} style={{
            padding: "5px 12px", fontSize: 9, fontWeight: 600, color: D.textMuted,
            letterSpacing: "0.1em", textTransform: "uppercase" as const,
          }}>
            {h}
          </div>
        ))}
      </div>

      {/* Rows */}
      {analyzers.map(({ key, result }) => {
        const pt        = result.problem_type ?? "general";
        const ptColor   = getLogStatusMeta(pt).color;
        const hs        = result.health_score ?? 100;
        const hc        = healthColor(hs);
        const findings  = result.findings ?? [];
        const critCount = findings.filter(f => ["critical", "high"].includes(resolvedSeverity(f))).length;
        const summaryText = result.executive_summary ?? "";
        const isOpen    = expandedKey === key;
        const label     = ANALYZER_LABEL[key] ?? key.toUpperCase().replace(/_/g, " ");

        return (
          <React.Fragment key={key}>
            <button
              onClick={() => setExpandedKey(isOpen ? null : key)}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 1fr 80px 72px 72px 1fr",
                width: "100%", background: isOpen ? D.bgBase : "transparent",
                border: "none", cursor: "pointer", textAlign: "left",
                borderBottom: isOpen ? "none" : `1px solid ${D.border}`,
              }}
            >
              {/* Analyzer name */}
              <div style={{ ...colStyle, fontFamily: D.mono, fontSize: 11, color: D.textPrimary, fontWeight: 500 }}>
                <span style={{ marginRight: 6, color: D.textMuted, fontSize: 9 }}>{isOpen ? "▾" : "▸"}</span>
                {label}
              </div>
              {/* Problem type */}
              <div style={{ ...colStyle, fontFamily: D.mono, fontSize: 10, color: ptColor, letterSpacing: "0.05em" }}>
                {pt.toUpperCase().replace(/_/g, " ")}
              </div>
              {/* Health */}
              <div style={{ ...colStyle, fontFamily: D.mono, fontSize: 11, color: hc }}>
                {Math.round(hs)}/100
              </div>
              {/* Findings */}
              <div style={{ ...colStyle, fontFamily: D.mono, fontSize: 11, color: D.textSecond }}>
                {findings.length}
              </div>
              {/* Critical */}
              <div style={{ ...colStyle, fontFamily: D.mono, fontSize: 11, color: critCount > 0 ? D.red : D.grey }}>
                {critCount > 0 ? critCount : "—"}
              </div>
              {/* Summary truncated */}
              <div style={{ ...colStyle, fontSize: 11, color: D.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>
                {summaryText.slice(0, 60)}{summaryText.length > 60 ? "…" : ""}
              </div>
            </button>

            {/* Expanded detail row */}
            {isOpen && (
              <div style={{
                background: D.bgBase, borderBottom: `1px solid ${D.border}`,
                padding: "12px 16px",
              }}>
                {summaryText && (
                  <p style={{ margin: "0 0 10px", fontSize: 12, color: D.textSecond, lineHeight: 1.65, fontStyle: "italic" }}>
                    {summaryText}
                  </p>
                )}
                {findings.length === 0 ? (
                  <div style={{ fontSize: 11, color: D.textMuted, fontStyle: "italic" }}>No findings recorded.</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {findings.slice(0, 6).map((f, fi) => {
                      const sev = resolvedSeverity(f);
                      const sc  = severityColor(sev);
                      return (
                        <div key={fi} style={{
                          borderLeft: `2px solid ${sc}`,
                          background: D.bgCard, border: `1px solid ${D.border}`,
                          borderLeftWidth: 2, borderLeftColor: sc,
                          padding: "6px 10px",
                        }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: f.description ? 2 : 0 }}>
                            <span style={{ fontSize: 12, fontWeight: 500, color: D.textPrimary, flex: 1, fontFamily: D.mono }}>
                              {f.title || f.finding_type || `Finding ${fi + 1}`}
                            </span>
                            <SeverityBadge severity={sev} />
                          </div>
                          {f.description && (
                            <div style={{ fontSize: 11, color: D.textSecond, lineHeight: 1.5 }}>
                              {f.description.length > 160 ? f.description.slice(0, 160) + "…" : f.description}
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {findings.length > 6 && (
                      <div style={{ fontSize: 11, color: D.textMuted, padding: "4px 0", fontFamily: D.mono }}>
                        +{findings.length - 6} more findings
                      </div>
                    )}
                  </div>
                )}
                {(result.recommendations ?? []).length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 9, fontWeight: 600, color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
                      RECOMMENDATIONS
                    </div>
                    <ul style={{ margin: 0, padding: "0 0 0 16px", display: "flex", flexDirection: "column", gap: 4 }}>
                      {(result.recommendations ?? []).map((r, ri) => (
                        <li key={ri} style={{ fontSize: 12, color: D.green, lineHeight: 1.55 }}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Prioritized Fixes  (left-border style, no rounded circles)
// ─────────────────────────────────────────────────────────────────────────────

const EFFORT_COLOR: Record<string, string> = { low: D.green, medium: D.amber, high: D.red };

function PrioritizedFixes({ fixes }: { fixes: Fix[] }) {
  const [open, setOpen] = useState(true);
  if (!fixes?.length) return null;

  const sorted = [...fixes].sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));

  return (
    <div style={{ marginBottom: 20 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: "100%", background: "transparent", border: "none", padding: 0, marginBottom: 8, cursor: "pointer", textAlign: "left" }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted }}>{open ? "▾" : "▸"}</span>
          <span style={{ fontSize: 10, fontWeight: 600, color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.1em" }}>
            RECOMMENDED ACTIONS
          </span>
          <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted }}>{fixes.length} prioritized fixes</span>
        </div>
      </button>

      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {sorted.map((fix, i) => {
            const effortColor = EFFORT_COLOR[fix.effort?.toLowerCase() ?? ""] ?? D.grey;
            return (
              <div
                key={fix.fix_id ?? i}
                style={{
                  background: D.bgCard,
                  border: `1px solid ${D.border}`,
                  borderLeftWidth: 2,
                  borderLeftColor: effortColor,
                  overflow: "hidden",
                }}
              >
                {/* Fix header */}
                <div style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  gap: 12, padding: "10px 14px",
                  borderBottom: fix.description ? `1px solid ${D.border}` : "none",
                }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span style={{ fontFamily: D.mono, fontSize: 14, fontWeight: 400, color: D.blue, flexShrink: 0 }}>
                      {fix.priority ?? i + 1}
                    </span>
                    <span style={{ fontSize: 13, fontWeight: 500, color: D.textPrimary }}>
                      {fix.title ?? `Fix ${i + 1}`}
                    </span>
                  </div>
                  {fix.effort && (
                    <span style={{
                      fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                      border: `1px solid ${effortColor}`, color: effortColor,
                      padding: "1px 6px", letterSpacing: "0.08em", flexShrink: 0,
                      fontFamily: D.mono,
                    }}>
                      {fix.effort.toUpperCase()} EFFORT
                    </span>
                  )}
                </div>
                {fix.description && (
                  <div style={{ padding: "10px 14px 10px 38px", fontSize: 12, color: D.textSecond, lineHeight: 1.65 }}>
                    {renderMarkdown(fix.description)}
                  </div>
                )}
                {fix.code_snippet && (
                  <div style={{
                    padding: "10px 14px",
                    background: D.bgBase,
                    color: "#cdd6f4",
                    fontFamily: D.mono, fontSize: 11, lineHeight: 1.6,
                    borderTop: `1px solid ${D.border}`,
                    whiteSpace: "pre-wrap", overflowX: "auto",
                  }}>
                    {fix.code_snippet}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent Chain Section  (collapsible wrapper — dark industrial)
// ─────────────────────────────────────────────────────────────────────────────

function AgentChainSection({
  agentChain,
  correlations,
}: {
  agentChain:   AgentChainStep[];
  correlations: any[];
}) {
  const [open, setOpen] = useState(true);

  const totalMs = agentChain.reduce((s, n) => s + (n.duration_ms ?? 0), 0);
  const fmtTime = totalMs < 1000 ? `${totalMs}ms` : `${(totalMs / 1000).toFixed(2)}s`;

  return (
    <div style={{ background: D.bgCard, border: `1px solid ${D.border}`, marginBottom: 12 }}>
      {/* Header */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", background: "transparent", border: "none",
          padding: "9px 14px", cursor: "pointer", textAlign: "left",
          display: "flex", alignItems: "center", gap: 10,
          borderBottom: open ? `1px solid ${D.border}` : "none",
        }}
      >
        <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted }}>{open ? "▾" : "▸"}</span>
        <span style={{ fontSize: 10, fontWeight: 600, color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.1em", flex: 1 }}>
          AGENT EXECUTION CHAIN
        </span>
        <span style={{ fontSize: 9, color: D.textMuted, fontFamily: D.mono }}>
          {agentChain.length} steps
        </span>
        <span style={{ fontSize: 9, fontFamily: D.mono, color: D.textMuted, marginLeft: 10 }}>
          {fmtTime} total
        </span>
      </button>

      {open && (
        <div style={{ padding: "12px 16px" }}>
          <div style={{ fontSize: 9, color: D.textMuted, letterSpacing: "0.08em", marginBottom: 12, fontFamily: D.mono }}>
            EVERY STEP OF THIS RCA RUN — NO BLACK BOX.
          </div>
          <AgentChainMap agentChain={agentChain} correlations={correlations} />
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline caption  (breadcrumb-style, static)
// ─────────────────────────────────────────────────────────────────────────────

function PipelineCaption({ jobId }: { jobId?: string }) {
  const steps = ["routing", "analyzers", "triangulation", "recommender"];
  return (
    <div style={{ fontFamily: D.mono, fontSize: 11, color: D.textMuted, lineHeight: 1.6 }}>
      {steps.map((step, i) => (
        <React.Fragment key={step}>
          <span>{step}</span>
          {i < steps.length - 1 && <span style={{ margin: "0 5px", color: D.border }}>→</span>}
        </React.Fragment>
      ))}
      {jobId && (
        <span style={{ marginLeft: 14, color: D.textMuted }}>JOB: <span style={{ color: D.textSecond }}>{jobId}</span></span>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Fallback plain recommendations
// ─────────────────────────────────────────────────────────────────────────────

function RecommendationsList({ items }: { items: string[] }) {
  if (!items?.length) return null;
  return (
    <div style={{ background: D.bgCard, border: `1px solid ${D.border}`, padding: "14px 18px", marginBottom: 16 }}>
      <div style={{ fontSize: 9, fontWeight: 600, color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>
        RECOMMENDED ACTIONS
      </div>
      <ul style={{ margin: 0, padding: "0 0 0 18px", display: "flex", flexDirection: "column", gap: 6 }}>
        {items.map((r, i) => (
          <li key={i} style={{ fontSize: 13, color: D.green, lineHeight: 1.65 }}>{r}</li>
        ))}
      </ul>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Log file browser types + helpers
// ─────────────────────────────────────────────────────────────────────────────

interface LogFileEntry {
  path:        string;
  filename:    string;
  category:    string;
  size_bytes:  number;
  modified_at: string;
}

type CategoryKey = "spark" | "airflow" | "data" | "infra" | "change" | "unknown";

const CATEGORY_OPTIONS: CategoryKey[] = ["spark", "airflow", "data", "infra", "change", "unknown"];

function formatBytes(bytes: number): string {
  if (bytes < 1024)        return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export default function DemoRCA() {
  // ── Log file browser state ───────────────────────────────────────────────
  const [logFiles,         setLogFiles]         = useState<LogFileEntry[]>([]);
  const [loadingLogs,      setLoadingLogs]      = useState(false);
  const [logsError,        setLogsError]        = useState<string | null>(null);
  const [selectedPaths,    setSelectedPaths]    = useState<Set<string>>(new Set());
  const [categoryOverride, setCategoryOverride] = useState<Record<string, string>>({});
  const [collapsedGroups,  setCollapsedGroups]  = useState<Set<string>>(new Set());

  // ── Legacy mode state (fallback when nothing selected) ───────────────────
  const [include, setInclude] = useState<IncludeFlags>({
    spark: true, airflow: true, data: true, infra: true, change: false,
  });
  const [userQuery, setUserQuery] = useState("Investigate the demo OHLCV pipeline incident.");
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState<string | null>(null);
  const [report,    setReport]    = useState<RCAReport | null>(null);

  // ── Load log file list ───────────────────────────────────────────────────
  const loadLogs = async () => {
    setLoadingLogs(true);
    setLogsError(null);
    try {
      const res  = await fetch("/api/logs/browse");
      if (!res.ok) {
        // Kratos API (port 8000) not running — show empty list, not a hard error
        setLogFiles([]);
        return;
      }
      const text = await res.text();
      setLogFiles(JSON.parse(text) as LogFileEntry[]);
    } catch (e: any) {
      // Network error (ECONNREFUSED) — silently show empty list
      setLogFiles([]);
    } finally {
      setLoadingLogs(false);
    }
  };

  // Load log list on mount
  React.useEffect(() => { loadLogs(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── File selection helpers ───────────────────────────────────────────────
  const toggleFile = (path: string) =>
    setSelectedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });

  const getCategory = (f: LogFileEntry): string =>
    categoryOverride[f.path] ?? f.category;

  const toggleGroup = (group: string) =>
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group); else next.add(group);
      return next;
    });

  // ── Group files by sub-directory ────────────────────────────────────────
  const grouped: Record<string, LogFileEntry[]> = {};
  for (const f of logFiles) {
    const parts = f.path.split("/");
    const group = parts.length > 2 ? parts.slice(0, -1).join("/") : parts[0];
    if (!grouped[group]) grouped[group] = [];
    grouped[group].push(f);
  }
  const groupKeys = Object.keys(grouped).sort();

  // ── Run RCA ──────────────────────────────────────────────────────────────
  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setReport(null);

    try {
      let res: Response;
      if (selectedPaths.size > 0) {
        // File-browser mode — call the new endpoint with selected files
        const files = logFiles
          .filter(f => selectedPaths.has(f.path))
          .map(f => ({ path: f.path, category: getCategory(f) }));
        res = await fetch("/api/run_rca_from_file", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ files, user_query: userQuery || undefined }),
        });
      } else {
        // Legacy mode — hardcoded fixture scenario
        res = await fetch("/api/run_rca_from_logs", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ scenario: "demo_incident", include, user_query: userQuery || null }),
        });
      }

      const text = await res.text();
      if (!res.ok) throw new Error(`RCA request failed (${res.status}): ${text.slice(0, 300)}`);
      let data: RCAReport;
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(
          `Backend returned non-JSON (is FastAPI running on port 8000?).\n` +
          `First 200 chars: ${text.slice(0, 200)}`
        );
      }
      setReport(data);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  // ── Derived display values ───────────────────────────────────────────────
  const ip            = report?.issue_profile;
  const healthScore   = ip?.overall_health_score ?? 0;
  const problemType   = ip?.dominant_problem_type ?? "general";
  const confidence    = ip?.overall_confidence;
  const agentsInvoked = ip?.agents_invoked ?? [];
  const execSummary   = report?.executive_summary ?? "";
  const fixes         = report?.prioritized_fixes ?? [];

  const plainRecs: string[] = fixes.length > 0 ? [] : [
    ...(ip?.log_analysis?.recommendations    ?? []),
    ...(ip?.data_analysis?.recommendations   ?? []),
    ...(ip?.infra_analysis?.recommendations  ?? []),
    ...(ip?.change_analysis?.recommendations ?? []),
  ];

  return (
    <div style={{
      height: "100%", overflowY: "auto",
      padding: "20px 28px",
      fontFamily: "'Inter', system-ui, sans-serif",
      background: D.bgSurface,
      color: D.textPrimary,
      fontSize: 13,
    }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>

        {/* ── Breadcrumb top bar ── */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: 16, paddingBottom: 12, borderBottom: `1px solid ${D.border}`,
        }}>
          <div style={{ fontFamily: D.mono, fontSize: 12, color: D.textMuted }}>
            kratos<span style={{ color: D.border }}> / </span>
            rca<span style={{ color: D.border }}> / </span>
            <span style={{ color: D.textSecond }}>demo-rca</span>
          </div>
          {report?.job_id && (
            <div style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted }}>
              JOB: <span style={{ color: D.textSecond }}>{report.job_id}</span>
              {report.generated_at && (
                <span style={{ marginLeft: 12, color: D.textMuted }}>
                  {new Date(report.generated_at as string).toLocaleTimeString()}
                </span>
              )}
            </div>
          )}
        </div>

        {/* ── Page header ── */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontFamily: D.mono, fontSize: 11, color: D.textMuted, letterSpacing: "0.15em", marginBottom: 2 }}>
            KRATOS RCA
          </div>
          <PipelineCaption jobId={report?.job_id} />
        </div>

        {/* ── Log file browser ── */}
        <div style={{ background: D.bgCard, border: `1px solid ${D.border}`, marginBottom: 12 }}>
          {/* Browser header */}
          <div style={{
            padding: "8px 14px",
            borderBottom: `1px solid ${D.border}`,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 9, fontWeight: 600, color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                AVAILABLE LOGS
              </span>
              <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textSecond, background: D.bgBase, padding: "1px 6px", border: `1px solid ${D.border}` }}>
                logs/
              </span>
              {logFiles.length > 0 && (
                <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted }}>{logFiles.length}</span>
              )}
              {selectedPaths.size > 0 && (
                <span style={{ fontFamily: D.mono, fontSize: 10, fontWeight: 600, color: D.blue }}>
                  {selectedPaths.size} selected
                </span>
              )}
            </div>
            <button
              onClick={loadLogs}
              disabled={loadingLogs}
              style={{
                padding: "3px 10px", fontSize: 10, fontWeight: 500,
                border: `1px solid ${D.border}`, background: D.bgBase,
                color: D.textSecond, cursor: loadingLogs ? "not-allowed" : "pointer",
                fontFamily: D.mono,
              }}
            >
              {loadingLogs ? "loading..." : "reload"}
            </button>
          </div>

          {loadingLogs && (
            <div style={{ padding: "14px 16px", color: D.textMuted, fontSize: 11, fontFamily: D.mono }}>
              loading log file list...
            </div>
          )}

          {logsError && !loadingLogs && (
            <div style={{ padding: "10px 14px", color: D.red, fontSize: 11, borderBottom: `1px solid ${D.border}`, fontFamily: D.mono }}>
              ERROR: {logsError}
            </div>
          )}

          {!loadingLogs && !logsError && logFiles.length === 0 && (
            <div style={{ padding: "14px 16px", color: D.textMuted, fontSize: 11 }}>
              No log files found in <code style={{ fontFamily: D.mono, color: D.textSecond }}>logs/</code>. Drop .log / .jsonl / .json files into any subfolder and click reload.
            </div>
          )}

          {!loadingLogs && logFiles.length > 0 && (
            <div>
              {groupKeys.map(group => {
                const files    = grouped[group];
                const isOpen   = !collapsedGroups.has(group);
                const selCount = files.filter(f => selectedPaths.has(f.path)).length;
                return (
                  <div key={group} style={{ borderBottom: `1px solid ${D.border}` }}>
                    <button
                      onClick={() => toggleGroup(group)}
                      style={{
                        width: "100%", background: "transparent", border: "none",
                        padding: "6px 14px", cursor: "pointer", textAlign: "left",
                        display: "flex", alignItems: "center", gap: 8,
                      }}
                    >
                      <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted }}>{isOpen ? "▾" : "▸"}</span>
                      <span style={{ fontFamily: D.mono, fontSize: 11, color: D.textSecond, flex: 1 }}>{group}</span>
                      <span style={{ fontSize: 10, color: D.textMuted, fontFamily: D.mono }}>{files.length}</span>
                      {selCount > 0 && (
                        <span style={{ fontFamily: D.mono, fontSize: 10, fontWeight: 600, color: D.blue }}>
                          {selCount} sel
                        </span>
                      )}
                    </button>

                    {isOpen && (
                      <div>
                        {files.map(f => {
                          const checked = selectedPaths.has(f.path);
                          const cat     = getCategory(f);
                          return (
                            <label
                              key={f.path}
                              style={{
                                display: "flex", alignItems: "center", gap: 10,
                                padding: "5px 14px 5px 28px", cursor: "pointer",
                                background: checked ? D.bgBase : "transparent",
                                borderTop: `1px solid ${D.border}`,
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleFile(f.path)}
                                style={{ width: 12, height: 12, flexShrink: 0, accentColor: D.blue }}
                              />
                              <span style={{ fontFamily: D.mono, fontSize: 11, color: checked ? D.textPrimary : D.textSecond, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {f.filename}
                              </span>
                              <span style={{ fontFamily: D.mono, fontSize: 10, color: D.textMuted, flexShrink: 0 }}>
                                {formatBytes(f.size_bytes)}
                              </span>
                              <select
                                value={cat}
                                onClick={e => e.stopPropagation()}
                                onChange={e => setCategoryOverride(prev => ({ ...prev, [f.path]: e.target.value }))}
                                style={{
                                  fontSize: 10, padding: "1px 4px",
                                  border: `1px solid ${D.border}`,
                                  background: D.bgBase, color: D.textSecond,
                                  cursor: "pointer", flexShrink: 0, fontFamily: D.mono,
                                }}
                              >
                                {CATEGORY_OPTIONS.map(opt => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </select>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {!loadingLogs && (
            <div style={{ padding: "5px 14px", borderTop: logFiles.length > 0 ? `1px solid ${D.border}` : "none" }}>
              <span style={{ fontFamily: D.mono, fontSize: 9, color: D.textMuted }}>
                {selectedPaths.size > 0
                  ? `${selectedPaths.size} file(s) selected for /api/run_rca_from_file`
                  : "no files selected — legacy demo scenario (run_rca_from_logs)"}
              </span>
            </div>
          )}
        </div>

        {/* ── Query + Run button ── */}
        <div style={{ background: D.bgCard, border: `1px solid ${D.border}`, padding: "12px 14px", marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 9, fontWeight: 600, color: D.textMuted, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 5, fontFamily: D.mono }}>
                QUERY
              </div>
              <input
                type="text"
                value={userQuery}
                disabled={loading}
                onChange={e => setUserQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !loading && handleRun()}
                placeholder="Describe the problem..."
                style={{
                  width: "100%", boxSizing: "border-box",
                  padding: "7px 10px",
                  border: `1px solid ${D.border}`,
                  background: loading ? D.bgBase : D.bgSurface,
                  color: D.textPrimary, fontSize: 13,
                  outline: "none", fontFamily: "'Inter', system-ui, sans-serif",
                }}
              />
            </div>
            <button
              onClick={handleRun}
              disabled={loading}
              style={{
                padding: "8px 24px",
                border: "none",
                background: loading ? D.grey : D.blue,
                color: "#fff", fontWeight: 600, fontSize: 13,
                cursor: loading ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", gap: 8,
                whiteSpace: "nowrap", letterSpacing: "0.02em",
              }}
            >
              {loading ? (
                <>
                  <span style={{ display: "inline-block", width: 12, height: 12, border: `2px solid #fff`, borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
                  RUNNING
                </>
              ) : "RUN RCA"}
            </button>
          </div>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>

        {/* ── Error banner ── */}
        {error && (
          <div style={{
            background: D.bgCard, border: `1px solid ${D.red}`,
            borderLeftWidth: 3, borderLeftColor: D.red,
            padding: "12px 14px", marginBottom: 16,
          }}>
            <div style={{ fontFamily: D.mono, fontSize: 10, fontWeight: 600, color: D.red, letterSpacing: "0.08em", marginBottom: 4 }}>
              RCA ERROR
            </div>
            <pre style={{ margin: 0, fontSize: 11, color: D.textSecond, whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: D.mono }}>
              {error}
            </pre>
          </div>
        )}

        {/* ── Results ── */}
        {report && (
          <>
            {/* Agent Execution Chain */}
            {(report.agent_chain?.length ?? 0) > 0 && (
              <>
                <SectionHeader>AGENT EXECUTION CHAIN</SectionHeader>
                <div style={{ marginBottom: 16 }}>
                  <AgentChainSection
                    agentChain={report.agent_chain!}
                    correlations={(report.issue_profile as any)?.correlations ?? []}
                  />
                </div>
              </>
            )}

            {/* Overall assessment */}
            <SectionHeader>OVERALL ASSESSMENT</SectionHeader>
            <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
              <HealthScoreBlock score={healthScore} />
              <LogStatusBlock problemType={problemType} />
              {confidence != null && <ConfidenceBlock value={confidence} />}
            </div>

            {/* Metadata strip */}
            <MetadataStrip
              agents={agentsInvoked}
              totalFindings={ip?.total_findings_count}
              criticalFindings={ip?.critical_findings_count}
              generatedAt={report.generated_at as string | undefined}
            />

            {/* Summary report */}
            {execSummary && (
              <>
                <SectionHeader>SUMMARY REPORT</SectionHeader>
                <div style={{ marginBottom: 16 }}>
                  <ExecutiveSummaryCard text={execSummary} />
                </div>
              </>
            )}

            {/* Analyzer details */}
            {ip && (
              <>
                <SectionHeader>ANALYZER DETAILS</SectionHeader>
                <AnalyzerTable issueProfile={ip} />
              </>
            )}

            {/* Recommended actions */}
            {fixes.length > 0 && (
              <PrioritizedFixes fixes={fixes} />
            )}

            {plainRecs.length > 0 && fixes.length === 0 && (
              <RecommendationsList items={plainRecs} />
            )}

            {fixes.length === 0 && plainRecs.length === 0 && (
              <div style={{
                background: D.bgCard, border: `1px solid ${D.border}`,
                padding: "12px 16px", marginBottom: 16,
              }}>
                <span style={{ fontFamily: D.mono, fontSize: 11, color: D.textMuted }}>NO RECOMMENDATIONS AVAILABLE</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
