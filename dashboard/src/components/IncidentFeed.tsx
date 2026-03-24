import React from 'react';
import type { Incident, Severity } from '../types';

const SEV: Record<Severity, { bg: string; text: string; dot: string }> = {
  Critical: { bg: 'bg-red-500/10',    text: 'text-red-400',    dot: 'bg-red-500' },
  High:     { bg: 'bg-orange-500/10', text: 'text-orange-400', dot: 'bg-orange-500' },
  Medium:   { bg: 'bg-yellow-500/10', text: 'text-yellow-400', dot: 'bg-yellow-500' },
  Low:      { bg: 'bg-gray-500/10',   text: 'text-gray-400',   dot: 'bg-gray-500' },
};

const DEMO_INCIDENTS: Incident[] = [
  {
    id: 'INC-001', severity: 'High',
    job_name: 'DepositAggregation-Run',
    error_msg: '"AGGRSTEP skipped — JCL disabled"',
    job_id: 'job-3301', timestamp: '2026-03-16 06:14:00',
    scenario_id: 'deposit_aggregation_failure',
  },
  {
    id: 'INC-002', severity: 'Critical',
    job_name: 'TrustClassifier-IRR',
    error_msg: '"IRR fallback to SGL — $61.8M gap"',
    job_id: 'job-4412', timestamp: '2026-03-16 07:02:00',
    scenario_id: 'trust_irr_misclassification',
  },
  {
    id: 'INC-003', severity: 'Critical',
    job_name: 'WireTransfer-MT202',
    error_msg: '"59 MT202 messages silently dropped"',
    job_id: 'job-5523', timestamp: '2026-03-16 08:45:00',
    scenario_id: 'wire_mt202_drop',
  },
];

interface Props {
  selected: string | null;
  onSelect: (inc: Incident) => void;
}

export function IncidentFeed({ selected, onSelect }: Props) {
  return (
    <aside className="w-64 flex-shrink-0 flex flex-col border-r"
           style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border-dim)' }}>
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b"
           style={{ borderColor: 'var(--border-dim)' }}>
        <svg className="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
        <span className="text-xs font-bold tracking-widest text-blue-300 uppercase">
          Incident Feed
        </span>
      </div>

      {/* Incident list */}
      <div className="flex-1 overflow-y-auto py-2 space-y-1 px-2">
        {DEMO_INCIDENTS.map(inc => {
          const sev    = SEV[inc.severity];
          const active = selected === inc.id;
          return (
            <button key={inc.id} onClick={() => onSelect(inc)}
              className={`w-full text-left rounded-lg p-3 border transition-all
                ${active
                  ? 'border-blue-500 bg-blue-500/5'
                  : 'border-transparent hover:border-slate-700 hover:bg-white/[0.02]'
                }`}
              style={{ borderColor: active ? 'var(--border-active)' : undefined }}>
              {/* Name + severity badge */}
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-semibold text-slate-200 truncate pr-2">
                  {inc.job_name}
                </span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full
                  flex-shrink-0 ${sev.bg} ${sev.text}`}>
                  {inc.severity}
                </span>
              </div>
              {/* Error */}
              <p className="text-xs text-slate-400 italic truncate mb-2">
                {inc.error_msg}
              </p>
              {/* Meta */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-slate-500">{inc.job_id}</span>
                <span className="text-[10px] text-slate-600">{inc.timestamp.split(' ')[1]}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer stat */}
      <div className="px-4 py-2 border-t text-[10px] text-slate-600 flex justify-between"
           style={{ borderColor: 'var(--border-dim)' }}>
        <span>{DEMO_INCIDENTS.length} incidents</span>
        <span className="text-green-500">● LIVE</span>
      </div>
    </aside>
  );
}

export { DEMO_INCIDENTS };
