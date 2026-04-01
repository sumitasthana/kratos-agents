import { useEffect, useRef } from 'react';
import type { RcaMessage, PhaseId } from '../types';
import { PhaseSections } from './PhaseSections';

interface MessageStreamProps {
  messages: RcaMessage[];
  isTracing: boolean;
  currentPhase: PhaseId | null;
}

export function MessageStream({ messages, isTracing, currentPhase }: MessageStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <PhaseSections
        messages={messages}
        currentPhase={currentPhase}
        isTracing={isTracing}
      />

      {/* Working indicator */}
      {isTracing && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 0' }}>
          <span
            className="animate-pulse-dot"
            style={{ color: '#3b82f6', fontSize: '12px', fontFamily: 'IBM Plex Mono, monospace' }}
          >
            ●
          </span>
          <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '11px', color: '#64748b' }}>
            agents working
            <span className="animate-blink">_</span>
          </span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
