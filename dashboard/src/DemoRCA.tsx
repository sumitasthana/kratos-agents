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

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens — identical to RCAFindings.tsx so pages look consistent
// ─────────────────────────────────────────────────────────────────────────────

const COLOR = {
  bg:          "#f9fafb",
  surface:     "#ffffff",
  border:      "#e5e7eb",
  borderMuted: "#f3f4f6",
  textPrimary: "#111827",
  textSecond:  "#6b7280",
  textMuted:   "#9ca3af",
  blue:        "#2563eb",
  blueBg:      "#eff6ff",
  blueBorder:  "#bfdbfe",
  critical: { bg: "#fef2f2", border: "#fca5a5", text: "#991b1b", badge: "#dc2626" },
  high:     { bg: "#fff7ed", border: "#fdba74", text: "#9a3412", badge: "#ea580c" },
  medium:   { bg: "#fffbeb", border: "#fcd34d", text: "#92400e", badge: "#d97706" },
  low:      { bg: "#f0fdf4", border: "#86efac", text: "#166534", badge: "#16a34a" },
  info:     { bg: "#f9fafb", border: "#e5e7eb", text: "#374151", badge: "#6b7280" },
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

function getSeverityStyle(s: string) {
  switch (s?.toLowerCase()) {
    case "critical": return COLOR.critical;
    case "high":     return COLOR.high;
    case "medium":   return COLOR.medium;
    case "low":      return COLOR.low;
    default:         return COLOR.info;
  }
}

function getLogStatusMeta(t: string) {
  switch (t?.toLowerCase()) {
    case "healthy":           return { bg: "#f0fdf4", border: "#bbf7d0", text: "#15803d", badge: "#16a34a", icon: "✓", label: "Healthy",           category: "No Issues"        };
    case "execution_failure": return { bg: "#fef2f2", border: "#fecaca", text: "#b91c1c", badge: "#dc2626", icon: "✕", label: "Execution Failure", category: "Job Failed"       };
    case "memory_pressure":   return { bg: "#faf5ff", border: "#e9d5ff", text: "#7e22ce", badge: "#9333ea", icon: "▲", label: "Memory Pressure",   category: "Resource Issue"   };
    case "shuffle_overhead":  return { bg: "#eff6ff", border: "#bfdbfe", text: "#1d4ed8", badge: "#2563eb", icon: "⇄", label: "Shuffle Overhead",  category: "Network I/O"      };
    case "data_skew":         return { bg: "#fefce8", border: "#fef08a", text: "#a16207", badge: "#ca8a04", icon: "≠", label: "Data Skew",         category: "Partition Issue"  };
    case "performance":       return { bg: "#fffbeb", border: "#fde68a", text: "#b45309", badge: "#d97706", icon: "◎", label: "Performance",       category: "Optimization"     };
    case "general":           return { bg: "#f9fafb", border: "#e5e7eb", text: "#374151", badge: "#6b7280", icon: "≡", label: "General",           category: "General Analysis" };
    default:                   return { bg: "#f9fafb", border: "#e5e7eb", text: "#374151", badge: "#6b7280", icon: "—", label: t || "Unknown",      category: "Unknown"          };
  }
}

function confidenceLabel(v: number): string {
  return v >= 80 ? "High confidence" : v >= 60 ? "Moderate confidence" : "Low confidence";
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared UI atoms
// ─────────────────────────────────────────────────────────────────────────────

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: COLOR.surface, border: `1px solid ${COLOR.border}`, borderRadius: 10, ...style }}>
      {children}
    </div>
  );
}

function CardLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
      {children}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = getSeverityStyle(severity);
  return (
    <span style={{
      padding: "2px 9px", borderRadius: 5, fontSize: 10, fontWeight: 700,
      background: s.bg, border: `1px solid ${s.border}`, color: s.text,
      textTransform: "uppercase", letterSpacing: 0.6, flexShrink: 0,
    }}>
      {severity || "info"}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Health Gauge Card  (SVG arc — identical style to RCAFindings)
// ─────────────────────────────────────────────────────────────────────────────

function HealthGaugeCard({ score }: { score: number }) {
  const color  = score >= 80 ? "#16a34a" : score >= 60 ? "#d97706" : "#dc2626";
  const status = score >= 80 ? "HEALTHY"  : score >= 60 ? "WARNING"  : "CRITICAL";
  const r = 28, circ = 2 * Math.PI * r, offset = circ - (score / 100) * circ;
  return (
    <Card style={{ padding: "18px 24px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      <CardLabel>Health score</CardLabel>
      <div style={{ position: "relative", display: "inline-block", marginBottom: 6 }}>
        <svg width={72} height={72} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={36} cy={36} r={r} fill="none" stroke={COLOR.borderMuted} strokeWidth={6} />
          <circle cx={36} cy={36} r={r} fill="none" stroke={color} strokeWidth={6}
            strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 700, color }}>
          {Math.round(score)}
        </div>
      </div>
      <div style={{ fontSize: 10, fontWeight: 700, color, letterSpacing: 0.8, textTransform: "uppercase" }}>{status}</div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Log Status Card  (dominant problem type)
// ─────────────────────────────────────────────────────────────────────────────

function LogStatusCard({ problemType }: { problemType: string }) {
  const m         = getLogStatusMeta(problemType);
  const isSpecific = ["execution_failure", "memory_pressure", "shuffle_overhead", "data_skew"]
    .includes(problemType?.toLowerCase());
  return (
    <div style={{ flex: 1, padding: "18px 20px", background: m.bg, border: `1px solid ${m.border}`, borderRadius: 10 }}>
      <CardLabel>Log status</CardLabel>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: m.badge, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 14, fontWeight: 700, flexShrink: 0 }}>
          {m.icon}
        </div>
        <span style={{ fontSize: 18, fontWeight: 700, color: m.text, letterSpacing: -0.3 }}>{m.label}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 10, fontWeight: 700, background: m.badge, color: "#fff", letterSpacing: 0.4, textTransform: "uppercase" }}>
          {m.category}
        </span>
        {isSpecific && (
          <span style={{ padding: "3px 10px", borderRadius: 6, fontSize: 10, fontWeight: 600, background: "transparent", border: `1px solid ${m.border}`, color: m.text }}>
            Dominant issue
          </span>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Confidence Card
// ─────────────────────────────────────────────────────────────────────────────

function ConfidenceCard({ value }: { value: number }) {
  const pct   = value <= 1.0 ? Math.round(value * 100) : Math.round(value);
  const color = pct >= 80 ? "#16a34a" : pct >= 60 ? "#d97706" : "#dc2626";
  return (
    <Card style={{ flex: 1, padding: "18px 20px" }}>
      <CardLabel>Confidence</CardLabel>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontSize: 28, fontWeight: 700, color, letterSpacing: -1 }}>{pct}%</span>
        <span style={{ fontSize: 11, color: COLOR.textMuted }}>{confidenceLabel(pct)}</span>
      </div>
      <div style={{ background: COLOR.borderMuted, borderRadius: 4, height: 6, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.7s ease" }} />
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Summary renderer
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
            <span style={{ color: COLOR.textMuted, flexShrink: 0, marginTop: 1 }}>·</span>
            <span>{renderInline(cleaned)}</span>
          </div>
        ) : (
          <div key={i} style={{ marginBottom: line.trim() ? 4 : 8 }}>{renderInline(cleaned)}</div>
        );
      })}
    </div>
  );
}

function ExecutiveSummaryCard({ text }: { text: string }) {
  return (
    <Card style={{ borderLeft: `3px solid ${COLOR.blue}`, overflow: "hidden", marginBottom: 0 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "14px 16px" }}>
        <div style={{
          width: 22, height: 22, borderRadius: 999,
          background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, fontSize: 12, color: COLOR.blue, marginTop: 1,
        }}>✓</div>
        <p style={{ margin: 0, lineHeight: 1.75, fontSize: 13, color: "#374151", whiteSpace: "pre-wrap" }}>
          {text}
        </p>
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Agents invoked tags
// ─────────────────────────────────────────────────────────────────────────────

function AgentTags({ agents }: { agents: string[] }) {
  if (!agents?.length) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      <span style={{ fontSize: 11, color: COLOR.textMuted, fontWeight: 600 }}>Invoked:</span>
      {agents.map((a, i) => (
        <span key={i} style={{ padding: "2px 9px", borderRadius: 5, fontSize: 11, fontWeight: 500, background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`, color: COLOR.blue }}>
          {a}
        </span>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Analyzer strip  (collapsible per-analyzer cards)
// ─────────────────────────────────────────────────────────────────────────────

const ANALYZER_META: Record<string, { label: string; icon: string }> = {
  log_analysis:    { label: "Spark / Log",     icon: "📋" },
  code_analysis:   { label: "Code Analyzer",   icon: "🔍" },
  data_analysis:   { label: "Data Profiler",   icon: "📊" },
  change_analysis: { label: "Change Analyzer", icon: "🔀" },
  infra_analysis:  { label: "Infra Analyzer",  icon: "🖥️" },
};

function AnalyzerStrip({ issueProfile }: { issueProfile: IssueProfile }) {
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

  return (
    <Card style={{ marginBottom: 16, overflow: "hidden" }}>
      <div style={{ padding: "8px 16px 7px", borderBottom: `1px solid ${COLOR.borderMuted}`, display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>Per-analyzer results</span>
        <span style={{ fontSize: 10, color: COLOR.textMuted, background: COLOR.borderMuted, borderRadius: 4, padding: "1px 7px", fontWeight: 600 }}>
          {analyzers.length}
        </span>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap" }}>
        {analyzers.map(({ key, result }, i) => {
          const problemType = result.problem_type ?? "general";
          const m      = getLogStatusMeta(problemType);
          const meta   = ANALYZER_META[key] ?? { label: key, icon: "—" };
          const isOpen = expandedKey === key;
          const hs     = result.health_score ?? 100;
          const hColor = hs >= 80 ? "#16a34a" : hs >= 60 ? "#d97706" : "#dc2626";

          return (
            <div
              key={key}
              style={{ flex: "1 1 180px", minWidth: 160, borderRight: i < analyzers.length - 1 ? `1px solid ${COLOR.border}` : "none" }}
            >
              <button
                onClick={() => setExpandedKey(isOpen ? null : key)}
                style={{ width: "100%", background: "transparent", border: "none", padding: "11px 16px", cursor: "pointer", textAlign: "left" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 5 }}>
                  <span style={{ fontSize: 12, lineHeight: 1 }}>{meta.icon}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: COLOR.textPrimary, flex: 1 }}>{meta.label}</span>
                  <span style={{ fontSize: 10, color: isOpen ? COLOR.blue : COLOR.textMuted }}>{isOpen ? "▾" : "▸"}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ padding: "2px 8px", borderRadius: 5, fontSize: 10, fontWeight: 700, background: m.bg, border: `1px solid ${m.border}`, color: m.text, textTransform: "uppercase", letterSpacing: 0.4 }}>
                    {problemType.replace(/_/g, " ")}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: hColor }}>{Math.round(hs)}/100</span>
                </div>
              </button>

              {isOpen && (
                <div style={{ borderTop: `1px solid ${COLOR.borderMuted}`, background: COLOR.bg, padding: "8px 14px 12px" }}>
                  {result.executive_summary && (
                    <p style={{ margin: "0 0 8px", fontSize: 12, color: COLOR.textSecond, lineHeight: 1.6, fontStyle: "italic" }}>
                      {result.executive_summary}
                    </p>
                  )}
                  {(result.findings ?? []).length === 0 ? (
                    <div style={{ fontSize: 11, color: COLOR.textMuted, fontStyle: "italic", padding: "4px 0" }}>No findings.</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {(result.findings ?? []).slice(0, 5).map((f, fi) => {
                        const sev = resolvedSeverity(f);
                        const sc  = getSeverityStyle(sev);
                        return (
                          <div key={fi} style={{ padding: "7px 10px", borderRadius: 6, background: sc.bg, border: `1px solid ${sc.border}`, borderLeft: `3px solid ${sc.badge}` }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: f.description ? 3 : 0 }}>
                              <span style={{ fontSize: 12, fontWeight: 600, color: COLOR.textPrimary, flex: 1 }}>
                                {f.title || f.finding_type || `Finding ${fi + 1}`}
                              </span>
                              <SeverityBadge severity={sev} />
                            </div>
                            {f.description && (
                              <div style={{ fontSize: 11, color: COLOR.textSecond, lineHeight: 1.5 }}>
                                {f.description.length > 160 ? f.description.slice(0, 160) + "…" : f.description}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {(result.findings ?? []).length > 5 && (
                        <div style={{ fontSize: 11, color: COLOR.textMuted, textAlign: "center", paddingTop: 4 }}>
                          +{result.findings!.length - 5} more findings
                        </div>
                      )}
                    </div>
                  )}
                  {(result.recommendations ?? []).length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 5 }}>Recommendations</div>
                      <ul style={{ margin: 0, padding: "0 0 0 16px", display: "flex", flexDirection: "column", gap: 4 }}>
                        {(result.recommendations ?? []).map((r, ri) => (
                          <li key={ri} style={{ fontSize: 12, color: "#166534", lineHeight: 1.55 }}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Prioritized Fixes
// ─────────────────────────────────────────────────────────────────────────────

const EFFORT_COLOR: Record<string, string> = { low: "#16a34a", medium: "#d97706", high: "#dc2626" };

function PrioritizedFixes({ fixes }: { fixes: Fix[] }) {
  const [open, setOpen] = useState(true);
  if (!fixes?.length) return null;

  const sorted = [...fixes].sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99));

  return (
    <div style={{ marginBottom: 20 }}>
      <button onClick={() => setOpen(o => !o)} style={{ width: "100%", background: "transparent", border: "none", padding: 0, marginBottom: 8, cursor: "pointer" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 2px" }}>
          <span style={{ width: 18, height: 18, borderRadius: 999, border: `1px solid ${COLOR.border}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: COLOR.textMuted, background: COLOR.surface, flexShrink: 0 }}>
            {open ? "▾" : "▸"}
          </span>
          <span style={{ fontSize: 13, fontWeight: 700, color: COLOR.textPrimary }}>Prioritized fixes</span>
          <span style={{ fontSize: 11, fontWeight: 600, color: COLOR.textMuted, background: COLOR.borderMuted, padding: "1px 7px", borderRadius: 5 }}>{fixes.length}</span>
        </div>
      </button>

      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {sorted.map((fix, i) => {
            const effortColor = EFFORT_COLOR[fix.effort?.toLowerCase() ?? ""] ?? COLOR.textMuted;
            return (
              <Card key={fix.fix_id ?? i} style={{ overflow: "hidden", borderLeft: `3px solid ${COLOR.blue}` }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "10px 14px", background: COLOR.blueBg, borderBottom: `1px solid ${COLOR.blueBorder}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ minWidth: 24, height: 24, background: COLOR.blue, color: "#fff", borderRadius: 6, fontWeight: 700, fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      {fix.priority ?? i + 1}
                    </div>
                    <span style={{ fontWeight: 600, fontSize: 13, color: COLOR.textPrimary }}>{fix.title ?? `Fix ${i + 1}`}</span>
                  </div>
                  {fix.effort && (
                    <span style={{ padding: "2px 9px", borderRadius: 5, fontSize: 10, fontWeight: 700, textTransform: "uppercase", background: "transparent", border: `1px solid ${effortColor}`, color: effortColor, letterSpacing: 0.5 }}>
                      {fix.effort} effort
                    </span>
                  )}
                </div>
                {fix.description && (
                  <div style={{ padding: "10px 14px", fontSize: 13, color: "#374151", lineHeight: 1.65 }}>
                    {renderMarkdown(fix.description)}
                  </div>
                )}
                {fix.code_snippet && (
                  <div style={{ padding: "8px 14px", background: "#1e1e2e", color: "#cdd6f4", fontFamily: "monospace", fontSize: 11, lineHeight: 1.6, borderTop: `1px solid ${COLOR.borderMuted}`, whiteSpace: "pre-wrap", overflowX: "auto" }}>
                    {fix.code_snippet}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline caption  (static)
// ─────────────────────────────────────────────────────────────────────────────

function PipelineCaption({ jobId }: { jobId?: string }) {
  const steps = ["Routing Agent", "Analyzers (Spark / Airflow / Data / Infra / Change)", "Triangulation", "Recommender"];
  return (
    <div style={{ fontSize: 11, color: COLOR.textMuted, lineHeight: 1.6 }}>
      <span style={{ fontWeight: 600, color: COLOR.textSecond }}>Pipeline: </span>
      {steps.map((step, i) => (
        <React.Fragment key={step}>
          <span>{step}</span>
          {i < steps.length - 1 && <span style={{ margin: "0 5px", color: COLOR.textMuted }}>→</span>}
        </React.Fragment>
      ))}
      {" "}via <code style={{ fontSize: 10 }}>KratosOrchestrator</code>
      {jobId && <> · <span style={{ fontFamily: "monospace", fontSize: 10 }}>{jobId}</span></>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Fallback: plain string recommendations
// ─────────────────────────────────────────────────────────────────────────────

function RecommendationsList({ items }: { items: string[] }) {
  if (!items?.length) return null;
  return (
    <Card style={{ marginBottom: 16, padding: "14px 18px" }}>
      <CardLabel>Recommended actions</CardLabel>
      <ul style={{ margin: 0, padding: "0 0 0 18px", display: "flex", flexDirection: "column", gap: 6 }}>
        {items.map((r, i) => (
          <li key={i} style={{ fontSize: 13, color: "#166534", lineHeight: 1.65 }}>{r}</li>
        ))}
      </ul>
    </Card>
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
      const text = await res.text();
      if (!res.ok) throw new Error(`Browse failed (${res.status}): ${text.slice(0, 200)}`);
      setLogFiles(JSON.parse(text) as LogFileEntry[]);
    } catch (e: any) {
      setLogsError(e?.message ?? String(e));
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
      padding: "24px 28px",
      fontFamily: "Segoe UI, system-ui, Arial, sans-serif",
      background: COLOR.bg,
      color: COLOR.textPrimary,
      fontSize: 13,
    }}>
      <div style={{ maxWidth: 900, margin: "0 auto" }}>

        {/* ── Page title + pipeline caption ── */}
        <div style={{ marginBottom: 20 }}>
          <h1 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 800, color: COLOR.textPrimary }}>
            🔬 Demo RCA — Real Fixture Logs
          </h1>
          <PipelineCaption jobId={report?.job_id} />
        </div>

        {/* ── Log file browser ── */}
        <Card style={{ marginBottom: 16, overflow: "hidden" }}>
          {/* Browser header */}
          <div style={{
            padding: "10px 16px 9px",
            borderBottom: `1px solid ${COLOR.borderMuted}`,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>
                Available logs
              </span>
              <code style={{ fontSize: 10, color: COLOR.textSecond, background: COLOR.borderMuted, padding: "1px 7px", borderRadius: 4 }}>logs/</code>
              {logFiles.length > 0 && (
                <span style={{ fontSize: 10, color: COLOR.textMuted, background: COLOR.borderMuted, borderRadius: 4, padding: "1px 7px", fontWeight: 600 }}>
                  {logFiles.length}
                </span>
              )}
              {selectedPaths.size > 0 && (
                <span style={{ fontSize: 10, fontWeight: 700, color: COLOR.blue, background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`, borderRadius: 4, padding: "1px 7px" }}>
                  {selectedPaths.size} selected
                </span>
              )}
            </div>
            <button
              onClick={loadLogs}
              disabled={loadingLogs}
              style={{ padding: "4px 14px", fontSize: 11, fontWeight: 600, borderRadius: 6, border: `1px solid ${COLOR.border}`, background: COLOR.surface, color: COLOR.textSecond, cursor: loadingLogs ? "not-allowed" : "pointer" }}
            >
              {loadingLogs ? "Loading…" : "↺ Reload"}
            </button>
          </div>

          {/* Loading */}
          {loadingLogs && (
            <div style={{ padding: "18px 16px", color: COLOR.textMuted, fontSize: 12, fontStyle: "italic" }}>
              Loading log file list…
            </div>
          )}

          {/* Browse error */}
          {logsError && !loadingLogs && (
            <div style={{ padding: "12px 16px", color: COLOR.critical.text, fontSize: 12, background: COLOR.critical.bg }}>
              ⚠ {logsError}
            </div>
          )}

          {/* Empty state */}
          {!loadingLogs && !logsError && logFiles.length === 0 && (
            <div style={{ padding: "18px 16px", color: COLOR.textMuted, fontSize: 12 }}>
              No log files found in <code>logs/</code>. Drop <code>.log</code> / <code>.jsonl</code> / <code>.json</code> files into any subfolder and click Reload.
            </div>
          )}

          {/* File groups */}
          {!loadingLogs && logFiles.length > 0 && (
            <div>
              {groupKeys.map(group => {
                const files    = grouped[group];
                const isOpen   = !collapsedGroups.has(group);
                const selCount = files.filter(f => selectedPaths.has(f.path)).length;
                return (
                  <div key={group} style={{ borderBottom: `1px solid ${COLOR.borderMuted}` }}>
                    {/* Group header */}
                    <button
                      onClick={() => toggleGroup(group)}
                      style={{ width: "100%", background: "transparent", border: "none", padding: "7px 16px", cursor: "pointer", textAlign: "left", display: "flex", alignItems: "center", gap: 8 }}
                    >
                      <span style={{ fontSize: 10, color: isOpen ? COLOR.blue : COLOR.textMuted }}>{isOpen ? "▾" : "▸"}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: COLOR.textSecond, flex: 1 }}>
                        📁 {group}
                      </span>
                      <span style={{ fontSize: 10, color: COLOR.textMuted }}>{files.length} file{files.length !== 1 ? "s" : ""}</span>
                      {selCount > 0 && (
                        <span style={{ fontSize: 10, fontWeight: 700, color: COLOR.blue, background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`, borderRadius: 4, padding: "1px 6px" }}>
                          {selCount} ✓
                        </span>
                      )}
                    </button>

                    {/* File rows */}
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
                                padding: "6px 16px 6px 28px", cursor: "pointer",
                                background: checked ? COLOR.blueBg : "transparent",
                                borderTop: `1px solid ${COLOR.borderMuted}`,
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleFile(f.path)}
                                style={{ width: 13, height: 13, flexShrink: 0, accentColor: COLOR.blue }}
                              />
                              <span style={{ fontSize: 12, color: COLOR.textPrimary, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                📄 {f.filename}
                              </span>
                              <span style={{ fontSize: 10, color: COLOR.textMuted, flexShrink: 0 }}>
                                {formatBytes(f.size_bytes)}
                              </span>
                              <span style={{ fontSize: 10, color: COLOR.textMuted, flexShrink: 0 }}>category:</span>
                              <select
                                value={cat}
                                onClick={e => e.stopPropagation()}
                                onChange={e => setCategoryOverride(prev => ({ ...prev, [f.path]: e.target.value }))}
                                style={{ fontSize: 11, padding: "1px 4px", borderRadius: 4, border: `1px solid ${COLOR.border}`, background: COLOR.surface, color: COLOR.textPrimary, cursor: "pointer", flexShrink: 0 }}
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

          {/* Status hint */}
          {!loadingLogs && (
            <div style={{ padding: "7px 16px", background: COLOR.borderMuted }}>
              <span style={{ fontSize: 10, color: COLOR.textMuted }}>
                {selectedPaths.size > 0
                  ? `▶ Run RCA will analyse the ${selectedPaths.size} selected file(s) via /api/run_rca_from_file.`
                  : "No files selected — Run RCA will use the hardcoded demo scenario (legacy mode)."}
              </span>
            </div>
          )}
        </Card>

        {/* ── User query + run button ── */}
        <Card style={{ marginBottom: 20, padding: "14px 16px" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: COLOR.textSecond, marginBottom: 6 }}>User query</label>
              <input
                type="text"
                value={userQuery}
                disabled={loading}
                onChange={e => setUserQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !loading && handleRun()}
                placeholder="Describe the problem…"
                style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", border: `1px solid ${COLOR.border}`, borderRadius: 7, fontSize: 13, color: COLOR.textPrimary, background: loading ? COLOR.bg : COLOR.surface, outline: "none" }}
              />
            </div>
            <button
              onClick={handleRun} disabled={loading}
              style={{ padding: "9px 26px", borderRadius: 7, border: "none", background: loading ? COLOR.blueBg : COLOR.blue, color: loading ? COLOR.blue : "#fff", fontWeight: 700, fontSize: 14, cursor: loading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap", transition: "background 0.15s" }}
            >
              {loading ? (
                <>
                  <span style={{ display: "inline-block", width: 14, height: 14, border: `2px solid ${COLOR.blue}`, borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
                  Running…
                </>
              ) : "▶  Run RCA"}
            </button>
          </div>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </Card>

        {/* ── Error banner ── */}
        {error && (
          <Card style={{ marginBottom: 20, padding: "14px 16px", background: COLOR.critical.bg, borderColor: COLOR.critical.border }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: COLOR.critical.text, marginBottom: 4 }}>RCA Error</div>
            <pre style={{ margin: 0, fontSize: 12, color: "#a8071a", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{error}</pre>
          </Card>
        )}

        {/* ── Results ── */}
        {report && (
          <>
            {/* Overall assessment row */}
            <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
              Overall assessment
            </div>
            <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
              <HealthGaugeCard score={healthScore} />
              <LogStatusCard problemType={problemType} />
              {confidence != null && <ConfidenceCard value={confidence} />}
            </div>

            {/* Agents invoked + metadata row */}
            {(agentsInvoked.length > 0 || ip?.total_findings_count != null) && (
              <Card style={{ marginBottom: 16, padding: "10px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                  <AgentTags agents={agentsInvoked} />
                  <div style={{ display: "flex", gap: 14, fontSize: 11, color: COLOR.textMuted }}>
                    {ip?.total_findings_count != null && (
                      <span>Findings: <strong style={{ color: COLOR.textPrimary }}>{ip.total_findings_count}</strong></span>
                    )}
                    {ip?.critical_findings_count != null && ip.critical_findings_count > 0 && (
                      <span>Critical: <strong style={{ color: COLOR.critical.badge }}>{ip.critical_findings_count}</strong></span>
                    )}
                    {report.generated_at && (
                      <span>Generated: <strong style={{ color: COLOR.textPrimary }}>{new Date(report.generated_at as string).toLocaleTimeString()}</strong></span>
                    )}
                  </div>
                </div>
              </Card>
            )}

            {/* Summary report */}
            {execSummary && (
              <>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                  Summary report
                </div>
                <div style={{ marginBottom: 16 }}>
                  <ExecutiveSummaryCard text={execSummary} />
                </div>
              </>
            )}

            {/* Per-analyzer results */}
            {ip && (
              <>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                  Analyzer details
                </div>
                <AnalyzerStrip issueProfile={ip} />
              </>
            )}

            {/* Prioritized fixes */}
            {fixes.length > 0 && (
              <>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                  Recommended actions
                </div>
                <PrioritizedFixes fixes={fixes} />
              </>
            )}

            {/* Fallback: plain string recommendations */}
            {plainRecs.length > 0 && fixes.length === 0 && (
              <>
                <div style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
                  Recommended actions
                </div>
                <RecommendationsList items={plainRecs} />
              </>
            )}

            {/* No recommendations at all */}
            {fixes.length === 0 && plainRecs.length === 0 && (
              <Card style={{ padding: "14px 18px", marginBottom: 16 }}>
                <span style={{ fontSize: 12, color: COLOR.textMuted, fontStyle: "italic" }}>No recommendations available yet.</span>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
