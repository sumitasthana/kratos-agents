"""
src/demo/ontology/canon_graphs.py

Hardcoded CanonGraph definitions for the 3 demo scenarios.

Design:
  - All node IDs are deterministic stable strings (no UUIDs) so that tests
    can reference them by name without mocking the DB.
  - All labels/rel-types are taken verbatim from causelink/ontology/schema.py.
  - Each graph embeds its OntologyPath so that ValidationGate R2 passes
    without requiring state.ontology_paths_used to be populated externally.

Usage::

    from src.demo.ontology.canon_graphs import get_canon_graph
    graph = get_canon_graph("deposit_aggregation_failure")
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

from causelink.ontology.models import CanonEdge, CanonGraph, CanonNode, OntologyPath

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_PROVENANCE = "demo:hardcoded"


def _node(
    neo4j_id: str,
    label: str,
    primary_key: str,
    primary_value: str,
    **properties: object,
) -> CanonNode:
    return CanonNode(
        neo4j_id=neo4j_id,
        labels=[label],
        primary_key=primary_key,
        primary_value=primary_value,
        properties={"name": primary_value, **properties},
        provenance=_PROVENANCE,
    )


def _edge(rel_type: str, start: str, end: str, **props: object) -> CanonEdge:
    return CanonEdge(
        type=rel_type,
        start_node_id=start,
        end_node_id=end,
        properties=dict(props),
        provenance=_PROVENANCE,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — deposit_aggregation_failure
# ---------------------------------------------------------------------------
#
# CanonGraph path (using actual schema.py labels):
#   CTL-C2 -[GENERATES]-> INC-001
#   CTL-C2 -[MANDATES]-> RUL-AGG -[DEPENDS_ON]-> PIP-DIJ
#        -[RUNS_JOB]-> STP-AGG -[USES_SCRIPT]-> ART-JCL
# ---------------------------------------------------------------------------

def _build_deposit_aggregation_failure() -> CanonGraph:
    nodes = [
        _node("node-daf-inc001",  "Incident",         "incident_id",         "INC-001",
              title="FDIC Coverage Overstated — Depositor Aggregation Skipped",
              severity="CRITICAL"),
        _node("node-daf-ctl-c2",  "ControlObjective", "control_id",          "C2",
              name="Coverage Calculation Accuracy", regulation="12 CFR § 330.1(b)"),
        _node("node-daf-rul-agg", "Rule",              "rule_id",             "RUL-AGG",
              name="depositor_aggregation", description="Deposits must be summed at depositor level"),
        _node("node-daf-pip-dij", "Pipeline",          "pipeline_id",         "PIP-DIJ",
              name="DAILY-INSURANCE-JOB", jcl="batch/DAILY-INSURANCE-JOB.jcl"),
        _node("node-daf-stp-agg", "Job",               "job_id",              "STP-AGG",
              name="AGGRSTEP", step_number=3, status="SKIPPED",
              defect="DEF-LDS-001"),
        _node("node-daf-art-jcl", "Script",            "artifact_id",         "ART-JCL",
              name="DAILY-INSURANCE-JOB.jcl",
              path="operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl",
              defect_line=3),
    ]

    edges = [
        _edge("GENERATES",   "node-daf-ctl-c2",  "node-daf-inc001",
              reason="Control failure triggered compliance incident"),
        _edge("MANDATES",    "node-daf-ctl-c2",  "node-daf-rul-agg",
              citation="12 CFR § 330.1(b)"),
        _edge("DEPENDS_ON",  "node-daf-rul-agg", "node-daf-pip-dij",
              reason="Rule requires pipeline execution"),
        _edge("RUNS_JOB",    "node-daf-pip-dij", "node-daf-stp-agg",
              step=3),
        _edge("USES_SCRIPT", "node-daf-stp-agg", "node-daf-art-jcl",
              defect="DEF-LDS-001"),
    ]

    path = OntologyPath(
        path_id="path-daf-001",
        description=(
            "ControlObjective-[MANDATES]->Rule-[DEPENDS_ON]->Pipeline"
            "-[RUNS_JOB]->Job-[USES_SCRIPT]->Script"
        ),
        node_sequence=[
            "node-daf-ctl-c2",
            "node-daf-rul-agg",
            "node-daf-pip-dij",
            "node-daf-stp-agg",
            "node-daf-art-jcl",
        ],
        rel_type_sequence=["MANDATES", "DEPENDS_ON", "RUNS_JOB", "USES_SCRIPT"],
        hop_count=4,
        query_used="demo:hardcoded:deposit_aggregation_failure",
    )

    return CanonGraph(
        anchor_neo4j_id="node-daf-inc001",
        anchor_label="Incident",
        anchor_primary_key="incident_id",
        anchor_primary_value="INC-001",
        nodes=nodes,
        edges=edges,
        ontology_paths_used=[path],
        retrieved_at=datetime(2026, 3, 16, 6, 0, 0),
        max_hops=5,
    )


# ---------------------------------------------------------------------------
# Scenario 2 — trust_irr_misclassification
# ---------------------------------------------------------------------------
#
#   CTL-A3 -[GENERATES]-> INC-002
#   CTL-A3 -[MANDATES]-> RUL-IRR -[DEPENDS_ON]-> PIP-TDB
#        -[RUNS_JOB]-> ART-COB -[USES_SCRIPT]-> ART-BCJ
# ---------------------------------------------------------------------------

def _build_trust_irr_misclassification() -> CanonGraph:
    nodes = [
        _node("node-tim-inc002",  "Incident",         "incident_id",  "INC-002",
              title="Trust_Irrevocable Accounts Misclassified as Single Depositor",
              severity="CRITICAL"),
        _node("node-tim-ctl-a3",  "ControlObjective", "control_id",   "A3",
              name="Fiduciary Documentation", regulation="12 CFR § 330.13"),
        _node("node-tim-rul-irr", "Rule",              "rule_id",      "RUL-IRR",
              name="irr_orc_assignment",
              description="IRR deposits must use per-beneficiary coverage"),
        _node("node-tim-pip-tdb", "Pipeline",          "pipeline_id",  "PIP-TDB",
              name="TRUST-DAILY-BATCH", jcl="batch/TRUST-DAILY-BATCH.jcl"),
        _node("node-tim-art-cob", "Job",               "job_id",       "ART-COB",
              name="TRUST-INSURANCE-CALC",
              path="operational_systems/trust_custody_system/cobol/TRUST-INSURANCE-CALC.cob",
              defect="DEF-TCS-001"),
        _node("node-tim-art-bcj", "Script",            "artifact_id",  "ART-BCJ",
              name="BeneficiaryClassifier.java",
              path="operational_systems/trust_custody_system/java/BeneficiaryClassifier.java",
              defect="DEF-TCS-003", defect_line=147),
    ]

    edges = [
        _edge("GENERATES",   "node-tim-ctl-a3",  "node-tim-inc002",
              reason="Fiduciary control failure triggered compliance incident"),
        _edge("MANDATES",    "node-tim-ctl-a3",  "node-tim-rul-irr",
              citation="12 CFR § 330.13"),
        _edge("DEPENDS_ON",  "node-tim-rul-irr", "node-tim-pip-tdb",
              reason="IRR rule must be enforced by trust batch pipeline"),
        _edge("RUNS_JOB",    "node-tim-pip-tdb", "node-tim-art-cob",
              program="TRUST-INSURANCE-CALC"),
        _edge("USES_SCRIPT", "node-tim-art-cob", "node-tim-art-bcj",
              defect="DEF-TCS-003"),
    ]

    path = OntologyPath(
        path_id="path-tim-001",
        description=(
            "ControlObjective-[MANDATES]->Rule-[DEPENDS_ON]->Pipeline"
            "-[RUNS_JOB]->Job-[USES_SCRIPT]->Script"
        ),
        node_sequence=[
            "node-tim-ctl-a3",
            "node-tim-rul-irr",
            "node-tim-pip-tdb",
            "node-tim-art-cob",
            "node-tim-art-bcj",
        ],
        rel_type_sequence=["MANDATES", "DEPENDS_ON", "RUNS_JOB", "USES_SCRIPT"],
        hop_count=4,
        query_used="demo:hardcoded:trust_irr_misclassification",
    )

    return CanonGraph(
        anchor_neo4j_id="node-tim-inc002",
        anchor_label="Incident",
        anchor_primary_key="incident_id",
        anchor_primary_value="INC-002",
        nodes=nodes,
        edges=edges,
        ontology_paths_used=[path],
        retrieved_at=datetime(2026, 3, 16, 8, 15, 0),
        max_hops=5,
    )


# ---------------------------------------------------------------------------
# Scenario 3 — wire_mt202_drop
# ---------------------------------------------------------------------------
#
#   CTL-B1 -[GENERATES]-> INC-003
#   CTL-B1 -[MANDATES]-> RUL-SWF -[DEPENDS_ON]-> PIP-WNR
#        -[RUNS_JOB]-> MOD-SWP -[USES_SCRIPT]-> ART-SWP
# ---------------------------------------------------------------------------

def _build_wire_mt202_drop() -> CanonGraph:
    nodes = [
        _node("node-wmd-inc003",  "Incident",         "incident_id",  "INC-003",
              title="MT202/MT202COV Wire Transfers Silently Dropped — GL Break $284.7M",
              severity="CRITICAL"),
        _node("node-wmd-ctl-b1",  "ControlObjective", "control_id",   "B1",
              name="Daily Balance Snapshot", regulation="12 CFR § 370.4(a)(1)"),
        _node("node-wmd-rul-swf", "Rule",              "rule_id",      "RUL-SWF",
              name="swift_message_completeness",
              description="All SWIFT message types must be parsed and posted to GL"),
        _node("node-wmd-pip-wnr", "Pipeline",          "pipeline_id",  "PIP-WNR",
              name="WIRE-NIGHTLY-RECON"),
        _node("node-wmd-mod-swp", "Job",               "job_id",       "MOD-SWP",
              name="swift_parser.parse_message",
              path="operational_systems/wire_transfer_system/python/swift_parser.py",
              defect="DEF-WTS-001"),
        _node("node-wmd-art-swp", "Script",            "artifact_id",  "ART-SWP",
              name="swift_parser.py",
              path="operational_systems/wire_transfer_system/python/swift_parser.py",
              defect="DEF-WTS-001", defect_function="parse_message"),
    ]

    edges = [
        _edge("GENERATES",   "node-wmd-ctl-b1",  "node-wmd-inc003",
              reason="Daily balance snapshot control failure triggered GL break incident"),
        _edge("MANDATES",    "node-wmd-ctl-b1",  "node-wmd-rul-swf",
              citation="12 CFR § 370.4(a)(1)"),
        _edge("DEPENDS_ON",  "node-wmd-rul-swf", "node-wmd-pip-wnr",
              reason="SWIFT completeness rule must be enforced by nightly recon pipeline"),
        _edge("RUNS_JOB",    "node-wmd-pip-wnr", "node-wmd-mod-swp",
              module="swift_parser"),
        _edge("USES_SCRIPT", "node-wmd-mod-swp", "node-wmd-art-swp",
              defect="DEF-WTS-001"),
    ]

    path = OntologyPath(
        path_id="path-wmd-001",
        description=(
            "ControlObjective-[MANDATES]->Rule-[DEPENDS_ON]->Pipeline"
            "-[RUNS_JOB]->Job-[USES_SCRIPT]->Script"
        ),
        node_sequence=[
            "node-wmd-ctl-b1",
            "node-wmd-rul-swf",
            "node-wmd-pip-wnr",
            "node-wmd-mod-swp",
            "node-wmd-art-swp",
        ],
        rel_type_sequence=["MANDATES", "DEPENDS_ON", "RUNS_JOB", "USES_SCRIPT"],
        hop_count=4,
        query_used="demo:hardcoded:wire_mt202_drop",
    )

    return CanonGraph(
        anchor_neo4j_id="node-wmd-inc003",
        anchor_label="Incident",
        anchor_primary_key="incident_id",
        anchor_primary_value="INC-003",
        nodes=nodes,
        edges=edges,
        ontology_paths_used=[path],
        retrieved_at=datetime(2026, 3, 16, 22, 5, 0),
        max_hops=5,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_BUILDERS: Dict[str, object] = {
    "deposit_aggregation_failure": _build_deposit_aggregation_failure,
    "trust_irr_misclassification": _build_trust_irr_misclassification,
    "wire_mt202_drop":             _build_wire_mt202_drop,
}


def get_canon_graph(scenario_id: str) -> CanonGraph:
    """Return a freshly constructed CanonGraph for *scenario_id*."""
    builder = _BUILDERS.get(scenario_id)
    if builder is None:
        raise KeyError(
            f"Unknown scenario '{scenario_id}'. "
            f"Available: {sorted(_BUILDERS.keys())}"
        )
    return builder()  # type: ignore[operator]


def list_scenario_ids() -> list[str]:
    """Return the list of registered scenario IDs in insertion order."""
    return list(_BUILDERS.keys())
