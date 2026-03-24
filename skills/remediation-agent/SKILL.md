# Remediation Generation Skill

## Trigger
Activates during Phase 6 (RECOMMEND). Also activates when the user asks:
"How do I fix this?", "What's the remediation?", "What needs to change?",
"What's the fix for DEF-XXX?", or "Give me the action plan."

## Primary Responsibility
Generate a ranked, evidence-grounded list of `RemediationAction` objects.
Every action must cite a real `defect_id` from the confirmed hypothesis set,
a real FDIC regulation section, and a real file path in `operational_systems/`.

---

## Grounding Rules (Anti-Hallucination — All Required)

1. **defect_ref** must be a `defect_id` that appears in the confirmed hypothesis
   set (`state.hypotheses` with `status=CONFIRMED` or `status=SUPPORTED`).
2. **regulation_citation** must be an exact section from 12 CFR Part 330 or 370.
   No paraphrasing. No inventing sections. Only cite sections that exist.
3. **file** must correspond to a real path under `operational_systems/`:
   - `operational_systems/legacy_deposit_system/...`
   - `operational_systems/trust_custody_system/...`
   - `operational_systems/wire_transfer_system/...`
4. **Never** recommend actions for defects not in the confirmed hypothesis set
   (even if other defects are known — stay scoped to the investigation).

---

## Action Type Definitions

Choose **exactly one** type per action:

| Type | When to use | Required extra fields |
|---|---|---|
| `CODE_FIX` | Source file change (COBOL, Java, Python, JCL) | `file`, `line_range`, `before`, `after` |
| `CONFIG_UPDATE` | JCL/properties parameter change | `file`, `param_name`, `current_value`, `correct_value` |
| `CONTROL_ADD` | New control or monitoring rule required | `control_id`, `frequency`, `threshold` |
| `PROCESS_CHANGE` | Operational procedure update (no code change) | `procedure_name`, `change_description` |
| `DATA_REMEDIATION` | Retroactive data correction required | `validation_query` (SQL or grep command) |

---

## Priority Ordering Rules

1. **Priority 1**: The action that directly fixes `root_cause_final`.
2. **Priority 2**: Secondary defects from the same system (same DEF-XXX-* prefix).
3. **Priority 3**: Detective control additions (to catch similar failures earlier).
4. **Priority 4**: Data remediation (retroactive correction of affected accounts).
5. **Priority 5**: Always end with a **validation step** (how to confirm the fix worked).

---

## Per-Scenario Remediation Playbooks

### deposit_aggregation_failure (DEF-LDS-001)

**Action 1 — CODE_FIX (Priority 1 — Root Cause)**:
- `file`: `operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl`
- Fix: Uncomment `//AGGRSTEP EXEC PGM=AGGR0001` at Step 3
- `regulation_citation`: `12 CFR § 330.1(b)` — per-depositor aggregation requirement
- `validation_query`: `grep -n "AGGRSTEP" DAILY-INSURANCE-JOB.jcl | grep -v "/\*"`

**Action 2 — CODE_FIX (Priority 2)**:
- `file`: `operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl`
- Fix: Change field delimiter from comma to pipe (DEF-LDS-004)
- `regulation_citation`: `12 CFR § 330.1(b)`

**Action 3 — DATA_REMEDIATION (Priority 4)**:
- `validation_query`: `SELECT COUNT(*) FROM accounts WHERE current_balance > 250000 AND orc_code IN ('Joint_JTWROS','Business_LLC','Trust_Revocable')`
- Description: Re-run aggregation on 1,951 accounts with balance > $250,000 after AGGRSTEP fix

**Action 4 — CONTROL_ADD (Priority 3)**:
- Add CI/CD gate that fails the JCL deploy if any EXEC step is commented out
- `regulation_citation`: `12 CFR § 330.6` — change control for insurance calculation systems

### trust_irr_misclassification (DEF-TCS-001)

**Action 1 — CODE_FIX (Priority 1 — Root Cause)**:
- `file`: `operational_systems/trust_custody_system/cobol/TRUST-INSURANCE-CALC.cob`
- Fix: Implement IRR branch in ORC assignment logic (currently missing, falls to SGL)
- `regulation_citation`: `12 CFR § 330.13` — irrevocable trust coverage rules

**Action 2 — CODE_FIX (Priority 2)**:
- `file`: `operational_systems/trust_custody_system/java/BeneficiaryClassifier.java`
- Fix: Add `case "IRR":` branch in the ORC switch statement (currently falls through to `"SGL"`)
- `regulation_citation`: `12 CFR § 330.13`

**Action 3 — DATA_REMEDIATION (Priority 4)**:
- `validation_query`: `SELECT COUNT(*), SUM(current_balance) FROM accounts WHERE orc_code = 'Trust_Irrevocable' AND account_status = 'Active'`
- Expected: 253 accounts, ~$61.8M to reprocess

### wire_mt202_drop (DEF-WTS-001)

**Action 1 — CODE_FIX (Priority 1 — Root Cause)**:
- `file`: `operational_systems/wire_transfer_system/python/swift_parser.py`
- Fix: Add `elif msg_type in ("MT202", "MT202COV"):` branch in `parse_message()` with full handler
- `regulation_citation`: `12 CFR § 370.4(a)(1)` — daily balance snapshot accuracy

**Action 2 — DATA_REMEDIATION (Priority 4)**:
- `validation_query`: `grep -c "MT202" /logs/WIRE-NIGHTLY-RECON-*.log`
- Description: Recover 47 dropped MT202 + 12 MT202COV messages; reconcile $284,700,000 GL break

**Action 3 — CONTROL_ADD (Priority 3)**:
- Add message-type coverage test in CI: every SWIFT message type (MT103, MT202, MT202COV) must have a handler assertion
- `regulation_citation`: `12 CFR § 370.4(a)(1)`

---

## Output Schema Per Action

```json
{
  "action_id": "REM-001",
  "type": "CODE_FIX",
  "priority": 1,
  "defect_ref": "DEF-LDS-001",
  "regulation_citation": "12 CFR § 330.1(b)",
  "description": "Uncomment the AGGRSTEP EXEC step (Step 3) in DAILY-INSURANCE-JOB.jcl to restore depositor-level aggregation.",
  "file": "operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl",
  "line_range": [42, 44],
  "before": "// *AGGRSTEP EXEC PGM=AGGR0001",
  "after": "//AGGRSTEP  EXEC PGM=AGGR0001",
  "validation_query": "grep -n 'AGGRSTEP' DAILY-INSURANCE-JOB.jcl | grep -v '/\\*'"
}
```

---

## Conversational Response Format

```
**Remediation Plan** for INC-001 (DEF-LDS-001):

1. [CODE_FIX · Priority 1] Uncomment AGGRSTEP in DAILY-INSURANCE-JOB.jcl (line 43).
   Regulation: 12 CFR § 330.1(b). Validates with: grep -n "AGGRSTEP" ... | grep -v "/*"

2. [DATA_REMEDIATION · Priority 4] Re-run aggregation on 1,951 over-SMDIA accounts.
   Query: SELECT COUNT(*) FROM accounts WHERE current_balance > 250000

3. [CONTROL_ADD · Priority 3] Add JCL step-commenting CI gate.

Want the full change diff for Action 1?
```

---

## Audit Trace Entry

```python
AuditEntry(
    phase=PhaseEnum.RECOMMEND,
    agent="RemediationAgent",
    action=AuditAction.ACCEPTED,
    evidence_id=None,
    reason="3 RemediationActions generated for DEF-LDS-001. Priority 1 addresses root_cause_final directly. Regulation: 12 CFR § 330.1(b)."
)
```
