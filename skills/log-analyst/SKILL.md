# Log Analyst Skill

## Trigger
Activates during Phase 2 (LOGS_FIRST) of every investigation. Also activates
when a user pastes a raw log snippet and asks what it means, or when the
orchestrator needs to classify a log file before dispatching to ROUTE.

## Primary Responsibility
Read the log file for the active scenario, locate the defect signal line,
construct one or more `EvidenceObject` records with correct tier labels,
and return them for appending to `state.evidence_objects`.

---

## Log Signal Patterns (Exact Match Required)

| pattern_id | Log signal (exact substring) | tier | scenario |
|---|---|---|---|
| `DEMO-AGG-001` | `AGGRSTEP — skipped (disabled in JCL)` | CRITICAL | `deposit_aggregation_failure` |
| `DEMO-IRR-001` | `fallback ORC=SGL (IRR not implemented)` | CRITICAL | `trust_irr_misclassification` |
| `DEMO-MT202-001` | `silently dropped (no handler)` | CRITICAL | `wire_mt202_drop` |

These are **exact substring matches** — no fuzzy matching, no regex.
If none are found, produce a `MissingEvidence` object with `blocking=True`.

---

## Log Reading Protocol

1. Get log file path from `ScenarioPack.log_filename` (relative to `scenarios/`).
2. Read the full log text. Do not truncate — logs are ≤ 500 lines.
3. Scan line-by-line for the signal substring.
4. Record the **first matching line number**, the **full line text**, and
   the **surrounding 3 lines** (context window) in `content`.
5. If the signal appears on multiple lines, record all occurrences as SIGNAL-tier
   evidence objects, plus the first as CRITICAL.

---

## EvidenceObject Construction

For the CRITICAL defect line:
```python
EvidenceObject(
    evidence_id="EVD-" + uuid4_short(),
    source_system="batch_log",
    source_file="scenarios/<scenario_id>/logs/<filename>.log",
    entity_type="job_step",
    entity_id="<job_id>",
    tier="CRITICAL",
    content={
        "line_number": 0,
        "line_text": "<full matching line>",
        "context_before": ["<line n-1>", "<line n-2>"],
        "context_after": ["<line n+1>", "<line n+2>"],
        "signal_matched": "<exact signal string>",
        "pattern_id": "<DEMO-XXX-001>"
    },
    timestamp=<job_run.started_at parsed as datetime>
)
```

For secondary SIGNAL lines (errors, warnings near the signal):
```python
EvidenceObject(
    evidence_id="EVD-" + uuid4_short(),
    tier="SIGNAL",
    content={...same structure...}
)
```

---

## Secondary Signal Keywords

After finding the primary signal, scan for these secondary patterns and
produce SIGNAL-tier EvidenceObjects for each cluster found:

| keyword | entity_type | notes |
|---|---|---|
| `ERROR` or `FATAL` | `log_error` | within 10 lines of primary signal |
| `FAILED` or `ABEND` | `job_failure` | anywhere in log |
| `accounts_processed: 0` or ` processed=0` | `metric_zero` | indicates no-op run |
| `ORC=SGL` (when scenario is IRR) | `orc_mismatch` | repeated fallback |
| `dropped` + `MT202` | `message_drop` | any line with both tokens |

Do not produce more than 10 EvidenceObjects per log file.

---

## Missing Evidence Protocol

If the primary signal **is not found** in the log:

```python
MissingEvidence(
    missing_evidence_id="MEV-001",
    description="Primary log signal not found in <filename>.log",
    expected_source="batch_log",
    expected_entity_id="<job_id>",
    blocking=True,
    resolution_hint="Provide the job execution log containing the AGGRSTEP/IRR/MT202 signal"
)
```

Append to `state.missing_evidence`. Set `state.status = INSUFFICIENT_EVIDENCE`.
Do NOT proceed to ROUTE — gate R8 will block PERSIST anyway. Surface the blocker early.

---

## Temporal Ordering Rule

All EvidenceObjects produced in this phase must carry a `timestamp` that is:
- Equal to or after `job_run.started_at`
- Equal to or before `job_run.ended_at` (if present)
- If log line has a timestamp, parse it; otherwise, use `job_run.started_at + line_offset_seconds`

Temporal ordering is required for CausalEngine's edge validation (time arrow constraint).

---

## Output Schema

```json
{
  "evidence_objects": [
    {
      "evidence_id": "EVD-001",
      "tier": "CRITICAL",
      "source_system": "batch_log",
      "signal_matched": "AGGRSTEP — skipped (disabled in JCL)",
      "pattern_id": "DEMO-AGG-001"
    }
  ],
  "missing_evidence": [],
  "primary_signal_found": true,
  "pattern_id_triggered": "DEMO-AGG-001"
}
```

---

## Audit Trace Entry

```python
AuditEntry(
    phase=PhaseEnum.LOGS_FIRST,
    agent="LogAnalystAgent",
    action=AuditAction.ACCEPTED,    # REJECTED if signal not found
    evidence_id="EVD-001",
    reason="Signal 'AGGRSTEP — skipped (disabled in JCL)' found at line 47. Pattern DEMO-AGG-001 triggered. Tier: CRITICAL."
)
```
