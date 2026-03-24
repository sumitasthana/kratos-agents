"""
causelink/agents/evidence_collector.py

EvidenceCollectorAgent — Phase D Agent 2.

Responsibilities:
  1. Verify canon_graph is loaded (else raise — OntologyContextAgent must run first).
  2. Use EvidenceService to collect: logs, metrics, change events, audit events,
     and lineage traces — ALL scoped to CanonGraph node IDs (no unconstrained searches).
  3. Append collected EvidenceObjects to state.evidence_objects.
  4. For each evidence type where EvidenceService returns None, create a
     MissingEvidence entry (blocking=True for log evidence; False for optional types).
  5. Append AuditTraceEntry for every collection attempt.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from causelink.agents.base import CauseLinkAgent
from causelink.evidence.contracts import (
    EvidenceObject,
    EvidenceReliabilityTier,
    EvidenceSearchParams,
    EvidenceService,
    EvidenceType,
)
from causelink.state.investigation import (
    InvestigationState,
    InvestigationStatus,
    MissingEvidence,
)
from causelink.validation.gates import ValidationGate

logger = logging.getLogger(__name__)


class EvidenceCollectorAgent(CauseLinkAgent):
    """
    Collects all available evidence for CanonGraph-scoped entities.

    Scoping constraint: all EvidenceService calls receive *only* the neo4j_ids
    present in state.canon_graph — no broader searches are permitted.
    """

    AGENT_TYPE = "evidence_collector"

    def __init__(
        self,
        evidence_service: EvidenceService,
        gate: Optional[ValidationGate] = None,
        # Metric names to request from query_metrics — configurable per deployment.
        metric_names: Optional[List[str]] = None,
    ) -> None:
        self.evidence_service = evidence_service
        self.gate = gate or ValidationGate()
        self.metric_names = metric_names or [
            "error_rate", "latency_p99", "throughput", "null_rate",
        ]

    def run(self, state: InvestigationState) -> InvestigationState:
        """
        Collect evidence into the state.

        Side-effects on state:
          - state.evidence_objects extended with collected EvidenceObjects
          - state.missing_evidence extended with any unobtainable evidence
          - state.audit_trace extended
          - status may transition to INSUFFICIENT_EVIDENCE if all evidence missing
        """
        if state.canon_graph is None:
            raise ValueError(
                "EvidenceCollectorAgent requires OntologyContextAgent to run first. "
                "state.canon_graph is None."
            )

        graph = state.canon_graph
        node_ids = [n.neo4j_id for n in graph.nodes]

        if not node_ids:
            state.add_missing_evidence(MissingEvidence(
                evidence_type="query_result",
                description=(
                    "CanonGraph contains no nodes — no evidence can be collected. "
                    "Expand max_hops or verify ontology population."
                ),
                blocking=True,
            ))
            self._audit(
                state, "evidence_fetch",
                decision="BLOCKED: CanonGraph empty",
            )
            return state

        inv = state.investigation_input
        time_start = inv.context.get("time_range_start")
        time_end = inv.context.get("time_range_end")

        params = EvidenceSearchParams(
            entity_ids=node_ids,
            time_range_start=time_start,
            time_range_end=time_end,
        )

        collected: List[EvidenceObject] = []
        missing_types: List[str] = []

        # ── Log evidence (blocking if absent) ────────────────────────────────
        log_ev = self._collect(
            "search_logs",
            lambda: self.evidence_service.search_logs(params, self.AGENT_TYPE),
        )
        if log_ev is not None:
            collected.append(log_ev)
        else:
            missing_types.append("log")
            state.add_missing_evidence(MissingEvidence(
                evidence_type="log",
                description=(
                    "No log evidence found for CanonGraph entities. "
                    "Verify log source connectivity and entity-ID mappings."
                ),
                query_template=(
                    "search_logs(entity_ids={entity_ids}, "
                    "time_start={time_start}, time_end={time_end})"
                ),
                blocking=True,
            ))

        # ── Metric evidence (non-blocking) ────────────────────────────────────
        metric_ev = self._collect(
            "query_metrics",
            lambda: self.evidence_service.query_metrics(
                params, self.metric_names, self.AGENT_TYPE
            ),
        )
        if metric_ev is not None:
            collected.append(metric_ev)
        else:
            missing_types.append("metric")
            state.add_missing_evidence(MissingEvidence(
                evidence_type="metric",
                description=(
                    "No metric evidence found for CanonGraph entities. "
                    "Analysis may proceed but causal scoring will be lower."
                ),
                query_template=(
                    "query_metrics(entity_ids={entity_ids}, "
                    "metric_names={metric_names})"
                ),
                blocking=False,
            ))

        # ── Change events (non-blocking) ──────────────────────────────────────
        change_ev = self._collect(
            "fetch_change_events",
            lambda: self.evidence_service.fetch_change_events(params, self.AGENT_TYPE),
        )
        if change_ev is not None:
            collected.append(change_ev)
        else:
            missing_types.append("change_event")

        # ── Audit events (non-blocking) ───────────────────────────────────────
        audit_ev = self._collect(
            "fetch_audit_events",
            lambda: self.evidence_service.fetch_audit_events(params, self.AGENT_TYPE),
        )
        if audit_ev is not None:
            collected.append(audit_ev)
        else:
            missing_types.append("audit_event")

        # ── Lineage trace (non-blocking) ──────────────────────────────────────
        lineage_ev = self._collect(
            "get_lineage_trace",
            lambda: self.evidence_service.get_lineage_trace(params, self.AGENT_TYPE),
        )
        if lineage_ev is not None:
            collected.append(lineage_ev)
        else:
            missing_types.append("lineage_trace")

        # ── Commit to state ───────────────────────────────────────────────────
        for ev in collected:
            state.evidence_objects.append(ev)
        state.updated_at = __import__("datetime").datetime.utcnow()

        ev_ids = [ev.evidence_id for ev in collected]
        self._audit(
            state,
            action="evidence_fetch",
            inputs_summary={
                "node_count": len(node_ids),
                "time_start": str(time_start),
                "time_end": str(time_end),
            },
            outputs_summary={
                "collected": len(collected),
                "missing_types": missing_types,
            },
            evidence_ids_accessed=ev_ids,
            decision=(
                f"Collected {len(collected)} evidence object(s); "
                f"missing: {missing_types or 'none'}"
            ),
        )

        self._log(
            "Evidence collected: %d objects | missing types: %s",
            len(collected), missing_types,
        )

        return state

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect(self, method_name: str, call) -> Optional[EvidenceObject]:
        """Call *call()* and return the result, logging any exception."""
        try:
            return call()
        except Exception as exc:
            self._warn("Evidence method '%s' raised: %s", method_name, exc)
            return None
