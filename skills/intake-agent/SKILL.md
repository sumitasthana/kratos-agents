# Intake Agent Skill

## Trigger
Activates during Phase 1 (INTAKE) of every investigation. Also activates
when validating a scenario_id, parsing an anchor node from user input,
or checking whether a scenario pack is well-formed before proceeding.

## Primary Responsibility
Validate the investigation request, resolve the ontology anchor, load the
scenario pack from disk, seed the InvestigationState with the correct CanonGraph,
and confirm the investigation is ready to proceed to LOGS_FIRST.

---

## Validation Checklist (Run in Order)

1. **Scenario ID exists** — check `ScenarioRegistry.scenario_ids()`. If unknown,
   return `AnchorNotFound` error with list of valid IDs.

2. **Scenario pack is well-formed** — `ScenarioPack` must have:
   - `incident.json`: `incident_id`, `severity`, `anchor_type` present
   - `job_run.json`: `job_id`, `status`, `started_at` present
   - `logs/*.log`: at least one log file present
   - `controls.json`: at least one control entry present
   - `sample_data/accounts.json`: at least one account present

3. **Anchor resolution** — extract anchor node from `incident.json`:
   - `anchor_type` must be one of: `Incident | Violation | Job | Pipeline | System`
   - `anchor_primary_key` derived from anchor_type (e.g., `incident_id` for Incident)
   - `anchor_primary_value` is the INC-XXX / JOB-XXX identifier

4. **CanonGraph seed** — call `ScenarioSeeder.seed(scenario_id)`:
   - Returns a hardcoded `CanonGraph` from `demo/ontology/canon_graphs.py`
   - Verify `anchor_neo4j_id != "NOT_FOUND"` (R6 gate)
   - Verify graph has ≥ 6 nodes and ≥ 5 edges (minimum for 6-hop path)

5. **InvestigationState init** — create new state with:
   - `investigation_id`: new UUID
   - `status`: `INITIALIZING`
   - `canon_graph`: seeded graph from step 4
   - `investigation_input.anchor`: resolved anchor from step 3

---

## Anchor Type → Ontology Label Mapping

| anchor_type | CanonNode label | primary_key field |
|---|---|---|
| `Incident` | `Incident` | `incident_id` |
| `Violation` | `Violation` | `violation_id` |
| `Job` | `Job` | `job_id` |
| `Pipeline` | `Pipeline` | `pipeline_id` |
| `System` | `Job` (closest) | `system_name` |

---

## Known Anchors (Demo Mode)

| scenario_id | anchor_type | anchor_primary_value |
|---|---|---|
| `deposit_aggregation_failure` | `Incident` | `INC-001` |
| `trust_irr_misclassification` | `Incident` | `INC-002` |
| `wire_mt202_drop` | `Incident` | `INC-003` |

---

## Error Response Schema

```json
{
  "error": "ANCHOR_NOT_FOUND | SCENARIO_INVALID | PACK_MALFORMED | GRAPH_SEED_FAILED",
  "message": "<human-readable description>",
  "detail": {
    "scenario_id": "<provided value>",
    "valid_scenarios": ["deposit_aggregation_failure", "trust_irr_misclassification", "wire_mt202_drop"],
    "blocking_check": "<which validation step failed>"
  }
}
```

---

## Conversational Parsing (When anchor_type is inferred from natural language)

If the user provides a description rather than a structured JSON, extract:

1. **System clue words → scenario_id mapping**:
   - "deposit", "aggregation", "SMDIA", "overstated coverage" → `deposit_aggregation_failure`
   - "trust", "irrevocable", "IRR", "misclassified", "fiduciary" → `trust_irr_misclassification`
   - "wire", "MT202", "SWIFT", "GL break", "dropped" → `wire_mt202_drop`

2. **If ambiguous**, ask ONE clarifying question:
   "Which system is affected — deposit processing, trust accounts, or wire transfers?"

3. **Default job_id per scenario**:
   - `deposit_aggregation_failure` → `DAILY-INSURANCE-JOB-20260316`
   - `trust_irr_misclassification` → `TRUST-DAILY-BATCH-20260316`
   - `wire_mt202_drop` → `WIRE-NIGHTLY-RECON-20260316`

---

## Output Schema

```json
{
  "investigation_id": "<uuid>",
  "scenario_id": "<string>",
  "job_id": "<string>",
  "anchor": {
    "anchor_type": "Incident",
    "anchor_primary_key": "incident_id",
    "anchor_primary_value": "INC-001"
  },
  "canon_graph_node_count": 0,
  "canon_graph_edge_count": 0,
  "status": "READY | BLOCKED",
  "blocking_reason": null
}
```

---

## Audit Trace Entry

```python
AuditEntry(
    phase=PhaseEnum.INTAKE,
    agent="IntakeAgent",
    action=AuditAction.ACCEPTED,
    evidence_id=None,
    reason="Anchor INC-001 resolved. CanonGraph seeded: 8 nodes, 7 edges. Ready for LOGS_FIRST."
)
```
