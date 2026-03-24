/**
 * types/demo.ts
 *
 * Shared TypeScript interfaces for the Kratos Demo UI.
 * Every component and hook imports from here. No inline types.
 */

export type RuntimeState = 'BOOT' | 'IDLE' | 'RUNNING' | 'CONFIRMED' | 'ERROR';

export type ScenarioId =
  | 'deposit_aggregation_failure'
  | 'trust_irr_misclassification'
  | 'wire_mt202_drop';

export interface ScenarioMeta {
  id: ScenarioId;
  title: string;
  subtitle: string;
  system: string;
  controlFailed: string;
  defectId: string;
  defaultJobId: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
  color: 'amber' | 'red' | 'green';
}

export interface ScenarioSummary {
  scenario_id: ScenarioId;
  incident_id: string;
  title: string;
  severity: string;
  regulation: string;
  job_id: string;
  total_accounts: number;
  total_controls: number;
  failed_controls: number;
  description: string;
}

export interface BootState {
  stage: 'CONNECTING' | 'LOADING_SCENARIOS' | 'LOADING_CSV' | 'SEEDING_ONTOLOGY' | 'READY' | 'FAILED';
  message: string;
  scenariosLoaded: number;
  recordsLoaded: number;
  nodesSeeded: number;
  elapsed: number;
  error?: string;
  completedStages: number;
  stageTimings: Partial<Record<BootState['stage'], number>>;
}

export interface StatusBarState {
  runtimeState: RuntimeState;
  scenarioId: ScenarioId | undefined;
  activePhase: string | undefined;
  currentHop: number | undefined;
  totalHops: number | undefined;
  confidence: number | undefined;
  recordsLoaded: number;
  latencyMs: number | undefined;
  // Observability section (optional — populated only when obs API is reachable)
  obsP95Ms: number | null;
  obsAlertCount: number;
  obsSseConnections: number;
  obsError: boolean;
}
