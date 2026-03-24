import React from 'react';
import type { ChatMsg } from '../types';

interface Props {
  onSubmit:     (text: string) => void;   // starts a new full trace
  onAsk:        (text: string) => void;   // follow-up question (no reset)
  disabled:     boolean;
  onAbort:      () => void;
  hasResult:    boolean;
  chatMessages: ChatMsg[];
}

const SUGGESTIONS = [
  'Deposit run showing accounts over SMDIA limit',
  'Trust IRR classifier falling back to SGL ownership code',
  'Wire MT202 messages not appearing in GL reconciliation',
];

export function ChatInput({ onSubmit, onAsk, disabled, onAbort, hasResult, chatMessages }: Props) {
  const [val, setVal] = React.useState('');
  const ref      = React.useRef<HTMLTextAreaElement>(null);
  const threadEl = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => { if (!disabled) ref.current?.focus(); }, [disabled]);
  React.useEffect(() => {
    if (threadEl.current) threadEl.current.scrollTop = threadEl.current.scrollHeight;
  }, [chatMessages]);

  const submit = () => {
    const trimmed = val.trim();
    if (!trimmed || disabled) return;
    // Post-trace: route to follow-up ask; pre-trace: start new investigation
    if (hasResult) {
      onAsk(trimmed);
    } else {
      onSubmit(trimmed);
    }
    setVal('');
  };

  const buttonLabel = hasResult ? 'Ask →' : 'Trace ↗';

  return (
    <div className="border-t flex flex-col"
         style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--border-dim)' }}>

      {/* ── Chat message thread ── */}
      {chatMessages.length > 0 && (
        <div
          ref={threadEl}
          className="px-4 pt-3 pb-1 space-y-2 overflow-y-auto"
          style={{ maxHeight: 160, borderBottom: '1px solid var(--border-dim)' }}
        >
          {chatMessages.map((m, i) => (
            <div
              key={i}
              className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {m.role === 'assistant' && (
                <div className="w-5 h-5 rounded-full bg-blue-600 flex-shrink-0
                                flex items-center justify-center text-[9px] text-white font-bold mt-0.5">
                  K
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-xl px-3 py-2 text-[11px] leading-relaxed ${
                  m.role === 'user' ? 'rounded-tr-sm' : 'rounded-tl-sm'
                }`}
                style={{
                  background: m.role === 'user' ? '#1e40af' : 'var(--bg-card)',
                  color:      m.role === 'user' ? '#e0e7ff' : 'var(--text-primary)',
                  border:     m.role === 'assistant' ? '1px solid var(--border-dim)' : 'none',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="px-4 py-3 space-y-2">
        {/* Suggestion chips — show only before any investigation */}
        {!val && !disabled && !hasResult && (
          <div className="flex gap-2 flex-wrap">
            {SUGGESTIONS.map((s, i) => (
              <button key={i} onClick={() => setVal(s)}
                className="text-[10px] text-slate-400 border rounded-full px-3 py-1
                           hover:border-blue-500 hover:text-blue-300 transition-colors"
                style={{ borderColor: 'var(--border-dim)' }}>
                {s.length > 40 ? s.slice(0, 40) + '…' : s}
              </button>
            ))}
          </div>
        )}

        {/* Ask-mode context hint + re-trace link */}
        {hasResult && !disabled && (
          <div className="flex items-center justify-between">
            <span className="text-[9px]" style={{ color: 'var(--text-dim)' }}>
              Follow-up question about this investigation
            </span>
            <button
              onClick={() => { setVal(''); onSubmit('(re-run)'); }}
              className="text-[9px] hover:text-blue-400 transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              ↺ New trace
            </button>
          </div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2">
          <textarea
            ref={ref}
            rows={2}
            value={val}
            onChange={e => setVal(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            disabled={disabled}
            placeholder={
              hasResult
                ? 'Ask a question about this investigation…'
                : 'Ask a question about the evidence or suggest a manual query…'
            }
            className="flex-1 resize-none rounded-lg px-3 py-2.5 text-xs
                       border outline-none placeholder-slate-600 transition-colors
                       disabled:opacity-50"
            style={{
              background:  'var(--bg-code)',
              borderColor: 'var(--border-dim)',
              color:       'var(--text-primary)',
            }}
          />
          {disabled ? (
            <button onClick={onAbort}
              className="px-3 py-2 rounded-lg text-xs font-medium text-red-400
                         border border-red-500/30 hover:bg-red-500/10 transition-colors
                         flex-shrink-0">
              Stop
            </button>
          ) : (
            <button onClick={submit} disabled={!val.trim()}
              className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors
                         flex-shrink-0 disabled:opacity-30 ${
                           hasResult
                             ? 'bg-purple-600 text-white hover:bg-purple-500'
                             : 'bg-blue-600 text-white hover:bg-blue-500'
                         }`}>
              {buttonLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
