"""
src/demo/agents/demo_routing_agent.py

DemoRoutingAgent — ROUTE phase.

Selects the hypothesis pattern that best matches the evidence collected
in LOGS_FIRST, prepares the canon graph anchor node, and sets up the
backtracking context.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from causelink.agents.base_reasoning_agent import BaseReasoningAgent
from causelink.state.investigation import InvestigationState

if TYPE_CHECKING:
    from src.infrastructure.base_adapter import InfrastructureAdapter

log = logging.getLogger(__name__)

_ROUTING_METADATA: dict[str, dict] = {
    "deposit_aggregation_failure": {
        "anchor_node_id": "node-daf-inc-001",
        "anchor_node_label": "Incident",
        "pattern_id": "DEMO-AGG-001",
        "pattern_name": "AGG_STEP_DISABLED",
        "trigger_signal": "AGGRSTEP — skipped (disabled in JCL)",
        "entry_edge": "TRIGGERED_BY",
        "confidence": 0.95,
    },
    "trust_irr_misclassification": {
        "anchor_node_id": "node-tim-inc-002",
        "anchor_node_label": "Incident",
        "pattern_id": "DEMO-IRR-001",
        "pattern_name": "IRR_NOT_IMPLEMENTED",
        "trigger_signal": "fallback ORC=SGL (IRR not implemented)",
        "entry_edge": "TRIGGERED_BY",
        "confidence": 0.90,
    },
    "wire_mt202_drop": {
        "anchor_node_id": "node-wmd-inc-003",
        "anchor_node_label": "Incident",
        "pattern_id": "DEMO-MT202-001",
        "pattern_name": "MT202_HANDLER_MISSING",
        "trigger_signal": "silently dropped (no handler)",
        "entry_edge": "TRIGGERED_BY",
        "confidence": 0.95,
    },
}


class DemoRoutingAgent(BaseReasoningAgent):
    """Selects hypothesis pattern and prepares ontology backtracking context."""

    @property
    def agent_name(self) -> str:
        return "DemoRoutingAgent"

    @property
    def phase(self) -> str:
        return "ROUTE"

    def build_prompt(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
    ) -> str:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _ROUTING_METADATA.get(scenario_id, {})
        ev_json = json.dumps(
            [{"evidence_id": ev.evidence_id, "tier": str(ev.reliability_tier),
              "summary": ev.summary[:150]}
             for ev in state.evidence_objects[:5]],
            indent=2,
        )

        return f"""You are the RoutingAgent. Your phase is ROUTE (pattern selection).

SCENARIO: {scenario_id}
EVIDENCE:
{ev_json}

KNOWN PATTERNS:
  AGG_STEP_DISABLED     → fires when: "skipped (disabled in JCL)"
  IRR_NOT_IMPLEMENTED   → fires when: "fallback ORC=SGL"
  MT202_HANDLER_MISSING → fires when: "silently dropped"

YOUR TASK:
1. <observe> the evidence signals and match against known patterns
2. <test> each candidate pattern — only one should fire per scenario
3. <accept> the matching pattern and identify the anchor node
4. <conclude> the routing decision

JSON output:
```json
{{
  "anchor_node_id": "{meta.get('anchor_node_id', '')}",
  "anchor_node_label": "Incident",
  "chosen_pattern_id": "{meta.get('pattern_id', '')}",
  "chosen_pattern_name": "{meta.get('pattern_name', '')}",
  "trigger_signal": "{meta.get('trigger_signal', '')}",
  "entry_rel_type": "TRIGGERED_BY",
  "routing_confidence": {meta.get('confidence', 0.90)}
}}
```"""

    def parse_response(
        self,
        response_text: str,
        state: InvestigationState,
    ) -> InvestigationState:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _ROUTING_METADATA.get(scenario_id, {})

        if meta:
            state.investigation_input.context["routing"] = {
                "anchor_node_id": meta["anchor_node_id"],
                "pattern_id": meta["pattern_id"],
                "pattern_name": meta["pattern_name"],
                "entry_edge": meta["entry_edge"],
            }

        return state

    def build_fallback_thoughts(
        self,
        state: InvestigationState,
        context: dict,
    ) -> list[tuple[str, str]]:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _ROUTING_METADATA.get(scenario_id, {})
        pattern_name = meta.get("pattern_name", "UNKNOWN")
        trigger = meta.get("trigger_signal", "")
        anchor = meta.get("anchor_node_id", "")

        return [
            ("OBSERVING", (
                f"Reviewing {len(state.evidence_objects)} evidence object(s) "
                f"collected in LOGS_FIRST for scenario '{scenario_id}'."
            )),
            ("TESTING",   "Testing AGG_STEP_DISABLED pattern — looking for 'disabled in JCL' signal."),
            ("TESTING",   "Testing IRR_NOT_IMPLEMENTED pattern — looking for 'fallback ORC=SGL' signal."),
            ("TESTING",   "Testing MT202_HANDLER_MISSING pattern — looking for 'silently dropped' signal."),
            ("ACCEPTING", (
                f"Pattern {pattern_name!r} fires. Trigger signal: '{trigger}'. "
                f"Anchor node: {anchor}."
            )),
            ("CONCLUDING", (
                f"Routing confirmed to {pattern_name}. "
                f"Entry relationship: TRIGGERED_BY. "
                f"Backtracking will start from incident anchor and walk toward the root cause."
            )),
        ]
