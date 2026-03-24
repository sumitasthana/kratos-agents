# RCA Orchestrator Skill

## Trigger
Activates at the start of every new incident investigation, before any other skill.
This skill governs phase routing, agent delegation, and parallelization decisions.

## Primary Responsibility
Sequence and coordinate the 7-phase pipeline. Delegate each phase to the right
sub-skill/agent. Enforce phase gate conditions before advancing. Synthesize
results from parallel agents into a unified InvestigationState delta.

---

## Phase → Agent → Output Mapping

| Phase | # | Agent/Skill | Required Output |
|---|---|---|---|
| INTAKE | 1 | `skills/intake-agent/SKILL.md` | `{scenario_id, anchor_node, canon_graph}` |
| LOGS_FIRST | 2 | `skills/log-analyst/SKILL.md` | `[EvidenceObject, ...]` with tier labels |
| ROUTE | 3 | self (pattern match) | `{pattern_id, pattern_name, log_signal_matched}` |
| BACKTRACK | 4 | All 4 sub-agents in parallel (see below) | Merged state delta |
| INCIDENT_CARD | 5 | self (synthesis) | Structured `IncidentCard` |
| RECOMMEND | 6 | `skills/remediation-agent/SKILL.md` | `[RemediationAction, ...]` |
| PERSIST | 7 | self | Final SSE event + session save |

---

## BACKTRACK Parallelization (Phase 4)

Agents 4a–4d run **in parallel** — never serially:

| Agent | Responsibility | Tool budget | Stopping condition |
|---|---|---|---|
| 4a — OntologyContext | BFS neighbourhood of anchor + 6 hops | 10 | All 6-hop nodes resolved or depth exceeded |
| 4b — EvidenceCollector | Search all evidence sources for canon-node IDs | 15 | All canonical node IDs have ≥ 1 EvidenceObject |
| 4c — HypothesisGenerator | Pattern-match → emit up to 5 Hypotheses | 10 | 1 CONFIRMED or 5 hypotheses emitted |
| 4d — CausalEngine | Build CausalEdge chain, validate structural paths | 10 | Root-to-leaf path fully validated |

Synthesize after **all four** return or a 30-second hard timeout per agent.
If an agent times out, mark its outputs as `PARTIAL` and continue.
Do not discard timed-out agent work — include it with a warning in audit_trace.

**RankerAgent (4e)** runs after all four complete and scores candidates:
- Calls `ConfidenceCalculator.compute(E, T, D, H)` with per-dimension floats.
- Sets `root_cause_final` if composite ≥ 0.70 AND no blocking MissingEvidence.
- Appends `RootCauseCandidate` to state — never replaces prior candidates.

---

## Phase Gate Conditions

| Before advancing to | Block if |
|---|---|
| LOGS_FIRST | `anchor_neo4j_id == "NOT_FOUND"` (R6) |
| ROUTE | Zero EvidenceObjects in state |
| BACKTRACK | R6 still violated, or any gate R1–R5 unresolvable |
| INCIDENT_CARD | Any BACKTRACK agent returned `BLOCKED` |
| RECOMMEND | `root_cause_candidates` list is empty |
| PERSIST | ValidationGate.run(state).all_passed is False |

Emit `status: PARTIAL` rather than failing silently. Always include the blocking
reason in the phase SSE event: `{"phase": "X", "status": "BLOCKED", "reason": "..."}`.

---

## Delegation Message Template

When spawning any sub-agent or skill, always pass:

```json
{
  "objective": "<single sentence — what the agent must find>",
  "output_format": "<exact schema expected back>",
  "tool_budget": "<max tool calls: 5|10|15|20>",
  "stopping_condition": "<when to stop — e.g. 'stop once DEF-ID confirmed'>",
  "ontology_context": {
    "anchor_label": "Incident",
    "anchor_value": "INC-001",
    "relevant_node_ids": ["INC-001", "CTL-C2", "RUL-AGG"],
    "relevant_rel_types": ["TRIGGERED_BY", "MANDATES", "DEPENDS_ON"]
  }
}
```

Never delegate without an `objective` — agents without a clear objective produce
unfocused, expensive work.

---

## SSE Event Schema (One Event Per Phase)

```json
{
  "phase": "INTAKE | LOGS_FIRST | ROUTE | BACKTRACK | INCIDENT_CARD | RECOMMEND | PERSIST",
  "phase_number": 1,
  "status": "OK | PARTIAL | BLOCKED",
  "duration_ms": 0,
  "state_delta": {
    "evidence_added": 0,
    "hypotheses_added": 0,
    "edges_added": 0,
    "root_cause_final": null
  },
  "blocking_reason": null
}
```

---

## Cross-Scenario Investigations

When the user asks about multiple scenarios simultaneously:
1. Spawn one parallel sub-orchestrator per scenario (max 3 simultaneous).
2. Each sub-orchestrator runs the full 7-phase pipeline independently.
3. After all complete, synthesize a cross-scenario comparison table:
   - Shared defect patterns (DEF-XSY-*)
   - Distinct root causes per scenario
   - Combined regulatory impact (total accounts + total AUM gap)
4. Never merge InvestigationState across scenarios — keep them separate.

---

## Effort Budget by Task Type

| Task | Total tool budget | Orchestrator calls | Sub-agent calls |
|---|---|---|---|
| Incident ID lookup only | 3 | 1 | 0 |
| Single-scenario full RCA | 50 | 10 | 40 |
| Cross-scenario (all 3) | 120 | 15 | 35 × 3 |

---

## Audit Trace Requirement

Append to `state.audit_trace` at every phase transition:

```python
AuditEntry(
    phase=PhaseEnum.INTAKE,          # or whichever phase completes
    agent="RcaOrchestrator",
    action=AuditAction.ACCEPTED,     # or REJECTED
    evidence_id=None,                # None for phase-level entries
    reason="Phase INTAKE completed — anchor INC-001 resolved, canon_graph seeded"
)
```

Log BOTH successful advances AND blocked transitions with their reasons.
