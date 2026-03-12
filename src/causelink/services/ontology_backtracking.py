"""
causelink/services/ontology_backtracking.py

OntologyBacktrackingService — ontology-driven multi-hop backtracking with early stop.

Core behaviour:
  1. Accept an InvestigationState (must have canon_graph populated).
  2. Build a deterministic traversal sequence from the anchor node across
     all applicable chain types (operational, compliance, lineage, change, log).
  3. Evaluate each node in order using NodeEvaluatorRegistry.
  4. In NORMAL mode: stop at the first CONFIRMED FAILED node (not the anchor).
  5. In EXPLORATORY mode: evaluate all nodes regardless of failure.
  6. Return BacktrackingResult which includes lineage_walk and failure_node.
  7. Provide to_dashboard_summary() to produce an RcaDashboardSummary.

Early-stop semantics:
  - The anchor node IS evaluated (to record its status) but NEVER triggers
    the early stop, even when it is an Incident or Violation.
  - The first NON-ANCHOR node confirmed as FAILED triggers FIRST_CONFIRMED_FAILURE.
  - All subsequent nodes are marked NOT_EVALUATED_DUE_TO_EARLY_STOP.

Chain traversal order (deterministic):
  Priority 1 — Operational:  System, Job, Pipeline
  Priority 2 — Compliance:   Incident, Violation, Rule, ControlObjective, Regulation
  Priority 3 — Lineage:      Script, Transformation, Table, Column, DataSource, Dataset
  Priority 4 — Change:       CodeEvent
  Priority 5 — Log scope:    LogSource
  Priority 6 — Ownership:    Owner
  (ties broken by BFS hop distance from anchor)

Ontology-first invariant:
  Only nodes and edges present in state.canon_graph are traversed.
  The traversal never queries Neo4j at evaluation time.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from causelink.ontology.models import CanonGraph, CanonNode
from causelink.services.dashboard_schema import (
    AgentAnalysisChainEntry,
    BacktrackingResult,
    LineageWalkNode,
    NodeEvaluationResult,
    NodeStatus,
    RcaDashboardSummary,
    StopReason,
    TraversalMode,
)
from causelink.services.node_evaluators import EvidenceScoper, NodeEvaluatorRegistry
from causelink.state.investigation import InvestigationState, InvestigationStatus

logger = logging.getLogger(__name__)

# ─── Chain priority map ───────────────────────────────────────────────────────
# Lower number = evaluated earlier (higher priority in root-cause search).

_LABEL_CHAIN_PRIORITY: Dict[str, int] = {
    # Operational chain — checked first (most common root causes)
    "System": 1,
    "Job": 1,
    "Pipeline": 1,
    # Compliance chain
    "Incident": 2,
    "Violation": 2,
    "Rule": 2,
    "ControlObjective": 2,
    "Regulation": 2,
    "Escalation": 2,
    "Remediation": 2,
    # Lineage chain
    "Script": 3,
    "Transformation": 3,
    "Table": 3,
    "Column": 3,
    "DataSource": 3,
    "Dataset": 3,
    # Change provenance
    "CodeEvent": 4,
    # Log scope
    "LogSource": 5,
    # Ownership (lowest priority)
    "Owner": 6,
}

_DEFAULT_CHAIN_PRIORITY = 7  # for any labels not in the map

# Relationship types associated with each chain (used for lineage walk labelling)
_OPERATIONAL_RELS: frozenset = frozenset({"RUNS_JOB", "EXECUTES", "DEPENDS_ON"})
_COMPLIANCE_RELS: frozenset = frozenset({
    "CREATES", "GENERATES", "MANDATES", "IMPLEMENTED_BY", "ENFORCED_BY",
    "TYPICALLY_IMPLEMENTS", "TRIGGERS",
})
_LINEAGE_RELS: frozenset = frozenset({
    "USES_SCRIPT", "READS", "WRITES", "CONTAINS", "HAS_COLUMN",
    "DERIVED_FROM", "SOURCED_FROM", "HAS_TRANSFORMATION",
})
_CHANGE_RELS: frozenset = frozenset({"CHANGED_BY"})
_LOG_RELS: frozenset = frozenset({"LOGGED_IN"})
_OWNERSHIP_RELS: frozenset = frozenset({
    "OWNS_PIPELINE", "OWNS_JOB", "OWNS_SYSTEM", "OWNS_CONTROL",
    "ASSIGNED_TO", "RESOLVED_BY",
})


def _label_priority(node: CanonNode) -> int:
    """Return chain priority for the given node's primary label."""
    primary = node.labels[0] if node.labels else ""
    return _LABEL_CHAIN_PRIORITY.get(primary, _DEFAULT_CHAIN_PRIORITY)


def _chain_name_for_label(label: str) -> str:
    """Map a node label to its chain type name."""
    if label in ("System", "Job", "Pipeline"):
        return "operational"
    if label in ("Incident", "Violation", "Rule", "ControlObjective", "Regulation",
                 "Escalation", "Remediation"):
        return "compliance"
    if label in ("Script", "Transformation", "Table", "Column", "DataSource", "Dataset"):
        return "lineage"
    if label == "CodeEvent":
        return "change_provenance"
    if label == "LogSource":
        return "log_scope"
    return "general"


def _problem_type_for_failure(node: CanonNode) -> str:
    """Derive a problem_type string from the failed node's label."""
    label = node.labels[0] if node.labels else ""
    chain = _chain_name_for_label(label)
    mapping = {
        "operational": "execution_failure",
        "compliance": "compliance_gap",
        "lineage": "lineage",
        "change_provenance": "regression_risk",
        "log_scope": "general",
    }
    return mapping.get(chain, "general")


# ─── Traversal sequence builder ───────────────────────────────────────────────


def _bfs_traversal(
    graph: CanonGraph,
    anchor_id: str,
) -> List[Tuple[CanonNode, int, str]]:
    """
    BFS from the anchor node collecting all reachable nodes in the CanonGraph.

    Returns a list of (node, hop_distance, incoming_rel_type) tuples.
    The anchor node is the first entry with hop_distance=0 and rel_type="".

    Tie-breaking for equal hop distance: sort by label chain priority.
    Nodes are never revisited.
    """
    anchor_node = graph.get_node(anchor_id)
    if anchor_node is None:
        return []

    visited: Set[str] = {anchor_id}
    # queue: (node, hop, incoming_rel_type)
    queue: deque = deque([(anchor_node, 0, "")])
    result: List[Tuple[CanonNode, int, str]] = []

    while queue:
        node, hop, incoming_rel = queue.popleft()
        result.append((node, hop, incoming_rel))

        # Expand adjacency (both directions)
        adj_edges = graph._adj.get(node.neo4j_id, [])
        # Sort adjacent edges for deterministic ordering
        adj_edges_sorted = sorted(adj_edges, key=lambda e: e.type)

        for edge in adj_edges_sorted:
            # Determine the neighbor ID and the relationship type for this step
            if edge.start_node_id == node.neo4j_id:
                neighbor_id = edge.end_node_id
                rel_label = edge.type
            else:
                neighbor_id = edge.start_node_id
                rel_label = edge.type

            if neighbor_id in visited:
                continue
            visited.add(neighbor_id)

            nb = graph.get_node(neighbor_id)
            if nb is not None:
                queue.append((nb, hop + 1, rel_label))

    return result


def _build_traversal_sequence(
    graph: CanonGraph,
) -> List[Tuple[CanonNode, int, str]]:
    """
    Build a deterministic, priority-sorted traversal sequence from the anchor.

    Order:
      1. Anchor node (hop=0) — always first.
      2. All other nodes sorted by (chain_priority, hop_distance, node_label).

    Returns list of (node, hop, incoming_rel_type) tuples.
    """
    bfs_result = _bfs_traversal(graph, graph.anchor_neo4j_id)
    if not bfs_result:
        return []

    anchor_entry = bfs_result[0]  # anchor is always first from BFS
    rest = bfs_result[1:]

    # Sort non-anchor nodes by (priority, hop, label)
    rest_sorted = sorted(
        rest,
        key=lambda t: (_label_priority(t[0]), t[1], t[0].labels[0] if t[0].labels else ""),
    )

    return [anchor_entry] + rest_sorted


def _path_string_from_anchor(
    graph: CanonGraph,
    target_node: CanonNode,
    hop: int,
    incoming_rel: str,
) -> str:
    """
    Build a human-readable structural path string for a node.

    For the anchor: returns its label.
    For other nodes: returns 'AnchorLabel-[REL]->NodeLabel (hop N)'.
    """
    anchor_node = graph.get_node(graph.anchor_neo4j_id)
    anchor_label = (
        anchor_node.labels[0] if anchor_node and anchor_node.labels else graph.anchor_label
    )
    target_label = target_node.labels[0] if target_node.labels else "Unknown"

    if hop == 0:
        return anchor_label

    if incoming_rel:
        return f"{anchor_label}-[...]->...{incoming_rel}->{target_label} (hop {hop})"
    return f"{anchor_label}->...{target_label} (hop {hop})"


# ─── OntologyBacktrackingService ─────────────────────────────────────────────


class OntologyBacktrackingService:
    """
    Performs ontology-driven multi-hop backtracking with early-stop logic.

    Usage::

        service = OntologyBacktrackingService()
        result = service.backtrack_with_early_stop(state, mode="normal")
        summary = service.to_dashboard_summary(state, result)

    Constraints:
      - state.canon_graph must be populated before calling backtrack_with_early_stop.
      - The traversal never queries Neo4j — it uses only the CanonGraph.
      - Evidence comes only from state.evidence_objects and state.hypotheses.
      - No evidence or graph structure is fabricated.
    """

    def __init__(self) -> None:
        self._registry = NodeEvaluatorRegistry()

    def backtrack_with_early_stop(
        self,
        state: InvestigationState,
        mode: str = "normal",
    ) -> BacktrackingResult:
        """
        Execute the multi-hop backtracking traversal.

        Parameters
        ----------
        state : InvestigationState
            Investigation state. Must have canon_graph populated.
            Evidence and hypotheses may be empty (nodes evaluate as UNKNOWN).
        mode : str
            'normal' — stop at first confirmed failure (default).
            'exploratory' — evaluate all nodes; do not stop early.

        Returns
        -------
        BacktrackingResult
            Includes traversal_sequence, failure_node, stop_reason, lineage_walk.

        Raises
        ------
        ValueError
            When state.canon_graph is None (OntologyContextAgent must run first).
        """
        if state.canon_graph is None:
            raise ValueError(
                "OntologyBacktrackingService requires state.canon_graph. "
                "Run OntologyContextAgent first."
            )

        traversal_mode = (
            TraversalMode.EXPLORATORY if mode == "exploratory" else TraversalMode.NORMAL
        )
        graph = state.canon_graph
        anchor_id = graph.anchor_neo4j_id

        if anchor_id == "NOT_FOUND":
            return BacktrackingResult(
                traversal_sequence=[],
                failure_node=None,
                stop_reason=StopReason.ONTOLOGY_GAP,
                traversal_mode=traversal_mode,
                lineage_walk=[],
                anchor_type=graph.anchor_label,
                anchor_id=graph.anchor_primary_value,
                chains_evaluated=[],
                total_nodes_in_graph=0,
            )

        scoper = EvidenceScoper(state)
        traversal_order = _build_traversal_sequence(graph)

        if not traversal_order:
            return BacktrackingResult(
                traversal_sequence=[],
                failure_node=None,
                stop_reason=StopReason.ONTOLOGY_GAP,
                traversal_mode=traversal_mode,
                lineage_walk=[],
                anchor_type=graph.anchor_label,
                anchor_id=graph.anchor_primary_value,
                chains_evaluated=[],
                total_nodes_in_graph=len(graph.nodes),
            )

        evaluated: List[NodeEvaluationResult] = []
        failure_node: Optional[NodeEvaluationResult] = None
        stop_reason: Optional[StopReason] = None
        stop_triggered = False
        chains_seen: Set[str] = set()

        max_hops_limit = state.investigation_input.max_hops

        for idx, (node, hop, incoming_rel) in enumerate(traversal_order):
            is_anchor = node.neo4j_id == anchor_id

            # Respect hop limit
            if hop > max_hops_limit:
                if stop_reason is None:
                    stop_reason = StopReason.MAX_HOPS_REACHED
                evaluated.append(
                    self._registry.mark_not_evaluated(
                        node=node,
                        order_index=idx,
                        ontology_path=_path_string_from_anchor(
                            graph, node, hop, incoming_rel
                        ),
                    )
                )
                continue

            # Track which chains have been visited
            primary_label = node.labels[0] if node.labels else ""
            chains_seen.add(_chain_name_for_label(primary_label))

            # Build ontology path string for this node
            ontology_path = _path_string_from_anchor(graph, node, hop, incoming_rel)

            # If early stop triggered in NORMAL mode, mark remaining as not evaluated
            if stop_triggered and traversal_mode == TraversalMode.NORMAL:
                evaluated.append(
                    self._registry.mark_not_evaluated(
                        node=node,
                        order_index=idx,
                        ontology_path=ontology_path,
                    )
                )
                continue

            # Evaluate the node
            result = self._registry.evaluate(
                node=node,
                scoper=scoper,
                order_index=idx,
                ontology_path=ontology_path,
                graph=graph,
            )
            evaluated.append(result)

            # Early stop logic: never stop at the anchor itself
            if (
                not is_anchor
                and result.status == NodeStatus.FAILED
                and traversal_mode == TraversalMode.NORMAL
            ):
                failure_node = result
                stop_reason = StopReason.FIRST_CONFIRMED_FAILURE
                stop_triggered = True
                logger.info(
                    "[BACKTRACKING] Early stop at node %s (label=%s, hop=%d).",
                    node.primary_value or node.neo4j_id,
                    primary_label,
                    hop,
                )
                continue  # mark remaining nodes in next iterations

        # Determine final stop_reason if not already set
        if stop_reason is None:
            stop_reason = self._determine_stop_reason(evaluated, state)

        # In EXPLORATORY mode, find the first failed non-anchor node
        if traversal_mode == TraversalMode.EXPLORATORY and failure_node is None:
            anchor_node_id = anchor_id
            failure_node = next(
                (
                    e
                    for e in evaluated
                    if e.node_id != anchor_node_id and e.status == NodeStatus.FAILED
                ),
                None,
            )

        lineage_walk = self._build_lineage_walk(
            traversal_order=traversal_order,
            evaluations={e.node_id: e for e in evaluated},
        )

        return BacktrackingResult(
            traversal_sequence=evaluated,
            failure_node=failure_node,
            stop_reason=stop_reason,
            traversal_mode=traversal_mode,
            lineage_walk=lineage_walk,
            anchor_type=graph.anchor_label,
            anchor_id=graph.anchor_primary_value,
            chains_evaluated=sorted(chains_seen),
            total_nodes_in_graph=len(graph.nodes),
        )

    def to_dashboard_summary(
        self,
        state: InvestigationState,
        result: BacktrackingResult,
    ) -> RcaDashboardSummary:
        """
        Transform a BacktrackingResult into a UI-ready RcaDashboardSummary.

        Parameters
        ----------
        state : InvestigationState
            The source investigation state for evidence IDs, paths, and audit trace.
        result : BacktrackingResult
            The result from backtrack_with_early_stop().

        Returns
        -------
        RcaDashboardSummary
            Fully typed, deterministic summary for front-end consumption.
        """
        inv = state.investigation_input
        anchor = inv.anchor

        # Determine failed node info
        failed_node = result.failure_node
        failed_node_id: Optional[str] = failed_node.node_id if failed_node else None
        failed_node_status: Optional[NodeStatus] = (
            failed_node.status if failed_node else None
        )
        failure_reason: Optional[str] = (
            failed_node.failure_reason if failed_node else None
        )

        # Health score: 100 if all healthy, 0 if confirmed failure
        health_score, health_status = self._compute_health(result)

        # Problem type from failed node label, else general
        if failed_node:
            fn_node = state.canon_graph.get_node(failed_node.node_id) if state.canon_graph else None
            problem_type = _problem_type_for_failure(fn_node) if fn_node else "general"
        else:
            problem_type = self._infer_problem_type(result, state)

        # Control triggered: pick from failed node's control_ids (compliance chain)
        control_triggered: Optional[str] = None
        lineage_failure_node: Optional[str] = None
        if failed_node:
            if failed_node.control_ids:
                control_triggered = failed_node.control_ids[0]
            fn_lbl = failed_node.node_label
            if fn_lbl in ("Script", "Table", "Column", "Dataset", "DataSource",
                          "Transformation"):
                lineage_failure_node = failed_node.node_name

        # Consolidated findings from all evaluated nodes
        all_findings: List[str] = []
        for node_eval in result.traversal_sequence:
            if node_eval.status != NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP:
                all_findings.extend(node_eval.findings)

        # Deduplicate while preserving order
        seen_findings: Set[str] = set()
        deduped_findings: List[str] = []
        for f in all_findings:
            if f not in seen_findings:
                seen_findings.add(f)
                deduped_findings.append(f)

        # Evidence IDs referenced across all evaluated nodes
        all_ev_ids: List[str] = []
        seen_ev: Set[str] = set()
        for node_eval in result.traversal_sequence:
            for eid in node_eval.evidence_ids:
                if eid not in seen_ev:
                    seen_ev.add(eid)
                    all_ev_ids.append(eid)

        # OntologyPath IDs
        path_ids = [p.path_id for p in state.ontology_paths_used]

        # Audit trace lines
        audit_lines = [
            f"[{e.agent_type.upper()}] {e.action}: {e.decision or ''}"
            for e in state.audit_trace
            if e.decision or e.action
        ]

        # Agent analysis chain
        agent_chain = self._build_agent_chain(state, result)

        # Confidence: max confidence across failed node or best available
        confidence = failed_node.confidence if failed_node else self._best_confidence(result)

        # Scenario name
        scenario_name = (
            f"{anchor.anchor_type} {anchor.anchor_primary_value} RCA"
        )

        return RcaDashboardSummary(
            investigation_id=inv.investigation_id,
            scenario_name=scenario_name,
            anchor_type=anchor.anchor_type,
            anchor_id=anchor.anchor_primary_value,
            health_score=health_score,
            health_status=health_status,
            problem_type=problem_type,
            control_triggered=control_triggered,
            lineage_failure_node=lineage_failure_node,
            confidence=confidence,
            lineage_walk=result.lineage_walk,
            failed_node=failed_node_id,
            failed_node_status=failed_node_status,
            failure_reason=failure_reason,
            findings=deduped_findings,
            agent_analysis_chain=agent_chain,
            evidence_objects=all_ev_ids,
            ontology_paths_used=path_ids,
            audit_trace=audit_lines,
            stop_reason=result.stop_reason,
            traversal_mode=result.traversal_mode,
            generated_at=datetime.now(tz=timezone.utc),
        )

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _determine_stop_reason(
        self,
        evaluated: List[NodeEvaluationResult],
        state: InvestigationState,
    ) -> StopReason:
        """
        Determine the stop reason when no explicit early stop was triggered.

        Checks in order: max hops reached, insufficient evidence, exploratory, general.
        """
        if state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE:
            return StopReason.INSUFFICIENT_EVIDENCE

        all_unknown = all(
            e.status in (NodeStatus.UNKNOWN, NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP)
            for e in evaluated
            if e.node_id != (
                state.canon_graph.anchor_neo4j_id if state.canon_graph else ""
            )
        )
        if all_unknown and state.missing_evidence:
            return StopReason.INSUFFICIENT_EVIDENCE

        # Check if traversal consumed all nodes within max hops
        max_hops = state.investigation_input.max_hops
        if any(e.ontology_path and f"hop {max_hops}" in e.ontology_path for e in evaluated):
            return StopReason.MAX_HOPS_REACHED

        return StopReason.EXPLORATORY_CONTINUE

    @staticmethod
    def _compute_health(result: BacktrackingResult) -> Tuple[float, str]:
        """Derive numeric health score and label from traversal results."""
        if result.failure_node is not None:
            conf = result.failure_node.confidence
            # health_score decreases with confidence in failure
            score = max(0.0, round((1.0 - conf) * 100, 1))
            return score, "FAILED"

        evaluated = [
            e for e in result.traversal_sequence
            if e.status != NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP
        ]
        if not evaluated:
            return 50.0, "UNKNOWN"

        degraded = sum(1 for e in evaluated if e.status == NodeStatus.DEGRADED)
        unknown = sum(1 for e in evaluated if e.status == NodeStatus.UNKNOWN)
        healthy = sum(1 for e in evaluated if e.status == NodeStatus.HEALTHY)
        total = len(evaluated)

        if healthy == total:
            return 100.0, "HEALTHY"
        if unknown == total:
            return 50.0, "UNKNOWN"

        # Weighted score
        score = round(((healthy * 100) + (degraded * 40) + (unknown * 50)) / total, 1)
        status = "DEGRADED" if degraded > 0 else "UNKNOWN"
        return min(100.0, score), status

    @staticmethod
    def _best_confidence(result: BacktrackingResult) -> float:
        evaluated = [
            e for e in result.traversal_sequence
            if e.status not in (
                NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP, NodeStatus.UNKNOWN
            )
        ]
        if not evaluated:
            return 0.0
        return max(e.confidence for e in evaluated)

    @staticmethod
    def _infer_problem_type(
        result: BacktrackingResult, state: InvestigationState
    ) -> str:
        """
        Infer problem type when there is no confirmed failure node.

        Checks degraded nodes for clues; falls back to 'general'.
        """
        degraded = [
            e for e in result.traversal_sequence
            if e.status == NodeStatus.DEGRADED
        ]
        if not degraded:
            return "general"
        first = degraded[0]
        return _problem_type_for_failure(
            type(
                "Node",
                (),
                {"labels": [first.node_label]},
            )()
        )

    @staticmethod
    def _build_lineage_walk(
        traversal_order: List[Tuple[CanonNode, int, str]],
        evaluations: Dict[str, NodeEvaluationResult],
    ) -> List[LineageWalkNode]:
        """
        Build the ordered lineage walk for dashboard visualisation.

        Only includes nodes from the operational and lineage chains plus
        the anchor, to keep the walk compact and readable.
        """
        if not traversal_order:
            return []

        walk: List[LineageWalkNode] = []
        # Include anchor + operational + lineage nodes (the most useful for a walk view)
        _walk_labels = frozenset({
            "Incident", "Violation",
            "System", "Job", "Pipeline",
            "Script", "Table", "Column", "DataSource", "Dataset",
        })

        step = 0
        for idx, (node, hop, incoming_rel) in enumerate(traversal_order):
            primary_label = node.labels[0] if node.labels else ""
            if primary_label not in _walk_labels:
                continue

            result = evaluations.get(node.neo4j_id)
            if result is None:
                continue

            display_name = node.primary_value or node.neo4j_id
            subtitle = f"{primary_label} / {node.primary_value or node.neo4j_id}"
            ontology_fragment = incoming_rel if hop > 0 else ""

            walk.append(LineageWalkNode(
                node_id=node.neo4j_id,
                display_name=display_name,
                label=primary_label,
                status=result.status,
                subtitle=subtitle,
                order_index=step,
                ontology_path_fragment=ontology_fragment,
                was_evaluated=(
                    result.status != NodeStatus.NOT_EVALUATED_DUE_TO_EARLY_STOP
                ),
            ))
            step += 1

        return walk

    @staticmethod
    def _build_agent_chain(
        state: InvestigationState,
        result: BacktrackingResult,
    ) -> List[AgentAnalysisChainEntry]:
        """
        Synthesise the agent analysis chain from audit trace entries.

        Groups audit trace entries by agent_type and builds one
        AgentAnalysisChainEntry per distinct agent.
        """
        agent_order = [
            "ontology_context",
            "evidence_collector",
            "hypothesis_generator",
            "causal_engine",
            "ranker",
            "backtracking",
        ]
        agent_display = {
            "ontology_context": "Ontology Context Agent",
            "evidence_collector": "Evidence Collector Agent",
            "hypothesis_generator": "Hypothesis Generator Agent",
            "causal_engine": "Causal Engine Agent",
            "ranker": "Ranker Agent",
            "backtracking": "Backtracking Service",
        }

        # Collect last decision per agent from audit trace
        agent_decisions: Dict[str, str] = {}
        agent_paths: Dict[str, str] = {}
        for entry in state.audit_trace:
            at = entry.agent_type
            if entry.decision:
                agent_decisions[at] = entry.decision

        # Agents that actually ran (appear in audit trace)
        agents_ran = {e.agent_type for e in state.audit_trace}

        # Health and problem type from traversal result
        _, health_label = OntologyBacktrackingService._compute_health(result)
        problem_type = "general"
        if result.failure_node:
            problem_type = _problem_type_for_failure(
                type("N", (), {"labels": [result.failure_node.node_label]})()
            )

        chain: List[AgentAnalysisChainEntry] = []

        # Include backtracking as a synthetic agent entry
        agents_to_render = [a for a in agent_order if a in agents_ran or a == "backtracking"]

        for agent_type in agents_to_render:
            if agent_type not in agents_ran and agent_type != "backtracking":
                continue

            if agent_type == "backtracking":
                status_text = "completed"
                key_finding = (
                    f"Backtracking found failure node: {result.failure_node.node_name}"
                    if result.failure_node
                    else f"Backtracking completed: stop_reason={result.stop_reason.value}"
                )
                control = (
                    result.failure_node.control_ids[0]
                    if result.failure_node and result.failure_node.control_ids
                    else None
                )
                chain.append(AgentAnalysisChainEntry(
                    agent_name="Backtracking Service",
                    status=status_text,
                    health=health_label,
                    problem_type=problem_type,
                    control=control,
                    key_finding=key_finding,
                    duration_ms=0,
                ))
                continue

            decision = agent_decisions.get(agent_type, "")
            status_text = "completed" if decision else "skipped"
            if "ERROR" in decision.upper():
                status_text = "error"
            elif "BLOCKED" in decision.upper() or "INSUFFICIENT" in decision.upper():
                status_text = "blocked"

            key_finding = decision[:120] if decision else "No findings recorded."
            display = agent_display.get(agent_type, agent_type)

            chain.append(AgentAnalysisChainEntry(
                agent_name=display,
                status=status_text,
                health=health_label,
                problem_type=problem_type,
                control=None,
                key_finding=key_finding,
                duration_ms=0,
            ))

        return chain


# ─── Public convenience function ──────────────────────────────────────────────


def backtrack_with_early_stop(
    state: InvestigationState,
    mode: str = "normal",
) -> BacktrackingResult:
    """
    Module-level convenience function for the OntologyBacktrackingService.

    Equivalent to OntologyBacktrackingService().backtrack_with_early_stop(state, mode).

    Parameters
    ----------
    state : InvestigationState
        Must have state.canon_graph populated.
    mode : str
        'normal' or 'exploratory'.

    Returns
    -------
    BacktrackingResult
    """
    return OntologyBacktrackingService().backtrack_with_early_stop(state, mode)
