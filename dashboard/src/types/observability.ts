/**
 * dashboard/src/types/observability.ts
 *
 * TypeScript interfaces for the /obs API responses.
 * All types match the JSON shapes returned by src/obs_api.py.
 */

// ── /obs/metrics/live ────────────────────────────────────────────────────────

export interface LiveMetricsInvestigations {
  started_total: number;
  completed_total: number;
  in_flight: number;
  error_total: number;
  error_rate: number; // 0–1
}

export interface LiveMetricsPerformance {
  phase_p50_ms: number;
  phase_p95_ms: number;
  phase_p99_ms: number;
  phase_mean_ms: number;
}

export interface LiveMetricsEvidence {
  collected_total: number;
  rejected_total: number;
  signal_ratio: number; // 0–1
}

export interface LiveMetricsBacktracking {
  avg_hops: number;
  early_stops_total: number;
  max_hops_reached_total: number;
}

export interface LiveMetricsValidation {
  pass_total: number;
  fail_total: number;
  gate_fail_rate: number; // 0–1
}

export interface LiveMetricsConfidence {
  current_avg: number; // 0–1
  below_threshold_total: number;
  p50: number;
  p95: number;
}

export interface LiveMetricsSse {
  active_connections: number;
  events_emitted_total: number;
}

export interface LiveMetricsData {
  csv_records_loaded: number;
  smdia_exposures: number;
}

export interface LiveMetricsApi {
  request_p95_ms: number;
  error_total: number;
}

export interface LiveMetrics {
  investigations: LiveMetricsInvestigations;
  performance: LiveMetricsPerformance;
  evidence: LiveMetricsEvidence;
  backtracking: LiveMetricsBacktracking;
  validation: LiveMetricsValidation;
  confidence: LiveMetricsConfidence;
  sse: LiveMetricsSse;
  data: LiveMetricsData;
  api: LiveMetricsApi;
  timestamp: string; // ISO-8601
}

// ── /obs/traces/{investigation_id} ───────────────────────────────────────────

export interface ObsSpan {
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  name: string;
  start_time_ms: number;
  end_time_ms: number;
  duration_ms: number;
  status: "OK" | "ERROR" | "UNSET";
  attributes: Record<string, string | number | boolean>;
  events: ObsSpanEvent[];
}

export interface ObsSpanEvent {
  name: string;
  timestamp_ms: number;
  attributes: Record<string, string | number | boolean>;
}

// ── /obs/events ──────────────────────────────────────────────────────────────

export interface ObsEvent {
  event_id: string;
  event_name: string;
  timestamp: string; // ISO-8601
  trace_id: string | null;
  payload: Record<string, unknown>;
}

// ── /obs/logs/stream ─────────────────────────────────────────────────────────

export interface ObsLogLine {
  timestamp: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  logger: string;
  message: string;
  trace_id: string | null;
  span_id: string | null;
  investigation_id: string | null;
  scenario_id: string | null;
  phase: string | null;
  extra: Record<string, unknown>;
}

// ── /obs/alerts/active ───────────────────────────────────────────────────────

export type AlertSeverity = "CRITICAL" | "WARNING" | "INFO";

export interface ObsAlert {
  alert_id: string;
  name: string;
  severity: AlertSeverity;
  message: string;
  value: number;
  threshold: number;
  fired_at: string; // ISO-8601
}

// ── /obs/health ──────────────────────────────────────────────────────────────

export type HealthStatus = "ok" | "degraded" | "down";

export interface HealthCheckItem {
  status: HealthStatus;
  latency_ms: number | null;
  detail: string | null;
}

export interface HealthCheck {
  overall: HealthStatus;
  checks: Record<string, HealthCheckItem>;
  timestamp: string;
}
