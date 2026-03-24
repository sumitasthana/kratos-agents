import React from 'react';
import type { ConfidenceBreakdown } from '../types';

interface Props { confidence: ConfidenceBreakdown | null; }

const TIER_COLOR: Record<string, string> = {
  CONFIRMED: '#22c55e',
  HIGH:      '#3b82f6',
  MEDIUM:    '#eab308',
  LOW:       '#ef4444',
};

export function ConfidenceGauge({ confidence }: Props) {
  if (!confidence) return null;
  const pct   = Math.round(confidence.composite * 100);
  const color = TIER_COLOR[confidence.tier] ?? '#3b82f6';
  const r = 28;
  const c = 2 * Math.PI * r;
  const dash = (confidence.composite * c).toFixed(1);

  return (
    <div className="flex items-center gap-4 px-4 py-3 rounded-lg border"
         style={{ background: 'var(--bg-card)', borderColor: 'var(--border-dim)' }}>
      {/* Arc gauge */}
      <svg width="68" height="68" viewBox="0 0 68 68" className="flex-shrink-0">
        <circle cx="34" cy="34" r={r} fill="none"
                stroke="var(--border-dim)" strokeWidth="5" />
        <circle cx="34" cy="34" r={r} fill="none"
                stroke={color} strokeWidth="5"
                strokeDasharray={`${dash} ${c}`}
                strokeLinecap="round"
                transform="rotate(-90 34 34)"
                style={{ transition: 'stroke-dasharray 0.6s ease' }} />
        <text x="34" y="38" textAnchor="middle"
              style={{ fill: color, fontSize: '14px', fontWeight: 700,
                       fontFamily: 'monospace' }}>
          {pct}%
        </text>
      </svg>

      {/* Breakdown bars */}
      <div className="flex-1 space-y-1.5">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold text-slate-300">Confidence</span>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                style={{ color, background: `${color}18` }}>
            {confidence.tier}
          </span>
        </div>
        {(['E', 'T', 'D', 'H'] as const).map(k => {
          const labels: Record<string, string> = {
            E: 'Evidence', T: 'Topology', D: 'Defect Spec', H: 'Historical',
          };
          const val = confidence[k] ?? 0;
          return (
            <div key={k} className="flex items-center gap-2">
              <span className="text-[10px] text-slate-500 w-20">{labels[k]}</span>
              <div className="flex-1 h-1.5 rounded-full bg-slate-800">
                <div className="h-full rounded-full transition-all"
                     style={{ width: `${val * 100}%`, background: color, opacity: 0.7 }} />
              </div>
              <span className="text-[10px] font-mono text-slate-400 w-8 text-right">
                {(val * 100).toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}