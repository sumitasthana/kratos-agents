import React, { useState } from 'react';
import { IncidentFeed } from './components/IncidentFeed';
import { HopTracer }        from './components/HopTracer';
import { ChatInput }        from './components/ChatInput';
import { ConfidenceGauge }  from './components/ConfidenceGauge';
import { ControlScanPanel } from './components/ControlScanPanel';
import { RcaTracePanel }    from './components/RcaTracePanel';
import { ThemeToggle }      from './components/ThemeToggle';
import { useRcaStream }     from './hooks/useRcaStream';
import { useTheme }         from './hooks/useTheme';
import type { Incident, ControlResult } from './types';

const MOCK_CONTROLS: Record<string, ControlResult[]> = {
  'INC-001': [
    {
      control_id: 'CTL-AGG-01', status: 'FAIL',
      description: 'Deposit aggregation step must execute on every run',
      regulation: 'FDIC §370.4(a)',
      gap: 'AGGRSTEP commented out in JCL',
    },
    {
      control_id: 'CTL-AGG-02', status: 'WARN',
      description: 'Job completion audit log must include step-level status',
      regulation: 'FDIC §370.5(b)',
      gap: 'Log shows success despite skip',
    },
    {
      control_id: 'CTL-AGG-03', status: 'PASS',
      description: 'SMDIA threshold = $250,000 per account category',
      regulation: 'FDIC §330.1',
    },
  ],
  'INC-002': [
    {
      control_id: 'CTL-IRR-01', status: 'FAIL',
      description: 'IRR ownership code must be assigned for qualifying trusts',
      regulation: 'FDIC §330.10(b)',
      gap: 'Fallback ORC=SGL always fires',
    },
    {
      control_id: 'CTL-IRR-02', status: 'FAIL',
      description: 'Trust classification must not fall back silently',
      regulation: 'FDIC §330.10(c)',
    },
    {
      control_id: 'CTL-IRR-03', status: 'PASS',
      description: 'Account universe must be complete (6,006 records)',
      regulation: 'FDIC §370.4',
    },
  ],
  'INC-003': [
    {
      control_id: 'CTL-MT202-01', status: 'FAIL',
      description: 'All SWIFT message types must have registered handlers',
      regulation: 'FDIC §370.3(d)',
      gap: 'MT202 has no handler — silent drop',
    },
    {
      control_id: 'CTL-MT202-02', status: 'FAIL',
      description: 'Wire GL reconciliation must balance within ±$1',
      regulation: 'FDIC §370.6(a)',
      gap: '$284.7M break detected',
    },
    {
      control_id: 'CTL-MT202-03', status: 'MISSING',
      description: 'Dead-letter queue for unhandled message types',
      regulation: 'FDIC §370.3(e)',
    },
  ],
};

export default function DemoRCA() {
  const [selected, setSelected] = useState<Incident | null>(null);
  const { result, tracing, syncPct, trace, abort,
          phases, hopNodes, scenarioId, incidentId,
          chatMessages, ask } = useRcaStream();
  useTheme(); // applies dark/light class to <html> on mount

  const handleSelect = (inc: Incident) => {
    setSelected(inc);
    const query = inc.error_msg.replace(/^"|"$/g, '');
    trace(`Incident ${inc.id}: ${inc.job_name} — ${query}`);
  };

  const controls   = selected ? (MOCK_CONTROLS[selected.id] ?? []) : [];
  const hopCount   = phases.length;
  const finalPhase = phases[phases.length - 1]?.phase ?? '';

  return (
    <div className="h-screen flex flex-col"
         style={{ background: 'var(--bg-root)', overflow: 'hidden' }}>

      {/* ── Top bar ── */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b flex-shrink-0"
              style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border-dim)' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-blue-600 flex items-center
                          justify-center text-[10px] font-bold text-white">K</div>
          <span className="text-sm font-semibold text-slate-200">
            Kratos Intelligence Platform
          </span>
          <span className="text-[10px] text-slate-600 ml-1">
            Multi-Hop RCA Dashboard
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-slate-500">
          <span>FDIC Part 370/330</span>
          <span className="w-px h-3 bg-slate-700" />
          <span className="text-green-400">● DEMO MODE</span>
          <ThemeToggle />
        </div>
      </header>

      {/* ── Main layout ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: Incident Feed */}
        <IncidentFeed selected={selected?.id ?? null} onSelect={handleSelect} />

        {/* Center: Hop Tracer */}
        <main className="flex-1 flex flex-col overflow-hidden border-r"
              style={{ borderColor: 'var(--border-dim)' }}>

          {/* Panel header */}
          {selected && (
            <div className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0"
                 style={{ borderColor: 'var(--border-dim)', background: 'var(--bg-panel)' }}>
              <div className="flex items-center gap-3">
                <div className="w-7 h-7 rounded bg-blue-600/20 flex items-center justify-center">
                  <span className="text-blue-400 text-xs">⟳</span>
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-slate-200">
                    {selected.job_name} Analysis
                  </h2>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {tracing && (
                      <div className="w-1.5 h-1.5 rounded-full bg-blue-400 pulse" />
                    )}
                    <span className="text-[10px] text-slate-500 uppercase tracking-widest">
                      {tracing
                        ? `Tracing hops… (${hopCount}/7)`
                        : hopCount > 0
                          ? `${hopCount} hops complete — ${finalPhase}`
                          : 'Idle'
                      }
                    </span>
                  </div>
                </div>
              </div>

              {/* Status badge — no tab toggle needed */}
              <div className="flex items-center gap-1.5 text-[10px]">
                {result && !tracing && (
                  <span
                    className="px-2 py-0.5 rounded font-bold text-[10px] uppercase"
                    style={{ background: '#14532d', color: '#86efac' }}
                  >
                    ✓ COMPLETE
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Scrollable hop area */}
          <HopTracer
            phases={phases}
            hopNodes={hopNodes}
            scenarioId={scenarioId}
            incidentId={incidentId}
            tracing={tracing}
            jobName={selected?.job_name ?? null}
          />

          {/* Bottom chat */}
          <ChatInput
            onSubmit={trace}
            onAsk={ask}
            disabled={tracing}
            onAbort={abort}
            hasResult={result !== null}
            chatMessages={chatMessages}
          />
        </main>

        {/* Right panel — always-visible control scan + findings after trace */}
        {selected && (
          <aside className="w-80 flex-shrink-0 overflow-y-auto p-4 space-y-4"
                 style={{ background: 'var(--bg-sidebar)' }}>

            {/* Control scan — always at top */}
            <div className="space-y-2">
              <span className="text-[10px] font-bold tracking-widest uppercase text-slate-500">
                Control Scan — {selected.id}
              </span>
              <ControlScanPanel controls={controls} loading={false} />
            </div>

            {/* Confidence gauge — appears when trace completes */}
            {result?.confidence && (
              <ConfidenceGauge confidence={result.confidence} />
            )}

            {/* Root cause + recommendations — appears when trace completes */}
            <RcaTracePanel result={result} />

          </aside>
        )}
      </div>

      {/* ── Status bar ── */}
      <footer className="flex items-center justify-between px-5 py-1.5 border-t flex-shrink-0"
              style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border-dim)' }}>
        <div className="flex items-center gap-1.5 text-[10px]">
          <span className={tracing ? 'text-blue-400' : 'text-slate-600'}>↗</span>
          <span className={`font-semibold ${tracing ? 'text-blue-400' : 'text-slate-600'}`}>
            {tracing ? 'TRACE ACTIVE' : 'TRACE IDLE'}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-slate-600">
          <span>≡</span>
          <span>EVIDENCE SYNC: {syncPct}%</span>
        </div>
      </footer>
    </div>
  );
}
