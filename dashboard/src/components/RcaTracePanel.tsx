import React, { useState } from 'react';
import type { RcaResult } from '../types';

interface Props { result: RcaResult | null; }

const EFFORT_COLOR: Record<string, string> = {
  LOW:    '#22c55e',
  MEDIUM: '#f59e0b',
  HIGH:   '#ef4444',
};

function effortColor(effort: string | undefined | null) {
  const key = (effort ?? '').toUpperCase().split(' ')[0] || 'LOW';
  return EFFORT_COLOR[key] ?? '#6b7280';
}

export function RcaTracePanel({ result }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!result) return null;

  const pct    = Math.round((result.confidence?.composite ?? 0) * 100);
  const locked = result.root_cause_final !== null;
  const tierClr = locked ? 'text-green-400' : 'text-yellow-400';

  return (
    <div className="space-y-4 text-sm">
      {/* Root cause block */}
      <div className="rounded-lg border p-4 space-y-2"
           style={{ background: 'var(--bg-card)', borderColor: 'var(--border-dim)' }}>
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
            Root Cause
          </span>
          <span className={`text-[10px] font-bold ${tierClr}`}>
            {locked ? '● LOCKED' : '○ PENDING'}
          </span>
        </div>
        <p className={`font-mono text-xs ${locked ? 'text-green-300' : 'text-yellow-300'}`}>
          {result.root_cause_final ?? 'Investigating — awaiting structural path validation'}
        </p>
      </div>

      {/* Remediation actions */}
      {result.remediation?.length > 0 && (
        <div className="space-y-2">
          <span className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
            Remediation — {result.remediation.length} action{result.remediation.length !== 1 ? 's' : ''}
          </span>
          {result.remediation.map((rem, i) => {
            const isOpen = expanded === i;
            const pctConf = Math.round((rem.confidence ?? 0) * 100);
            return (
              <div
                key={i}
                className="rounded-lg border overflow-hidden transition-all"
                style={{ borderColor: isOpen ? '#3b82f6' : 'var(--border-dim)' }}
              >
                {/* Clickable header */}
                <button
                  className="w-full text-left px-3 py-2.5 flex items-start justify-between gap-2 group"
                  style={{ background: isOpen ? 'var(--bg-code)' : 'var(--bg-panel)' }}
                  onClick={() => setExpanded(isOpen ? null : i)}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="text-[11px] font-bold flex-shrink-0 w-5 h-5 rounded-full
                                 flex items-center justify-center"
                      style={{ background: '#1e3a5f', color: '#60a5fa' }}
                    >
                      {rem.rank}
                    </span>
                    <span className="text-[11px] font-semibold truncate"
                          style={{ color: 'var(--text-primary)' }}>
                      {rem.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span
                      className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
                      style={{ background: '#0f172a', color: '#60a5fa' }}
                    >
                      {rem.defect_id}
                    </span>
                    <span className="text-[10px] font-bold"
                          style={{ color: effortColor(rem.effort) }}>
                      {(rem.effort ?? 'N/A').toUpperCase().split(' ')[0]}
                    </span>
                    <span className="text-slate-500 text-[10px]">
                      {isOpen ? '▾' : '▸'}
                    </span>
                  </div>
                </button>

                {/* Expanded detail */}
                {isOpen && (
                  <div className="px-3 pb-3 pt-1 space-y-2 border-t"
                       style={{ borderColor: 'var(--border-dim)', background: 'var(--bg-card)' }}>
                    <p className="text-[11px] leading-relaxed"
                       style={{ color: 'var(--text-primary)' }}>
                      {rem.action}
                    </p>
                    <div className="flex flex-wrap gap-3 mt-1">
                      <div>
                        <span className="text-[9px] uppercase tracking-widest"
                              style={{ color: 'var(--text-muted)' }}>Regulation</span>
                        <p className="text-[10px] font-mono" style={{ color: '#60a5fa' }}>
                          {rem.regulation}
                        </p>
                      </div>
                      <div>
                        <span className="text-[9px] uppercase tracking-widest"
                              style={{ color: 'var(--text-muted)' }}>Effort</span>
                        <p className="text-[10px] font-semibold"
                           style={{ color: effortColor(rem.effort) }}>
                          {rem.effort ?? 'N/A'}
                        </p>
                      </div>
                      <div>
                        <span className="text-[9px] uppercase tracking-widest"
                              style={{ color: 'var(--text-muted)' }}>Confidence</span>
                        <p className="text-[10px] font-mono" style={{ color: '#22c55e' }}>
                          {pctConf}%
                        </p>
                      </div>
                    </div>
                    <p className="text-[9px] font-mono truncate"
                       style={{ color: 'var(--text-muted)' }}>
                      {rem.artifact}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Regulation citations */}
      {result.regulation_citations?.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
            Regulation Citations
          </span>
          {result.regulation_citations.map((cite, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px] text-slate-400">
              <span className="text-blue-500">§</span>{cite}
            </div>
          ))}
        </div>
      )}

      {/* Audit trace */}
      {result.audit_trace?.length > 0 && (
        <details className="group">
          <summary className="text-[10px] font-bold tracking-widest uppercase
                              text-slate-500 cursor-pointer hover:text-slate-300">
            Audit Trace ({result.audit_trace.length} entries) ▸
          </summary>
          <div className="mt-2 space-y-1 pl-2 border-l"
               style={{ borderColor: 'var(--border-dim)' }}>
            {result.audit_trace.map((entry, i) => (
              <div key={i} className="text-[10px] text-slate-500 font-mono">
                <span className="text-slate-600">{entry.ts}</span>{' '}
                <span className="text-blue-400">[{entry.agent}]</span>{' '}
                {entry.action}: {entry.detail}
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Confidence summary */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-slate-600">composite confidence:</span>
        <span className={`text-xs font-bold font-mono ${
          pct >= 90 ? 'text-green-400' :
          pct >= 70 ? 'text-blue-400' :
          pct >= 40 ? 'text-yellow-400' : 'text-red-400'
        }`}>{pct}%</span>
        {result.confidence?.tier && (
          <span className="text-[10px] text-slate-600">({result.confidence.tier})</span>
        )}
      </div>
    </div>
  );
}
