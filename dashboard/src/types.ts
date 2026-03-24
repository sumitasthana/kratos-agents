export type Severity = 'Critical' | 'High' | 'Medium' | 'Low';

export interface Incident {
  id:          string;       // "INC-001"
  job_name:    string;       // "PaymentProcessor-Main"
  error_msg:   string;       // "RuntimeError: Transaction failed"
  job_id:      string;       // "job-8842"
  timestamp:   string;       // "2023-10-27 14:20:01"
  severity:    Severity;
  scenario_id: string;       // "deposit_aggregation_failure"
}

export interface HopEvent {
  phase:      string;        // "LOGS_FIRST"
  hop:        number;        // 2
  skill:      string;        // "log-analyst"
  summary:    string;        // one-sentence finding
  evidence?:  EvidenceRef;
  confidence?: ConfidenceBreakdown;
}

export interface EvidenceRef {
  file:    string;
  lang:    string;
  snippet: string;
  label:   string;
}

export interface ConfidenceBreakdown {
  composite: number;
  tier:      'LOW' | 'MEDIUM' | 'HIGH' | 'CONFIRMED';
  E: number; T: number; D: number; H: number;
}

export interface RcaResult {
  incident_id:          string;
  root_cause_final:     string | null;
  defect_id:            string | null;
  confidence:           ConfidenceBreakdown;
  regulation_citations: string[];
  remediation:          RemAction[];
  audit_trace:          AuditEntry[];
}

export interface RemAction {
  rank:        number;
  defect_id:   string;
  priority:    number;
  title:       string;
  artifact:    string;
  action:      string;
  regulation:  string;
  effort:      string;
  confidence:  number;
}

export interface ChatMsg {
  role:    'user' | 'assistant';
  content: string;
  ts:      string;
}

export interface AuditEntry {
  ts:     string;
  agent:  string;
  action: string;
  detail: string;
}

export interface ControlResult {
  control_id:  string;
  status:      'PASS' | 'FAIL' | 'WARN' | 'MISSING';
  description: string;
  regulation:  string;
  gap?:        string;
}

export interface PhaseStep {
  phase:        string;
  phase_number: number;
  status:       string;
  summary:      string;
  agent:        string;
  details:      Record<string, unknown>;
}

export interface HopNode {
  from_node_id: string;
  to_node_id:   string;
  rel_type:     string;
  hop_index:    number;
  status:       string;   // "confirmed" | "artifact_defect"
}
