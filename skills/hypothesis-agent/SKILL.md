# Hypothesis Generation Skill

## Trigger
Activates during BACKTRACK Phase 4c, and whenever the user asks:
"What caused X?", "What could have failed?", "What's the hypothesis?",
or any variation requesting causal explanation.

## Primary Responsibility
Generate a ranked list of hypotheses grounded in `HypothesisPatternLibrary`.
Every hypothesis must cite a real `pattern_id`, a real `defect_id`, and at least
one real `EvidenceObject` from current state. Hypotheses without evidence are invalid.

---

## Pattern-First Rule (Non-Negotiable)

No `Hypothesis` object may be created without a matching pattern from
`HypothesisPatternLibrary`. The demo patterns are:

| pattern_id | Fires when | DEF-ID linked |
|---|---|---|
| `DEMO-AGG-001` | Log contains `"AGGRSTEP — skipped (disabled in JCL)"` | DEF-LDS-001 |
| `DEMO-IRR-001` | Log contains `"fallback ORC=SGL (IRR not implemented)"` | DEF-TCS-001, DEF-TCS-003 |
| `DEMO-MT202-001` | Log contains `"silently dropped (no handler)"` | DEF-WTS-001 |

Built-in library patterns (CLK-P001 through CLK-P008) are also valid.
Any `pattern_id` not in this list → reject, log `REJECTED` to audit_trace.

---

## Generation Rules

1. Query `HypothesisPatternLibrary.match(state)` to get `PatternMatchResult` list.
2. Filter to `satisfied=True` results only.
3. For each satisfied pattern, check:
   - **R2**: `defect_id` maps to a known pattern → reject unknowns
   - **R3**: All `involved_node_ids` exist in `canon_graph.nodes` → reject if any missing
   - At least one `evidence_ref` points to a real `EvidenceObject.evidence_id` in state
4. If all three checks pass → status: `CANDIDATE`
5. Rank by `confidence_prior` descending. Present top 3, generate at most 5.
6. A hypothesis with zero `evidence_refs` is **INVALID** — discard silently
   (do NOT log an error — simply skip and move to the next pattern).

---

## Anti-Hallucination Checks (Detailed)

| Check | Pass condition | Fail action |
|---|---|---|
| R2: pattern_id known | `pattern_id` in `HypothesisPatternLibrary.all_pattern_ids()` | status=REJECTED, log reason |
| R3: nodes exist | All `involved_node_ids` in `state.canon_graph.nodes` keys | status=REJECTED, log reason |
| Evidence grounded | `len(evidence_refs) >= 1` | Discard silently |
| Defect ID registered | `defect_id` in known defect registry (see CLAUDE.md) | status=REJECTED, log reason |

---

## Hypothesis Ranking by Prior

After generating candidates, order by `confidence_prior` descending:

| Scenario | Rank 1 hypothesis | Prior |
|---|---|---|
| `deposit_aggregation_failure` | AGG_STEP_DISABLED (DEF-LDS-001) | 0.92 |
| `trust_irr_misclassification` | IRR_NOT_IMPLEMENTED (DEF-TCS-001) | 0.90 |
| `wire_mt202_drop` | MT202_HANDLER_MISSING (DEF-WTS-001) | 0.93 |

Present top 3. If only 1 passes all checks, present that one with note that
alternatives were filtered by R2/R3 — do not fabricate additional hypotheses.

---

## Output Schema

```json
{
  "hypothesis_id": "HYP-001",
  "defect_id": "DEF-LDS-001",
  "pattern_id": "DEMO-AGG-001",
  "description": "Step 3 (AGGRSTEP) was commented out in DAILY-INSURANCE-JOB.jcl, causing depositor aggregation to be skipped. 1,951 accounts exceed SMDIA without correct per-depositor rollup.",
  "evidence_refs": ["EVD-001"],
  "involved_node_ids": ["STP-AGG", "ART-JCL", "PIP-DIJ"],
  "confidence_prior": 0.92,
  "status": "CANDIDATE",
  "rejection_reason": null
}
```

Rejected hypothesis (log but do not surface to user unless they ask):
```json
{
  "hypothesis_id": "HYP-002",
  "pattern_id": "UNKNOWN-PATTERN",
  "status": "REJECTED",
  "rejection_reason": "R2 violation: pattern_id 'UNKNOWN-PATTERN' not in HypothesisPatternLibrary"
}
```

---

## Conversational Explanation Format

When explaining a hypothesis to the user in chat mode:

```
**Hypothesis**: [DEF-ID] — [description]
**Pattern**: [pattern_id] ([pattern name])
**Evidence**: [EVD-ID] — [one-line evidence description]
**Prior confidence**: [X.XX] ([LOW/MEDIUM/HIGH])
**Supported by ontology path**: [INC→CTL→RUL→PIP→STP→ART]
```

Do not use jargon like "pattern_match_result" — translate to plain English
while preserving the exact IDs.

---

## Audit Trace Entry

```python
AuditEntry(
    phase=PhaseEnum.BACKTRACK,
    agent="HypothesisGeneratorAgent",
    action=AuditAction.ACCEPTED,       # or REJECTED
    evidence_id="EVD-001",
    reason="Pattern DEMO-AGG-001 satisfied. Hypothesis HYP-001 (DEF-LDS-001) CANDIDATE. Prior: 0.92."
)
```
