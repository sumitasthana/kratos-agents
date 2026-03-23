/**
 * types/causelink.ts
 *
 * CauseLink domain interfaces matching the backend InvestigationState,
 * CanonGraph, SSE events, and all phase-level structures.
 */

export type PhaseId =
  | 'INTAKE'
  | 'LOGS_FIRST'
  | 'ROUTE'
  | 'BACKTRACK'
  | 'INCIDENT_CARD'
  | 'RECOMMEND'
  | 'PERSIST';

export type PhaseStatus = 'PENDING' | 'RUNNING' | 'PASS' | 'FAIL';
export type HopStatus = 'UNKNOWN' | 'CONFIRMED_FAILED' | 'PASSING' | 'ROOT_CAUSE';
export type InvestigationStatus =
  | 'STARTED'
  | 'RUNNING'
  | 'CONFIRMED'
  | 'INCONCLUSIVE'
  | 'ESCALATED'
  | 'ERROR'
  | 'COMPLETED'
  | 'ONTOLOGY_LOADING'
  | 'EVIDENCE_COLLECTION'
  | 'HYPOTHESIS_GENERATION'
  | 'CAUSAL_ANALYSIS'
  | 'VALIDATION';
export type ControlStatus = 'PASS' | 'FAIL' | 'WARN' | 'NOT_APPLICABLE' | 'FAILED' | 'PASSED' | 'WARNING';
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

// ── Ontology ────────────────────────────────────────────────────────────────

export interface CanonNode {
  id: string;
  label: string;
  props: Record<string, unknown>;
}

export interface CanonEdge {
  from: string;
  to: string;
  type: string;
  // Legacy keys from backend
  from_node_id?: string;
  to_node_id?: string;
  rel_type?: string;
}

export interface CanonGraph {
  nodes: CanonNode[];
  edges: CanonEdge[];
}

// ── Backtracking ─────────────────────────────────────────────────────────────

export interface BacktrackHop {
  hopIndex: number;
  fromNodeId: string;
  toNodeId: string;
  relType: string;
  status: HopStatus;
  evidenceIds: string[];
  nodeLabel: string;
  nodeName: string;
}

// ── Phases ───────────────────────────────────────────────────────────────────

export interface PhaseResult {
  phase: PhaseId;
  phaseNumber: number;
  investigationId: string;
  scenarioId: string;
  status: string;
  summary: string;
  details: Record<string, unknown>;
  emittedAt: string;
  // Computed on the frontend
  uiStatus?: PhaseStatus;
  agentsInvoked?: string[];
  evidenceAdded?: number;
  hypothesesAdded?: number;
  hopsRevealed?: BacktrackHop[];
  auditEntries?: AuditEntry[];
  durationMs?: number;
}

// ── Audit ────────────────────────────────────────────────────────────────────

export interface AuditEntry {
  phase: PhaseId;
  agent: string;
  action: 'ACCEPTED' | 'REJECTED' | 'PROMOTED' | 'CONFIRMED';
  evidenceId?: string;
  reason: string;
  timestamp: string;
}

// ── Controls ─────────────────────────────────────────────────────────────────

export interface ControlFinding {
  control_id: string;
  controlId?: string;
  name: string;
  citation?: string;
  regulation?: string;
  status: ControlStatus;
  finding?: string;
  failure_reason?: string | null;
  severity: Severity;
  affectedCount?: number;
  defect_id?: string | null;
  artifact?: string | null;
  last_tested?: string | null;
}

// ── Control scan result ───────────────────────────────────────────────────────

export interface ControlScanResult {
  scenario_id: string;
  incident_id: string;
  scanned_at: string;
  total_controls: number;
  passed: number;
  failed: number;
  warnings: number;
  critical_failures: number;
  has_critical_failure: boolean;
  findings: ControlFinding[];
}

// ── Recommendations ──────────────────────────────────────────────────────────

export interface Recommendation {
  rank: number;
  action: string;
  artifactRef?: string;
  artifact?: string;          // alias for artifactRef
  lineRef?: string;
  regulatoryBasis?: string;
  regulation?: string;        // alias for regulatoryBasis
  effort?: 'LOW' | 'MEDIUM' | 'HIGH';
  impact?: Severity;
  severity?: Severity;        // alias for impact
  confidence?: number;
  defectId?: string;
  defect_id?: string;         // snake_case alias
}

// ── Confidence ───────────────────────────────────────────────────────────────

export interface ConfidenceBreakdown {
  // camelCase (frontend canonical)
  evidenceScore: number;
  temporalScore: number;
  depthScore: number;
  hypothesisScore: number;
  composite: number;
  threshold: number;
  confirmed: boolean;
  // snake_case aliases (from backend PhaseEvent details)
  evidence_score?: number;
  temporal_score?: number;
  depth_score?: number;
  hypothesis_alignment_score?: number;
  composite_score?: number;
  weights?: { evidence: number; temporal: number; depth: number; hypothesis: number };
  validationGates?: Record<string, 'PASS' | 'FAIL'>;
}

// ── Incident ──────────────────────────────────────────────────────────────────

export interface IncidentCard {
  incidentId: string;
  scenarioId: string;
  jobId: string;
  title: string;
  description: string;
  severity: Severity;
  failedControl?: ControlFinding;
  rootCauseNodeId: string;
  rootCauseLabel: string;
  rootCauseDescription: string;
  artifactRef: string;
  defectId: string;
  regulatoryCitation: string;
  causalPath: string[];
  elapsedMs: number;
  // camelCase extras (may not always be present)
  controlId?: string;
  controlName?: string;
  regulation?: string;
  status?: string;
  reportedAt?: string;
  defectArtifact?: string;
  defectDescription?: string;
  impact?: Record<string, unknown>;
  // snake_case aliases from backend
  incident_id?: string;
  control_id?: string;
  control_name?: string;
  defect_id?: string;
  defect_artifact?: string;
  defect_description?: string;
  reported_at?: string;
}

// ── Rejected alternatives ─────────────────────────────────────────────────────

export interface RejectedAlternative {
  hypothesisId: string;
  description: string;
  rejectionReason: string;
  patternId: string;
}

// ── Full investigation state (frontend) ───────────────────────────────────────

export interface InvestigationState {
  investigationId: string;
  scenarioId: string;
  jobId: string;
  status: InvestigationStatus;
  currentPhase: PhaseId;
  phases: Partial<Record<PhaseId, PhaseResult>>;
  canonGraph: CanonGraph;
  backtrackChain: BacktrackHop[];
  controls: ControlFinding[];
  incidentCard: IncidentCard | null;
  recommendations: Recommendation[];
  rejectedAlternatives: RejectedAlternative[];
  confidence: ConfidenceBreakdown | null;
  auditTrace: AuditEntry[];
  startedAt: string;
  completedAt: string | null;
  validationGates: Record<string, 'PASS' | 'FAIL'>;
  rawPhaseEvents: PhaseResult[];
  thoughts: AgentThought[];
}

// ── SSE events ────────────────────────────────────────────────────────────────

export type SSEEventType =
  | 'PHASE_COMPLETE'
  | 'HOP_REVEALED'
  | 'INVESTIGATION_COMPLETE'
  | 'ERROR'
  | 'KEEPALIVE'
  | 'AGENT_THOUGHT';

// ── Agent reasoning ───────────────────────────────────────────────────────────

export type ThoughtType =
  | 'OBSERVING'
  | 'HYPOTHESISING'
  | 'TESTING'
  | 'REJECTING'
  | 'ACCEPTING'
  | 'CONCLUDING'
  | 'WARNING';

export interface AgentThought {
  agent: string;
  step_index: number;
  thought_type: ThoughtType;
  content: string;
  evidence_refs: string[];
  node_refs: string[];
  confidence_delta: number;
  phase: string;
  timestamp?: string;
}

// ── Infrastructure adapter ────────────────────────────────────────────────────

export interface AdapterMeta {
  adapter_id: string;
  display_name: string;
  environment: string;
}

export interface SSEEvent {
  // New format (when type field is present)
  type?: SSEEventType;
  phase?: PhaseId | string;
  data?: Partial<Record<string, unknown>>;
  timestamp?: string;
  // Legacy PhaseEvent fields (when type is absent)
  phase_number?: number;
  investigation_id?: string;
  scenario_id?: string;
  status?: string;
  summary?: string;
  details?: Record<string, unknown>;
  emitted_at?: string;
}
