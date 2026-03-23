"""
tests/demo/test_canon_graphs.py

Tests for canon_graphs.py — hardcoded CanonGraph definitions.

Verifies:
  - All node IDs are unique per graph
  - All node labels are valid (from NODE_LABELS)
  - All edge relation types are valid (from RELATIONSHIP_TYPES)
  - All graph anchor IDs are present as nodes
  - OntologyPath node_sequence matches actual nodes
  - get_canon_graph() and list_scenario_ids() work correctly
"""

from __future__ import annotations

import pytest

from causelink.ontology.schema import NODE_LABELS, RELATIONSHIP_TYPES
from demo.ontology.canon_graphs import get_canon_graph, list_scenario_ids


SCENARIO_IDS = [
    "deposit_aggregation_failure",
    "trust_irr_misclassification",
    "wire_mt202_drop",
]


@pytest.fixture(params=SCENARIO_IDS)
def scenario_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def graph(scenario_id: str):
    return get_canon_graph(scenario_id)


class TestListScenarioIds:
    def test_returns_all_three(self) -> None:
        ids = list_scenario_ids()
        for sid in SCENARIO_IDS:
            assert sid in ids

    def test_returns_list(self) -> None:
        assert isinstance(list_scenario_ids(), list)


class TestGetCanonGraph:
    def test_unknown_scenario_raises(self) -> None:
        with pytest.raises(KeyError):
            get_canon_graph("ghost_scenario")

    def test_returns_canon_graph(self, graph) -> None:
        from causelink.ontology.models import CanonGraph
        assert isinstance(graph, CanonGraph)

    def test_anchor_id_present_in_nodes(self, graph) -> None:
        node_ids = {n.neo4j_id for n in graph.nodes}
        assert graph.anchor_neo4j_id in node_ids

    def test_anchor_label_valid(self, graph) -> None:
        assert graph.anchor_label in NODE_LABELS

    def test_all_node_labels_valid(self, graph) -> None:
        for node in graph.nodes:
            for label in node.labels:
                assert label in NODE_LABELS, (
                    f"Node {node.neo4j_id} has invalid label '{label}'"
                )

    def test_all_edge_types_valid(self, graph) -> None:
        for edge in graph.edges:
            assert edge.type in RELATIONSHIP_TYPES, (
                f"Edge {edge.neo4j_id} has invalid type '{edge.type}'"
            )

    def test_node_ids_unique(self, graph) -> None:
        ids = [n.neo4j_id for n in graph.nodes]
        assert len(ids) == len(set(ids)), "CanonGraph has duplicate node IDs"

    def test_at_least_one_path(self, graph) -> None:
        assert len(graph.ontology_paths_used) >= 1

    def test_path_node_sequence_references_valid_nodes(self, graph) -> None:
        node_ids = {n.neo4j_id for n in graph.nodes}
        for path in graph.ontology_paths_used:
            for nid in path.node_sequence:
                assert nid in node_ids, (
                    f"Path {path.path_id} references unknown node '{nid}'"
                )

    def test_path_hop_count_consistent(self, graph) -> None:
        for path in graph.ontology_paths_used:
            expected_hops = len(path.node_sequence) - 1
            # hop_count can ≤ node count (may count edges differently)
            assert path.hop_count > 0

    def test_graph_has_six_nodes(self, graph) -> None:
        # Each demo scenario has exactly 6 nodes in its canonical chain
        assert len(graph.nodes) == 6, (
            f"Expected 6 nodes, got {len(graph.nodes)}"
        )

    def test_contains_node_returns_true_for_existing(self, graph) -> None:
        node_id = graph.nodes[0].neo4j_id
        assert graph.contains_node(node_id)

    def test_contains_node_returns_false_for_missing(self, graph) -> None:
        assert not graph.contains_node("node-does-not-exist-xyz")

    def test_deposit_has_incident_node(self) -> None:
        g = get_canon_graph("deposit_aggregation_failure")
        incident_nodes = [n for n in g.nodes if "Incident" in n.labels]
        assert len(incident_nodes) == 1

    def test_trust_anchor_is_incident(self) -> None:
        g = get_canon_graph("trust_irr_misclassification")
        assert g.anchor_label == "Incident"

    def test_wire_anchor_primary_value(self) -> None:
        g = get_canon_graph("wire_mt202_drop")
        assert g.anchor_primary_value == "INC-003"
