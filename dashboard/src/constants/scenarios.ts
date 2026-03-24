/**
 * constants/scenarios.ts
 *
 * SCENARIO_META — display names, defect IDs, colors, and job defaults
 * for the three FDIC Part 370/330 demo scenarios.
 */

import type { ScenarioMeta } from '../types/demo';

export const SCENARIO_META: ScenarioMeta[] = [
  {
    id: 'deposit_aggregation_failure',
    title: 'Deposit Aggregation Failure',
    subtitle: 'AGGRSTEP disabled — 1,951 accounts under-insured',
    system: 'legacy_deposit_system',
    controlFailed: 'C2 — Coverage Calculation Accuracy',
    defectId: 'DEF-LDS-001',
    defaultJobId: 'DAILY-INSURANCE-JOB-20260316',
    severity: 'CRITICAL',
    color: 'red',
  },
  {
    id: 'trust_irr_misclassification',
    title: 'Trust IRR Misclassification',
    subtitle: 'IRR→SGL fallback — $61.8M coverage gap',
    system: 'trust_custody_system',
    controlFailed: 'A3 — Fiduciary Documentation',
    defectId: 'DEF-TCS-001',
    defaultJobId: 'TRUST-DAILY-BATCH-20260316',
    severity: 'CRITICAL',
    color: 'amber',
  },
  {
    id: 'wire_mt202_drop',
    title: 'Wire MT202 Drop',
    subtitle: 'MT202/MT202COV silently dropped — $284.7M GL break',
    system: 'wire_transfer_system',
    controlFailed: 'B1 — Daily Balance Snapshot',
    defectId: 'DEF-WTS-001',
    defaultJobId: 'WIRE-NIGHTLY-RECON-20260316',
    severity: 'CRITICAL',
    color: 'green',
  },
];

export const SCENARIO_META_MAP: Record<string, ScenarioMeta> = Object.fromEntries(
  SCENARIO_META.map((s) => [s.id, s])
);

export const PHASE_ORDER = [
  'INTAKE',
  'LOGS_FIRST',
  'ROUTE',
  'BACKTRACK',
  'INCIDENT_CARD',
  'RECOMMEND',
  'PERSIST',
] as const;

export const PHASE_LABELS: Record<string, string> = {
  INTAKE:        '1. Intake',
  LOGS_FIRST:    '2. Logs',
  ROUTE:         '3. Route',
  BACKTRACK:     '4. Backtrack',
  INCIDENT_CARD: '5. Incident',
  RECOMMEND:     '6. Recommend',
  PERSIST:       '7. Persist',
};

export const TOTAL_PHASES = PHASE_ORDER.length;
