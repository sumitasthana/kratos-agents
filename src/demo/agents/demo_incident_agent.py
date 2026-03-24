"""
src/demo/agents/demo_incident_agent.py

DemoIncidentAgent — INCIDENT_CARD phase.

Synthesizes the incident card from collected evidence, the causal chain,
and scenario metadata. Produces a structured IncidentCard with compliance
citations, severity, and impact assessment.
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

_INCIDENT_METADATA: dict[str, dict] = {
    "deposit_aggregation_failure": {
        "incident_id": "INC-001",
        "title": "Depositor-Level Aggregation Failure — SMDIA Overstated",
        "regulation": "12 CFR § 330.1(b)",
        "regulation_name": "FDIC Part 330 — Depositor Aggregation",
        "control_id": "C2",
        "control_name": "Coverage Calculation Accuracy",
        "severity": "CRITICAL",
        "impact_summary": (
            "1,951 of 6,006 accounts (32.5%) classified above the $250,000 SMDIA limit "
            "without depositor-level aggregation. Deposits from the same depositor at "
            "the same institution are being counted independently, causing overstated coverage."
        ),
        "defect_ids": ["DEF-LDS-001", "DEF-LDS-004"],
        "remediation_deadline": "2026-03-23T23:59:59Z",
    },
    "trust_irr_misclassification": {
        "incident_id": "INC-002",
        "title": "Trust_Irrevocable ORC Misclassification — IRR Treated as SGL",
        "regulation": "12 CFR § 330.13",
        "regulation_name": "FDIC Part 330 — Trust Account Coverage",
        "control_id": "A3",
        "control_name": "Fiduciary Documentation",
        "severity": "HIGH",
        "impact_summary": (
            "253 Trust_Irrevocable accounts incorrectly classified as Single (SGL). "
            "Each beneficiary of an irrevocable trust is entitled to $250,000 coverage. "
            "Using SGL classification collapses multi-beneficiary coverage to a single limit. "
            "Estimated coverage gap: ~$61.8M."
        ),
        "defect_ids": ["DEF-TCS-001", "DEF-TCS-003", "DEF-TCS-006"],
        "remediation_deadline": "2026-03-23T23:59:59Z",
    },
    "wire_mt202_drop": {
        "incident_id": "INC-003",
        "title": "SWIFT MT202/MT202COV Drop — GL Break $284.7M",
        "regulation": "12 CFR § 370.4(a)(1)",
        "regulation_name": "FDIC Part 370 — Recordkeeping for Timely Deposit Insurance",
        "control_id": "B1",
        "control_name": "Daily Balance Snapshot",
        "severity": "CRITICAL",
        "impact_summary": (
            "47 MT202 + 12 MT202COV SWIFT messages silently dropped by swift_parser.py. "
            "No GL entries posted for these inter-bank transfers. "
            "GL break: $284,700,000. "
            "Daily balance snapshot for 2026-03-16 is materially misstated."
        ),
        "defect_ids": ["DEF-WTS-001", "DEF-WTS-007"],
        "remediation_deadline": "2026-03-17T05:00:00Z",
    },
}


class DemoIncidentAgent(BaseReasoningAgent):
    """Constructs the structured IncidentCard from evidence and causal chain."""

    @property
    def agent_name(self) -> str:
        return "DemoIncidentAgent"

    @property
    def phase(self) -> str:
        return "INCIDENT_CARD"

    def build_prompt(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
    ) -> str:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _INCIDENT_METADATA.get(scenario_id, {})
        chain_ids = [e.cause_node_id for e in state.causal_graph_edges]
        if state.causal_graph_edges:
            chain_ids.append(state.causal_graph_edges[-1].effect_node_id)

        return f"""You are the IncidentAgent. Your phase is INCIDENT_CARD (synthesis).

SCENARIO: {scenario_id}
EVIDENCE COUNT: {len(state.evidence_objects)}
CAUSAL CHAIN: {chain_ids}
HYPOTHESES: {[h.hypothesis_id for h in state.hypotheses]}

INCIDENT METADATA:
{json.dumps(meta, indent=2)}

YOUR TASK:
1. <observe> the causal chain and evidence to understand the scope
2. <test> the regulation citation and confirm the compliance gap
3. <conclude> the incident card synthesising severity, impact, and regulatory context

JSON output:
```json
{{
  "incident_id": "{meta.get('incident_id', '')}",
  "title": "{meta.get('title', '')}",
  "severity": "{meta.get('severity', 'HIGH')}",
  "regulation": "{meta.get('regulation', '')}",
  "control_failed": "{meta.get('control_id', '')}",
  "impact_summary": "{meta.get('impact_summary', '')[:200]}",
  "defect_ids": {json.dumps(meta.get('defect_ids', []))},
  "remediation_deadline": "{meta.get('remediation_deadline', '')}"
}}
```"""

    def parse_response(
        self,
        response_text: str,
        state: InvestigationState,
    ) -> InvestigationState:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _INCIDENT_METADATA.get(scenario_id, {})

        if meta:
            state.investigation_input.context["incident_card"] = {
                "incident_id": meta["incident_id"],
                "title": meta["title"],
                "severity": meta["severity"],
                "regulation": meta["regulation"],
                "regulation_name": meta["regulation_name"],
                "control_id": meta["control_id"],
                "control_name": meta["control_name"],
                "impact_summary": meta["impact_summary"],
                "defect_ids": meta["defect_ids"],
                "remediation_deadline": meta["remediation_deadline"],
            }

        return state

    def build_fallback_thoughts(
        self,
        state: InvestigationState,
        context: dict,
    ) -> list[tuple[str, str]]:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _INCIDENT_METADATA.get(scenario_id, {})
        inc_id = meta.get("incident_id", "INC-???")
        control = meta.get("control_id", "")
        regulation = meta.get("regulation", "")
        severity = meta.get("severity", "HIGH")
        impact = meta.get("impact_summary", "")[:200]

        return [
            ("OBSERVING", (
                f"Synthesising incident card for {inc_id}. "
                f"Causal chain has {len(state.causal_edges)} confirmed edges. "
                f"{len(state.evidence_objects)} evidence object(s) support the findings."
            )),
            ("TESTING", (
                f"Verifying regulatory citation {regulation}. "
                f"Control {control} ({meta.get('control_name', '')}) is confirmed FAILED."
            )),
            ("ACCEPTING", (
                f"Severity: {severity}. {impact}"
            )),
            ("CONCLUDING", (
                f"Incident card {inc_id} complete. "
                f"Defects cited: {meta.get('defect_ids', [])}. "
                f"Remediation deadline: {meta.get('remediation_deadline', 'TBD')}."
            )),
        ]
