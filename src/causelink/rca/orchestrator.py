"""causelink/rca/orchestrator.py

ChatRcaOrchestrator — 7-stage chat-driven RCA pipeline.

Stages:
  1. Intake         — validate scenario, resolve anchor, load/create session
  2. Logs-first     — determine job status from logs (mock: pattern-match on job_id)
  3. Route          — select analyzers based on job status and scenario
  4. Backtrack      — run full CauseLink pipeline then OntologyBacktrackingService
  5. Incident card  — synthesize structured incident card from backtracking result
  6. Recommend      — generate grounded, rule-based recommendations
  7. Persist        — save session with latest summary and incident card

Follow-up queries against an existing completed session are answered via
rule-based intent detection against the stored session data — no LLM required.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from causelink.agents.causal_engine import CausalEngineAgent
from causelink.agents.evidence_collector import EvidenceCollectorAgent
from causelink.agents.hypothesis_generator import HypothesisGeneratorAgent
from causelink.agents.ontology_context import OntologyContextAgent
from causelink.agents.ranker import RankerAgent
from causelink.evidence.contracts import (
    EvidenceObject,
    EvidenceReliabilityTier,
    EvidenceSearchParams,
    EvidenceService,
    EvidenceType,
)
from causelink.ontology.models import CanonEdge, CanonGraph, CanonNode, OntologyPath
from causelink.services.ontology_backtracking import OntologyBacktrackingService
from causelink.state.investigation import (
    InvestigationAnchor,
    InvestigationInput,
    InvestigationState,
    InvestigationStatus,
)

from .models import ChatRcaResponse, IncidentCard, JobInvestigationRequest, JobStatusSummary
from .scenario_config import ScenarioConfig, get_scenario
from .session import JobInvestigationSession, SessionStore, get_session_store

# ─── Deterministic ID helpers ─────────────────────────────────────────────────


def _stable_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _mk_node(label: str, seed: str, pk_override: Optional[str] = None) -> CanonNode:
    return CanonNode(
        neo4j_id=_stable_id(f"node:{label}:{seed}"),
        labels=[label],
        primary_key=pk_override or f"{label.lower()}_id",
        primary_value=seed,
        properties={},
        provenance="rca-mock",
    )


def _mk_edge(rel_type: str, start_seed: str, end_seed: str, s_label: str, e_label: str) -> CanonEdge:
    return CanonEdge(
        neo4j_id=_stable_id(f"edge:{rel_type}:{start_seed}:{end_seed}"),
        type=rel_type,
        start_node_id=_stable_id(f"node:{s_label}:{start_seed}"),
        end_node_id=_stable_id(f"node:{e_label}:{end_seed}"),
        properties={},
        provenance="rca-mock",
    )


def _mk_path(node_ids: List[str], rel_types: List[str], name: str) -> OntologyPath:
    return OntologyPath(
        path_id=_stable_id(f"path:{name}"),
        description=name,
        node_sequence=node_ids,
        rel_type_sequence=rel_types,
        hop_count=len(rel_types),
        query_used="(rca-mock: no live query)",
    )


def _mk_ev(ev_type: EvidenceType, seed: str, reliability: float = 0.85) -> EvidenceObject:
    raw = f"rca-mock:{seed}".encode()
    return EvidenceObject(
        evidence_id=_stable_id(f"ev:{seed}"),
        type=ev_type,
        source_system="rca-mock",
        content_ref=f"file:///tmp/rca-mock/{seed.replace(':', '_')}.json",
        summary=f"Mock evidence ({ev_type.value}) for {seed}",
        reliability=reliability,
        reliability_tier=EvidenceObject.tier_for(reliability),
        raw_hash=EvidenceObject.make_hash(raw),
        collected_by="rca-orchestrator",
    )


# ─── Scenario anchor resolution ───────────────────────────────────────────────

_ANCHOR_MAP: Dict[str, Tuple[str, str]] = {
    # scenario_id → (anchor_label, pk_name)
    "gl_reconciliation": ("Job", "job_id"),
    "joint_qualification": ("Job", "job_id"),
    "signature_card_validation": ("Incident", "incident_id"),
    "schema_drift": ("Pipeline", "pipeline_id"),
    "rule_enforcement": ("Pipeline", "pipeline_id"),
}


def _resolve_anchor(scenario_id: str, job_id: str) -> Tuple[str, str, str]:
    """Return (anchor_label, primary_key, primary_value) for a job_id + scenario."""
    label, pk = _ANCHOR_MAP.get(scenario_id, ("Job", "job_id"))
    if label == "Job":
        pv = job_id
    elif label == "Incident":
        pv = f"INC-{job_id}"
    elif label == "Pipeline":
        pv = f"PIPE-{job_id}"
    else:
        pv = job_id
    return label, pk, pv


# ─── Mock job status ──────────────────────────────────────────────────────────


def _determine_mock_job_status(job_id: str) -> str:
    """Deterministic job status from job_id pattern, then hash-based fallback."""
    jid = job_id.upper()
    if any(w in jid for w in ("FAIL", "ERR", "BAD", "BREAK", "DOWN", "CRASH")):
        return "FAILED"
    if any(w in jid for w in ("WARN", "SLOW", "DG", "DEGRADE", "ISSUE", "LAG")):
        return "DEGRADED"
    if any(w in jid for w in ("OK", "PASS", "SUCC", "GOOD", "DONE", "COMPLETE")):
        return "SUCCESS"
    h = sum(ord(c) for c in job_id) % 3
    return ["FAILED", "DEGRADED", "SUCCESS"][h]


# ─── Mock evidence service ────────────────────────────────────────────────────


class _RcaEvidenceService(EvidenceService):
    """Full mock evidence service for demo/test mode."""

    def search_logs(self, params: EvidenceSearchParams, collected_by: str) -> Optional[EvidenceObject]:
        return _mk_ev(EvidenceType.LOG, f"logs:{params.correlation_id or 'demo'}", 0.88)

    def query_metrics(self, params: EvidenceSearchParams, metric_names: List[str], collected_by: str) -> Optional[EvidenceObject]:
        return _mk_ev(EvidenceType.METRIC, "metrics:demo", 0.75)

    def fetch_change_events(self, params: EvidenceSearchParams, collected_by: str) -> Optional[EvidenceObject]:
        return _mk_ev(EvidenceType.CHANGE_EVENT, "changes:demo", 0.80)

    def fetch_audit_events(self, params: EvidenceSearchParams, collected_by: str) -> Optional[EvidenceObject]:
        return _mk_ev(EvidenceType.AUDIT_EVENT, "audit:demo", 0.92)

    def get_lineage_trace(self, params: EvidenceSearchParams, collected_by: str) -> Optional[EvidenceObject]:
        return _mk_ev(EvidenceType.LINEAGE_TRACE, "lineage:demo", 0.70)

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceObject]:
        return None


# ─── Mock ontology adapters ───────────────────────────────────────────────────


class _ScenarioMockAdapter:
    """
    Scenario-aware mock ontology adapter.

    Builds a scenario-appropriate CanonGraph using the provided anchor_type
    and job_id. All adapter methods return the same pre-built graph.
    """

    def __init__(self, scenario_id: str, anchor_type: str, anchor_pv: str) -> None:
        self._scenario_id = scenario_id
        self._anchor_type = anchor_type
        self._anchor_pv = anchor_pv
        self._graph: CanonGraph = self._build_graph()

    # ── Graph builders ────────────────────────────────────────────────────

    def _build_graph(self) -> CanonGraph:
        at = self._anchor_type
        if at == "Incident":
            return self._build_compliance_graph()
        if at == "Pipeline":
            return self._build_pipeline_graph()
        return self._build_job_graph()

    def _build_job_graph(self) -> CanonGraph:
        """Job anchor: compliance + lineage chains."""
        jid = self._anchor_pv
        job = _mk_node("Job", jid, "job_id")
        sys_ = _mk_node("System", f"SYS-{jid}")
        pipe = _mk_node("Pipeline", f"PIPE-{jid}")
        scr = _mk_node("Script", f"SCR-{jid}")
        log = _mk_node("LogSource", f"LOG-{jid}")
        tbl = _mk_node("Table", f"TBL-{jid}")
        vio = _mk_node("Violation", f"VIO-{jid}")
        rule = _mk_node("Rule", f"RULE-{jid}")

        path = _mk_path(
            [job.neo4j_id, pipe.neo4j_id, scr.neo4j_id, tbl.neo4j_id],
            ["EXECUTES", "USES_SCRIPT", "READS"],
            f"job-lineage:{jid}",
        )
        comp_path = _mk_path(
            [job.neo4j_id, vio.neo4j_id, rule.neo4j_id],
            ["TRIGGERS", "ENFORCED_BY"],
            f"job-compliance:{jid}",
        )
        return CanonGraph(
            anchor_neo4j_id=job.neo4j_id,
            anchor_label="Job",
            anchor_primary_key="job_id",
            anchor_primary_value=jid,
            nodes=[job, sys_, pipe, scr, log, tbl, vio, rule],
            edges=[
                _mk_edge("RUNS_JOB", f"SYS-{jid}", jid, "System", "Job"),
                _mk_edge("EXECUTES", jid, f"PIPE-{jid}", "Job", "Pipeline"),
                _mk_edge("USES_SCRIPT", f"PIPE-{jid}", f"SCR-{jid}", "Pipeline", "Script"),
                _mk_edge("LOGGED_IN", f"PIPE-{jid}", f"LOG-{jid}", "Pipeline", "LogSource"),
                _mk_edge("READS", f"SCR-{jid}", f"TBL-{jid}", "Script", "Table"),
                _mk_edge("TRIGGERS", f"VIO-{jid}", jid, "Violation", "Job"),
                _mk_edge("ENFORCED_BY", f"VIO-{jid}", f"RULE-{jid}", "Violation", "Rule"),
            ],
            ontology_paths_used=[path, comp_path],
            retrieved_at=datetime.utcnow(),
            max_hops=3,
        )

    def _build_compliance_graph(self) -> CanonGraph:
        """Incident anchor: Violation + Rule compliance chain."""
        pv = self._anchor_pv
        # anchor_pv for Incident is "INC-{job_id}"
        jid = pv[4:] if pv.startswith("INC-") else pv
        inc = _mk_node("Incident", pv, "incident_id")
        vio = _mk_node("Violation", f"VIO-{jid}")
        rule = _mk_node("Rule", f"RULE-{jid}")
        sys_ = _mk_node("System", f"SYS-{jid}")
        job = _mk_node("Job", jid, "job_id")

        path = _mk_path(
            [inc.neo4j_id, vio.neo4j_id, rule.neo4j_id],
            ["GENERATES", "ENFORCED_BY"],
            f"compliance-chain:{jid}",
        )
        return CanonGraph(
            anchor_neo4j_id=inc.neo4j_id,
            anchor_label="Incident",
            anchor_primary_key="incident_id",
            anchor_primary_value=pv,
            nodes=[inc, vio, rule, sys_, job],
            edges=[
                _mk_edge("GENERATES", f"VIO-{jid}", pv, "Violation", "Incident"),
                _mk_edge("ENFORCED_BY", f"VIO-{jid}", f"RULE-{jid}", "Violation", "Rule"),
                _mk_edge("GENERATES", f"SYS-{jid}", pv, "System", "Incident"),
                _mk_edge("RUNS_JOB", f"SYS-{jid}", jid, "System", "Job"),
            ],
            ontology_paths_used=[path],
            retrieved_at=datetime.utcnow(),
            max_hops=3,
        )

    def _build_pipeline_graph(self) -> CanonGraph:
        """Pipeline anchor: lineage + code change chains."""
        pv = self._anchor_pv
        jid = pv[5:] if pv.startswith("PIPE-") else pv
        pipe = _mk_node("Pipeline", pv, "pipeline_id")
        scr = _mk_node("Script", f"SCR-{jid}")
        tbl = _mk_node("Table", f"TBL-{jid}")
        col1 = _mk_node("Column", f"COL1-{jid}")
        col2 = _mk_node("Column", f"COL2-{jid}")
        ce = _mk_node("CodeEvent", f"CE-{jid}")
        log = _mk_node("LogSource", f"LOG-{jid}")
        vio = _mk_node("Violation", f"VIO-{jid}")
        rule = _mk_node("Rule", f"RULE-{jid}")

        lineage_path = _mk_path(
            [pipe.neo4j_id, scr.neo4j_id, tbl.neo4j_id, col1.neo4j_id],
            ["USES_SCRIPT", "READS", "HAS_COLUMN"],
            f"pipeline-lineage:{jid}",
        )
        log_path = _mk_path(
            [pipe.neo4j_id, log.neo4j_id],
            ["LOGGED_IN"],
            f"pipeline-log:{jid}",
        )
        return CanonGraph(
            anchor_neo4j_id=pipe.neo4j_id,
            anchor_label="Pipeline",
            anchor_primary_key="pipeline_id",
            anchor_primary_value=pv,
            nodes=[pipe, scr, tbl, col1, col2, ce, log, vio, rule],
            edges=[
                _mk_edge("USES_SCRIPT", pv, f"SCR-{jid}", "Pipeline", "Script"),
                _mk_edge("READS", f"SCR-{jid}", f"TBL-{jid}", "Script", "Table"),
                _mk_edge("HAS_COLUMN", f"TBL-{jid}", f"COL1-{jid}", "Table", "Column"),
                _mk_edge("DERIVED_FROM", f"COL1-{jid}", f"COL2-{jid}", "Column", "Column"),
                _mk_edge("CHANGED_BY", f"SCR-{jid}", f"CE-{jid}", "Script", "CodeEvent"),
                _mk_edge("LOGGED_IN", pv, f"LOG-{jid}", "Pipeline", "LogSource"),
                _mk_edge("ENFORCED_BY", f"VIO-{jid}", f"RULE-{jid}", "Violation", "Rule"),
            ],
            ontology_paths_used=[lineage_path, log_path],
            retrieved_at=datetime.utcnow(),
            max_hops=5,
        )

    # ── Adapter interface ─────────────────────────────────────────────────

    def get_neighborhood(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=3):
        return self._graph

    def get_compliance_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=5):
        return self._graph

    def get_lineage_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=5):
        return self._graph

    def get_change_provenance_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=4):
        return self._graph

    def get_log_scope_chain(self, anchor_label, anchor_primary_key, anchor_primary_value, max_hops=2):
        return self._graph

    def validate_shortest_path(self, start_node_id, end_node_id, max_hops=3):
        return _mk_path(
            [start_node_id, end_node_id],
            ["EXECUTES"],
            f"shortest-path:{start_node_id[:8]}",
        )


# ─── Intent detection ─────────────────────────────────────────────────────────


def _detect_intent(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ("why", "reason", "cause", "fail", "broke", "error", "issue")):
        return "failure_reason"
    if any(w in q for w in ("control", "ctrl", "rule", "regulation", "compliance")):
        return "control_triggered"
    if any(w in q for w in ("lineage", "script", "transform", "upstream", "downstream", "pipeline")):
        return "lineage_failure"
    if any(w in q for w in ("recommend", "fix", "remediat", "action", "next step", "how to")):
        return "recommendation"
    if any(w in q for w in ("dashboard", "open", "view", "show", "navigate")):
        return "dashboard_url"
    if any(w in q for w in ("code", "change", "commit", "deploy", "pr", "release")):
        return "change_analysis"
    if any(w in q for w in ("data", "null", "schema", "column", "table", "row")):
        return "data_analysis"
    if any(w in q for w in ("infra", "resource", "memory", "oom", "cpu", "disk", "hardware")):
        return "infra_analysis"
    return "general"


# ─── ChatRcaOrchestrator ──────────────────────────────────────────────────────


class ChatRcaOrchestrator:
    """
    7-stage chat-driven RCA orchestrator.

    In mock_mode=True (the default), all external calls (Neo4j, evidence APIs)
    are replaced by deterministic in-process adapters. This makes the orchestrator
    safe to call in tests and CI without any network dependencies.

    In mock_mode=False, the caller is responsible for injecting a live
    Neo4jOntologyAdapter via the `adapter` parameter.
    """

    def __init__(
        self,
        mock_mode: bool = True,
        adapter: Any = None,
        store: Optional[SessionStore] = None,
    ) -> None:
        self._mock_mode = mock_mode
        self._adapter = adapter  # used in live mode only
        self._store = store or get_session_store()
        self._bt_service = OntologyBacktrackingService()

    # ─── Public API ───────────────────────────────────────────────────────

    def investigate(self, req: JobInvestigationRequest) -> ChatRcaResponse:
        """
        Run (or continue) an investigation for the given job.

        First call: runs all 7 stages and returns the full investigation result.
        Subsequent calls with the same session_id / job_id: answers follow-up
        query from stored session data without re-running the pipeline.
        """
        # Stage 0: resolve scenario (validate early)
        try:
            scenario = get_scenario(req.scenario_id)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        # Stage 1: find or create session
        session = self._resolve_session(req)

        # For completed sessions without a forced refresh, answer from cache
        if session.status == "completed" and not req.refresh:
            return self._answer_from_session(req, session)

        # ── Fresh investigation ───────────────────────────────────────────

        # Stage 2: logs-first — determine job status
        job_status = self._stage_logs_first(req)

        # Stage 3: route — select analyzers
        routing = self._stage_route(scenario, job_status)

        # Stage 4: backtracking
        summary_dict, bt_ok = self._stage_backtrack(req, scenario)

        # Stage 5: incident card
        incident_card = self._stage_incident_card(req, scenario, job_status, summary_dict)

        # Stage 6: recommendations (written into incident_card in place)
        incident_card.recommendations = self._generate_recommendations(
            incident_card.problem_type, incident_card, scenario
        )

        # Stage 7: persist
        session = self._stage_persist(
            session, job_status, summary_dict, incident_card, routing
        )

        answer = self._compose_answer(req.user_query, job_status.status, summary_dict, incident_card)
        followups = self._suggest_followups(job_status.status, summary_dict)

        return ChatRcaResponse(
            session_id=session.session_id,
            job_id=req.job_id,
            scenario_id=req.scenario_id,
            answer=answer,
            summary=summary_dict,
            job_status=job_status.status,
            incident_card=incident_card,
            dashboard_url=session.dashboard_url,
            suggested_followups=followups,
            audit_ref=f"{session.session_id}/audit",
        )

    # ─── Stage helpers ────────────────────────────────────────────────────

    def _resolve_session(self, req: JobInvestigationRequest) -> JobInvestigationSession:
        # Explicit session_id lookup
        if req.session_id:
            sess = self._store.get(req.session_id)
            if sess is not None:
                return sess
        # Job-id lookup (e.g. follow-up without explicit session_id)
        sess = self._store.get_by_job(req.job_id)
        if sess is not None and not req.refresh:
            return sess
        # Create new session
        anchor_label, anchor_pk, anchor_pv = _resolve_anchor(req.scenario_id, req.job_id)
        return self._store.create(
            scenario_id=req.scenario_id,
            job_id=req.job_id,
            anchor_type=anchor_label,
            anchor_id=anchor_pv,
        )

    def _stage_logs_first(self, req: JobInvestigationRequest) -> JobStatusSummary:
        """Stage 2: Determine job status. Mock: pattern-match on job_id."""
        status = _determine_mock_job_status(req.job_id)
        confidence = {"FAILED": 0.90, "DEGRADED": 0.75, "SUCCESS": 0.85}.get(status, 0.50)
        rationale = (
            f"Job ID '{req.job_id}' matched pattern for status '{status}' "
            f"(mock logs-first check, confidence={confidence:.0%})."
        )
        return JobStatusSummary(
            job_id=req.job_id,
            status=status,
            source="mock",
            confidence=confidence,
            classification_rationale=rationale,
        )

    def _stage_route(self, scenario: ScenarioConfig, job_status: JobStatusSummary) -> List[str]:
        """Stage 3: Select analyzers from scenario's allowed list based on job status."""
        analyzers = scenario.allowed_analyzers[:]
        # Prioritise infra analyzer first for FAILED jobs
        if job_status.status == "FAILED" and "InfraAnalyzer" in analyzers:
            analyzers = ["InfraAnalyzer"] + [a for a in analyzers if a != "InfraAnalyzer"]
        elif job_status.status == "DEGRADED" and "DataProfiler" in analyzers:
            analyzers = ["DataProfiler"] + [a for a in analyzers if a != "DataProfiler"]
        return analyzers

    def _stage_backtrack(
        self,
        req: JobInvestigationRequest,
        scenario: ScenarioConfig,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Stage 4: Run the CauseLink pipeline then backtracking.

        Returns (summary_dict, success_flag).
        """
        anchor_label, anchor_pk, anchor_pv = _resolve_anchor(req.scenario_id, req.job_id)

        inv_input = InvestigationInput(
            investigation_id=_stable_id(f"inv:{req.session_id or req.job_id}:{req.scenario_id}"),
            anchor=InvestigationAnchor(
                anchor_type=anchor_label,
                anchor_primary_key=anchor_pk,
                anchor_primary_value=anchor_pv,
            ),
            max_hops=req.max_hops,
            confidence_threshold=0.40,
        )
        state = InvestigationState(investigation_input=inv_input)

        adapter = (
            _ScenarioMockAdapter(req.scenario_id, anchor_label, anchor_pv)
            if self._mock_mode
            else self._adapter
        )
        ev_svc = _RcaEvidenceService() if self._mock_mode else self._adapter  # type: ignore[assignment]

        try:
            state = OntologyContextAgent(adapter=adapter).run(state)
            if state.status == InvestigationStatus.INSUFFICIENT_EVIDENCE:
                return None, False

            state = EvidenceCollectorAgent(evidence_service=ev_svc).run(state)  # type: ignore[arg-type]
            state = HypothesisGeneratorAgent().run(state)
            state = CausalEngineAgent(adapter=adapter).run(state)
            state = RankerAgent().run(state)

            bt_result = self._bt_service.backtrack_with_early_stop(state, mode=req.mode)
            summary = self._bt_service.to_dashboard_summary(state, bt_result)
            return summary.to_dict(), True

        except Exception:  # pragma: no cover — surface errors gracefully
            return None, False

    def _stage_incident_card(
        self,
        req: JobInvestigationRequest,
        scenario: ScenarioConfig,
        job_status: JobStatusSummary,
        summary_dict: Optional[Dict[str, Any]],
    ) -> IncidentCard:
        """Stage 5: Synthesize incident card from backtracking result."""
        s = summary_dict or {}
        problem_type = s.get("problem_type") or (scenario.expected_problem_types[0] if scenario.expected_problem_types else "general")
        control = s.get("control_triggered") or (scenario.expected_controls[0] if scenario.expected_controls else None)
        confidence = float(s.get("confidence", 0.0))
        health_score = float(s.get("health_score", 0.0))
        failed_node = s.get("failed_node")
        failure_reason = s.get("failure_reason")

        # Derive failed_node_label from lineage_walk
        failed_node_label: Optional[str] = None
        for lw in s.get("lineage_walk", []):
            if lw.get("node_id") == failed_node:
                failed_node_label = lw.get("label")
                break

        findings: List[str] = s.get("findings", [])
        if not findings:
            findings = [
                f"Job {req.job_id} has status {job_status.status} under scenario '{scenario.title}'.",
                f"Problem type: {problem_type}.",
            ]
            if control:
                findings.append(f"Control {control} was triggered during investigation.")

        dashboard_url = f"#jobs/{req.job_id}/dashboard"

        return IncidentCard(
            incident_id=None,  # synthetic — not in ontology
            job_id=req.job_id,
            scenario_id=req.scenario_id,
            scenario_name=scenario.title,
            job_status=job_status.status,
            problem_type=problem_type,
            control_triggered=control,
            failed_node=failed_node,
            failed_node_label=failed_node_label,
            failure_reason=failure_reason,
            confidence=confidence,
            health_score=health_score,
            findings=findings,
            dashboard_url=dashboard_url,
        )

    def _generate_recommendations(
        self,
        problem_type: str,
        incident: IncidentCard,
        scenario: ScenarioConfig,
    ) -> List[str]:
        """Stage 6: Rule-based recommendation generation."""
        recs: List[str] = []

        if problem_type == "execution_failure":
            recs.append(
                f"Review execution logs for job '{incident.job_id}' to identify the failure point."
            )
            if incident.failed_node:
                recs.append(
                    f"Investigate node '{incident.failed_node}': validate configuration and dependencies."
                )
            recs.append("Check system resource availability at the recorded failure time.")

        if problem_type == "compliance_gap":
            ctrl = incident.control_triggered
            recs.append(
                f"Escalate to the control owner for {ctrl or 'the triggered control'}."
            )
            recs.append("Review the applicable rule and control objective for remediation steps.")
            recs.append(
                "File a formal incident report if the control breach meets reporting thresholds."
            )

        if problem_type in ("lineage", "regression_risk"):
            recs.append("Inspect upstream data sources for schema or format changes.")
            recs.append("Validate schema compatibility between source and target tables.")
            recs.append(
                "Review recent code changes (CodeEvent) that may have introduced a regression."
            )

        if not recs:
            recs.append("Review the investigation dashboard for detailed analysis.")
            recs.append("Consult the relevant control team for remediation guidance.")

        return recs

    def _stage_persist(
        self,
        session: JobInvestigationSession,
        job_status: JobStatusSummary,
        summary_dict: Optional[Dict[str, Any]],
        incident_card: IncidentCard,
        routing: List[str],
    ) -> JobInvestigationSession:
        """Stage 7: Save investigation results to session."""
        session.status = "completed"
        session.latest_summary = summary_dict
        session.latest_incident_card = incident_card.model_dump(mode="json")
        session.dashboard_url = incident_card.dashboard_url
        session.context = {
            "job_status": job_status.status,
            "routing": routing,
            "problem_type": incident_card.problem_type,
            "control_triggered": incident_card.control_triggered,
            "confidence": incident_card.confidence,
        }
        self._store.update(session)
        return session

    # ─── Follow-up query answering ────────────────────────────────────────

    def _answer_from_session(
        self,
        req: JobInvestigationRequest,
        session: JobInvestigationSession,
    ) -> ChatRcaResponse:
        """Answer a follow-up query against an existing completed session."""
        intent = _detect_intent(req.user_query)
        s = session.latest_summary or {}
        card = session.latest_incident_card or {}
        job_status = session.context.get("job_status", "UNKNOWN")
        job_id = req.job_id

        def _fmt_lineage(lw_list: List[Dict[str, Any]]) -> str:
            names = [n.get("display_name", "?") for n in lw_list]
            return " -> ".join(names) if names else "lineage data not available"

        intent_answers: Dict[str, str] = {
            "failure_reason": (
                f"The job {job_id} failed due to: "
                f"{s.get('failure_reason', 'no specific reason identified')}. "
                f"Failed node: {s.get('failed_node', 'N/A')} "
                f"(status: {s.get('failed_node_status', 'N/A')}). "
                f"Confidence: {float(s.get('confidence', 0)):.0%}."
            ),
            "control_triggered": (
                f"Control triggered: {s.get('control_triggered') or 'none detected'}."
            ),
            "lineage_failure": (
                f"Lineage failure node: {s.get('lineage_failure_node', 'none identified')}. "
                f"Lineage walk: {_fmt_lineage(s.get('lineage_walk', []))}"
            ),
            "recommendation": "\n".join(
                card.get("recommendations", ["No recommendations available."])
            ),
            "dashboard_url": (
                f"View the full investigation dashboard at: {session.dashboard_url}"
            ),
            "change_analysis": (
                f"Problem type: {s.get('problem_type', 'N/A')}. "
                "This may be related to a recent code change or deployment. "
                "Review the agent analysis chain in the dashboard for details."
            ),
            "data_analysis": (
                f"Lineage failure node: {s.get('lineage_failure_node', 'none')}. "
                "Verify upstream schema compatibility and column nullability."
            ),
            "infra_analysis": (
                f"Job status: {job_status}. "
                "Check system resource metrics at the time of the incident. "
                "Review LogSource evidence in the dashboard."
            ),
            "general": (
                f"Job {job_id} has status {job_status}. "
                f"Problem type: {s.get('problem_type', 'N/A')}. "
                f"Confidence: {float(s.get('confidence', 0)):.0%}. "
                "See the dashboard for full investigation details."
            ),
        }

        answer = intent_answers.get(intent, intent_answers["general"])

        # Reconstruct IncidentCard from stored dict
        incident_card: Optional[IncidentCard] = None
        if card:
            try:
                incident_card = IncidentCard(**card)
            except Exception:
                pass

        return ChatRcaResponse(
            session_id=session.session_id,
            job_id=req.job_id,
            scenario_id=req.scenario_id,
            answer=answer,
            summary=session.latest_summary,
            job_status=job_status,
            incident_card=incident_card,
            dashboard_url=session.dashboard_url,
            suggested_followups=self._suggest_followups(job_status, s),
            audit_ref=f"{session.session_id}/audit",
        )

    # ─── Composition helpers ──────────────────────────────────────────────

    def _compose_answer(
        self,
        query: str,
        job_status_str: str,
        summary_dict: Optional[Dict[str, Any]],
        incident_card: IncidentCard,
    ) -> str:
        s = summary_dict or {}
        job_id = incident_card.job_id
        problem_type = incident_card.problem_type

        # Brief intent-specific answer when query is provided
        if query and query.strip():
            intent = _detect_intent(query)
            if intent == "failure_reason" and s.get("failure_reason"):
                return (
                    f"The job {job_id} failed due to: {s['failure_reason']}. "
                    f"Failed node: {s.get('failed_node', 'N/A')}. "
                    f"Confidence: {float(s.get('confidence', 0)):.0%}."
                )
            if intent == "control_triggered":
                ctrl = s.get("control_triggered")
                return f"Control triggered: {ctrl or 'none detected'}."
            if intent == "recommendation":
                recs = incident_card.recommendations
                return "\n".join(recs) if recs else "No recommendations available."

        findings = s.get("findings", [])
        first_finding = findings[0] if findings else "No findings recorded."

        return (
            f"Investigation of job {job_id} is complete. "
            f"Status: {job_status_str}. "
            f"Problem type: {problem_type}. "
            f"Key finding: {first_finding} "
            f"View the full dashboard at: {incident_card.dashboard_url}"
        )

    def _suggest_followups(
        self, job_status_str: str, summary_dict: Dict[str, Any]
    ) -> List[str]:
        followups: List[str] = []
        if job_status_str == "FAILED":
            followups.append("What is the failure reason?")
            followups.append("Which control was triggered?")
            followups.append("Show the lineage failure path.")
        elif job_status_str == "DEGRADED":
            followups.append("What caused the degradation?")
            followups.append("Which data nodes are affected?")
        else:
            followups.append("Was any control triggered?")
            followups.append("Show the data lineage for this job.")
        followups.append("What are the recommendations?")
        followups.append("Open the dashboard.")
        return followups[:5]
