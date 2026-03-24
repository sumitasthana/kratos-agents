"""
src/demo/agents/demo_backtracking_agent.py

DemoBacktrackingAgent — BACKTRACK phase.

Walks the CanonGraph hop-by-hop from the incident anchor node toward the
root cause, making one LLM call per hop to reason about which edge to
follow and why alternatives were rejected.

In fallback mode, deterministically follows the pre-defined causal chain
for the scenario, emitting synthetic thought steps explaining each hop.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from causelink.agents.base_reasoning_agent import BaseReasoningAgent
from causelink.state.investigation import (
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
)

if TYPE_CHECKING:
    from src.infrastructure.base_adapter import InfrastructureAdapter

log = logging.getLogger(__name__)

# Causal chains per scenario — used in fallback mode
_CAUSAL_CHAIN_NODE_IDS: dict[str, list[str]] = {
    "deposit_aggregation_failure": [
        "node-daf-ctl-c2",
        "node-daf-rul-agg",
        "node-daf-pip-dij",
        "node-daf-stp-agg",
        "node-daf-art-jcl",
    ],
    "trust_irr_misclassification": [
        "node-tim-ctl-a3",
        "node-tim-rul-irr",
        "node-tim-pip-tdb",
        "node-tim-art-cob",
        "node-tim-art-bcj",
    ],
    "wire_mt202_drop": [
        "node-wmd-ctl-b1",
        "node-wmd-rul-swf",
        "node-wmd-pip-wnr",
        "node-wmd-mod-swp",
        "node-wmd-art-swp",
    ],
}

_PATTERN_IDS: dict[str, str] = {
    "deposit_aggregation_failure": "DEMO-AGG-001",
    "trust_irr_misclassification": "DEMO-IRR-001",
    "wire_mt202_drop":             "DEMO-MT202-001",
}

_SCENARIO_METADATA: dict[str, dict] = {
    "deposit_aggregation_failure": {
        "rel_types": ["MANDATES", "DEPENDS_ON", "RUNS_JOB", "USES_SCRIPT"],
        "node_names": ["CTL-C2", "RUL-AGG", "PIP-DIJ", "STP-AGG", "ART-JCL"],
        "hop_explanations": [
            ("OBSERVING",     "Starting at INC-001 (overstated_coverage). TRIGGERED_BY relationship points to CTL-C2 (Coverage Calculation Accuracy). This is the compliance control that mandates depositor-level aggregation under 12 CFR § 330.1(b)."),
            ("TESTING",       "CTL-C2 mandates RUL-AGG (depositor_aggregation_rule). The rule requires that all accounts owned by the same depositor be aggregated before applying the $250,000 SMDIA limit. Evidence confirms this rule was not applied."),
            ("TESTING",       "RUL-AGG depends on PIP-DIJ (DAILY-INSURANCE-JOB). The pipeline is the execution vehicle for the aggregation rule. If the pipeline is disabled or has a step commented out, the rule is silently skipped."),
            ("ACCEPTING",     "PIP-DIJ runs STP-AGG (AGGRSTEP). The critical log signal «AGGRSTEP — skipped (disabled in JCL)» directly confirms this step was disabled. This is CONFIRMED_FAILED."),
            ("CONCLUDING",    "STP-AGG is implemented in ART-JCL (DAILY-INSURANCE-JOB.jcl). DEF-LDS-001: Step 3 AGGRSTEP is commented out in the JCL. This is the ROOT CAUSE — a configuration defect in the job control language."),
        ],
    },
    "trust_irr_misclassification": {
        "rel_types": ["MANDATES", "DEPENDS_ON", "RUNS_JOB", "DEPENDS_ON"],
        "node_names": ["CTL-A3", "RUL-IRR", "PIP-TDB", "ART-COB", "ART-BCJ"],
        "hop_explanations": [
            ("OBSERVING",     "Starting at INC-002 (irr_misclassification). TRIGGERED_BY points to CTL-A3 (Fiduciary Documentation control). This control enforces correct ORC classification for Trust_Irrevocable accounts under 12 CFR § 330.13."),
            ("TESTING",       "CTL-A3 mandates RUL-IRR (trust_irr_classification_rule). The rule states IRR accounts must be classified separately from SGL accounts. The log signal confirms a fallback to SGL — meaning IRR is not implemented."),
            ("TESTING",       "RUL-IRR depends on PIP-TDB (TRUST-DAILY-BATCH). The trust processing pipeline is responsible for executing the IRR classification logic. Evidence confirms the pipeline runs but produces incorrect output."),
            ("ACCEPTING",     "PIP-TDB runs ART-COB (TRUST-INSURANCE-CALC.cob). The COBOL program is the CONFIRMED_FAILED source — it contains no IRR branch. The fallback to SGL is hardcoded. DEF-TCS-001 confirmed."),
            ("CONCLUDING",    "ART-COB depends on ART-BCJ (BeneficiaryClassifier.java). The Java classifier also implements IRR→SGL fallback (DEF-TCS-003). Both artifacts are ROOT CAUSE nodes — the defect spans COBOL and Java layers."),
        ],
    },
    "wire_mt202_drop": {
        "rel_types": ["MANDATES", "DEPENDS_ON", "RUNS_JOB", "IMPLEMENTED_IN"],
        "node_names": ["CTL-B1", "RUL-SWF", "PIP-WNR", "MOD-SWP", "ART-SWP"],
        "hop_explanations": [
            ("OBSERVING",     "Starting at INC-003 (gl_break). TRIGGERED_BY points to CTL-B1 (Daily Balance Snapshot control). This control requires all wire transactions to be captured for GL reconciliation under 12 CFR § 370.4(a)(1)."),
            ("TESTING",       "CTL-B1 mandates RUL-SWF (swift_message_handling_rule). The rule requires all SWIFT message types (MT103, MT202, MT202COV) to be processed and posted to the GL. The log confirms MT202/MT202COV are silently dropped."),
            ("TESTING",       "RUL-SWF depends on PIP-WNR (WIRE-NIGHTLY-RECON). The nightly reconciliation pipeline runs the SWIFT parser. Total transactions reconciled is less than total received — confirming drop exists."),
            ("ACCEPTING",     "PIP-WNR runs MOD-SWP (swift_parser module). The module is CONFIRMED_FAILED — it only handles MT103. MT202 and MT202COV fall through with no handler. DEF-WTS-001 confirmed."),
            ("CONCLUDING",    "MOD-SWP is implemented in ART-SWP (swift_parser.py). The parse_message() function at line ~47 has an if MT103 branch with no else clause. This is the ROOT CAUSE. GL break: $284,700,000."),
        ],
    },
}


class DemoBacktrackingAgent(BaseReasoningAgent):
    """Walks the CanonGraph hop-by-hop, reasoning about each edge selection."""

    @property
    def agent_name(self) -> str:
        return "DemoBacktrackingAgent"

    @property
    def phase(self) -> str:
        return "BACKTRACK"

    def build_prompt(
        self,
        state: InvestigationState,
        adapter: "InfrastructureAdapter",
        context: dict,
    ) -> str:
        graph = state.canon_graph
        evidence_objects = state.evidence_objects
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        chain = _CAUSAL_CHAIN_NODE_IDS.get(scenario_id, [])

        nodes_json = json.dumps(
            [{"id": n.neo4j_id, "label": n.label, "primary_value": n.primary_value}
             for n in (graph.nodes if graph else [])],
            indent=2,
        )
        edges_json = json.dumps(
            [{"from": e.from_node_id, "to": e.to_node_id, "type": e.rel_type}
             for e in (graph.edges if graph else [])],
            indent=2,
        )
        ev_json = json.dumps(
            [{"evidence_id": ev.evidence_id, "tier": str(ev.reliability_tier),
              "summary": ev.summary[:200]}
             for ev in evidence_objects[:5]],
            indent=2,
        )

        return f"""You are the BacktrackingAgent. Your phase is BACKTRACK (hop-by-hop ontology walk).

SCENARIO: {scenario_id}
EVIDENCE COLLECTED:
{ev_json}

CANON GRAPH NODES:
{nodes_json}

CANON GRAPH EDGES:
{edges_json}

CAUSAL CHAIN TARGET (known root-cause path):
{json.dumps(chain, indent=2)}

YOUR TASK:
Walk from the incident anchor node to the root cause, hop by hop.
For EACH hop:
1. <observe> the current node and its outgoing edges
2. <test> each available edge — which should be followed based on evidence?
3. <reject> edges that don't lead toward the root cause (explain why)
4. <accept> the correct edge and the node it leads to
5. At the leaf node: <conclude> that this is the root cause

The known root cause is the last node in the causal chain above.
Apply the early-stop rule: when you reach a leaf node (Artifact/JobStep/Module)
that has CONFIRMED_FAILED evidence, stop and set is_root_cause=true.

JSON output schema:
```json
{{
  "hops": [
    {{
      "from_node_id": "...",
      "to_node_id": "...",
      "rel_type": "MANDATES",
      "to_node_status": "CONFIRMED_FAILED",
      "is_root_cause": false,
      "evidence_ids_used": [],
      "rejected_edges": []
    }}
  ],
  "root_cause_node_id": "...",
  "defect_id": "DEF-LDS-001"
}}
```"""

    def parse_response(
        self,
        response_text: str,
        state: InvestigationState,
    ) -> InvestigationState:
        # Try to extract hop data from LLM response
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        chain = _CAUSAL_CHAIN_NODE_IDS.get(scenario_id, [])
        pattern_id = _PATTERN_IDS.get(scenario_id, "DEMO-AGG-001")

        parsed_hops: list[dict] | None = None
        if response_text:
            try:
                json_start = response_text.rfind("```json")
                json_end = response_text.rfind("```", json_start + 3) if json_start != -1 else -1
                if json_start != -1 and json_end > json_start:
                    raw_json = response_text[json_start + 7:json_end].strip()
                    data = json.loads(raw_json)
                    parsed_hops = data.get("hops")
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        # Build hypothesis and causal edges from chain
        evidence_ids = [ev.evidence_id for ev in state.evidence_objects]
        graph = state.canon_graph
        path = graph.ontology_paths_used[0] if (graph and graph.ontology_paths_used) else None

        hypothesis = Hypothesis(
            description=(
                f"Causal chain from {chain[0]} to {chain[-1]} "
                f"via {len(chain) - 1} hops confirms root cause."
            ),
            involved_node_ids=chain,
            evidence_object_ids=evidence_ids[:1],
            ontology_path_ids=[path.path_id] if path else [],
            status=HypothesisStatus.SUPPORTED,
            confidence=0.90,
            generated_by="DemoBacktrackingAgent",
            pattern_id=pattern_id,
        )
        state.add_hypothesis(hypothesis)

        # Build causal edges
        meta = _SCENARIO_METADATA.get(scenario_id, {})
        rel_types = meta.get("rel_types", ["DEPENDS_ON"] * len(chain))
        for i in range(len(chain) - 1):
            edge = CausalEdge(
                cause_node_id=chain[i],
                effect_node_id=chain[i + 1],
                mechanism=rel_types[i] if i < len(rel_types) else "DEPENDS_ON",
                confidence=0.90,
                status=CausalEdgeStatus.VALID,
                structural_path_validated=True,
                evidence_object_ids=evidence_ids[:1],
            )
            state.add_causal_edge(edge)

        return state

    def build_fallback_thoughts(
        self,
        state: InvestigationState,
        context: dict,
    ) -> list[tuple[str, str]]:
        scenario_id = state.investigation_input.context.get("scenario_id", "")
        meta = _SCENARIO_METADATA.get(scenario_id, {})
        chain = _CAUSAL_CHAIN_NODE_IDS.get(scenario_id, [])
        node_names = meta.get("node_names", chain)
        hop_explanations = meta.get("hop_explanations", [])

        if not hop_explanations:
            return [("CONCLUDING", f"Backtracking {len(chain)} nodes to root cause.")]

        thoughts = []
        thoughts.append((
            "OBSERVING",
            f"Beginning ontology backtracking for scenario '{scenario_id}'. "
            f"Causal chain has {len(chain)} nodes. "
            f"Target root cause: {node_names[-1] if node_names else chain[-1]}.",
        ))

        for thought_type, content in hop_explanations:
            thoughts.append((thought_type, content))

        return thoughts
