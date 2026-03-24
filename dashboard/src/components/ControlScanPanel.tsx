import React from 'react';
import type { ControlResult } from '../types';

const STATUS: Record<ControlResult['status'], { icon: string; color: string; bg: string }> = {
  PASS:    { icon: '✓', color: 'text-green-400',  bg: 'bg-green-500/10'  },
  FAIL:    { icon: '✗', color: 'text-red-400',    bg: 'bg-red-500/10'    },
  WARN:    { icon: '⚠', color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  MISSING: { icon: '○', color: 'text-slate-500',  bg: 'bg-slate-500/10'  },
};

interface Props { controls: ControlResult[]; loading: boolean; }

export function ControlScanPanel({ controls, loading }: Props) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent
                        rounded-full animate-spin" />
      </div>
    );
  }

  const passing = controls.filter(c => c.status === 'PASS').length;
  const failing = controls.filter(c => c.status === 'FAIL').length;
  const warning = controls.filter(c => c.status === 'WARN').length;

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex gap-3 text-xs">
        <span className="text-green-400 font-mono">{passing} PASS</span>
        <span className="text-red-400 font-mono">{failing} FAIL</span>
        <span className="text-yellow-400 font-mono">{warning} WARN</span>
      </div>

      {/* Control rows */}
      <div className="space-y-1.5">
        {controls.map(ctrl => {
          const st = STATUS[ctrl.status];
          return (
            <div key={ctrl.control_id}
                 className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border ${st.bg}`}
                 style={{ borderColor: 'var(--border-dim)' }}>
              <span className={`text-sm font-bold mt-0.5 ${st.color}`}>{st.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-slate-300">
                    {ctrl.control_id}
                  </span>
                  <span className="text-[10px] text-slate-500">{ctrl.regulation}</span>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5">{ctrl.description}</p>
                {ctrl.gap && (
                  <p className="text-[10px] text-red-400 mt-1 italic">Gap: {ctrl.gap}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
