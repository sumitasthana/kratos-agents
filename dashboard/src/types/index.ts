export type Priority = 'P1' | 'P2' | 'P3' | 'P4';

export type IncidentStatus = 'active' | 'investigating' | 'resolved';

export interface Incident {
  id: string;
  service: string;
  severity: Priority;
  error: string;
  job: string;
  status: IncidentStatus;
  timestamp?: string;
}

export type MessageType =
  | 'system'
  | 'agent'
  | 'hop'
  | 'evidence'
  | 'triangulation'
  | 'recommendation';

export type PhaseId =
  | 'INTAKE'
  | 'LOGS_FIRST'
  | 'ROUTE'
  | 'BACKTRACK'
  | 'INCIDENT_CARD'
  | 'RECOMMEND'
  | 'PERSIST';

interface BaseMessage {
  id: string;
  phase: PhaseId;
  timestamp: number;
}

export interface SystemMessage extends BaseMessage {
  type: 'system';
  text: string;
}

export interface AgentMessage extends BaseMessage {
  type: 'agent';
  agent: string;
  text: string;
  tag?: 'evidence' | 'finding' | 'info';
}

export interface Hop {
  from: string;
  edge: string;
  to: string;
}

export interface HopMessage extends BaseMessage {
  type: 'hop';
  hops: Hop[];
}

export interface EvidenceMessage extends BaseMessage {
  type: 'evidence';
  source: string;
  filename: string;
  language: string;
  defect: string;
  code: string;
}

export interface TriangulationMessage extends BaseMessage {
  type: 'triangulation';
  confidence: number;
  rootCause: string;
  regulation: string;
  defect: string;
}

export interface RecommendationItem {
  priority: Priority;
  action: string;
  owner: string;
  effort: string;
  regulation?: string;
}

export interface RecommendationMessage extends BaseMessage {
  type: 'recommendation';
  items: RecommendationItem[];
}

export type RcaMessage =
  | SystemMessage
  | AgentMessage
  | HopMessage
  | EvidenceMessage
  | TriangulationMessage
  | RecommendationMessage;
