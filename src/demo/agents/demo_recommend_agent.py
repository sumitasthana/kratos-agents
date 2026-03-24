"""
src/demo/agents/demo_recommend_agent.py

DemoRecommendAgent — RECOMMEND phase.

Generates ranked remediation recommendations by referencing the exact
defect IDs and artifact paths from the known operational system defects.

Each recommendation is sourced from specific defects under operational_systems/
and includes priority, estimated effort, and the regulatory citation addressed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from causelink.agents.base_reasoning_agent import BaseReasoningAgent
from causelink.state.investigation import InvestigationState

if TYPE_CHECKING:
    from src.infrastructure.base_adapter import InfrastructureAdapter

log = logging.getLogger(__name__)

_RECOMMENDATIONS: dict[str, list[dict]] = {
    "deposit_aggregation_failure": [
        {
            "defect_id": "DEF-LDS-001",
            "priority": 1,
            "title": "Re-enable AGGRSTEP in DAILY-INSURANCE-JOB.jcl",
            "artifact": "operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl",
            "action": (
                "Uncomment Step 3 (AGGRSTEP). The step was disabled with //* "
                "which caused the entire depositor aggregation to be skipped. "
                "Re-enable and validate with FDIC test dataset."
            ),
            "regulation": "12 CFR § 330.1(b)",
            "effort": "LOW — single-line JCL change",
            "confidence": 0.98,
        },
        {
            "defect_id": "DEF-LDS-002",
            "priority": 2,
            "title": "Implement IRR ORC branch in ORC-ASSIGNMENT.cob",
            "artifact": "operational_systems/legacy_deposit_system/cobol/ORC-ASSIGNMENT.cob",
            "action": (
                "Add WHEN 'IRR' branch to the EVALUATE ORC-CODE statement. "
                "Without this, IRR accounts silently default to SGL classification."
            ),
            "regulation": "12 CFR § 330.13",
            "effort": "MEDIUM — COBOL source change + regression test",
            "confidence": 0.90,
        },
        {
            "defect_id": "DEF-LDS-004",
            "priority": 3,
            "title": "Fix delimiter in DAILY-INSURANCE-JOB.jcl (comma → pipe)",
            "artifact": "operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl",
            "action": (
                "Change DELIMITER=, to DELIMITER=| in the extract step. "
                "Comma delimiter causes parse errors when account names contain commas. "
                "This is a secondary defect masking data quality issues."
            ),
            "regulation": "FDIC Data Integrity",
            "effort": "LOW",
            "confidence": 0.85,
        },
    ],
    "trust_irr_misclassification": [
        {
            "defect_id": "DEF-TCS-001",
            "priority": 1,
            "title": "Implement IRR branch in TRUST-INSURANCE-CALC.cob",
            "artifact": "operational_systems/trust_custody_system/cobol/TRUST-INSURANCE-CALC.cob",
            "action": (
                "Add WHEN 'IRR' case to the ORC classification EVALUATE block. "
                "Currently IRR falls through to the SGL branch, collapsing multi-beneficiary "
                "coverage. Each beneficiary requires a separate $250,000 coverage limit."
            ),
            "regulation": "12 CFR § 330.13",
            "effort": "MEDIUM — COBOL + regression",
            "confidence": 0.97,
        },
        {
            "defect_id": "DEF-TCS-003",
            "priority": 2,
            "title": "Fix BeneficiaryClassifier.java IRR → SGL fallback",
            "artifact": "operational_systems/trust_custody_system/java/BeneficiaryClassifier.java",
            "action": (
                "In the switch(orcCode) statement, add a case for 'IRR' that correctly "
                "calculates per-beneficiary coverage. "
                "The current code throws the IRR case to the SGL default."
            ),
            "regulation": "12 CFR § 330.13",
            "effort": "LOW — Java switch case addition",
            "confidence": 0.95,
        },
        {
            "defect_id": "DEF-TCS-006",
            "priority": 3,
            "title": "Fix sp_calculate_trust_insurance.sql to include sub-account balances",
            "artifact": "operational_systems/trust_custody_system/sql/sp_calculate_trust_insurance.sql",
            "action": (
                "Modify the stored procedure to include sub-account balances in the trust "
                "coverage calculation. Currently only the primary account balance is summed, "
                "causing underreporting of trust assets."
            ),
            "regulation": "12 CFR § 330.13",
            "effort": "MEDIUM — SQL stored procedure change",
            "confidence": 0.88,
        },
    ],
    "wire_mt202_drop": [
        {
            "defect_id": "DEF-WTS-001",
            "priority": 1,
            "title": "Add MT202/MT202COV handler in swift_parser.py",
            "artifact": "operational_systems/wire_transfer_system/python/swift_parser.py",
            "action": (
                "In parse_message(), add elif message_type == 'MT202' and "
                "elif message_type == 'MT202COV' branches. "
                "Currently only MT103 is handled — all other types silently return None. "
                "Also add a final else: raise ValueError(f'Unsupported SWIFT type: {message_type}') "
                "to detect future unhandled types."
            ),
            "regulation": "12 CFR § 370.4(a)(1)",
            "effort": "LOW — 20-line Python change",
            "confidence": 0.99,
        },
        {
            "defect_id": "DEF-WTS-007",
            "priority": 2,
            "title": "Fix nostro account matching in reconciliation.py",
            "artifact": "operational_systems/wire_transfer_system/python/reconciliation.py",
            "action": (
                "Update the reconciliation logic to include nostro accounts in the match set. "
                "Without nostro matching, inter-bank settlements are unreconciled "
                "even after MT202 is fixed."
            ),
            "regulation": "12 CFR § 370.4(a)(1)",
            "effort": "MEDIUM",
            "confidence": 0.85,
        },
        {
            "defect_id": "DEF-WTS-002",
            "priority": 3,
            "title": "Switch OFAC screening from batch to real-time in wire-config.properties",
            "artifact": "operational_systems/wire_transfer_system/config/wire-config.properties",
            "action": (
                "Change ofac.screening.mode=batch to ofac.screening.mode=realtime. "
                "The current 6-hour batch delay means sanctioned wires could settle "
                "before being flagged."
            ),
            "regulation": "OFAC / BSA",
            "effort": "LOW — config change",
            "confidence": 0.80,
        },
    ],
}


class DemoRecommendAgent(BaseReasoningAgent):
    """Generates ranked remediation recommendations from known defect catalog."""

    @property
    def agent_name(self) -> str:
        return "DemoRecommendAgent"

    @property
    def phase(self) -> str:
        return "RECOMMEND"

    def build_prompt(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
    ) -> str:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        recs = _RECOMMENDATIONS.get(scenario_id, [])

        return f"""You are the RecommendAgent. Your phase is RECOMMEND (remediation planning).

SCENARIO: {scenario_id}
CONFIRMED ROOT CAUSE: {state.causal_graph_edges[-1].effect_node_id if state.causal_graph_edges else 'unknown'}
KNOWN DEFECTS TO ADDRESS:
{[r['defect_id'] for r in recs]}

YOUR TASK:
1. <observe> the confirmed root cause and the list of defects
2. <test> each defect: is it directly causative or a secondary finding?
3. <accept> primary and secondary remediations, ranked by regulatory impact
4. <conclude> the prioritised remediation plan

Generate exactly {len(recs)} recommendations. Always cite exact defect IDs and artifact paths."""

    def parse_response(
        self,
        response_text: str,
        state: InvestigationState,
    ) -> InvestigationState:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        recs = _RECOMMENDATIONS.get(scenario_id, [])
        state.investigation_input.context["recommendations"] = recs
        return state

    def build_fallback_thoughts(
        self,
        state: InvestigationState,
        context: dict,
    ) -> list[tuple[str, str]]:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        recs = _RECOMMENDATIONS.get(scenario_id, [])

        if not recs:
            return [("CONCLUDING", "No recommendations found for this scenario.")]

        thoughts: list[tuple[str, str]] = []
        thoughts.append(("OBSERVING", (
            f"Generating remediation plan for scenario '{scenario_id}'. "
            f"{len(recs)} known defects to address. "
            f"Root cause: {recs[0]['defect_id']} ({recs[0]['artifact']})."
        ))
        )

        for rec in recs:
            if rec["priority"] == 1:
                thoughts.append(("ACCEPTING", (
                    f"PRIMARY [P{rec['priority']}] {rec['defect_id']}: {rec['title']}. "
                    f"Confidence: {rec['confidence']:.0%}. Effort: {rec['effort']}. "
                    f"Addresses {rec['regulation']}."
                )))
            else:
                thoughts.append(("TESTING", (
                    f"SECONDARY [P{rec['priority']}] {rec['defect_id']}: {rec['title']}. "
                    f"Effort: {rec['effort']}."
                )))

        thoughts.append(("CONCLUDING", (
            f"Remediation plan complete. {len(recs)} recommendations ranked by regulatory impact. "
            f"Priority 1 ({recs[0]['defect_id']}) is the mandatory first action. "
            f"All recommendations cite exact artifact paths under operational_systems/."
        )))
        return thoughts
