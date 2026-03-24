import React, { useState } from "react";
import { DEMO_SCENARIOS, FROM_LOGS_SCENARIOS, type ScenarioKey } from "./demoScenarios";


// ── Design tokens ─────────────────────────────────────────────────────────────


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


// ── Types ─────────────────────────────────────────────────────────────────────


type Finding = {
  title?:          string;
  description?:    string;
  severity?:       string;
  recommendation?: string;
  finding_type?:   string;
  agent_type?:     string;
};

type KPI = {
  label: string;
  value: string | number;
  color: string;
  sub?:  string;
};

type SeverityFilter   = "all" | "critical" | "high" | "medium" | "low" | "info";
type RCAFindingsProps  = { orchestratorData: any };
type LogStatusMeta    = { bg: string; border: string; text: string; badge: string; icon: string; label: string; category: string };
type SeverityStyle    = { bg: string; border: string; text: string; badge: string };

type SummarySection = {
  heading: string;
  items:   string[];
};

type ParsedSummary = {
  intro:    string;
  sections: SummarySection[];
};

// ── New types: mirrors Pydantic RecommendationReport / IssueProfile ───────────

type AnalysisResultT = {
  problem_type:      string;
  health_score:      number;
  confidence:        number;
  findings:          Finding[];
  recommendations:   string[];
  executive_summary: string;
};

type CrossAgentCorrelationT = {
  correlation_id:      string;
  contributing_agents: string[];
  pattern:             string;
  severity:            string;
  confidence:          number;
  evidence:            Record<string, any>;
  affected_artifacts:  string[];
};

type IssueProfileT = {
  job_id:                  string;
  generated_at:            string;
  dominant_problem_type:   string;
  log_analysis:            AnalysisResultT | null;
  code_analysis:           AnalysisResultT | null;
  data_analysis:           AnalysisResultT | null;
  change_analysis:         AnalysisResultT | null;
  infra_analysis:          AnalysisResultT | null;
  correlations:            CrossAgentCorrelationT[];
  lineage_map:             Record<string, string[]>;
  overall_health_score:    number;
  overall_confidence:      number;
  agents_invoked:          string[];
  total_findings_count:    number;
  critical_findings_count: number;
};


// ── RecommendationReport types (mirrors backend schemas.py Fix / RecommendationReport) ─

type Fix = {
  fix_id:            string;
  title:             string;
  description:       string;
  applies_to_agents: string[];
  priority:          number;
  effort:            string;   // "low" | "medium" | "high"
  code_snippet?:     string | null;
  references:        string[];
};

type RecommendationReport = {
  job_id:             string;
  generated_at:       string;
  issue_profile:      IssueProfileT;
  prioritized_fixes:  Fix[];
  executive_summary:  string;
  detailed_narrative: string;
  ontology_update?:   unknown;
  feedback_loop_signal: string;
  reviewer_notes?:    string | null;
};


// ── Constants ─────────────────────────────────────────────────────────────────


const SEVERITY_ORDER: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
};

const FILTER_OPTIONS: { value: SeverityFilter; label: string }[] = [
  { value: "all",      label: "All"      },
  { value: "critical", label: "Critical" },
  { value: "high",     label: "High"     },
  { value: "medium",   label: "Medium"   },
  { value: "low",      label: "Low"      },
  { value: "info",     label: "Info"     },
];

// Titles the LLM emits that are too generic to trust for severity inference
const GENERIC_TITLES = new Set(["issue", "analysis", "observation", "note", "finding"]);

// Only keep CRITICAL if one of these appears in the description body
const TRUE_CRITICAL_WORDS = ["crash", "oom", "out of memory", "job failed", "aborted", "killed"];

// Pattern for labeled rows inside finding bodies: "Symptom: ...", "Root Cause: ..."
const LABELED_ROW_PATTERN = /^(Symptom|Root Cause|Impact|Note|Cause|Effect|Action|Why):\s*(.*)/i;


// ── Severity resolution ───────────────────────────────────────────────────────
// Prevents false-positive CRITICAL badges on generic-titled cards that contain
// words like "failed" in a descriptive (not alarming) context.


function resolvedSeverity(f: Finding): string {
  const sev   = (f.severity || "info").toLowerCase();
  const title = (f.title    || "").toLowerCase().trim();

  if (sev === "critical" && GENERIC_TITLES.has(title)) {
    const desc          = (f.description || "").toLowerCase();
    const hasTrueCritical = TRUE_CRITICAL_WORDS.some(w => desc.includes(w));
    return hasTrueCritical ? "critical" : "high";
  }
  return sev;
}


// ── Log Status ────────────────────────────────────────────────────────────────


function getLogStatusMeta(t: string): LogStatusMeta {
  switch (t?.toLowerCase()) {
    case "healthy":           return { bg: "#f0fdf4", border: "#bbf7d0", text: "#15803d", badge: "#16a34a", icon: "OK",  label: "Healthy",           category: "No Issues"           };
    case "execution_failure": return { bg: "#fef2f2", border: "#fecaca", text: "#b91c1c", badge: "#dc2626", icon: "X",   label: "Execution Failure", category: "Job Failed"          };
    case "memory_pressure":   return { bg: "#faf5ff", border: "#e9d5ff", text: "#7e22ce", badge: "#9333ea", icon: "MEM", label: "Memory Pressure",   category: "Resource Issue"      };
    case "shuffle_overhead":  return { bg: "#eff6ff", border: "#bfdbfe", text: "#1d4ed8", badge: "#2563eb", icon: "SHF", label: "Shuffle Overhead",  category: "Network I/O Issue"   };
    case "data_skew":         return { bg: "#fefce8", border: "#fef08a", text: "#a16207", badge: "#ca8a04", icon: "SKW", label: "Data Skew",         category: "Partition Issue"     };
    case "performance":       return { bg: "#fffbeb", border: "#fde68a", text: "#b45309", badge: "#d97706", icon: "PERF",label: "Performance",       category: "Optimization Needed" };
    case "lineage":           return { bg: "#f0fdfa", border: "#99f6e4", text: "#0f766e", badge: "#0d9488", icon: "LIN", label: "Lineage",           category: "Data Flow"           };
    case "general":           return { bg: "#f9fafb", border: "#e5e7eb", text: "#374151", badge: "#6b7280", icon: "GEN", label: "General",           category: "General Analysis"    };
    default:                  return { bg: "#f9fafb", border: "#e5e7eb", text: "#374151", badge: "#6b7280", icon: "?",   label: t || "Unknown",      category: "Unknown"             };
  }
}

function getSeverityStyle(s: string): SeverityStyle {
  switch (s?.toLowerCase()) {
    case "critical": return COLOR.critical;
    case "high":     return COLOR.high;
    case "medium":   return COLOR.medium;
    case "low":      return COLOR.low;
    default:         return COLOR.info;
  }
}


// ── Summary parser ────────────────────────────────────────────────────────────
// Handles two LLM output shapes:
//   Shape A — sections on separate lines:   "\n- Data Flow:\n 1. Stage 0..."
//   Shape B — everything on one line:       "...summary. - Data Flow: 1. Stage 0..."
// Both are normalised before the section regex runs.


function parseSummary(raw: string): ParsedSummary {
  // 1. Strip leading emoji, stray bold markers, markdown bold
  let clean = raw
    .replace(/^[\u{1F300}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]\s*/u, "")
    .replace(/^\*+\s*/, "")
    .replace(/\*\*/g, "")
    .trim();

  // 2. Normalise Shape B: inject real newlines before inline " - Heading:" markers
  //    e.g. "...summary. - Data Flow: 1." → "...summary.\n- Data Flow: 1."
  clean = clean.replace(/\s+-\s+([A-Z][A-Za-z\s]{2,40}):/g, "\n- $1:");

  // 3. Find all section headers: lines starting with "- Heading:"
  const sectionRegex = /(?:^|\n)\s*-\s+([A-Z][^:\n]+):\s*/g;
  const matches: { index: number; heading: string; contentStart: number }[] = [];
  let match: RegExpExecArray | null;

  while ((match = sectionRegex.exec(clean)) !== null) {
    matches.push({
      index:        match.index,
      heading:      match[1].trim(),
      contentStart: match.index + match[0].length,
    });
  }

  if (matches.length === 0) {
    return { intro: clean, sections: [] };
  }

  // Everything before the first section header is the intro paragraph
  const intro = clean.slice(0, matches[0].index).trim();
  const sections: SummarySection[] = [];

  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].contentStart;
    const end   = i + 1 < matches.length ? matches[i + 1].index : clean.length;
    const body  = clean.slice(start, end).trim();

    const items: string[] = body
      .split(/\n/)
      .map(l => l.replace(/^[\d]+\.\s*/, "").replace(/^[-*]\s*/, "").trim())
      .filter(l => l.length > 0);

    if (items.length > 0) {
      sections.push({ heading: matches[i].heading, items });
    }
  }

  return { intro, sections };
}


// ── Inline bold / italic renderer ────────────────────────────────────────────


function renderInline(text: string): React.ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/).map((part, j) => {
    if (/^\*\*(.+)\*\*$/.test(part)) return <strong key={j}>{part.slice(2, -2)}</strong>;
    if (/^\*(.+)\*$/  .test(part)) return <em      key={j}>{part.slice(1, -1)}</em>;
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
        if (isBullet) {
          return (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4 }}>
              <span style={{ color: COLOR.textMuted, flexShrink: 0, marginTop: 1 }}>·</span>
              <span>{renderInline(cleaned)}</span>
            </div>
          );
        }
        return (
          <div key={i} style={{ marginBottom: line.trim() ? 4 : 8 }}>
            {renderInline(cleaned)}
          </div>
        );
      })}
    </div>
  );
}


// ── Confidence helpers ────────────────────────────────────────────────────────


function formatConfidence(raw: number): number {
  if (!raw) return 0;
  return raw <= 1.0 ? Math.round(raw * 100) : Math.round(raw);
}
function confidenceColor(v: number): string {
  return v >= 80 ? "#16a34a" : v >= 60 ? "#d97706" : "#dc2626";
}
function confidenceLabel(v: number): string {
  return v >= 80 ? "High confidence" : v >= 60 ? "Moderate confidence" : "Low confidence";
}


// ── Shared components ─────────────────────────────────────────────────────────


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

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div style={{ fontSize: 13, fontWeight: 700, color: COLOR.textPrimary, marginBottom: 0, display: "flex", alignItems: "center", gap: 8 }}>
      {title}
      {count !== undefined && (
        <span style={{ fontSize: 11, fontWeight: 600, color: COLOR.textMuted, background: COLOR.borderMuted, padding: "1px 7px", borderRadius: 5 }}>
          {count}
        </span>
      )}
    </div>
  );
}

function SectionToggleHeader({
  title, count, open, onToggle,
}: {
  title: string; count?: number; open: boolean; onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      style={{ width: "100%", background: "transparent", border: "none", padding: 0, margin: 0, cursor: "pointer" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 2px 10px" }}>
        <span style={{
          width: 18, height: 18, borderRadius: 999,
          border: `1px solid ${COLOR.border}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 10, color: COLOR.textMuted, background: COLOR.surface, flexShrink: 0,
        }}>
          {open ? "▾" : "▸"}
        </span>
        <SectionHeader title={title} count={count} />
      </div>
    </button>
  );
}


// ── Metric cards ──────────────────────────────────────────────────────────────


function LogStatusCard({ problemType }: { problemType: string }) {
  const m          = getLogStatusMeta(problemType);
  const isSpecific = ["execution_failure", "memory_pressure", "shuffle_overhead", "data_skew"]
    .includes(problemType?.toLowerCase());

  return (
    <div style={{ flex: 1, padding: "18px 20px", background: m.bg, border: `1px solid ${m.border}`, borderRadius: 10 }}>
      <CardLabel>Log Status</CardLabel>
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
            Dominant Issue
          </span>
        )}
      </div>
    </div>
  );
}

function ConfidenceCard({ value }: { value: number }) {
  const color = confidenceColor(value);
  return (
    <Card style={{ flex: 1, padding: "18px 20px" }}>
      <CardLabel>Confidence</CardLabel>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <span style={{ fontSize: 28, fontWeight: 700, color, letterSpacing: -1 }}>{value}%</span>
        <span style={{ fontSize: 11, color: COLOR.textMuted }}>{confidenceLabel(value)}</span>
      </div>
      <div style={{ background: COLOR.borderMuted, borderRadius: 4, height: 6, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.7s ease" }} />
      </div>
    </Card>
  );
}

function HealthGaugeCard({ score }: { score: number }) {
  const color  = score >= 80 ? "#16a34a" : score >= 60 ? "#d97706" : "#dc2626";
  const status = score >= 80 ? "HEALTHY"  : score >= 60 ? "WARNING"  : "CRITICAL";
  const r = 28, circ = 2 * Math.PI * r, offset = circ - (score / 100) * circ;

  return (
    <Card style={{ padding: "18px 24px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      <CardLabel>Health Score</CardLabel>
      <div style={{ position: "relative", display: "inline-block", marginBottom: 6 }}>
        <svg width={72} height={72} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={36} cy={36} r={r} fill="none" stroke={COLOR.borderMuted} strokeWidth={6} />
          <circle cx={36} cy={36} r={r} fill="none" stroke={color} strokeWidth={6}
            strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.8s ease" }}
          />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, fontWeight: 700, color }}>
          {score}
        </div>
      </div>
      <div style={{ fontSize: 10, fontWeight: 700, color, letterSpacing: 0.8, textTransform: "uppercase" }}>{status}</div>
    </Card>
  );
}

function ScoreBreakdownBar({ breakdown }: { breakdown: Record<string, number> }) {
  const items = [
    { key: "task_failures",    label: "Task Failures",    color: "#dc2626" },
    { key: "memory_pressure",  label: "Memory Pressure",  color: "#ea580c" },
    { key: "shuffle_overhead", label: "Shuffle Overhead", color: "#d97706" },
    { key: "data_skew",        label: "Data Skew",        color: "#9333ea" },
  ].filter(item => (breakdown[item.key] ?? 0) > 0);

  if (items.length === 0) return null;
  const total = items.reduce((s, i) => s + breakdown[i.key], 0);

  return (
    <Card style={{ marginBottom: 16, padding: "14px 18px" }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: COLOR.textPrimary, marginBottom: 12 }}>Score Penalty Breakdown</div>
      <div style={{ display: "flex", height: 6, borderRadius: 4, overflow: "hidden", marginBottom: 12, background: COLOR.borderMuted }}>
        {items.map((item, i) => (
          <div key={i} style={{ width: `${(breakdown[item.key] / total) * 100}%`, background: item.color, transition: "width 0.6s ease" }} />
        ))}
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {items.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: item.color }} />
            <span style={{ fontSize: 12, color: COLOR.textSecond }}>
              {item.label}
              <strong style={{ color: item.color, marginLeft: 4 }}>−{breakdown[item.key]}pts</strong>
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function KPIStrip({ data }: { data: any }) {
  const rcaMeta    = data?.raw_agent_responses?.root_cause?.metadata;
  const healthMeta = rcaMeta?.health_score;
  const perfMatrix = rcaMeta?.performance_matrix;
  const execSum    = data?.fingerprint?.metrics?.execution_summary;
  const kpis: KPI[] = [];

  if (healthMeta?.overall_score !== undefined) {
    const hc = healthMeta.status === "HEALTHY" ? "#16a34a" : healthMeta.status === "WARNING" ? "#d97706" : "#dc2626";
    kpis.push({ label: "Health", value: `${healthMeta.overall_score}/100`, color: hc, sub: healthMeta.status });
  }
  if (perfMatrix?.resource?.disk_spill_gb !== undefined) {
    const s = perfMatrix.resource.disk_spill_gb;
    kpis.push({ label: "Disk Spill", value: `${s} GB`, color: s > 20 ? "#dc2626" : s > 5 ? "#d97706" : "#16a34a", sub: s > 20 ? "OVER CAPACITY" : s > 5 ? "HIGH" : "OPTIMAL" });
  }
  if (perfMatrix?.execution?.failed_tasks !== undefined) {
    const f = perfMatrix.execution.failed_tasks;
    kpis.push({ label: "Failed Tasks", value: f, color: f > 0 ? "#dc2626" : "#16a34a", sub: f > 0 ? "ACTION NEEDED" : "CLEAN" });
  }
  if (perfMatrix?.execution?.task_success_rate !== undefined) {
    const r = perfMatrix.execution.task_success_rate;
    kpis.push({ label: "Success Rate", value: `${r}%`, color: r >= 99 ? "#16a34a" : r >= 90 ? "#d97706" : "#dc2626", sub: r >= 99 ? "EXCELLENT" : r >= 90 ? "DEGRADED" : "CRITICAL" });
  }
  if (perfMatrix?.resource?.shuffle_write_gb !== undefined) {
    const sh = perfMatrix.resource.shuffle_write_gb;
    kpis.push({ label: "Shuffle", value: `${sh} GB`, color: sh > 100 ? "#dc2626" : sh > 50 ? "#d97706" : COLOR.textPrimary, sub: sh > 100 ? "VERY HIGH" : sh > 50 ? "HIGH" : "NORMAL" });
  }
  if (execSum?.total_duration_ms !== undefined) {
    kpis.push({ label: "Duration", value: `${(execSum.total_duration_ms / 1000).toFixed(1)}s`, color: COLOR.textPrimary });
  }

  if (kpis.length === 0) return null;

  return (
    <Card style={{ display: "flex", overflow: "hidden", marginBottom: 16 }}>
      {kpis.map((k, i) => (
        <div key={i} style={{ flex: 1, textAlign: "center", padding: "14px 8px", borderRight: i < kpis.length - 1 ? `1px solid ${COLOR.border}` : "none" }}>
          <div style={{ fontSize: 17, fontWeight: 700, color: k.color, letterSpacing: -0.5 }}>{k.value}</div>
          <div style={{ fontSize: 11, color: COLOR.textMuted, marginTop: 2 }}>{k.label}</div>
          {k.sub && <div style={{ fontSize: 9, fontWeight: 700, color: k.color, marginTop: 3, letterSpacing: 0.5, textTransform: "uppercase" }}>{k.sub}</div>}
        </div>
      ))}
    </Card>
  );
}


// ── Executive Summary renderer ────────────────────────────────────────────────


function ExecutiveSummary({ raw }: { raw: string }) {
  const parsed = parseSummary(raw);

  return (
    <Card style={{ borderLeft: `3px solid ${COLOR.blue}`, overflow: "hidden" }}>
      {/* Intro paragraph */}
      <div style={{
        display: "flex", gap: 12, alignItems: "flex-start",
        padding: "14px 16px",
        borderBottom: parsed.sections.length > 0 ? `1px solid ${COLOR.borderMuted}` : "none",
      }}>
        <div style={{
          width: 22, height: 22, borderRadius: 999,
          background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, fontSize: 12, color: COLOR.blue, marginTop: 1,
        }}>
          OK
        </div>
        <p style={{ margin: 0, lineHeight: 1.7, fontSize: 13, color: "#374151" }}>
          {parsed.intro}
        </p>
      </div>

      {/* Named sections (Data Flow, Key Operations, Observations, etc.) */}
      {parsed.sections.map((sec, si) => (
        <div
          key={si}
          style={{
            padding: "12px 16px",
            borderBottom: si < parsed.sections.length - 1 ? `1px solid ${COLOR.borderMuted}` : "none",
            background: si % 2 === 0 ? COLOR.surface : COLOR.bg,
          }}
        >
          {/* Section heading pill */}
          <div style={{
            fontSize: 11, fontWeight: 700, color: COLOR.blue,
            textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 8,
          }}>
            {sec.heading}
          </div>

          {/* Bullet / stage items */}
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {sec.items.map((item, ii) => {
              const stageMatch = item.match(/^(Stage\s*\d+)/i);
              const numMatch   = item.match(/^(\d+)\.\s*(Stage\s*\d+)/i);
              const isStage    = !!(stageMatch || numMatch);
              const displayText = item.replace(/^\d+\.\s*/, "");

              return (
                <div key={ii} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  {isStage ? (
                    <span style={{
                      flexShrink: 0, minWidth: 20, height: 20,
                      background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`,
                      borderRadius: 5, display: "inline-flex", alignItems: "center",
                      justifyContent: "center", fontSize: 10, fontWeight: 700,
                      color: COLOR.blue, marginTop: 1,
                    }}>
                      {(item.match(/\d+/) || ["·"])[0]}
                    </span>
                  ) : (
                    <span style={{ color: COLOR.textMuted, flexShrink: 0, marginTop: 3, fontSize: 14, lineHeight: 1 }}>·</span>
                  )}
                  <span style={{ fontSize: 13, color: "#374151", lineHeight: 1.65 }}>
                    {renderInline(displayText)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </Card>
  );
}


// ── Severity badge ────────────────────────────────────────────────────────────


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


// ── Severity filter bar ───────────────────────────────────────────────────────
// Uses resolvedSeverity so counts reflect the corrected severity, not raw values.


function SeverityFilterBar({
  findings, active, onChange,
}: {
  findings: Finding[]; active: SeverityFilter; onChange: (v: SeverityFilter) => void;
}) {
  const counts: Record<string, number> = { all: findings.length };
  for (const f of findings) {
    const s = resolvedSeverity(f);
    counts[s] = (counts[s] || 0) + 1;
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
      <span style={{ fontSize: 11, color: COLOR.textMuted, fontWeight: 600, marginRight: 2 }}>Filter</span>
      {FILTER_OPTIONS.map((opt) => {
        const count    = counts[opt.value] ?? 0;
        const isActive = active === opt.value;
        const sStyle   = opt.value !== "all" ? getSeverityStyle(opt.value) : null;
        if (opt.value !== "all" && count === 0) return null;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            style={{
              padding: "4px 11px", borderRadius: 6,
              border: isActive ? `1.5px solid ${sStyle?.badge ?? COLOR.blue}` : `1px solid ${COLOR.border}`,
              background: isActive ? (sStyle?.bg ?? COLOR.blueBg) : COLOR.surface,
              color: isActive ? (sStyle?.text ?? COLOR.blue) : COLOR.textSecond,
              fontWeight: isActive ? 700 : 500, fontSize: 12, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 6, transition: "all 0.12s",
            }}
          >
            {opt.label}
            <span style={{
              minWidth: 17, height: 17,
              background: isActive ? (sStyle?.badge ?? COLOR.blue) : COLOR.borderMuted,
              color: isActive ? "#fff" : COLOR.textMuted,
              borderRadius: 4, display: "inline-flex", alignItems: "center",
              justifyContent: "center", fontSize: 10, fontWeight: 700,
            }}>
              {opt.value === "all" ? findings.length : count}
            </span>
          </button>
        );
      })}
    </div>
  );
}


// ── Finding card ──────────────────────────────────────────────────────────────
// Three changes vs original:
//   1. Uses resolvedSeverity() — no false CRITICAL on generic-titled cards
//   2. Labeled rows (Symptom/Root Cause/Impact) render in a two-column layout
//   3. f.recommendation renders in a green FIX block, never red


function FindingCard({ f, idx }: { f: Finding; idx: number }) {
  const sev = resolvedSeverity(f);
  const sc  = getSeverityStyle(sev);

  const bodyLines = (f.description || "")
    .split("\n")
    .map(l => l.trim())
    .filter(Boolean);

  // Use labeled layout when every non-empty line has a "Label: value" shape
  const isLabeled = bodyLines.length > 0 && bodyLines.every(l => LABELED_ROW_PATTERN.test(l));

  return (
    <div style={{
      borderRadius: 8, overflow: "hidden",
      border: `1px solid ${sc.border}`,
      borderLeft: `3px solid ${sc.badge}`,
    }}>

      {/* ── Title row + severity badge ── */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "10px 14px",
        background: sc.bg,
        borderBottom: bodyLines.length > 0 ? `1px solid ${sc.border}` : "none",
      }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: COLOR.textPrimary, lineHeight: 1.4 }}>
          {f.title || f.finding_type || `Finding ${idx + 1}`}
        </div>
        <SeverityBadge severity={sev} />
      </div>

      {/* ── Description body ── */}
      {bodyLines.length > 0 && (
        <div style={{ padding: "10px 14px", background: COLOR.surface }}>
          {isLabeled ? (
            // Two-column labeled layout: "Symptom │ value"
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {bodyLines.map((line, i) => {
                const m = line.match(LABELED_ROW_PATTERN);
                if (m) {
                  return (
                    <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start", fontSize: 12 }}>
                      <span style={{
                        minWidth: 90, fontWeight: 600, color: COLOR.textSecond,
                        flexShrink: 0, paddingTop: 1, textAlign: "right",
                      }}>
                        {m[1]}
                      </span>
                      <span style={{
                        flex: 1, color: "#374151", lineHeight: 1.55,
                        borderLeft: `2px solid ${COLOR.borderMuted}`, paddingLeft: 10,
                      }}>
                        {renderInline(m[2])}
                      </span>
                    </div>
                  );
                }
                return (
                  <div key={i} style={{ fontSize: 12, color: "#374151", lineHeight: 1.55 }}>
                    {renderInline(line)}
                  </div>
                );
              })}
            </div>
          ) : (
            // Prose / bullet layout
            <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.65 }}>
              {renderMarkdown(f.description || "")}
            </div>
          )}
        </div>
      )}

      {/* ── Recommended Fix — always green, visually separated ── */}
      {f.recommendation && (
        <div style={{
          padding: "10px 14px",
          background: "#f0fdf4",
          borderTop: "1px solid #bbf7d0",
          display: "flex", gap: 10, alignItems: "flex-start",
        }}>
          <div style={{
            minWidth: 34, height: 20,
            background: "#16a34a", color: "#fff",
            borderRadius: 4, fontSize: 10, fontWeight: 700,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0, letterSpacing: 0.3,
          }}>
            FIX
          </div>
          <div style={{ flex: 1, fontSize: 12, color: "#166534", lineHeight: 1.6 }}>
            {renderMarkdown(f.recommendation)}
          </div>
        </div>
      )}
    </div>
  );
}


// ── Agents footer ─────────────────────────────────────────────────────────────


function AgentsFooter({ data }: { data: any }) {
  if (!data.agents_used?.length) return null;
  return (
    <Card style={{ padding: "10px 16px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span style={{ fontSize: 11, color: COLOR.textMuted, fontWeight: 600 }}>Agents</span>
      {data.agents_used.map((a: string, i: number) => (
        <span key={i} style={{ padding: "2px 9px", borderRadius: 5, fontSize: 11, fontWeight: 500, background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`, color: COLOR.blue }}>
          {a}
        </span>
      ))}
      {data.total_processing_time_ms > 0 && (
        <span style={{ marginLeft: "auto", fontSize: 11, color: COLOR.textMuted }}>
          {(data.total_processing_time_ms / 1000).toFixed(2)}s
        </span>
      )}
    </Card>
  );
}


// ── Analyzer strip ────────────────────────────────────────────────────────────


const ANALYZER_META: Record<string, { label: string; icon: string }> = {
  log_analysis:    { label: "Log Analyzer",    icon: "[LOG]" },
  code_analysis:   { label: "Code Analyzer",   icon: "[CODE]" },
  data_analysis:   { label: "Data Profiler",   icon: "[DATA]" },
  change_analysis: { label: "Change Analyzer", icon: "[CHG]" },
  infra_analysis:  { label: "Infra Analyzer",   icon: "[INFRA]" },
};

function AnalyzerStrip({ issueProfile }: { issueProfile: IssueProfileT }) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const analyzers: { key: string; result: AnalysisResultT }[] = (
    [
      { key: "log_analysis",    result: issueProfile.log_analysis },
      { key: "code_analysis",   result: issueProfile.code_analysis },
      { key: "data_analysis",   result: issueProfile.data_analysis },
      { key: "change_analysis", result: issueProfile.change_analysis },
      { key: "infra_analysis",  result: issueProfile.infra_analysis },
    ] as { key: string; result: AnalysisResultT | null }[]
  ).filter((a): a is { key: string; result: AnalysisResultT } => a.result != null);

  if (analyzers.length === 0) return null;

  return (
    <Card style={{ marginBottom: 16, overflow: "hidden" }}>
      {/* Header label */}
      <div style={{
        padding: "8px 16px 7px",
        borderBottom: `1px solid ${COLOR.borderMuted}`,
        display: "flex", alignItems: "center", gap: 6,
      }}>
        <span style={{
          fontSize: 10, fontWeight: 700, color: COLOR.textMuted,
          textTransform: "uppercase", letterSpacing: 1,
        }}>
          Analyzers
        </span>
        <span style={{
          fontSize: 10, color: COLOR.textMuted, background: COLOR.borderMuted,
          borderRadius: 4, padding: "1px 7px", fontWeight: 600,
        }}>
          {analyzers.length}
        </span>
      </div>

      {/* One column per active analyzer */}
      <div style={{ display: "flex", flexWrap: "wrap" }}>
        {analyzers.map(({ key, result }, i) => {
          const m      = getLogStatusMeta(result.problem_type);
          const meta   = ANALYZER_META[key] ?? { label: key, icon: "—" };
          const isOpen = expandedKey === key;
          const hColor = result.health_score >= 80 ? "#16a34a"
            : result.health_score >= 60 ? "#d97706" : "#dc2626";

          return (
            <div
              key={key}
              style={{
                flex: "1 1 180px", minWidth: 160,
                borderRight: i < analyzers.length - 1 ? `1px solid ${COLOR.border}` : "none",
              }}
            >
              {/* Header button */}
              <button
                onClick={() => setExpandedKey(isOpen ? null : key)}
                style={{
                  width: "100%", background: "transparent", border: "none",
                  padding: "11px 16px", cursor: "pointer", textAlign: "left",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 5 }}>
                  <span style={{ fontSize: 12, lineHeight: 1 }}>{meta.icon}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: COLOR.textPrimary, flex: 1 }}>
                    {meta.label}
                  </span>
                  <span style={{ fontSize: 10, color: isOpen ? COLOR.blue : COLOR.textMuted }}>
                    {isOpen ? "▾" : "▸"}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    padding: "2px 8px", borderRadius: 5, fontSize: 10, fontWeight: 700,
                    background: m.bg, border: `1px solid ${m.border}`, color: m.text,
                    textTransform: "uppercase", letterSpacing: 0.4,
                  }}>
                    {result.problem_type.replace(/_/g, " ")}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: hColor }}>
                    {Math.round(result.health_score)}/100
                  </span>
                </div>
              </button>

              {/* Expanded findings */}
              {isOpen && (
                <div style={{
                  borderTop: `1px solid ${COLOR.borderMuted}`,
                  background: COLOR.bg,
                  padding: "8px 14px 12px",
                }}>
                  {(result.findings ?? []).length === 0 ? (
                    <div style={{ fontSize: 11, color: COLOR.textMuted, fontStyle: "italic", padding: "4px 0" }}>
                      No findings.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {(result.findings ?? []).slice(0, 5).map((f, fi) => {
                        const sev = resolvedSeverity(f);
                        const sc  = getSeverityStyle(sev);
                        return (
                          <div key={fi} style={{
                            padding: "7px 10px", borderRadius: 6,
                            background: sc.bg, border: `1px solid ${sc.border}`,
                            borderLeft: `3px solid ${sc.badge}`,
                          }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: f.description ? 3 : 0 }}>
                              <span style={{ fontSize: 12, fontWeight: 600, color: COLOR.textPrimary, flex: 1 }}>
                                {f.title || f.finding_type || `Finding ${fi + 1}`}
                              </span>
                              <SeverityBadge severity={sev} />
                            </div>
                            {f.description && (
                              <div style={{ fontSize: 11, color: COLOR.textSecond, lineHeight: 1.5 }}>
                                {f.description.length > 160
                                  ? f.description.slice(0, 160) + "…"
                                  : f.description}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {(result.findings ?? []).length > 5 && (
                        <div style={{ fontSize: 11, color: COLOR.textMuted, textAlign: "center", paddingTop: 4 }}>
                          +{result.findings.length - 5} more findings
                        </div>
                      )}
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


// ── Prioritized fixes section ────────────────────────────────────────────────


const EFFORT_COLOR: Record<string, string> = {
  low:    "#16a34a",
  medium: "#d97706",
  high:   "#dc2626",
};

function PrioritizedFixesSection({ fixes }: { fixes: Fix[] }) {
  const [open, setOpen] = useState(true);
  if (!fixes || fixes.length === 0) return null;

  return (
    <div style={{ marginBottom: 20 }}>
      <SectionToggleHeader
        title="Prioritized Fixes"
        count={fixes.length}
        open={open}
        onToggle={() => setOpen(!open)}
      />
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {fixes
            .slice()
            .sort((a, b) => a.priority - b.priority)
            .map((fix, i) => {
              const effortColor = EFFORT_COLOR[fix.effort?.toLowerCase()] ?? COLOR.textMuted;
              return (
                <Card
                  key={fix.fix_id || i}
                  style={{ overflow: "hidden", borderLeft: `3px solid ${COLOR.blue}` }}
                >
                  {/* Title row */}
                  <div
                    style={{
                      display: "flex", justifyContent: "space-between",
                      alignItems: "center", gap: 12,
                      padding: "10px 14px",
                      background: COLOR.blueBg,
                      borderBottom: `1px solid ${COLOR.blueBorder}`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{
                        minWidth: 24, height: 24,
                        background: COLOR.blue, color: "#fff",
                        borderRadius: 6, fontWeight: 700, fontSize: 12,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        flexShrink: 0,
                      }}>
                        {fix.priority}
                      </div>
                      <span style={{ fontWeight: 600, fontSize: 13, color: COLOR.textPrimary }}>
                        {fix.title}
                      </span>
                    </div>
                    <span style={{
                      padding: "2px 9px", borderRadius: 5,
                      fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                      background: "transparent",
                      border: `1px solid ${effortColor}`,
                      color: effortColor, letterSpacing: 0.5,
                    }}>
                      {fix.effort} effort
                    </span>
                  </div>

                  {/* Description */}
                  <div style={{ padding: "10px 14px", fontSize: 13, color: "#374151", lineHeight: 1.65 }}>
                    {renderMarkdown(fix.description)}
                  </div>

                  {/* Code snippet */}
                  {fix.code_snippet && (
                    <div style={{
                      padding: "8px 14px",
                      background: "#1e1e2e", color: "#cdd6f4",
                      fontFamily: "monospace", fontSize: 11, lineHeight: 1.6,
                      borderTop: `1px solid ${COLOR.borderMuted}`,
                      whiteSpace: "pre-wrap", overflowX: "auto",
                    }}>
                      {fix.code_snippet}
                    </div>
                  )}

                  {/* Applies-to agents */}
                  {(fix.applies_to_agents ?? []).length > 0 && (
                    <div style={{
                      padding: "7px 14px",
                      background: COLOR.surface,
                      borderTop: `1px solid ${COLOR.borderMuted}`,
                      display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
                    }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 0.5, marginRight: 4 }}>
                        Resolves
                      </span>
                      {fix.applies_to_agents.map((a, ai) => (
                        <span key={ai} style={{
                          padding: "2px 9px", borderRadius: 5, fontSize: 10, fontWeight: 600,
                          background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`, color: COLOR.blue,
                        }}>
                          {a.replace(/_/g, " ")}
                        </span>
                      ))}
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


// ── Correlations section ──────────────────────────────────────────────────────


function CorrelationsSection({ correlations }: { correlations: CrossAgentCorrelationT[] }) {
  const [open, setOpen] = useState(true);
  if (!correlations || correlations.length === 0) return null;

  return (
    <div style={{ marginBottom: 20 }}>
      <SectionToggleHeader
        title="Correlations"
        count={correlations.length}
        open={open}
        onToggle={() => setOpen(!open)}
      />
      {open && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {correlations.map((c, i) => {
            const sev = (c.severity || "info").toLowerCase();
            const sc  = getSeverityStyle(sev);
            const conf = c.confidence <= 1 ? Math.round(c.confidence * 100) : Math.round(c.confidence);
            return (
              <div key={c.correlation_id || i} style={{
                borderRadius: 8, overflow: "hidden",
                border:     `1px solid ${sc.border}`,
                borderLeft: `3px solid ${sc.badge}`,
              }}>
                {/* Pattern text + severity badge */}
                <div style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "flex-start", gap: 12,
                  padding: "10px 14px", background: sc.bg,
                }}>
                  <p style={{ margin: 0, fontSize: 13, color: COLOR.textPrimary, lineHeight: 1.6, flex: 1 }}>
                    {c.pattern}
                  </p>
                  <SeverityBadge severity={sev} />
                </div>
                {/* Contributing agents + confidence */}
                <div style={{
                  padding: "7px 14px", background: COLOR.surface,
                  borderTop: `1px solid ${sc.border}`,
                  display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap",
                }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, color: COLOR.textMuted,
                    textTransform: "uppercase", letterSpacing: 0.6, marginRight: 4,
                  }}>
                    Agents
                  </span>
                  {(c.contributing_agents ?? []).map((a, ai) => (
                    <span key={ai} style={{
                      padding: "2px 9px", borderRadius: 5,
                      fontSize: 10, fontWeight: 600,
                      background: COLOR.blueBg, border: `1px solid ${COLOR.blueBorder}`, color: COLOR.blue,
                    }}>
                      {a.replace(/_/g, " ")}
                    </span>
                  ))}
                  <span style={{ marginLeft: "auto", fontSize: 11, color: COLOR.textMuted }}>
                    {conf}% confidence
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ── Run RCA control panel ────────────────────────────────────────────────────
// Renders the query input, scenario picker and submit button.
// Kept as a pure presentational block so it can be read top-to-bottom.


const SCENARIO_OPTIONS: { value: ScenarioKey; label: string }[] = [
  { value: "spark_failure",   label: "Spark Failure"                },
  { value: "airflow_failure", label: "Airflow Failure"              },
  { value: "data_null_spike", label: "Data Null Spike"              },
  { value: "infra_pressure",  label: "Infra Pressure"               },
  { value: "demo_incident",   label: "Demo Incident (Real Logs)" },
];


// ── Main Component ────────────────────────────────────────────────────────────


export default function RCAFindings({ orchestratorData }: RCAFindingsProps) {
  // ── Filter / collapse state (unchanged) ────────────────────────────────────
  const [severityFilter,      setSeverityFilter]      = useState<SeverityFilter>("all");
  const [showFindings,        setShowFindings]        = useState(true);
  const [showRecommendations, setShowRecommendations] = useState(true);

  // ── Live RCA state ─────────────────────────────────────────────────────────
  const [loading,     setLoading]     = useState(false);
  const [rcaError,    setRcaError]    = useState<string | null>(null);
  const [liveReport,  setLiveReport]  = useState<RecommendationReport | null>(null);
  const [userQuery,   setUserQuery]   = useState("Why did my job fail?");
  const [scenario,    setScenario]    = useState<ScenarioKey>("spark_failure");

  // ── Demo Incident checkbox state (only used when scenario === "demo_incident") ─
  const [includeChecks, setIncludeChecks] = useState({
    spark:   true,
    airflow: true,
    data:    true,
    infra:   true,
    change:  false,
  });

  // ── HandleRunRCA ────────────────────────────────────────────────────────────
  const handleRunRCA = async () => {
    setLoading(true);
    setRcaError(null);
    setLiveReport(null);
    try {
      let res: Response;

      if (FROM_LOGS_SCENARIOS.has(scenario)) {
        // Demo Incident path — use real fixture logs via /api/run_rca_from_logs
        const body = {
          scenario:   "demo_ohlcv_pipeline",
          include:    includeChecks,
          user_query: userQuery,
        };
        res = await fetch("/api/run_rca_from_logs", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify(body),
        });
      } else {
        // Hard-coded fingerprint path — use /api/run_rca
        const demo = DEMO_SCENARIOS[scenario];
        const body = { user_query: userQuery, ...demo.payload };
        res = await fetch("/api/run_rca", {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify(body),
        });
      }

      if (!res.ok) {
        const msg = await res.text().catch(() => `HTTP ${res.status}`);
        throw new Error(`RCA request failed (${res.status}): ${msg.slice(0, 300)}`);
      }
      // Read body as text first so a mis-routed HTML page (e.g. the Vite SPA
      // fallback) shows a readable error rather than "Unexpected token '<'".
      const text = await res.text();
      let data: RecommendationReport;
      try {
        data = JSON.parse(text);
      } catch {
        throw new Error(
          `Backend returned non-JSON response. ` +
          `Check that the FastAPI server is running and the Vite proxy is ` +
          `forwarding /api/run_rca* to http://127.0.0.1:8000.\n\n` +
          `First 200 chars: ${text.slice(0, 200)}`
        );
      }
      setLiveReport(data);
    } catch (e: any) {
      setRcaError(e?.message ?? String(e));
    } finally {
      setLoading(false);
    }
  };

  // ── Effective data: live API result takes priority over static artifact ─────
  const effectiveData: any = liveReport ?? orchestratorData;

  // ── Detect new RecommendationReport format (has issue_profile) ─────────────
  const issueProfile: IssueProfileT | null = effectiveData?.issue_profile ?? null;

  // ── Prioritized fixes: use typed Fix[] from live report, fallback to mapped strings
  const prioritizedFixes: Fix[] = liveReport?.prioritized_fixes ?? [];

  // ── Executive summary / findings / recommendations ─────────────────────────
  const summary: string =
    effectiveData?.executive_summary ||
    effectiveData?.summary           ||
    issueProfile?.log_analysis?.executive_summary ||
    "";

  const recommendations: string[] =
    effectiveData?.recommendations ||
    ((effectiveData?.prioritized_fixes ?? []) as any[])
      .map((f: any) => `[${f.title}] ${f.description}`) ||
    [];

  const structFindings: Finding[] =
    effectiveData?.findings            ||
    issueProfile?.log_analysis?.findings ||
    [];

  const keyFindings: string[] = effectiveData?.key_findings || [];

  // ── Problem type: prefer log_analysis so LogStatusCard maps correctly ──────
  const problemType: string =
    issueProfile?.log_analysis?.problem_type ||
    issueProfile?.dominant_problem_type      ||
    effectiveData?.problem_type              ||
    "unknown";

  // ── Confidence: issue_profile uses 0-1 → formatConfidence normalises both ─
  const confidence: number = issueProfile
    ? formatConfidence(issueProfile.overall_confidence)
    : formatConfidence(effectiveData?.confidence ?? 0);

  // ── Health score: prefer issue_profile overall, fallback to nested path ───
  const healthScore: number | null =
    issueProfile?.overall_health_score ??
    effectiveData?.raw_agent_responses?.root_cause?.metadata?.health_score?.overall_score ??
    null;

  const breakdown: Record<string, number> =
    effectiveData?.raw_agent_responses?.root_cause?.metadata?.health_score?.breakdown ?? {};

  const agentsUsed: string[] =
    effectiveData?.agents_used || issueProfile?.agents_invoked || [];

  const totalTimeSec =
    effectiveData?.total_processing_time_ms != null
      ? (effectiveData.total_processing_time_ms / 1000).toFixed(2)
      : null;

  const filteredFindings = structFindings
    .filter(f => severityFilter === "all" || resolvedSeverity(f) === severityFilter)
    .sort((a, b) =>
      (SEVERITY_ORDER[resolvedSeverity(a)] ?? 4) -
      (SEVERITY_ORDER[resolvedSeverity(b)] ?? 4)
    );

  return (
    <div style={{
      padding: "24px 28px", maxWidth: 1000,
      fontFamily: "Segoe UI, system-ui, -apple-system, Arial, sans-serif",
      color: COLOR.textPrimary, fontSize: 13,
    }}>

      {/* ══ Run RCA control panel ══════════════════════════════════════════════ */}
      <Card style={{ marginBottom: 20, padding: "16px 18px" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: COLOR.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
          Run RCA
        </div>

        {/* Row 1: query + scenario + button */}
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          {/* User query */}
          <div style={{ flex: 3, minWidth: 200 }}>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: COLOR.textSecond, marginBottom: 4 }}>
              Query
            </label>
            <input
              type="text"
              value={userQuery}
              onChange={e => setUserQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !loading && handleRunRCA()}
              disabled={loading}
              placeholder="Describe the problem…"
              style={{
                width: "100%", padding: "7px 10px",
                border: `1px solid ${COLOR.border}`, borderRadius: 7,
                fontSize: 13, color: COLOR.textPrimary,
                background: loading ? COLOR.bg : COLOR.surface,
                outline: "none", boxSizing: "border-box",
              }}
            />
          </div>

          {/* Scenario */}
          <div style={{ flex: 1, minWidth: 160 }}>
            <label style={{ display: "block", fontSize: 11, fontWeight: 600, color: COLOR.textSecond, marginBottom: 4 }}>
              Scenario
            </label>
            <select
              value={scenario}
              onChange={e => {
                const key = e.target.value as ScenarioKey;
                setScenario(key);
                setUserQuery(DEMO_SCENARIOS[key].defaultQuery);
              }}
              disabled={loading}
              style={{
                width: "100%", padding: "7px 10px",
                border: `1px solid ${COLOR.border}`, borderRadius: 7,
                fontSize: 13, color: COLOR.textPrimary,
                background: loading ? COLOR.bg : COLOR.surface,
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {SCENARIO_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Submit */}
          <button
            onClick={handleRunRCA}
            disabled={loading}
            style={{
              padding: "8px 22px", borderRadius: 7, border: "none",
              background: loading ? COLOR.blueBg : COLOR.blue,
              color: loading ? COLOR.blue : "#fff",
              fontWeight: 700, fontSize: 13, cursor: loading ? "not-allowed" : "pointer",
              whiteSpace: "nowrap", transition: "background 0.15s",
              display: "flex", alignItems: "center", gap: 8,
            }}
          >
            {loading ? (
              <>
                <span style={{
                  display: "inline-block", width: 13, height: 13,
                  border: `2px solid ${COLOR.blue}`, borderTopColor: "transparent",
                  borderRadius: "50%",
                  animation: "spin 0.7s linear infinite",
                }} />
                Running…
              </>
            ) : "Run RCA"}
          </button>
        </div>

        {/* Row 2: signal-source checkboxes (only visible for Demo Incident scenario) */}
        {scenario === "demo_incident" && (
          <div style={{ marginTop: 10, display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: COLOR.textSecond }}>Include:</span>
            {([
              { key: "spark",   label: "Spark" },
              { key: "airflow", label: "Airflow" },
              { key: "data",    label: "Data Quality" },
              { key: "infra",   label: "Infra" },
              { key: "change",  label: "Git / Change" },
            ] as const).map(({ key, label }) => (
              <label key={key} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12,
                color: COLOR.textPrimary, cursor: loading ? "not-allowed" : "pointer" }}>
                <input
                  type="checkbox"
                  checked={includeChecks[key]}
                  disabled={loading}
                  onChange={e => setIncludeChecks(prev => ({ ...prev, [key]: e.target.checked }))}
                  style={{ cursor: loading ? "not-allowed" : "pointer" }}
                />
                {label}
              </label>
            ))}
          </div>
        )}

        {/* Spinning keyframe (injected once) */}
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

        {/* Error banner */}
        {rcaError && (
          <div style={{
            marginTop: 12, padding: "10px 14px",
            background: COLOR.critical.bg, border: `1px solid ${COLOR.critical.border}`,
            borderRadius: 7, fontSize: 12, color: COLOR.critical.text,
            display: "flex", alignItems: "flex-start", gap: 8,
          }}>
            <span style={{ flexShrink: 0, fontWeight: 700 }}>X</span>
            <span>{rcaError}</span>
          </div>
        )}
      </Card>

      {/* ── Loading indicator ── */}
      {loading && (
        <div style={{
          padding: "40px 20px", textAlign: "center",
          color: COLOR.blue, fontSize: 13, fontWeight: 600,
          border: `1px dashed ${COLOR.blueBorder}`, borderRadius: 10,
          background: COLOR.blueBg, marginBottom: 20,
        }}>
          <div style={{
            width: 32, height: 32, margin: "0 auto 12px",
            border: `3px solid ${COLOR.blueBorder}`, borderTopColor: COLOR.blue,
            borderRadius: "50%", animation: "spin 0.7s linear infinite",
          }} />
          Running RCA analysis…
        </div>
      )}

      {/* ── Placeholder when neither live report nor static artifact is available ── */}
      {!loading && !effectiveData && (
        <div style={{
          padding: "60px 20px", textAlign: "center",
          color: COLOR.textMuted, fontSize: 13,
          border: `1px dashed ${COLOR.border}`, borderRadius: 10,
          background: COLOR.bg,
        }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>[RCA]</div>
          <div style={{ fontWeight: 600, color: COLOR.textSecond, marginBottom: 6 }}>Run RCA to see results</div>
          <div style={{ fontSize: 12 }}>Select a scenario above, then click <strong>Run RCA</strong>.</div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════════════════
          Results — only rendered when effectiveData is available
      ══════════════════════════════════════════════════════════════════════════ */}
      {effectiveData && !loading && (<>

      {/* ── Top metric cards ── */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <LogStatusCard  problemType={problemType} />
        <ConfidenceCard value={confidence} />
        {healthScore !== null && <HealthGaugeCard score={Math.round(healthScore)} />}
      </div>

      {/* ── Score penalty breakdown ── */}
      <ScoreBreakdownBar breakdown={breakdown} />

      {/* ── KPI strip ── */}
      <KPIStrip data={orchestratorData} />

      {/* ── Analyzer strip (new analyzers: log, code, data, change) ── */}
      {issueProfile && <AnalyzerStrip issueProfile={issueProfile} />}

      {/* ── Agents top bar ── */}
      {agentsUsed.length > 0 && (
        <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: COLOR.textMuted }}>Agents</span>
          {agentsUsed.map((a, i) => (
            <span key={i} style={{ padding: "2px 8px", borderRadius: 999, border: `1px solid ${COLOR.border}`, background: COLOR.surface, fontSize: 11, color: COLOR.textSecond }}>
              {a}
            </span>
          ))}
          {totalTimeSec && (
            <span style={{ marginLeft: "auto", fontSize: 11, color: COLOR.textMuted }}>
              Total processing: {totalTimeSec}s
            </span>
          )}
        </div>
      )}

      {/* ── Executive summary ── */}
      {summary && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: COLOR.textPrimary, marginBottom: 10 }}>
            Executive Summary
          </div>
          <ExecutiveSummary raw={summary} />
        </div>
      )}

      {/* ── Cross-agent correlations ── */}
      {issueProfile && issueProfile.correlations?.length > 0 && (
        <CorrelationsSection correlations={issueProfile.correlations} />
      )}

      {/* ── Prioritized fixes (live report only) ── */}
      {prioritizedFixes.length > 0 && (
        <PrioritizedFixesSection fixes={prioritizedFixes} />
      )}

      {/* ── Structured findings (collapsible + filter) ── */}
      {structFindings.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <SectionToggleHeader
            title="Findings"
            count={structFindings.length}
            open={showFindings}
            onToggle={() => setShowFindings(!showFindings)}
          />
          {showFindings && (
            <>
              <SeverityFilterBar
                findings={structFindings}
                active={severityFilter}
                onChange={setSeverityFilter}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {filteredFindings.length > 0
                  ? filteredFindings.map((f, idx) => <FindingCard key={idx} f={f} idx={idx} />)
                  : (
                    <div style={{ padding: "28px 20px", textAlign: "center", color: COLOR.textMuted, fontSize: 13, background: COLOR.bg, border: `1px dashed ${COLOR.border}`, borderRadius: 8 }}>
                      No findings match this filter.
                    </div>
                  )
                }
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Key findings fallback (when no structured findings) ── */}
      {keyFindings.length > 0 && structFindings.length === 0 && (
        <div style={{ marginBottom: 20 }}>
          <SectionHeader title="Key Findings" count={keyFindings.length} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {keyFindings.map((f, idx) => (
              <Card key={idx} style={{ padding: "12px 16px", borderLeft: `3px solid ${COLOR.blue}`, fontSize: 13, color: "#374151", lineHeight: 1.65 }}>
                {renderMarkdown(f)}
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ── Recommendations (collapsible) ── */}
      {recommendations.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <SectionToggleHeader
            title="Recommendations"
            count={recommendations.length}
            open={showRecommendations}
            onToggle={() => setShowRecommendations(!showRecommendations)}
          />
          {showRecommendations && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {recommendations.map((rec, idx) => (
                <Card key={idx} style={{ padding: "13px 16px", display: "flex", gap: 14 }}>
                  <div style={{ minWidth: 24, height: 24, background: COLOR.blue, color: "#fff", borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 11, flexShrink: 0 }}>
                    {idx + 1}
                  </div>
                  <div style={{ flex: 1, lineHeight: 1.7, color: "#374151" }}>
                    {renderMarkdown(rec)}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Agents footer ── */}
      <AgentsFooter data={effectiveData} />

      {/* close the effectiveData guard */}
      </>)}
    </div>
  );
}
