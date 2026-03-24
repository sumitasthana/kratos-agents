"""
src/demo/ontology/scenario_seeder.py

ScenarioSeeder — seeds an InvestigationState with the canonical CanonGraph
for a given demo scenario.

Responsibilities:
  - Load the hardcoded CanonGraph from canon_graphs.py
  - Construct InvestigationInput + InvestigationAnchor from the scenario pack
  - Build an InvestigationState with canon_graph and ontology_schema_snapshot populated
  - Append an audit trace entry for the seeding step

No Neo4j calls are made.  Demo mode is 100% in-memory.

Usage::

    seeder = ScenarioSeeder()
    state  = seeder.seed("deposit_aggregation_failure", pack)
"""

from __future__ import annotations

import logging
from datetime import datetime

from causelink.ontology.schema import OntologySchemaSnapshot
from causelink.state.investigation import (
    AuditTraceEntry,
    InvestigationAnchor,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
)

from .canon_graphs import get_canon_graph
from ..loaders.scenario_loader import ScenarioPack

logger = logging.getLogger(__name__)


class ScenarioSeeder:
    """
    Constructs a fresh InvestigationState seeded with graph + schema for
    a given demo scenario.

    The returned state has:
      - status = ONTOLOGY_LOADING → EVIDENCE_COLLECTION (callers advance status)
      - canon_graph populated from canon_graphs.py (in-memory, no Neo4j)
      - ontology_schema_snapshot set from OntologySchemaSnapshot.current()
      - one AuditTraceEntry recording the seeding step
    """

    def seed(
        self,
        scenario_id: str,
        pack: ScenarioPack,
        confidence_threshold: float = 0.70,
    ) -> InvestigationState:
        """
        Build and return a seeded InvestigationState for *scenario_id*.

        Args:
            scenario_id: One of the registered demo scenario IDs.
            pack: The loaded ScenarioPack for this scenario.
            confidence_threshold: Passed to InvestigationInput.
                0.70 is used for demo mode (lower than production 0.80)
                so that our weighted composite scores confirm correctly.
        """
        inc = pack.incident
        anchor = InvestigationAnchor(
            anchor_type=inc.get("anchor_type", "Incident"),
            anchor_primary_key="incident_id",
            anchor_primary_value=inc["incident_id"],
        )
        investigation_input = InvestigationInput(
            anchor=anchor,
            max_hops=5,
            confidence_threshold=confidence_threshold,
            context={
                "scenario_id": scenario_id,
                "job_id": pack.job_id,
                "regulation": inc.get("regulation", ""),
                "defect_id": inc.get("defect_id", ""),
            },
            requested_by="demo_rca_service",
        )

        canon_graph = get_canon_graph(scenario_id)
        schema_snapshot = OntologySchemaSnapshot.current()

        state = InvestigationState(
            investigation_input=investigation_input,
            status=InvestigationStatus.ONTOLOGY_LOADING,
            canon_graph=canon_graph,
            ontology_schema_snapshot=schema_snapshot,
        )

        # Add the embedded ontology paths to state.ontology_paths_used so R2 passes
        # on both state and graph levels.
        for path in canon_graph.ontology_paths_used:
            state.add_ontology_path(path)

        state.append_audit(AuditTraceEntry(
            agent_type="ScenarioSeeder",
            action="ontology_load",
            inputs_summary={
                "scenario_id": scenario_id,
                "anchor": anchor.anchor_primary_value,
            },
            outputs_summary={
                "node_count":  len(canon_graph.nodes),
                "edge_count":  len(canon_graph.edges),
                "paths_loaded": len(canon_graph.ontology_paths_used),
            },
            decision="canon_graph_seeded_from_hardcoded_definitions",
        ))

        state.status = InvestigationStatus.EVIDENCE_COLLECTION
        logger.info(
            "ScenarioSeeder: seeded state for '%s' (anchor=%s, nodes=%d, edges=%d)",
            scenario_id,
            anchor.anchor_primary_value,
            len(canon_graph.nodes),
            len(canon_graph.edges),
        )
        return state
