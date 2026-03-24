# Confidence Scoring Skill

## Trigger
Activates during BACKTRACK Phase 4e (RankerAgent), and any time the user asks:
"How confident are you?", "What's the confidence score?", "Is this confirmed?",
or "Why is the confidence low?"

## Primary Responsibility
Compute the composite E×T×D×H confidence score for each RootCauseCandidate,
enforce all validation gates (R1–R8), and set `root_cause_final` when the
composite score ≥ 0.70 with no blocking MissingEvidence.

---

## Scoring Formula (Fixed — Never Modify Weights)

```
composite = 0.40 × E + 0.25 × T + 0.20 × D + 0.15 × H
```

| Dimension | Weight | Meaning |
|---|---|---|
| **E** — Evidence Strength | 0.40 | Tier quality of EvidenceObjects |
| **T** — Topology Match | 0.25 | CanonGraph path hop completion % |
| **D** — Defect Specificity | 0.20 | Uniqueness of defect in pattern library |
| **H** — Historical Pattern | 0.15 | Prior match rate in scenario registry |

**Confirmation threshold**: composite ≥ 0.70 to set `root_cause_final`.
**Demo tier**: threshold is 0.70 (production uses 0.80).

---

## Tier-to-E Score Mapping

| Evidence quality | E value range |
|---|---|
| All CRITICAL + ≥ 2 SIGNAL | 0.90 – 1.00 |
| ≥ 1 CRITICAL + ≥ 1 SIGNAL | 0.70 – 0.89 |
| ≥ 1 CRITICAL only | 0.50 – 0.69 |
| SIGNAL only (no CRITICAL) | 0.30 – 0.49 |
| No evidence found | 0.00 |

---

## Topology Match (T) Calculation

```
T = hops_completed / max_hops
```

For a 6-hop canonical path:
- 6/6 hops validated with `structural_path_validated=True` → T = 1.00
- 5/6 hops validated → T = 0.83
- 4/6 hops validated → T = 0.67
- < 4 hops → T ≤ 0.50 (LOW confidence likely)

---

## Defect Specificity (D) Calculation

| Pattern uniqueness | D value |
|---|---|
| Pattern matches exactly one defect_id | 1.00 |
| Pattern matches 2 defect_ids | 0.70 |
| Pattern matches 3+ defect_ids | 0.50 |
| Pattern id is unknown/unregistered | 0.00 |

For the 3 demo patterns: each maps to exactly one primary defect_id → D = 1.00.

---

## Historical Pattern (H) Calculation

For demo mode, H is fixed per scenario based on pre-computed registry priors:

| pattern_id | H value | Basis |
|---|---|---|
| DEMO-AGG-001 | 0.92 | 100% prior match rate (1/1 in registry) |
| DEMO-IRR-001 | 0.90 | 100% prior match rate (1/1 in registry) |
| DEMO-MT202-001 | 0.93 | 100% prior match rate (1/1 in registry) |
| CLK-P001 through CLK-P008 | 0.40 (default) | No prior investigation data |

---

## Expected Composite Scores (Demo Mode)

| scenario_id | E | T | D | H | Composite | Tier |
|---|---|---|---|---|---|---|
| `deposit_aggregation_failure` | 0.95 | 1.00 | 1.00 | 0.92 | **0.978** | CONFIRMED |
| `trust_irr_misclassification` | 0.92 | 1.00 | 1.00 | 0.90 | **0.968** | CONFIRMED |
| `wire_mt202_drop` | 0.95 | 1.00 | 1.00 | 0.93 | **0.980** | CONFIRMED |

All three scenarios are designed to CONFIRM — the defect signal is unambiguous.

---

## Confidence Tier Labels

| Composite score | Tier |
|---|---|
| ≥ 0.90 | CONFIRMED |
| 0.70 – 0.89 | HIGH |
| 0.40 – 0.69 | MEDIUM |
| < 0.40 | LOW |

---

## Blocking Gate R8

If ANY `MissingEvidence` in `state.missing_evidence` has `blocking=True`:
- Set `root_cause_final = None` regardless of composite score.
- Report the exact `missing_evidence_id` and `resolution_hint` to the user.
- Do NOT advance to PERSIST with null `root_cause_final` silently.

Example user message when blocked:
```
Confidence is 0.42 (LOW) — blocked on MissingEvidence MEV-001.
The AGGRSTEP→JCL edge is missing structural_path_validated=True.
Provide the JCL execution log to resolve this gate.
```

---

## Full Validation Gate Checklist (Run Before Setting root_cause_final)

| Gate | Check |
|---|---|
| R1 | All `hypothesis.evidence_refs` exist in `state.evidence_objects` |
| R2 | All `hypothesis.ontology_path_ids` exist in `state.ontology_paths_used` or `canon_graph` |
| R3 | All `hypothesis.involved_node_ids` exist in `canon_graph.nodes` |
| R4 | All VALID `CausalEdge`s have `structural_path_validated=True` |
| R5 | Only RankerAgent (this agent) may set CONFIRMED status |
| R6 | `canon_graph.anchor_neo4j_id != "NOT_FOUND"` |
| R7 | All node labels and rel-types are in the frozen 19/26 sets |
| R8 | No blocking `MissingEvidence` exists |

If ALL gates pass → set `root_cause_final` to the top `RootCauseCandidate.defect_id`.

---

## Output Schema

```json
{
  "composite": 0.978,
  "tier": "CONFIRMED",
  "breakdown": {
    "E": 0.95,
    "T": 1.00,
    "D": 1.00,
    "H": 0.92
  },
  "blocking_gates": [],
  "root_cause_locked": true,
  "root_cause_final": "DEF-LDS-001"
}
```

When blocked:
```json
{
  "composite": 0.42,
  "tier": "LOW",
  "breakdown": {"E": 0.30, "T": 0.67, "D": 1.00, "H": 0.92},
  "blocking_gates": ["R8: MissingEvidence MEV-001 (blocking=True)"],
  "root_cause_locked": false,
  "root_cause_final": null
}
```

---

## Audit Trace Entry

```python
AuditEntry(
    phase=PhaseEnum.BACKTRACK,
    agent="RankerAgent",
    action=AuditAction.ACCEPTED,
    evidence_id=None,
    reason="Composite 0.978 ≥ 0.70. Gates R1–R8 all passed. root_cause_final=DEF-LDS-001."
)
```
