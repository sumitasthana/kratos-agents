import { useEffect, useRef } from 'react';
import type { RcaMessage, AgentMessage, Priority } from '../types';
import { HopTrace } from './HopTrace';
import { EvidenceBlock } from './EvidenceBlock';
import { TriangulationCard } from './TriangulationCard';
import { RecommendationCard } from './RecommendationCard';

const PRIORITY_DOT: Record<Priority, string> = {
  P1: '#dc2626',
  P2: '#ea580c',
  P3: '#ca8a04',
  P4: '#16a34a',
};

const TAG_STYLE: Record<NonNullable<AgentMessage['tag']>, { bg: string; border: string; color: string }> = {
  evidence: { bg: '#172554', border: '#1e3a8a', color: '#93c5fd' },
  finding: { bg: '#271507', border: '#ea580c', color: '#fdba74' },
  info: { bg: '#0f172a', border: '#1e293b', color: '#64748b' },
};

function MessageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="animate-fade-slide" style={{ marginBottom: '12px' }}>
      {children}
    </div>
  );
}

interface MessageStreamProps {
  messages: RcaMessage[];
  isTracing: boolean;
}

export function MessageStream({ messages, isTracing }: MessageStreamProps) {
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
      {messages.map(msg => {
        switch (msg.type) {
          case 'system':
            return (
              <MessageWrapper key={msg.id}>
                <div
                  style={{
                    backgroundColor: '#0f172a',
                    border: '1px solid #111827',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <span style={{ color: '#334155', fontSize: '10px', fontFamily: 'IBM Plex Mono, monospace' }}>SYS</span>
                  <span style={{ fontSize: '12px', color: '#94a3b8' }}>{msg.text}</span>
                </div>
              </MessageWrapper>
            );

          case 'agent':
            return (
              <MessageWrapper key={msg.id}>
                <div>
                  {/* Agent header */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span
                      style={{
                        fontFamily: 'IBM Plex Mono, monospace',
                        fontSize: '10px',
                        color: '#3b82f6',
                        fontWeight: 600,
                      }}
                    >
                      {msg.agent}
                    </span>
                    {msg.tag && (
                      <span
                        style={{
                          fontFamily: 'IBM Plex Mono, monospace',
                          fontSize: '9px',
                          padding: '1px 5px',
                          borderRadius: '3px',
                          backgroundColor: TAG_STYLE[msg.tag].bg,
                          border: `1px solid ${TAG_STYLE[msg.tag].border}`,
                          color: TAG_STYLE[msg.tag].color,
                        }}
                      >
                        {msg.tag}
                      </span>
                    )}
                  </div>
                  {/* Message body */}
                  <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: '1.6' }}>
                    {msg.text}
                  </p>
                </div>
              </MessageWrapper>
            );

          case 'hop':
            return (
              <MessageWrapper key={msg.id}>
                <HopTrace hops={msg.hops} />
              </MessageWrapper>
            );

          case 'evidence':
            return (
              <MessageWrapper key={msg.id}>
                <EvidenceBlock
                  source={msg.source}
                  filename={msg.filename}
                  language={msg.language}
                  defect={msg.defect}
                  code={msg.code}
                />
              </MessageWrapper>
            );

          case 'triangulation':
            return (
              <MessageWrapper key={msg.id}>
                <TriangulationCard
                  confidence={msg.confidence}
                  rootCause={msg.rootCause}
                  regulation={msg.regulation}
                  defect={msg.defect}
                />
              </MessageWrapper>
            );

          case 'recommendation':
            return (
              <MessageWrapper key={msg.id}>
                <RecommendationCard items={msg.items} />
              </MessageWrapper>
            );

          default:
            return null;
        }
      })}

      {/* Working indicator */}
      {isTracing && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 0',
          }}
        >
          <span
            className="animate-pulse-dot"
            style={{ color: '#3b82f6', fontSize: '12px', fontFamily: 'IBM Plex Mono, monospace' }}
          >
            ●
          </span>
          <span
            style={{
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: '11px',
              color: '#64748b',
            }}
          >
            agents working
            <span className="animate-blink">_</span>
          </span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}

// Suppress unused import warning for PRIORITY_DOT — used for future severity coloring
void PRIORITY_DOT;
