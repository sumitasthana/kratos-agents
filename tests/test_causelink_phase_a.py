"""
tests/test_causelink_phase_a.py

Phase A smoke tests — no live Neo4j required.

These tests verify:
  1. Authoritative schema frozensets are complete and non-overlapping
  2. CanonNode / CanonEdge reject unknown labels/types at construction
  3. CanonGraph lookup helpers work correctly
  4. InvestigationState enforces citation and threshold rules
  5. ValidationGate enforces all 8 rules
  6. EvidenceObject construction and hash validation
  7. OntologySchemaSnapshot.current() captures the live schema
  8. Neo4jOntologyAdapter raises clearly when driver is absent or misconfigured
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from causelink.evidence.contracts import (
    EvidenceObject,
    EvidenceReliabilityTier,
    EvidenceSearchParams,
    EvidenceType,
    NullEvidenceService,
)
from causelink.ontology.adapter import OntologyAdapterError, Neo4jOntologyAdapter
from causelink.ontology.models import CanonEdge, CanonGraph, CanonNode, OntologyPath
from causelink.ontology.schema import (
    ANCHOR_LABELS,
    NODE_LABELS,
    RELATIONSHIP_TYPES,
    OntologySchemaSnapshot,
)
from causelink.state.investigation import (
    AuditTraceEntry,
    CausalEdge,
    CausalEdgeStatus,
    Hypothesis,
    HypothesisStatus,
    InvestigationAnchor,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
    MissingEvidence,
    RootCauseCandidate,
)
from causelink.validation.gates import ValidationGate, ValidationResult


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_node(
    label: str,
    neo4j_id: str = "node-1",
    primary_key: str = "incident_id",
    primary_value: str = "INC-001",
) -> CanonNode:
    return CanonNode(
        neo4j_id=neo4j_id,
        labels=[label],
        primary_key=primary_key,
        primary_value=primary_value,
        properties={},
        provenance="test",
    )


def _make_edge(
    rel_type: str,
    start: str = "node-1",
    end: str = "node-2",
) -> CanonEdge:
    return CanonEdge(
        neo4j_id="edge-1",
        type=rel_type,
        start_node_id=start,
        end_node_id=end,
        properties={},
        provenance="test",
    )


def _make_graph(anchor_id: str = "node-1") -> CanonGraph:
    incident_node = _make_node("Incident", neo4j_id=anchor_id)
    job_node = _make_node("Job", neo4j_id="node-2", primary_key="job_id", primary_value="J-1")
    edge = _make_edge("TRIGGERS", start=anchor_id, end="node-2")
    path = OntologyPath(
        path_id="path-1",
        description="test path",
        node_sequence=[anchor_id, "node-2"],
        rel_type_sequence=["TRIGGERS"],
        hop_count=1,
        query_used="test",
    )
    return CanonGraph(
        anchor_neo4j_id=anchor_id,
        anchor_label="Incident",
        anchor_primary_key="incident_id",
        anchor_primary_value="INC-001",
        nodes=[incident_node, job_node],
        edges=[edge],
        ontology_paths_used=[path],
    )


def _make_evidence(evidence_id: str = "ev-1") -> EvidenceObject:
    raw = b"dummy log content"
    raw_hash = EvidenceObject.make_hash(raw)
    return EvidenceObject(
        evidence_id=evidence_id,
        type=EvidenceType.LOG,
        source_system="test-system",
        content_ref="file:///tmp/ev/test.json",
        summary="Test log evidence",
        reliability=0.90,
        reliability_tier=EvidenceReliabilityTier.HIGH,
        raw_hash=raw_hash,
        collected_by="test_agent",
    )


def _make_state(canon_graph: CanonGraph | None = None) -> InvestigationState:
    return InvestigationState(
        investigation_input=InvestigationInput(
            anchor=InvestigationAnchor(
                anchor_type="Incident",
                anchor_primary_key="incident_id",
                anchor_primary_value="INC-001",
            )
        ),
        canon_graph=canon_graph,
        ontology_schema_snapshot=OntologySchemaSnapshot.current(),
    )


# ─── Schema tests ─────────────────────────────────────────────────────────────


class TestOntologySchema:
    def test_node_labels_count(self):
        assert len(NODE_LABELS) == 19

    def test_relationship_types_count(self):
        assert len(RELATIONSHIP_TYPES) == 26

    def test_anchor_labels_subset_of_node_labels(self):
        assert ANCHOR_LABELS.issubset(NODE_LABELS)

    def test_no_overlap_between_labels_and_rels(self):
        assert NODE_LABELS.isdisjoint(RELATIONSHIP_TYPES)

    def test_schema_snapshot_current(self):
        snap = OntologySchemaSnapshot.current()
        assert snap.schema_version == "1.0.0"
        assert set(snap.node_labels) == NODE_LABELS
        assert set(snap.relationship_types) == RELATIONSHIP_TYPES
        assert set(snap.anchor_labels) == ANCHOR_LABELS

    def test_known_labels_present(self):
        for label in ("Incident", "Violation", "Job", "Pipeline", "System", "Owner"):
            assert label in NODE_LABELS

    def test_known_rels_present(self):
        for rel in ("RUNS_JOB", "TRIGGERS", "MANDATES", "RESOLVED_BY", "OWNS_JOB"):
            assert rel in RELATIONSHIP_TYPES


# ─── CanonNode tests ──────────────────────────────────────────────────────────


class TestCanonNode:
    def test_valid_node_construction(self):
        node = _make_node("Incident")
        assert "Incident" in node.labels

    def test_rejects_unknown_label(self):
        with pytest.raises(ValueError, match="Ontology violation"):
            CanonNode(
                neo4j_id="x",
                labels=["FakeLabel"],
                properties={},
                provenance="test",
            )

    def test_rejects_mixed_labels(self):
        """A mix of valid + invalid labels must fail."""
        with pytest.raises(ValueError, match="Ontology violation"):
            CanonNode(
                neo4j_id="x",
                labels=["Incident", "FakeLabel"],
                properties={},
                provenance="test",
            )

    def test_multiple_valid_labels(self):
        node = CanonNode(
            neo4j_id="x",
            labels=["Job", "System"],
            properties={},
            provenance="test",
        )
        assert set(node.labels) == {"Job", "System"}


# ─── CanonEdge tests ──────────────────────────────────────────────────────────


class TestCanonEdge:
    def test_valid_edge_construction(self):
        edge = _make_edge("TRIGGERS")
        assert edge.type == "TRIGGERS"

    def test_rejects_unknown_rel_type(self):
        with pytest.raises(ValueError, match="Ontology violation"):
            CanonEdge(
                type="INVENTED_REL",
                start_node_id="a",
                end_node_id="b",
                properties={},
                provenance="test",
            )


# ─── CanonGraph tests ─────────────────────────────────────────────────────────


class TestCanonGraph:
    def test_get_node(self):
        graph = _make_graph("node-1")
        node = graph.get_node("node-1")
        assert node is not None
        assert "Incident" in node.labels

    def test_get_node_missing_returns_none(self):
        graph = _make_graph()
        assert graph.get_node("nonexistent") is None

    def test_neighbors(self):
        graph = _make_graph("node-1")
        neighbors = graph.neighbors("node-1")
        assert len(neighbors) == 1
        assert neighbors[0].neo4j_id == "node-2"

    def test_find_nodes_by_label(self):
        graph = _make_graph("node-1")
        incidents = graph.find_nodes_by_label("Incident")
        assert len(incidents) == 1

    def test_find_nodes_unknown_label_raises(self):
        graph = _make_graph()
        with pytest.raises(ValueError, match="Unknown ontology label"):
            graph.find_nodes_by_label("NotALabel")

    def test_contains_node(self):
        graph = _make_graph("node-1")
        assert graph.contains_node("node-1")
        assert not graph.contains_node("ghost")

    def test_summary_structure(self):
        graph = _make_graph("node-1")
        s = graph.summary()
        assert s["node_count"] == 2
        assert s["edge_count"] == 1
        assert "Incident" in s["label_counts"]

    def test_edges_between(self):
        graph = _make_graph("node-1")
        edges = graph.edges_between("node-1", "node-2")
        assert len(edges) == 1
        assert edges[0].type == "TRIGGERS"


# ─── EvidenceObject tests ─────────────────────────────────────────────────────


class TestEvidenceObject:
    def test_valid_construction(self):
        ev = _make_evidence()
        assert ev.evidence_id == "ev-1"
        assert ev.type == EvidenceType.LOG

    def test_make_hash(self):
        raw = b"test content"
        h = EvidenceObject.make_hash(raw)
        assert h.startswith("sha256:")
        assert len(h) == 71  # "sha256:" (7) + 64 hex chars

    def test_rejects_bad_hash_format(self):
        raw = b"x"
        with pytest.raises(ValueError, match="sha256:"):
            EvidenceObject(
                evidence_id="x",
                type=EvidenceType.LOG,
                source_system="test",
                content_ref="file:///tmp/x",
                summary="summary",
                reliability=0.9,
                reliability_tier=EvidenceReliabilityTier.HIGH,
                raw_hash="notahash",  # missing sha256: prefix
                collected_by="test",
            )

    def test_rejects_inconsistent_tier(self):
        raw_hash = EvidenceObject.make_hash(b"x")
        with pytest.raises(ValueError, match="inconsistent"):
            EvidenceObject(
                evidence_id="x",
                type=EvidenceType.METRIC,
                source_system="test",
                content_ref="file:///tmp/x",
                summary="summary",
                reliability=0.9,   # HIGH
                reliability_tier=EvidenceReliabilityTier.LOW,  # wrong
                raw_hash=raw_hash,
                collected_by="test",
            )

    def test_frozen(self):
        ev = _make_evidence()
        with pytest.raises(Exception):  # ValidationError or AttributeError
            ev.summary = "mutated"  # type: ignore[misc]

    def test_tier_for(self):
        assert EvidenceObject.tier_for(0.9) == EvidenceReliabilityTier.HIGH
        assert EvidenceObject.tier_for(0.6) == EvidenceReliabilityTier.MEDIUM
        assert EvidenceObject.tier_for(0.3) == EvidenceReliabilityTier.LOW

    def test_null_service_returns_none(self):
        svc = NullEvidenceService()
        params = EvidenceSearchParams(entity_ids=["node-1"])
        assert svc.search_logs(params, "agent") is None
        assert svc.get_evidence("ev-1") is None


# ─── InvestigationState tests ─────────────────────────────────────────────────


class TestInvestigationState:
    def test_initial_status(self):
        state = _make_state()
        assert state.status == InvestigationStatus.INITIALIZING

    def test_add_hypothesis_valid(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        h = Hypothesis(
            description="Test hypothesis",
            involved_node_ids=["node-1"],
            generated_by="test_agent",
        )
        state.add_hypothesis(h)
        assert len(state.hypotheses) == 1

    def test_add_hypothesis_rejects_unknown_node(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        h = Hypothesis(
            description="Bad hypothesis",
            involved_node_ids=["ghost-node-999"],
            generated_by="test_agent",
        )
        with pytest.raises(ValueError, match="not in the CanonGraph"):
            state.add_hypothesis(h)

    def test_blocking_missing_evidence_sets_escalation(self):
        state = _make_state()
        m = MissingEvidence(
            evidence_type="log",
            description="Need executor logs",
            blocking=True,
        )
        state.add_missing_evidence(m)
        assert state.escalation is True
        assert state.escalation_reason is not None

    def test_non_blocking_missing_evidence_no_escalation(self):
        state = _make_state()
        m = MissingEvidence(
            evidence_type="metric",
            description="Nice-to-have metric",
            blocking=False,
        )
        state.add_missing_evidence(m)
        assert state.escalation is False

    def test_set_root_cause_final_threshold_enforced(self):
        state = _make_state()
        candidate = RootCauseCandidate(
            node_id="node-1",
            description="Low confidence candidate",
            composite_score=0.40,  # below default 0.80 threshold
        )
        with pytest.raises(ValueError, match="composite_score"):
            state.set_root_cause_final(candidate, ranker_agent_type="ranker")

    def test_set_root_cause_final_blocking_items_enforced(self):
        state = _make_state()
        state.add_missing_evidence(
            MissingEvidence(evidence_type="log", description="x", blocking=True)
        )
        candidate = RootCauseCandidate(
            node_id="node-1",
            description="High confidence but blocked",
            composite_score=0.95,
        )
        with pytest.raises(ValueError, match="blocking evidence"):
            state.set_root_cause_final(candidate, ranker_agent_type="ranker")

    def test_set_root_cause_final_success(self):
        state = _make_state()
        candidate = RootCauseCandidate(
            node_id="node-1",
            description="Confirmed root cause",
            composite_score=0.90,
        )
        state.set_root_cause_final(candidate, ranker_agent_type="ranker")
        assert state.root_cause_final is not None
        assert state.status == InvestigationStatus.COMPLETED

    def test_transition_to_insufficient(self):
        state = _make_state()
        state.transition_to_insufficient("Not enough logs")
        assert state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE
        assert state.root_cause_final is None
        assert state.escalation is True

    def test_insufficient_evidence_report(self):
        state = _make_state()
        state.add_missing_evidence(
            MissingEvidence(
                evidence_type="log",
                description="Missing executor logs",
                blocking=True,
            )
        )
        report = state.insufficient_evidence_report()
        assert report["status"] == "Insufficient evidence"
        assert len(report["missing_evidence"]) == 1

    def test_audit_trace_append(self):
        state = _make_state()
        entry = AuditTraceEntry(
            agent_type="test_agent",
            action="test_action",
        )
        state.append_audit(entry)
        assert len(state.audit_trace) == 1


# ─── RootCauseCandidate status derivation ────────────────────────────────────


class TestRootCauseCandidateScoring:
    def test_confirmed_at_threshold(self):
        c = RootCauseCandidate(node_id="x", description="x", composite_score=0.85)
        assert c.status == HypothesisStatus.CONFIRMED

    def test_probable_range(self):
        c = RootCauseCandidate(node_id="x", description="x", composite_score=0.65)
        assert c.status == HypothesisStatus.PROBABLE

    def test_possible_range(self):
        c = RootCauseCandidate(node_id="x", description="x", composite_score=0.30)
        assert c.status == HypothesisStatus.POSSIBLE

    def test_boundary_at_0_80_is_confirmed(self):
        c = RootCauseCandidate(node_id="x", description="x", composite_score=0.80)
        assert c.status == HypothesisStatus.CONFIRMED

    def test_boundary_at_0_50_is_probable(self):
        c = RootCauseCandidate(node_id="x", description="x", composite_score=0.50)
        assert c.status == HypothesisStatus.PROBABLE


# ─── ValidationGate tests ─────────────────────────────────────────────────────


class TestValidationGate:
    def setup_method(self):
        self.gate = ValidationGate()

    def test_valid_canon_graph_passes(self):
        graph = _make_graph()
        result = self.gate.validate_canon_graph(graph)
        assert result.passed

    def test_not_found_anchor_fails_r6(self):
        graph = CanonGraph(
            anchor_neo4j_id="NOT_FOUND",
            anchor_label="Incident",
            anchor_primary_key="incident_id",
            anchor_primary_value="INC-MISSING",
        )
        result = self.gate.validate_canon_graph(graph)
        assert not result.passed
        assert any("R6" in v for v in result.violations)

    def test_hypothesis_invalid_node_id_fails_r3(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        h = Hypothesis(
            description="Test",
            involved_node_ids=["ghost-id"],
            generated_by="agent",
        )
        result = self.gate.validate_hypothesis(h, state)
        assert not result.passed
        assert any("R3" in v for v in result.violations)

    def test_hypothesis_unknown_evidence_id_fails_r1(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        h = Hypothesis(
            description="Test",
            involved_node_ids=["node-1"],
            evidence_object_ids=["ev-unknown"],
            generated_by="agent",
        )
        result = self.gate.validate_hypothesis(h, state)
        assert not result.passed
        assert any("R1" in v for v in result.violations)

    def test_hypothesis_valid_evidence_passes_r1(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        ev = _make_evidence("ev-real")
        state.evidence_objects.append(ev)
        h = Hypothesis(
            description="Test",
            involved_node_ids=["node-1"],
            evidence_object_ids=["ev-real"],
            generated_by="agent",
        )
        result = self.gate.validate_hypothesis(h, state)
        assert result.passed, result.violations

    def test_valid_causal_edge_without_path_fails_r4(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        edge = CausalEdge(
            cause_node_id="node-1",
            effect_node_id="node-2",
            mechanism="test cause",
            status=CausalEdgeStatus.VALID,
            structural_path_validated=False,  # not validated
        )
        result = self.gate.validate_causal_edge(edge, state)
        assert not result.passed
        assert any("R4" in v for v in result.violations)

    def test_pending_edge_without_path_passes(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        edge = CausalEdge(
            cause_node_id="node-1",
            effect_node_id="node-2",
            mechanism="test",
            status=CausalEdgeStatus.PENDING,
        )
        result = self.gate.validate_causal_edge(edge, state)
        assert result.passed, result.violations

    def test_r5_non_ranker_cannot_confirm(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        candidate = RootCauseCandidate(
            node_id="node-1",
            description="Attempt to confirm",
            composite_score=0.90,
        )
        result = self.gate.validate_root_cause_candidate(
            candidate, state, calling_agent="some_other_agent"
        )
        assert not result.passed
        assert any("R5" in v for v in result.violations)

    def test_r5_ranker_can_confirm(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        candidate = RootCauseCandidate(
            node_id="node-1",
            description="Ranker confirms",
            composite_score=0.90,
        )
        result = self.gate.validate_root_cause_candidate(
            candidate, state, calling_agent="ranker"
        )
        assert result.passed, result.violations

    def test_r8_blocking_evidence_prevents_confirm(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        state.add_missing_evidence(
            MissingEvidence(evidence_type="log", description="needed", blocking=True)
        )
        candidate = RootCauseCandidate(
            node_id="node-1",
            description="x",
            composite_score=0.90,
        )
        result = self.gate.validate_root_cause_candidate(
            candidate, state, calling_agent="ranker"
        )
        assert not result.passed
        assert any("R8" in v for v in result.violations)

    def test_check_missing_citations_empty_when_clean(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        ev = _make_evidence("ev-1")
        state.evidence_objects.append(ev)
        h = Hypothesis(
            description="Test",
            involved_node_ids=["node-1"],
            evidence_object_ids=["ev-1"],
            status=HypothesisStatus.SUPPORTED,
            generated_by="agent",
        )
        # Bypass node check since we just need to test citation check
        state.hypotheses.append(h)
        issues = self.gate.check_missing_citations(state)
        assert issues == []

    def test_check_missing_citations_detects_orphan(self):
        graph = _make_graph("node-1")
        state = _make_state(canon_graph=graph)
        h = Hypothesis(
            description="Orphan",
            involved_node_ids=["node-1"],
            evidence_object_ids=["ev-ghost"],  # not in state.evidence_objects
            status=HypothesisStatus.SUPPORTED,
            generated_by="agent",
        )
        state.hypotheses.append(h)  # bypass add_hypothesis node check
        issues = self.gate.check_missing_citations(state)
        assert any("ev-ghost" in i for i in issues)


# ─── Neo4jOntologyAdapter tests (no live DB) ─────────────────────────────────


class TestNeo4jOntologyAdapterNoDB:
    def test_from_env_raises_without_vars(self, monkeypatch):
        monkeypatch.delenv("NEO4J_URI", raising=False)
        monkeypatch.delenv("NEO4J_USER", raising=False)
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        with pytest.raises(OntologyAdapterError, match="Missing required env vars"):
            Neo4jOntologyAdapter.from_env()

    def test_invalid_anchor_label_raises(self, monkeypatch):
        """Adapter must reject anchor labels not in ANCHOR_LABELS before any DB call."""
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "test")

        # Patch the driver so no real connection is attempted
        with patch("causelink.ontology.adapter._NEO4J_AVAILABLE", True), \
             patch("causelink.ontology.adapter.GraphDatabase") as mock_gdb:
            mock_gdb.driver.return_value = MagicMock()
            adapter = Neo4jOntologyAdapter.from_env()
            with pytest.raises(OntologyAdapterError, match="Invalid anchor label"):
                adapter.get_neighborhood(
                    anchor_label="FakeLabel",
                    anchor_primary_key="id",
                    anchor_primary_value="123",
                )

    def test_hard_max_hops_is_capped(self, monkeypatch):
        """max_hops above _HARD_MAX_HOPS should be silently capped, not raise."""
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USER", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "test")

        with patch("causelink.ontology.adapter._NEO4J_AVAILABLE", True), \
             patch("causelink.ontology.adapter.GraphDatabase") as mock_gdb:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.run.return_value = []  # simulate empty result
            mock_driver = MagicMock()
            mock_driver.session.return_value = mock_session
            mock_gdb.driver.return_value = mock_driver

            adapter = Neo4jOntologyAdapter.from_env()
            # max_hops=99 must be capped at 6 — should not raise
            graph = adapter.get_neighborhood(
                anchor_label="Incident",
                anchor_primary_key="incident_id",
                anchor_primary_value="INC-001",
                max_hops=99,
            )
            assert graph.anchor_neo4j_id == "NOT_FOUND"
            assert graph.max_hops == 6
