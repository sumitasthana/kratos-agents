import { useState, type KeyboardEvent } from 'react';
import type { PhaseId } from '../types';

const PHASE_CHIPS: Partial<Record<PhaseId, string[]>> = {
  INTAKE: ['What controls failed?', 'Show incident timeline'],
  LOGS_FIRST: ['Show full Spark log', 'Compare with last successful run'],
  ROUTE: ['Why was this pattern selected?'],
  BACKTRACK: ['Show full evidence chain', 'Explain the root cause'],
  INCIDENT_CARD: ['How confident is this finding?'],
  RECOMMEND: ['Who needs to act?', 'What regulation was violated?', 'Export report'],
  PERSIST: ['Start new incident', 'Show summary'],
};

interface ChatInputProps {
  currentPhase: PhaseId | null;
  isTracing: boolean;
  onSend: (text: string) => void;
}

export function ChatInput({ currentPhase, isTracing, onSend }: ChatInputProps) {
  const [value, setValue] = useState('');
  const chips = currentPhase ? (PHASE_CHIPS[currentPhase] ?? []) : [];

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleSend();
  };

  return (
    <div
      style={{
        borderTop: '1px solid #111827',
        backgroundColor: '#030712',
        padding: '10px 16px 12px',
        flexShrink: 0,
      }}
    >
      {/* Chip row */}
      {chips.length > 0 && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
          {chips.map(chip => (
            <button
              key={chip}
              onClick={() => onSend(chip)}
              style={{
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '10px',
                padding: '3px 9px',
                borderRadius: '3px',
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                color: '#94a3b8',
                cursor: 'pointer',
                transition: 'border-color 0.15s, color 0.15s',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = '#3b82f6';
                (e.currentTarget as HTMLButtonElement).style.color = '#93c5fd';
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = '#1e293b';
                (e.currentTarget as HTMLButtonElement).style.color = '#94a3b8';
              }}
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {/* Input row */}
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <span
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '12px',
            color: '#3b82f6',
            flexShrink: 0,
          }}
        >
          ›
        </span>
        <input
          type="text"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder={isTracing ? 'Agents working...' : 'Ask about this incident...'}
          disabled={isTracing}
          style={{
            flex: 1,
            backgroundColor: 'transparent',
            border: 'none',
            outline: 'none',
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '12px',
            color: '#e2e8f0',
            caretColor: '#3b82f6',
          }}
        />
        <button
          onClick={handleSend}
          disabled={!value.trim() || isTracing}
          style={{
            fontFamily: 'IBM Plex Mono, monospace',
            fontSize: '10px',
            padding: '4px 10px',
            borderRadius: '3px',
            backgroundColor: value.trim() && !isTracing ? '#172554' : '#0f172a',
            border: `1px solid ${value.trim() && !isTracing ? '#3b82f6' : '#1e293b'}`,
            color: value.trim() && !isTracing ? '#93c5fd' : '#334155',
            cursor: value.trim() && !isTracing ? 'pointer' : 'not-allowed',
            transition: 'all 0.15s',
          }}
        >
          SEND
        </button>
      </div>
    </div>
  );
}
