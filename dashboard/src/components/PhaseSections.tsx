import { useState, useEffect, useRef } from 'react';
import type { RcaMessage, AgentMessage, PhaseId, Priority } from '../types';
import { useColors } from '../ThemeContext';
import { HopTrace } from './HopTrace';
import { EvidenceBlock } from './EvidenceBlock';
import { TriangulationCard } from './TriangulationCard';
import { RecommendationCard } from './RecommendationCard';

/* ── Section definitions ── */
interface SectionDef {
  id: string;
  label: string;
  phases: PhaseId[];
  icon: string;
}

const SECTIONS: SectionDef[] = [
  { id: 'ingestion', label: 'INGESTION & CONTEXT', phases: ['INTAKE'], icon: '▸' },
  { id: 'evidence', label: 'EVIDENCE COLLECTION', phases: ['LOGS_FIRST', 'ROUTE'], icon: '◆' },
  { id: 'investigation', label: 'INVESTIGATION', phases: ['BACKTRACK'], icon: '◉' },
  { id: 'rca', label: 'ROOT CAUSE ANALYSIS', phases: ['INCIDENT_CARD'], icon: '⚡' },
  { id: 'recommendations', label: 'RECOMMENDATIONS', phases: ['RECOMMEND', 'PERSIST'], icon: '★' },
];

/* ── Phase ordering for status calculation ── */
const PHASE_ORDER: PhaseId[] = [
  'INTAKE', 'LOGS_FIRST', 'ROUTE', 'BACKTRACK', 'INCIDENT_CARD', 'RECOMMEND', 'PERSIST',
];

/* ── Helpers ── */
function extractHypothesis(text: string): string {
  const match = text.match(/'root_cause_hypothesis':\s*'([^']+)'/);
  if (match) return match[1];
  try {
    const obj = JSON.parse(text.replace(/'/g, '"'));
    return obj.root_cause_hypothesis || text;
  } catch {
    return text;
  }
}

function isKeepalive(msg: RcaMessage): boolean {
  return msg.type === 'system' && (msg.text?.startsWith('Pipeline running') ?? false);
}

function isChatMessage(msg: RcaMessage): boolean {
  return msg.type === 'user' || (msg.type === 'agent' && msg.phase === 'PERSIST' && !msg.tag);
}

function isDuplicateFinding(msg: RcaMessage, seen: Set<string>): boolean {
  if (msg.type !== 'agent' || msg.tag !== 'finding') return false;
  const hyp = extractHypothesis(msg.text ?? '').slice(0, 80);
  if (seen.has(hyp)) return true;
  seen.add(hyp);
  return false;
}

function getSectionStatus(
  section: SectionDef,
  currentPhase: PhaseId | null,
  isTracing: boolean,
  messageCount: number,
): 'pending' | 'active' | 'complete' {
  if (!currentPhase) return messageCount > 0 ? 'complete' : 'pending';
  const currentIdx = PHASE_ORDER.indexOf(currentPhase);
  const sectionPhaseIndices = section.phases.map(p => PHASE_ORDER.indexOf(p));
  const sectionStart = Math.min(...sectionPhaseIndices);
  const sectionEnd = Math.max(...sectionPhaseIndices);

  if (currentIdx > sectionEnd) return 'complete';
  if (currentIdx >= sectionStart && isTracing) return 'active';
  if (messageCount > 0 && !isTracing) return 'complete';
  return 'pending';
}

/* ── Styles ── */
const TAG_STYLE: Record<NonNullable<AgentMessage['tag']>, { bg: string; border: string; color: string }> = {
  evidence: { bg: '#172554', border: '#1e3a8a', color: '#93c5fd' },
  finding: { bg: '#271507', border: '#ea580c', color: '#fdba74' },
  info: { bg: '#0f172a', border: '#1e293b', color: '#64748b' },
};

/* ── Sub-components ── */
function TruncatableText({ text, limit = 200 }: { text: string; limit?: number }) {
  const [expanded, setExpanded] = useState(false);
  const needsTruncation = text.length > limit;
  return (
    <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: '1.6', wordBreak: 'break-word' }}>
      {needsTruncation && !expanded ? text.slice(0, limit) + '...' : text}
      {needsTruncation && (
        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer',
            fontSize: '11px', marginLeft: '4px', padding: 0, fontFamily: 'IBM Plex Mono, monospace',
          }}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </p>
  );
}

function StatusIcon({ status }: { status: 'pending' | 'active' | 'complete' }) {
  if (status === 'complete') {
    return <span style={{ color: '#22c55e', fontSize: '12px', fontFamily: 'IBM Plex Mono, monospace' }}>✓</span>;
  }
  if (status === 'active') {
    return <span className="animate-pulse-dot" style={{ color: '#3b82f6', fontSize: '10px' }}>●</span>;
  }
  return <span style={{ color: '#334155', fontSize: '10px' }}>●</span>;
}

function FindingBlock({ text }: { text: string }) {
  const hypothesis = extractHypothesis(text);
  // If we extracted a clean hypothesis, render it nicely
  if (hypothesis !== text) {
    return (
      <div style={{
        padding: '10px 14px',
        backgroundColor: '#0a0f1a',
        border: '1px solid #1e293b',
        borderLeft: '3px solid #ea580c',
        borderRadius: '4px',
      }}>
        <div style={{
          fontFamily: 'IBM Plex Mono, monospace', fontSize: '9px',
          color: '#ea580c', letterSpacing: '0.1em', marginBottom: '6px', fontWeight: 600,
        }}>
          HYPOTHESIS
        </div>
        <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: '1.6', fontStyle: 'italic' }}>
          "{hypothesis}"
        </p>
      </div>
    );
  }
  return <TruncatableText text={text} limit={200} />;
}

function renderMessage(msg: RcaMessage) {
  switch (msg.type) {
    case 'system':
      return (
        <div style={{
          backgroundColor: '#0f172a', border: '1px solid #111827',
          borderRadius: '6px', padding: '8px 12px',
          display: 'flex', alignItems: 'center', gap: '8px',
        }}>
          <span style={{ color: '#334155', fontSize: '10px', fontFamily: 'IBM Plex Mono, monospace' }}>SYS</span>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>{msg.text}</span>
        </div>
      );

    case 'agent':
      return (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{
              fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px',
              color: '#3b82f6', fontWeight: 600,
            }}>
              {msg.agent}
            </span>
            {msg.tag && (
              <span style={{
                fontFamily: 'IBM Plex Mono, monospace', fontSize: '9px',
                padding: '1px 5px', borderRadius: '3px',
                backgroundColor: TAG_STYLE[msg.tag].bg,
                border: `1px solid ${TAG_STYLE[msg.tag].border}`,
                color: TAG_STYLE[msg.tag].color,
              }}>
                {msg.tag}
              </span>
            )}
          </div>
          {msg.tag === 'finding' ? (
            <FindingBlock text={msg.text ?? ''} />
          ) : msg.tag === 'evidence' ? (
            <TruncatableText text={msg.text ?? ''} limit={200} />
          ) : (
            <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: '1.6', wordBreak: 'break-word' }}>
              {msg.text}
            </p>
          )}
        </div>
      );

    case 'hop':
      return <HopTrace hops={msg.hops} />;

    case 'evidence':
      return (
        <EvidenceBlock
          source={msg.source} filename={msg.filename}
          language={msg.language} defect={msg.defect} code={msg.code}
        />
      );

    case 'triangulation':
      return (
        <TriangulationCard
          confidence={msg.confidence} rootCause={msg.rootCause}
          regulation={msg.regulation} defect={msg.defect}
        />
      );

    case 'recommendation':
      return <RecommendationCard items={msg.items} />;

    default:
      return null;
  }
}

/* ── Main Component ── */
interface PhaseSectionsProps {
  messages: RcaMessage[];
  currentPhase: PhaseId | null;
  isTracing: boolean;
}

export function PhaseSections({ messages, currentPhase, isTracing }: PhaseSectionsProps) {
  const c = useColors();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  // Progressive reveal: which sections are visible (index into SECTIONS)
  const [revealedCount, setRevealedCount] = useState(0);
  const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevMsgCountRef = useRef(0);

  // Group messages into sections, filtering noise
  const findingSeen = new Set<string>();
  const grouped: Record<string, RcaMessage[]> = {};
  const chatMessages: RcaMessage[] = [];

  for (const msg of messages) {
    if (isKeepalive(msg)) continue;
    if (isChatMessage(msg)) { chatMessages.push(msg); continue; }
    if (isDuplicateFinding(msg, findingSeen)) continue;

    const section = SECTIONS.find(s => s.phases.includes(msg.phase));
    if (section) {
      (grouped[section.id] ??= []).push(msg);
    }
  }

  // Count sections that have messages
  const populatedSections = SECTIONS.filter(s => (grouped[s.id]?.length ?? 0) > 0);

  // Progressive reveal: when a burst of messages arrives, reveal sections one by one
  useEffect(() => {
    const totalPipelineMessages = messages.filter(m => m.type !== 'user' && !isKeepalive(m)).length;
    const hadBurst = totalPipelineMessages > prevMsgCountRef.current + 3;
    prevMsgCountRef.current = totalPipelineMessages;

    if (hadBurst && populatedSections.length > revealedCount) {
      // Start progressive reveal with staggered timing
      if (revealTimerRef.current) clearTimeout(revealTimerRef.current);

      const revealNext = (idx: number) => {
        if (idx >= populatedSections.length) return;
        revealTimerRef.current = setTimeout(() => {
          setRevealedCount(idx + 1);
          // Auto-expand this section, collapse previous
          setExpanded(prev => {
            const next = { ...prev };
            // Collapse all except the newly revealed
            for (const s of SECTIONS) next[s.id] = false;
            next[populatedSections[idx].id] = true;
            return next;
          });
          revealNext(idx + 1);
        }, idx === 0 ? 300 : 1500); // First section fast, then 1.5s stagger
      };
      revealNext(revealedCount);
    } else if (!hadBurst && populatedSections.length > revealedCount) {
      // Incremental message (e.g., during live streaming) — reveal immediately
      setRevealedCount(populatedSections.length);
    }

    return () => {
      if (revealTimerRef.current) clearTimeout(revealTimerRef.current);
    };
  }, [messages.length, populatedSections.length]);

  // When all sections are revealed and pipeline done, expand all
  useEffect(() => {
    if (!isTracing && revealedCount >= populatedSections.length && populatedSections.length > 0) {
      const expandAll: Record<string, boolean> = {};
      for (const s of populatedSections) expandAll[s.id] = true;
      setExpanded(expandAll);
    }
  }, [isTracing, revealedCount, populatedSections.length]);

  // Reset on new incident
  useEffect(() => {
    if (messages.length === 0) {
      setRevealedCount(0);
      setExpanded({});
      prevMsgCountRef.current = 0;
    }
  }, [messages.length === 0]);

  const toggle = (id: string) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

  // Only show sections that have been revealed
  const visibleSections = populatedSections.slice(0, revealedCount);
  // Sections with data but not yet revealed show as "active" placeholders
  const pendingSections = populatedSections.slice(revealedCount, revealedCount + 1);

  return (
    <>
      {/* Revealed sections with full content */}
      {visibleSections.map(section => {
        const sectionMessages = grouped[section.id] ?? [];
        const sectionIdx = SECTIONS.indexOf(section);
        const isLast = sectionIdx === visibleSections.length - 1;
        const status: 'pending' | 'active' | 'complete' =
          isTracing && isLast ? 'active' : 'complete';
        const isExpanded = expanded[section.id] ?? false;

        return (
          <div
            key={section.id}
            className="animate-fade-slide"
            style={{
              marginBottom: '8px',
              border: `1px solid ${c.border}`,
              borderRadius: '6px',
              overflow: 'hidden',
              backgroundColor: c.bgCard,
            }}
          >
            <button
              onClick={() => toggle(section.id)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                backgroundColor: c.bgElevated,
                border: 'none',
                borderBottom: isExpanded ? `1px solid ${c.border}` : 'none',
                cursor: 'pointer',
                transition: 'background-color 0.15s',
              }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#131b2e'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#0f172a'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className={`chevron ${isExpanded ? '' : 'collapsed'}`}>▾</span>
                <span style={{
                  fontFamily: 'IBM Plex Mono, monospace',
                  fontSize: '9px',
                  color: status === 'active' ? '#93c5fd' : '#94a3b8',
                  letterSpacing: '0.12em',
                  fontWeight: 600,
                }}>
                  {section.label}
                </span>
                <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '9px', color: '#475569' }}>
                  ({sectionMessages.length})
                </span>
              </div>
              <StatusIcon status={status} />
            </button>

            <div className={`section-body ${isExpanded ? 'expanded' : 'collapsed'}`}>
              <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {sectionMessages.map(msg => (
                  <div key={msg.id}>{renderMessage(msg)}</div>
                ))}
              </div>
            </div>
          </div>
        );
      })}

      {/* Next section being "analyzed" — show as active placeholder */}
      {pendingSections.map(section => (
        <div
          key={section.id}
          className="animate-fade-slide"
          style={{
            marginBottom: '8px',
            border: '1px solid #111827',
            borderRadius: '6px',
            overflow: 'hidden',
            backgroundColor: '#0d1017',
          }}
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px',
            backgroundColor: '#0f172a',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '9px', color: '#93c5fd', letterSpacing: '0.12em', fontWeight: 600 }}>
                {section.label}
              </span>
              <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '9px', color: '#475569', fontStyle: 'italic' }}>
                analyzing...
              </span>
            </div>
            <StatusIcon status="active" />
          </div>
        </div>
      ))}

      {/* Chat messages render outside sections */}
      {chatMessages.map(msg => (
        <div key={msg.id} className="animate-fade-slide" style={{ marginBottom: '12px' }}>
          {msg.type === 'user' ? (
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <div style={{
                backgroundColor: '#172554', border: '1px solid #1e3a8a',
                borderRadius: '6px', padding: '8px 12px', maxWidth: '75%',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <span style={{
                    fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px',
                    color: '#60a5fa', fontWeight: 600,
                  }}>You</span>
                </div>
                <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: '1.6' }}>
                  {msg.text}
                </p>
              </div>
            </div>
          ) : msg.type === 'agent' ? (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <span style={{
                  fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px',
                  color: '#22c55e', fontWeight: 600,
                }}>Kratos</span>
              </div>
              <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: '1.6', wordBreak: 'break-word' }}>
                {msg.text}
              </p>
            </div>
          ) : null}
        </div>
      ))}
    </>
  );
}
