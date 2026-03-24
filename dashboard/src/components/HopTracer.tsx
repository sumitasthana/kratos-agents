import React, { useMemo, useState } from 'react';
import type { PhaseStep, HopNode } from '../types';

// ── Phase pipeline metadata ────────────────────────────────────────────────

const PHASE_META: Record<string, { icon: string; agent: string; shortLabel: string }> = {
  INTAKE:        { icon: '⬡', agent: 'IntakeAgent',    shortLabel: 'Intake'   },
  LOGS_FIRST:    { icon: '◎', agent: 'EvidenceAgent',  shortLabel: 'Log Scan' },
  ROUTE:         { icon: '⇢', agent: 'RoutingAgent',   shortLabel: 'Route'    },
  BACKTRACK:     { icon: '⟳', agent: 'BacktrackAgent', shortLabel: 'Backtrack'},
  INCIDENT_CARD: { icon: '⊞', agent: 'IncidentAgent',  shortLabel: 'Incident' },
  RECOMMEND:     { icon: '⊕', agent: 'RecommendAgent', shortLabel: 'Recommend'},
  PERSIST:       { icon: '✓', agent: 'RankerAgent',    shortLabel: 'Persist'  },
};

const PHASES_ORDER = [
  'INTAKE', 'LOGS_FIRST', 'ROUTE', 'BACKTRACK',
  'INCIDENT_CARD', 'RECOMMEND', 'PERSIST',
] as const;

// ── Node metadata ──────────────────────────────────────────────────────────

interface NodeMeta { label: string; name: string; color: string }

const NODE_META: Record<string, NodeMeta> = {
  'INC-001': { label: 'Incident', name: 'overstated_coverage',           color: '#ef4444' },
  'INC-002': { label: 'Incident', name: 'irr_misclassified',             color: '#ef4444' },
  'INC-003': { label: 'Incident', name: 'mt202_dropped',                 color: '#ef4444' },
  'CTL-C2':  { label: 'Control',  name: 'Coverage Accuracy C2',          color: '#f59e0b' },
  'CTL-A3':  { label: 'Control',  name: 'Fiduciary Docs A3',             color: '#f59e0b' },
  'CTL-B1':  { label: 'Control',  name: 'Daily Balance Snapshot B1',     color: '#f59e0b' },
  'RUL-AGG': { label: 'Rule',     name: 'depositor_aggregation',         color: '#a855f7' },
  'RUL-IRR': { label: 'Rule',     name: 'irr_classification',            color: '#a855f7' },
  'RUL-SWF': { label: 'Rule',     name: 'swift_completeness',            color: '#a855f7' },
  'PIP-DIJ': { label: 'Pipeline', name: 'DAILY-INSURANCE-JOB',           color: '#06b6d4' },
  'PIP-TDB': { label: 'Pipeline', name: 'TRUST-DAILY-BATCH',             color: '#06b6d4' },
  'PIP-WNR': { label: 'Pipeline', name: 'WIRE-NIGHTLY-RECON',            color: '#06b6d4' },
  'STP-AGG': { label: 'JobStep',  name: 'AGGRSTEP (DISABLED)',           color: '#f97316' },
  'ART-JCL': { label: 'Artifact', name: 'DAILY-INSURANCE-JOB.jcl:61',   color: '#ef4444' },
  'ART-COB': { label: 'Artifact', name: 'TRUST-INSURANCE-CALC.cob:197',  color: '#ef4444' },
  'ART-BCJ': { label: 'Artifact', name: 'BeneficiaryClassifier.java:58', color: '#ef4444' },
  'MOD-SWP': { label: 'Module',   name: 'swift_parser.parse_message()',  color: '#f97316' },
  'ART-SWP': { label: 'Artifact', name: 'swift_parser.py:87',            color: '#ef4444' },
};

function nodeMeta(id: string): NodeMeta {
  return NODE_META[id] ?? { label: id.split('-')[0] ?? id, name: id, color: '#6b7280' };
}

// ── Defect code snippets ───────────────────────────────────────────────────

interface SnippetLine { n: number; code: string; defect?: boolean }
interface DefectSnippet { file: string; lang: string; defect_id: string; lines: SnippetLine[] }

const DEFECT_SNIPPETS: Record<string, DefectSnippet> = {
  deposit_aggregation_failure: {
    file: 'batch/DAILY-INSURANCE-JOB.jcl',
    lang: 'JCL',
    defect_id: 'DEF-LDS-001',
    lines: [
      { n: 57, code: '//*--- STEP 3: AGGREGATE BY DEPOSITOR+ORC ---' },
      { n: 58, code: '//* BUG: THIS STEP IS COMMENTED OUT. Calculation' },
      { n: 59, code: '//*     runs per-account, not aggregated totals.' },
      { n: 60, code: '//*     Violates 12 CFR § 330.1(b).' },
      { n: 61, code: '//*STEP03   EXEC PGM=IKJEFT01,REGION=64M',      defect: true },
      { n: 62, code: '//*SYSTSPRT DD SYSOUT=*',                        defect: true },
      { n: 63, code: '//*SYSTSIN  DD *',                                defect: true },
      { n: 64, code: '//*  DSN SYSTEM(DB2P)',                           defect: true },
      { n: 65, code: '//*  RUN PROGRAM(DSNTEP2) PLAN(DSNTEP4)',         defect: true },
      { n: 66, code: '//*  END',                                        defect: true },
    ],
  },
  trust_irr_misclassification: {
    file: 'cobol/TRUST-INSURANCE-CALC.cob',
    lang: 'COBOL',
    defect_id: 'DEF-TCS-001',
    lines: [
      { n: 193, code: '       3200-CALC-IRREVOCABLE.' },
      { n: 194, code: '      * Irrevocable Trust — 12 CFR § 330.13' },
      { n: 195, code: '      * Per non-contingent interest per beneficiary' },
      { n: 196, code: '      * BUG: SECTION NOT IMPLEMENTED',                   defect: true },
      { n: 197, code: '      * All IRR falls through to SGL ($250K flat)',       defect: true },
      { n: 199, code: '           COMPUTE WS-CALC-BALANCE =' },
      { n: 200, code: '               TRUST-BALANCE + TRUST-ACCRUED-INT' },
      { n: 206, code: '      * FALLBACK: Apply SGL limit',                       defect: true },
      { n: 222, code: "           MOVE 'SGL'             TO RES-ORC-TYPE",       defect: true },
      { n: 223, code: "           MOVE 'SGL_DEFAULT_BUG' TO RES-CALC-METHOD",    defect: true },
    ],
  },
  wire_mt202_drop: {
    file: 'python/swift_parser.py',
    lang: 'Python',
    defect_id: 'DEF-WTS-001',
    lines: [
      { n: 76, code: 'def parse_swift_message(raw_text: str) -> Optional[WireTransfer]:' },
      { n: 77, code: '    """Parse SWIFT MT103. BUG: MT202/MT202COV dropped."""' },
      { n: 82, code: '    if "{2:O103" in raw_text:' },
      { n: 83, code: '        wire.message_type = "MT103"' },
      { n: 84, code: '    elif "{2:O202" in raw_text:' },
      { n: 85, code: '        wire.message_type = "MT202"' },
      { n: 86, code: '        return None  # BUG: MT202 dropped — no handler', defect: true },
      { n: 87, code: '    else:' },
      { n: 88, code: '        return None  # MT202COV also dropped silently',   defect: true },
    ],
  },
};

// ── Causal chain builder ───────────────────────────────────────────────────

type NodeStatus = 'failed' | 'root_cause' | 'defect';

interface ChainEntry { nodeId: string; relToNext: string | null; status: NodeStatus }

function buildChain(incidentId: string, hopNodes: HopNode[]): ChainEntry[] {
  if (hopNodes.length === 0) {
    return [{ nodeId: incidentId, relToNext: null, status: 'failed' }];
  }
  const items: ChainEntry[] = [];
  items.push({ nodeId: incidentId, relToNext: 'TRIGGERED_BY', status: 'failed' });

  for (let i = 0; i < hopNodes.length; i++) {
    const hop    = hopNodes[i];
    const isLast = i === hopNodes.length - 1;
    if (i === 0) {
      items.push({ nodeId: hop.from_node_id, relToNext: hop.rel_type, status: 'failed' });
    } else {
      items[items.length - 1].relToNext = hop.rel_type;
    }
    items.push({
      nodeId:    hop.to_node_id,
      relToNext: null,
      status:    isLast && hop.status === 'artifact_defect' ? 'defect'
                 : isLast                                   ? 'root_cause'
                 : 'failed',
    });
  }
  // When artifact is the defect, the node before it is the root cause
  const last = items[items.length - 1];
  if (last.status === 'defect' && items.length >= 2) {
    items[items.length - 2].status = 'root_cause';
  }
  return items;
}

// ── Syntax highlighter ─────────────────────────────────────────────────────

function highlight(code: string, lang: string): string {
  const esc = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  if (lang === 'JCL') {
    return esc
      .replace(/(\/\/\*.*)/g, '<span style="color:#6b7280;font-style:italic">$1</span>')
      .replace(/(\/\/\w+)/g, '<span style="color:#60a5fa">$1</span>')
      .replace(/\b(EXEC|PGM|DD|DISP|DSN|REGION)\b/g, '<span style="color:#c084fc">$1</span>');
  }
  if (lang === 'COBOL') {
    return esc
      .replace(/(^\s+\*.*)/gm, '<span style="color:#6b7280;font-style:italic">$1</span>')
      .replace(/\b(COMPUTE|MOVE|PERFORM|IF|ELSE|END-IF|WHEN|EVALUATE)\b/g,
               '<span style="color:#c084fc">$1</span>')
      .replace(/('.*?')/g, '<span style="color:#86efac">$1</span>');
  }
  if (lang === 'Python') {
    return esc
      .replace(/(#.*)/g, '<span style="color:#6b7280;font-style:italic">$1</span>')
      .replace(/\b(def|return|if|elif|else|None|Optional)\b/g,
               '<span style="color:#c084fc">$1</span>')
      .replace(/(".*?")/g, '<span style="color:#86efac">$1</span>');
  }
  return esc;
}

// ── Phase Pipeline ─────────────────────────────────────────────────────────

function PhasePipeline({
  completedPhases,
  activePhase,
  tracing,
}: {
  completedPhases: Set<string>;
  activePhase: string | null;
  tracing: boolean;
}) {
  return (
    <div
      className="flex items-start gap-0 px-5 py-3 border-b flex-shrink-0 overflow-x-auto"
      style={{ background: 'var(--bg-panel)', borderColor: 'var(--border-dim)' }}
    >
      {PHASES_ORDER.map((phase, i) => {
        const meta     = PHASE_META[phase];
        const done     = completedPhases.has(phase);
        const isActive = activePhase === phase && tracing;

        const dotColor  = done ? '#22c55e' : isActive ? '#3b82f6' : '#374151';
        const textColor = done ? 'var(--text-primary)' : isActive ? '#93c5fd' : 'var(--text-dim)';

        return (
          <React.Fragment key={phase}>
            <div className="flex flex-col items-center gap-1 min-w-[72px]">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px]
                             font-bold border-2 transition-all duration-300 ${isActive ? 'pulse' : ''}`}
                style={{
                  background:  done ? `${dotColor}22` : isActive ? '#1d4ed8' : 'var(--bg-code)',
                  borderColor: dotColor,
                  color:       done ? dotColor : isActive ? '#fff' : 'var(--text-dim)',
                }}
              >
                {done ? '✓' : meta.icon}
              </div>
              <span
                className="text-[9px] font-bold tracking-wide text-center leading-tight"
                style={{ color: textColor }}
              >
                {meta.shortLabel}
              </span>
              <span className="text-[8px] text-center leading-tight" style={{ color: 'var(--text-dim)' }}>
                {!done && !isActive ? '—' : meta.agent}
              </span>
            </div>
            {i < PHASES_ORDER.length - 1 && (
              <div
                className="h-px flex-1 mt-3.5 mx-1 transition-colors"
                style={{ background: done ? '#374151' : 'var(--border-dim)', minWidth: 12 }}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ── Chain node row ─────────────────────────────────────────────────────────

function ChainNodeRow({ entry, delay }: { entry: ChainEntry; delay: number }) {
  const meta        = nodeMeta(entry.nodeId);
  const isRootCause = entry.status === 'root_cause';
  const isDefect    = entry.status === 'defect';
  const isSpecial   = isRootCause || isDefect;
  const dotColor    = isDefect ? '#ef4444' : isRootCause ? '#f97316' : meta.color;

  const badge = isDefect
    ? { label: 'CONFIRMED DEFECT', bg: '#7f1d1d', color: '#fca5a5' }
    : isRootCause
    ? { label: 'ROOT CAUSE',       bg: '#431407', color: '#fdba74' }
    : { label: 'CONFIRMED FAILED', bg: '#1a1f2e', color: '#ef4444' };

  return (
    <div className="hop-enter" style={{ animationDelay: `${delay}ms` }}>
      {/* Node row */}
      <div
        className="flex items-center gap-3 rounded-lg px-4 py-2.5 border"
        style={{
          background:  isSpecial ? `${dotColor}11` : 'var(--bg-card)',
          borderColor: isSpecial ? `${dotColor}55` : 'var(--border-dim)',
          boxShadow:   isSpecial ? `0 0 12px ${dotColor}22` : 'none',
        }}
      >
        <span className="text-xs font-bold" style={{ color: dotColor, minWidth: 12 }}>
          {isSpecial ? '◉' : '●'}
        </span>
        <code className="text-[11px] font-mono font-bold min-w-[60px]" style={{ color: dotColor }}>
          {entry.nodeId}
        </code>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wide"
          style={{ background: `${meta.color}22`, color: meta.color }}
        >
          {meta.label}
        </span>
        <span className="text-xs flex-1 font-mono" style={{ color: 'var(--text-primary)' }}>
          {meta.name}
        </span>
        <span
          className="text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-widest"
          style={{ background: badge.bg, color: badge.color }}
        >
          {badge.label}
        </span>
      </div>
      {/* Arrow */}
      {entry.relToNext && (
        <div className="flex items-center gap-2 pl-[52px] py-1">
          <div className="w-px h-4" style={{ background: 'var(--border-dim)' }} />
          <span
            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border uppercase"
            style={{ color: '#60a5fa', borderColor: '#1e3a5f', background: '#0f1f35' }}
          >
            ↓ {entry.relToNext}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Defect code box ────────────────────────────────────────────────────────

function DefectBox({ snippet }: { snippet: DefectSnippet }) {
  return (
    <div
      className="rounded-xl border-2 overflow-hidden hop-enter"
      style={{ borderColor: '#7f1d1d', boxShadow: '0 0 24px rgba(239,68,68,0.15)' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{ background: '#1c0a0a', borderBottom: '1px solid #7f1d1d' }}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold" style={{ color: '#fca5a5' }}>⚑</span>
          <span className="text-[11px] font-mono" style={{ color: '#fca5a5' }}>
            {snippet.file}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-bold px-2 py-0.5 rounded"
            style={{ background: '#7f1d1d', color: '#fca5a5' }}
          >
            {snippet.defect_id}
          </span>
          <span
            className="text-[10px] font-bold px-2 py-0.5 rounded"
            style={{ background: '#0f172a', color: '#60a5fa' }}
          >
            {snippet.lang}
          </span>
        </div>
      </div>

      {/* Code table */}
      <div style={{ background: '#0a0505' }}>
        <table className="w-full border-collapse font-mono text-[11px] leading-relaxed">
          <tbody>
            {snippet.lines.map((line) => (
              <tr key={line.n} style={{ background: line.defect ? 'rgba(239,68,68,0.12)' : 'transparent' }}>
                <td
                  className="select-none px-3 py-0.5 text-right w-[42px]"
                  style={{
                    color:       line.defect ? '#fca5a5' : '#374151',
                    borderRight: `1px solid ${line.defect ? '#7f1d1d' : '#1a2235'}`,
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {line.n}
                </td>
                <td className="px-1.5 w-[20px]" style={{ color: '#ef4444' }}>
                  {line.defect ? '◀' : ''}
                </td>
                <td className="px-3 py-0.5">
                  <code
                    style={{ color: line.defect ? '#fca5a5' : '#8b9ab5' }}
                    dangerouslySetInnerHTML={{ __html: highlight(line.code, snippet.lang) }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div
        className="px-4 py-2"
        style={{ background: '#1c0a0a', borderTop: '1px solid #7f1d1d' }}
      >
        <span className="text-[10px]" style={{ color: '#6b7280' }}>
          Defect confirmed by pattern analysis · FDIC Part 370/330
        </span>
      </div>
    </div>
  );
}

// ── Phase log row ──────────────────────────────────────────────────────────

function formatDetailValue(key: string, val: unknown): string {
  if (key === 'recommendations' && Array.isArray(val)) {
    return `${val.length} action${val.length !== 1 ? 's' : ''} generated`;
  }
  if (key === 'confidence_breakdown' && typeof val === 'object' && val !== null) {
    const bd = val as Record<string, number>;
    const score = bd.composite_score ?? 0;
    return `composite ${Math.round(score * 100)}%`;
  }
  if (Array.isArray(val)) return `[${val.length} items]`;
  if (typeof val === 'object' && val !== null) {
    const s = JSON.stringify(val);
    return s.length > 80 ? s.slice(0, 77) + '...' : s;
  }
  return String(val);
}

function PhaseLogRow({
  phase, expanded, onToggle,
}: {
  phase: PhaseStep;
  expanded: boolean;
  onToggle: () => void;
}) {
  const meta = PHASE_META[phase.phase];
  const ok   = ['OK', 'CONFIRMED', 'SIGNAL_DETECTED'].includes(phase.status);
  const detailEntries = Object.entries(phase.details ?? {}).filter(
    ([k]) => k !== 'hop_nodes' // skip bulky arrays already rendered in chain
  );

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: expanded ? '#3b82f6' : 'var(--border-dim)' }}
    >
      {/* Clickable header */}
      <button
        className="w-full text-left flex items-start gap-3 px-3 py-2"
        style={{ background: expanded ? 'var(--bg-code)' : 'var(--bg-card)' }}
        onClick={onToggle}
      >
        <span className="text-[11px] mt-0.5 flex-shrink-0" style={{ color: ok ? '#22c55e' : '#ef4444' }}>
          {meta?.icon ?? '○'}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-bold uppercase tracking-widest"
              style={{ color: 'var(--text-muted)' }}
            >
              {phase.phase}
            </span>
            <span
              className="text-[9px] font-mono px-1.5 rounded"
              style={{ background: 'var(--bg-panel)', color: '#60a5fa' }}
            >
              {phase.agent}
            </span>
            <span className="text-[9px] ml-auto" style={{ color: ok ? '#22c55e' : '#ef4444' }}>
              {phase.status}
            </span>
            <span className="text-slate-500 text-[9px] flex-shrink-0">{expanded ? '▾' : '▸'}</span>
          </div>
          <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
            {phase.summary}
          </p>
        </div>
      </button>

      {/* Expanded detail panel */}
      {expanded && detailEntries.length > 0 && (
        <div
          className="px-3 pb-3 pt-2 border-t space-y-1.5"
          style={{ borderColor: 'var(--border-dim)', background: 'var(--bg-card)' }}
        >
          {detailEntries.map(([key, val]) => (
            <div key={key} className="flex gap-2 text-[10px] font-mono">
              <span className="flex-shrink-0" style={{ color: 'var(--text-dim)', minWidth: 120 }}>
                {key}:
              </span>
              <span style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                {formatDetailValue(key, val)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main export ────────────────────────────────────────────────────────────

interface Props {
  phases:     PhaseStep[];
  hopNodes:   HopNode[];
  scenarioId: string | null;
  incidentId: string | null;
  tracing:    boolean;
  jobName:    string | null;
}

const FULL_CHAIN_LENGTH = 6;   // INC + 5 chain nodes in every scenario

export function HopTracer({ phases, hopNodes, scenarioId, incidentId, tracing, jobName }: Props) {
  const completedPhases = useMemo(() => new Set(phases.map(p => p.phase)), [phases]);
  const lastPhase       = phases[phases.length - 1]?.phase ?? null;
  const activePhase     = tracing ? lastPhase : null;
  const [expandedPhase, setExpandedPhase] = useState<number | null>(null);

  const chain = useMemo(() => {
    if (!incidentId) return [];
    return buildChain(incidentId, hopNodes);
  }, [incidentId, hopNodes]);

  const snippet      = scenarioId ? (DEFECT_SNIPPETS[scenarioId] ?? null) : null;
  const chainComplete = chain.length >= FULL_CHAIN_LENGTH;

  if (!jobName) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3"
           style={{ color: 'var(--text-muted)' }}>
        <svg className="w-12 h-12 opacity-20" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="1">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4l3 3" />
        </svg>
        <p className="text-sm">Select an incident to begin tracing</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">

      {/* Phase pipeline */}
      <PhasePipeline completedPhases={completedPhases} activePhase={activePhase} tracing={tracing} />

      {/* Scrollable main area */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

        {phases.length === 0 && tracing && (
          <div className="flex items-center gap-2 text-sm pt-6 justify-center"
               style={{ color: 'var(--text-muted)' }}>
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            Initializing trace...
          </div>
        )}

        {/* Causal chain */}
        {chain.length > 0 && (
          <section>
            <div
              className="text-[10px] font-bold tracking-widest uppercase mb-3 flex items-center gap-2"
              style={{ color: 'var(--text-muted)' }}
            >
              <span>Causal Chain — Backtracking Trace</span>
              <span style={{ color: 'var(--border-active)' }}>
                {chain.length}/{FULL_CHAIN_LENGTH} nodes
              </span>
              {chainComplete && (
                <span
                  className="ml-auto text-[9px] px-2 py-0.5 rounded font-bold uppercase"
                  style={{ background: '#14532d', color: '#86efac' }}
                >
                  CHAIN COMPLETE
                </span>
              )}
            </div>
            <div className="space-y-0">
              {chain.map((entry, i) => (
                <ChainNodeRow key={entry.nodeId} entry={entry} delay={i * 90} />
              ))}
            </div>
          </section>
        )}

        {/* Root cause defect box */}
        {chainComplete && snippet && (
          <section>
            <div
              className="text-[10px] font-bold tracking-widest uppercase mb-3 flex items-center gap-2"
              style={{ color: '#fca5a5' }}
            >
              <span>⚑ Root Cause Defect</span>
              <span style={{ color: '#6b7280' }}>— {snippet.defect_id}</span>
            </div>
            <DefectBox snippet={snippet} />
          </section>
        )}

        {/* Phase log */}
        {phases.length > 0 && (
          <section>
            <div
              className="text-[10px] font-bold tracking-widest uppercase mb-2"
              style={{ color: 'var(--text-muted)' }}
            >
              Phase Log
            </div>
            <div className="space-y-1.5">
              {phases.filter(p => p.phase !== 'HOP_REVEALED').map((p, i) => (
                <PhaseLogRow
                  key={i}
                  phase={p}
                  expanded={expandedPhase === i}
                  onToggle={() => setExpandedPhase(expandedPhase === i ? null : i)}
                />
              ))}
            </div>
          </section>
        )}

        {tracing && phases.length > 0 && (
          <div className="flex items-center gap-2 text-blue-400 text-xs">
            <div className="w-2 h-2 rounded-full bg-blue-400 pulse" />
            Tracing next phase…
          </div>
        )}
      </div>
    </div>
  );
}
