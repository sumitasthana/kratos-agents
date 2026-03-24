"""
agents/orchestrator/orchestrator.py
KratosOrchestrator — top-level 7-phase RCA pipeline driver.

This module is the ONLY place that knows the execution order of Kratos phases.
It is intentionally NOT a BaseAgent subclass; it coordinates agents rather than
being one.

Architecture
------------
Phase execution order (INTAKE→LOGS_FIRST→ROUTE→BACKTRACK→INCIDENT_CARD→RECOMMEND→PERSIST)
is driven by the :data:`~workflow.phase_registry.PHASE_REGISTRY`.

    KratosOrchestrator.run(incident_id)
        │
        ├─ INTAKE         → fetch_incident, build IncidentContext
        ├─ LOGS_FIRST     → run tools in parallel (asyncio.gather)
        ├─ ROUTE          → RoutingAgent.invoke()
        ├─ BACKTRACK      → TriangulationAgent.invoke() (up to 7 concurrent)
        ├─ INCIDENT_CARD  → inline LLM synthesis
        ├─ RECOMMEND      → RecommendationAgent.invoke()
        │       └─ ReviewerAgent.invoke() (feedback loop, max 2 iterations)
        └─ PERSIST        → finalize, emit AuditEvent, update lineage
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from core.base_agent import AgentResult
from core.models import AuditEvent, EvidenceObject, IncidentContext, Priority
from workflow.phase_registry import PHASE_REGISTRY, PhaseConfig
from workflow.pipeline_phases import Phase, PhaseResult, RCAReport, PHASE_ORDER

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FEEDBACK_LOOPS = 2

_INCIDENT_CARD_SYSTEM_PROMPT = (
    "You are synthesising a structured incident card for a regulatory RCA report.\n"
    "Given all collected evidence and at least one IssueProfile, produce a concise\n"
    "incident card in JSON format:\n"
    '{"incident_title": "...", "summary": "...", '
    '"primary_root_cause": "...", "affected_regulations": ["..."], '
    '"severity": "P1|P2|P3|P4"}'
)


# ---------------------------------------------------------------------------
# Internal accumulator (mutable — updated across phases)
# ---------------------------------------------------------------------------

@dataclass
class _PipelineState:
    """Accumulates pipeline-wide results across all phases."""
    evidence:         List[Any] = field(default_factory=list)
    issue_profiles:   List[Any] = field(default_factory=list)
    recommendations:  List[Any] = field(default_factory=list)
    audit_trail:      List[Any] = field(default_factory=list)
    phases_executed:  List[str] = field(default_factory=list)
    final_root_cause: str       = ""
    incident_card:    Dict[str, Any] = field(default_factory=dict)
    metadata:         Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# KratosOrchestrator
# ---------------------------------------------------------------------------

class KratosOrchestrator:
    """
    Top-level driver for the Kratos 7-phase RCA pipeline.

    Parameters
    ----------
    connector:
        Object that provides ``fetch_incident(incident_id: str) -> dict``.
        Typically :class:`~src.bank_pipeline_connector.BankPipelineConnector`.
    llm:
        Any object satisfying the ``LLMClient`` Protocol
        (``async def ainvoke(messages) -> ...``).  Used to build agent
        instances and for inline LLM calls (INCIDENT_CARD phase).
    graph_state:
        Ontology / knowledge-graph dictionary injected into every
        ``IncidentContext.ontology_snapshot``.  Defaults to ``{}``.
    tool_registry:
        Dict mapping tool name → instantiated :class:`~tools.base_tool.BaseTool`.
        Used in LOGS_FIRST to run tools directly.  If omitted, LOGS_FIRST
        produces placeholder evidence.
    agent_registry:
        Dict mapping class-name → agent class (as produced by
        :func:`~agents.register_all_agents`).  Used as a fallback when a
        phase's ``agent_class`` is not available in ``phase_registry``.
    """

    def __init__(
        self,
        connector: Any,
        llm: Any,
        graph_state: Optional[Dict[str, Any]] = None,
        tool_registry: Optional[Dict[str, Any]] = None,
        agent_registry: Optional[Dict[str, Type[Any]]] = None,
    ) -> None:
        self._connector     = connector
        self._llm            = llm
        self._graph_state    = graph_state or {}
        self._tool_registry  = tool_registry or {}
        self._agent_registry = agent_registry or {}

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def run(self, incident_id: str) -> RCAReport:
        """
        Execute the full 7-phase pipeline and return a complete RCA report.

        On any non-retryable phase failure the orchestrator skips directly to
        PERSIST so that partial results are always persisted.

        Parameters
        ----------
        incident_id:
            Opaque identifier for the incident (passed to connector).

        Returns
        -------
        RCAReport
            Pydantic model containing all evidence, profiles, recommendations,
            and an append-only audit trail.
        """
        wall_start = time.monotonic()
        state      = _PipelineState()

        # ── Phase 1: INTAKE ──────────────────────────────────────────────────
        intake_cfg  = PHASE_REGISTRY[Phase.INTAKE]
        try:
            context, intake_result = await asyncio.wait_for(
                self._intake(incident_id),
                timeout=intake_cfg.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error("[Orchestrator] INTAKE timed out")
            return self._build_report(incident_id, state, time.monotonic() - wall_start, error="INTAKE timeout")
        except Exception as exc:
            logger.error("[Orchestrator] INTAKE failed: %s", exc)
            return self._build_report(incident_id, state, time.monotonic() - wall_start, error=str(exc))

        self._record_phase(state, intake_result)
        self._emit_audit(state, Phase.INTAKE, intake_result)

        if not intake_result.success:
            return self._build_report(incident_id, state, time.monotonic() - wall_start)

        # ── Phases 2-7: iterate the registry ─────────────────────────────────
        current_phase: Optional[Phase] = Phase.LOGS_FIRST
        feedback_loops: int = 0

        while current_phase is not None:
            cfg = PHASE_REGISTRY[current_phase]

            phase_start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    self._run_phase(cfg, context, state),
                    timeout=cfg.timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "[Orchestrator] Phase %s timed out after %ds",
                    current_phase.value, cfg.timeout_seconds,
                )
                result = PhaseResult(
                    phase=current_phase,
                    success=False,
                    error=f"Timeout after {cfg.timeout_seconds}s",
                    duration_seconds=cfg.timeout_seconds,
                )
            except Exception as exc:
                logger.exception(
                    "[Orchestrator] Unhandled error in phase %s", current_phase.value
                )
                result = PhaseResult(
                    phase=current_phase,
                    success=False,
                    error=str(exc),
                    duration_seconds=time.monotonic() - phase_start,
                )

            result.duration_seconds = time.monotonic() - phase_start
            self._record_phase(state, result)
            self._emit_audit(state, current_phase, result)

            # ── Skip-to-PERSIST on non-retryable failure ──────────────────
            if not result.success and not cfg.retry_on_failure:
                if current_phase != Phase.PERSIST:
                    logger.warning(
                        "[Orchestrator] Non-retryable failure in %s → skipping to PERSIST",
                        current_phase.value,
                    )
                    current_phase = Phase.PERSIST
                    continue
                else:
                    break  # PERSIST itself failed — just exit

            # ── Reviewer feedback loop (triggered after RECOMMEND) ─────────
            if current_phase == Phase.RECOMMEND and feedback_loops < MAX_FEEDBACK_LOOPS:
                loop_target = await self._handle_feedback_loop(context, state)
                if loop_target is not None:
                    feedback_loops += 1
                    logger.info(
                        "[Orchestrator] Reviewer flagged gaps → looping to %s (iteration %d/%d)",
                        loop_target.value, feedback_loops, MAX_FEEDBACK_LOOPS,
                    )
                    self._emit_audit_raw(
                        state, current_phase, "looped",
                        f"Reviewer gap → routing back to {loop_target.value} "
                        f"(iteration {feedback_loops})",
                        {"loop_target": loop_target.value},
                    )
                    current_phase = loop_target
                    continue

            current_phase = cfg.next_phase

        duration = time.monotonic() - wall_start
        logger.info(
            "[Orchestrator] Pipeline complete | incident=%s | phases=%s | %.1fs",
            incident_id, state.phases_executed, duration,
        )
        return self._build_report(incident_id, state, duration)

    # -------------------------------------------------------------------------
    # Phase dispatcher
    # -------------------------------------------------------------------------

    async def _run_phase(
        self,
        cfg: PhaseConfig,
        context: IncidentContext,
        state: _PipelineState,
    ) -> PhaseResult:
        """Dispatch to the correct handler for *cfg.phase*."""

        if cfg.phase == Phase.LOGS_FIRST:
            return await self._logs_first(context, cfg, state)

        if cfg.phase == Phase.INCIDENT_CARD:
            return await self._incident_card(context, state)

        if cfg.phase == Phase.PERSIST:
            return await self._persist(context, state)

        if cfg.agent_class is not None:
            return await self._run_agent_phase(cfg, context, state)

        # Unknown non-agent phase — skip gracefully
        logger.warning("[Orchestrator] No handler for phase %s", cfg.phase.value)
        return PhaseResult(phase=cfg.phase, success=True, metadata={"skipped": True})

    # -------------------------------------------------------------------------
    # Non-agent phase handlers
    # -------------------------------------------------------------------------

    async def _intake(self, incident_id: str) -> tuple[IncidentContext, PhaseResult]:
        """
        INTAKE phase — fetch incident from connector, build IncidentContext.

        Falls back to a minimal synthetic context if the connector raises or
        returns an empty dict (so the pipeline can always proceed).
        """
        try:
            raw: Dict[str, Any] = await self._call_connector(incident_id)
        except Exception as exc:
            logger.warning("[Orchestrator] Connector fetch failed: %s — using synthetic context", exc)
            raw = {}

        context = IncidentContext(
            incident_id    = incident_id,
            run_id         = raw.get("run_id", incident_id),
            pipeline_stage = raw.get("pipeline_stage", "unknown"),
            failed_controls= raw.get("failed_controls", []),
            ontology_snapshot = {**self._graph_state, **raw.get("ontology_snapshot", {})},
            metadata       = {k: v for k, v in raw.items()
                              if k not in {"run_id", "pipeline_stage", "failed_controls"}},
        )
        result = PhaseResult(
            phase   = Phase.INTAKE,
            success = True,
            metadata= {"incident_id": incident_id, "stage": context.pipeline_stage},
        )
        logger.info(
            "[INTAKE] incident=%s stage=%s controls=%s",
            incident_id, context.pipeline_stage, context.failed_controls,
        )
        return context, result

    async def _call_connector(self, incident_id: str) -> Dict[str, Any]:
        """Call connector.fetch_incident() — supports both sync and async."""
        fn = getattr(self._connector, "fetch_incident", None)
        if fn is None:
            return {}
        result = fn(incident_id)
        if asyncio.iscoroutine(result):
            return await result
        return result or {}

    async def _logs_first(
        self,
        context: IncidentContext,
        cfg: PhaseConfig,
        state: _PipelineState,
    ) -> PhaseResult:
        """
        LOGS_FIRST phase — run configured tools in parallel using asyncio.gather.

        Up to ``cfg.max_concurrency`` tools run simultaneously.  Each tool is
        expected to return an ``AgentResult``; we extract its evidence list.
        If no tools are configured or available, a placeholder EvidenceObject is
        produced so downstream phases always have *something* to work with.
        """
        tool_names = cfg.tools
        if not tool_names:
            return PhaseResult(phase=Phase.LOGS_FIRST, success=True)

        # Build coroutines — one per tool (semaphore guards concurrency)
        sem = asyncio.Semaphore(cfg.max_concurrency)

        async def _run_one_tool(name: str) -> List[EvidenceObject]:
            async with sem:
                tool = self._tool_registry.get(name)
                if tool is None:
                    logger.warning("[LOGS_FIRST] Tool %r not in tool_registry — generating placeholder", name)
                    return [EvidenceObject(
                        source_tool=name,
                        severity=Priority.P4,
                        description=f"Tool {name!r} not available during LOGS_FIRST phase.",
                    )]
                try:
                    raw_result = getattr(tool, "run", None)
                    if raw_result is not None:
                        agent_result: AgentResult = await raw_result(
                            incident_id=context.incident_id,
                            metadata=context.metadata,
                        )
                        return agent_result.evidence if isinstance(agent_result, AgentResult) else []
                except Exception as exc:
                    logger.warning("[LOGS_FIRST] Tool %r raised: %s", name, exc)
                    return [EvidenceObject(
                        source_tool=name,
                        severity=Priority.P3,
                        description=f"Tool {name!r} failed: {exc}",
                    )]
            return []

        tool_batches = await asyncio.gather(
            *[_run_one_tool(n) for n in tool_names],
            return_exceptions=False,
        )
        all_evidence: List[EvidenceObject] = [ev for batch in tool_batches for ev in batch]
        state.evidence.extend(all_evidence)

        logger.info("[LOGS_FIRST] Collected %d evidence items from %d tools", len(all_evidence), len(tool_names))
        return PhaseResult(
            phase    = Phase.LOGS_FIRST,
            success  = True,
            evidence = all_evidence,
            metadata = {"tools_run": tool_names, "evidence_count": len(all_evidence)},
        )

    async def _incident_card(
        self,
        context: IncidentContext,
        state: _PipelineState,
    ) -> PhaseResult:
        """
        INCIDENT_CARD phase — synthesise a structured incident summary via LLM.

        The card is stored in ``state.incident_card`` and surfaced in
        ``RCAReport.metadata["incident_card"]``.
        """
        ev_summary = [
            f"[{e.source_tool}] {e.severity.value}: {e.description[:120]}"
            for e in state.evidence[:20]
            if isinstance(e, EvidenceObject)
        ]
        profiles_summary = [
            str(getattr(p, "root_cause_hypothesis", p))[:200]
            for p in state.issue_profiles[:5]
        ]
        user_msg = (
            f"Incident ID: {context.incident_id}\n"
            f"Stage: {context.pipeline_stage}\n"
            f"Failed controls: {', '.join(context.failed_controls) or 'none'}\n\n"
            f"Evidence ({len(state.evidence)} items):\n"
            + "\n".join(ev_summary or ["  (none)"])
            + "\n\nIssue profiles:\n"
            + "\n".join(profiles_summary or ["  (none)"])
            + "\n\nSynthesise the incident card."
        )
        card: Dict[str, Any] = {}
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            msgs = [
                SystemMessage(content=_INCIDENT_CARD_SYSTEM_PROMPT),
                HumanMessage(content=user_msg),
            ]
            resp = await self._llm.ainvoke(msgs)
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if "```" in raw:
                raw = raw.split("```")[-2].lstrip("json").strip()
            card = json.loads(raw)
        except Exception as exc:
            logger.warning("[INCIDENT_CARD] LLM call failed: %s", exc)
            card = {
                "incident_title": f"Incident {context.incident_id}",
                "summary": "LLM synthesis unavailable.",
                "primary_root_cause": state.issue_profiles[0].root_cause_hypothesis
                    if state.issue_profiles and hasattr(state.issue_profiles[0], "root_cause_hypothesis")
                    else "Unknown",
                "affected_regulations": [],
                "severity": "P3",
            }

        state.incident_card = card
        state.final_root_cause = card.get("primary_root_cause", "")

        logger.info("[INCIDENT_CARD] title=%r root_cause=%r", card.get("incident_title"), state.final_root_cause)
        return PhaseResult(
            phase    = Phase.INCIDENT_CARD,
            success  = True,
            metadata = {"incident_card": card},
        )

    async def _persist(
        self,
        context: IncidentContext,
        state: _PipelineState,
    ) -> PhaseResult:
        """
        PERSIST phase — write final state, emit lineage update, log audit.

        Currently writes a structured summary to Python logging at INFO.
        Callers with persistent stores can subclass and override this method.
        """
        summary = {
            "incident_id":         context.incident_id,
            "final_root_cause":    state.final_root_cause,
            "evidence_count":      len(state.evidence),
            "issue_profiles":      len(state.issue_profiles),
            "recommendations":     len(state.recommendations),
            "phases_executed":     state.phases_executed,
            "audit_events":        len(state.audit_trail),
        }
        logger.info("[PERSIST] RCA pipeline complete: %s", json.dumps(summary, default=str))

        # Notify connector / downstream system if it supports the method
        persist_fn = getattr(self._connector, "persist_rca", None)
        if persist_fn is not None:
            try:
                result = persist_fn(summary)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("[PERSIST] connector.persist_rca() failed: %s", exc)

        return PhaseResult(
            phase    = Phase.PERSIST,
            success  = True,
            metadata = summary,
        )

    # -------------------------------------------------------------------------
    # Agent phase runner
    # -------------------------------------------------------------------------

    async def _run_agent_phase(
        self,
        cfg: PhaseConfig,
        context: IncidentContext,
        state: _PipelineState,
    ) -> PhaseResult:
        """
        Run a phase backed by a :class:`~core.base_agent.BaseAgent` subclass.

        For BACKTRACK (TriangulationAgent) the agent receives a context
        enriched with all evidence collected so far.
        For RECOMMEND (RecommendationAgent) the context is enriched with
        issue_profiles.
        """
        # Build an enriched context so agents get the latest accumulated state
        enriched_metadata = {
            **context.metadata,
            "evidence":       [
                e.model_dump() if hasattr(e, "model_dump") else dict(e)
                for e in state.evidence
            ],
            "issue_profiles": state.issue_profiles,
            "recommendations": state.recommendations,
            "selected_tools": state.metadata.get("selected_tools", cfg.tools),
        }
        enriched_context = IncidentContext(
            incident_id       = context.incident_id,
            run_id            = context.run_id,
            pipeline_stage    = context.pipeline_stage,
            failed_controls   = context.failed_controls,
            ontology_snapshot = context.ontology_snapshot,
            metadata          = enriched_metadata,
        )

        # Instantiate the agent
        agent_cls = cfg.agent_class
        agent = agent_cls(llm=self._llm)

        # BACKTRACK: up to max_concurrency parallel tool invocations
        if cfg.phase == Phase.BACKTRACK and cfg.max_concurrency > 1:
            result = await self._run_backtrack(agent, enriched_context, cfg)
        else:
            result: AgentResult = await agent.invoke(enriched_context)

        # Accumulate results into state
        if isinstance(result, AgentResult):
            state.evidence.extend(result.evidence)
            state.issue_profiles.extend(result.issue_profiles)
            state.recommendations.extend(result.recommendations)
            if result.metadata:
                state.metadata.update(result.metadata)
            agent_name = result.agent_name
        else:
            agent_name = getattr(agent, "agent_name", str(cfg.agent_class))

        return PhaseResult(
            phase            = cfg.phase,
            success          = True,
            evidence         = result.evidence if hasattr(result, "evidence") else [],
            issue_profiles   = result.issue_profiles if hasattr(result, "issue_profiles") else [],
            recommendations  = result.recommendations if hasattr(result, "recommendations") else [],
            next_phase       = Phase(result.next_phase) if (
                hasattr(result, "next_phase") and result.next_phase and
                result.next_phase in {p.value for p in Phase}
            ) else None,
            metadata         = result.metadata if hasattr(result, "metadata") else {},
        )

    async def _run_backtrack(
        self,
        agent: Any,
        context: IncidentContext,
        cfg: PhaseConfig,
    ) -> AgentResult:
        """
        BACKTRACK: invoke the TriangulationAgent up to *cfg.max_concurrency*
        times in parallel (each with a different tool-context slice).

        For now we run it once for the full evidence set and once per-tool
        slice if more than one tool produced evidence, capped at max_concurrency.
        Results are merged into a single AgentResult.
        """
        from core.base_agent import AgentResult as AR

        evidence: List[Any] = context.metadata.get("evidence", [])
        tools_used: List[str] = list({
            e.get("source_tool") if isinstance(e, dict) else getattr(e, "source_tool", "?")
            for e in evidence
        } - {None})

        if len(tools_used) <= 1:
            # Only one evidence source — single invocation
            return await agent.invoke(context)

        sem = asyncio.Semaphore(cfg.max_concurrency)

        async def _invoke_slice(tool_name: str) -> AR:
            async with sem:
                sliced_ev = [
                    e for e in evidence
                    if (e.get("source_tool") if isinstance(e, dict) else getattr(e, "source_tool", "")) == tool_name
                ]
                sliced_ctx = IncidentContext(
                    incident_id       = context.incident_id,
                    run_id            = context.run_id,
                    pipeline_stage    = context.pipeline_stage,
                    failed_controls   = context.failed_controls,
                    ontology_snapshot = context.ontology_snapshot,
                    metadata          = {**context.metadata, "evidence": sliced_ev},
                )
                return await agent.invoke(sliced_ctx)

        results: List[AR] = await asyncio.gather(
            *[_invoke_slice(t) for t in tools_used[:cfg.max_concurrency]],
            return_exceptions=False,
        )

        # Merge all partial results into one
        merged_evidence       = [ev for r in results for ev in (r.evidence or [])]
        merged_profiles       = [p  for r in results for p  in (r.issue_profiles or [])]
        merged_recs           = [rc for r in results for rc in (r.recommendations or [])]
        metadata              = {}
        for r in results:
            metadata.update(r.metadata or {})

        return AR(
            agent_name    = getattr(agent, "agent_name", "TriangulationAgent"),
            evidence      = merged_evidence,
            issue_profiles= merged_profiles,
            recommendations= merged_recs,
            next_phase    = "recommendation",
            metadata      = metadata,
        )

    # -------------------------------------------------------------------------
    # Reviewer feedback loop
    # -------------------------------------------------------------------------

    async def _handle_feedback_loop(
        self,
        context: IncidentContext,
        state: _PipelineState,
    ) -> Optional[Phase]:
        """
        Run :class:`~agents.reviewer.agent.ReviewerAgent` on the current state.

        Returns the Phase to loop back to, or *None* if the report is clean.
        """
        try:
            from agents.reviewer.agent import ReviewerAgent
        except ImportError as exc:
            logger.error("[Orchestrator] Cannot import ReviewerAgent: %s", exc)
            return None

        enriched_metadata = {
            **context.metadata,
            "evidence":       [
                e.model_dump() if hasattr(e, "model_dump") else dict(e)
                for e in state.evidence
            ],
            "issue_profiles":  state.issue_profiles,
            "recommendations": state.recommendations,
        }
        review_ctx = IncidentContext(
            incident_id       = context.incident_id,
            run_id            = context.run_id,
            pipeline_stage    = context.pipeline_stage,
            failed_controls   = context.failed_controls,
            ontology_snapshot = context.ontology_snapshot,
            metadata          = enriched_metadata,
        )

        try:
            reviewer   = ReviewerAgent(llm=self._llm)
            rev_result = await asyncio.wait_for(
                reviewer.invoke(review_ctx), timeout=60
            )
        except Exception as exc:
            logger.warning("[Orchestrator] ReviewerAgent failed: %s — skipping feedback loop", exc)
            return None

        # Append reviewer evidence to audit trail
        state.evidence.extend(rev_result.evidence)

        passed = rev_result.metadata.get("passed", True)
        if passed:
            logger.info("[Orchestrator] Reviewer PASSED — no feedback loop needed")
            return None

        next_phase_str = rev_result.next_phase  # "routing" | "done" | None
        if next_phase_str in ("routing", "route"):
            logger.info("[Orchestrator] Reviewer FAILED → looping back to ROUTE")
            return Phase.ROUTE

        logger.info("[Orchestrator] Reviewer FAILED, next_phase=%r — looping back to ROUTE by default", next_phase_str)
        return Phase.ROUTE

    # -------------------------------------------------------------------------
    # Audit helpers
    # -------------------------------------------------------------------------

    def _emit_audit(
        self,
        state: _PipelineState,
        phase: Phase,
        result: PhaseResult,
    ) -> None:
        """Append an AuditEvent based on a PhaseResult."""
        outcome = "success" if result.success else "failure"
        if result.error:
            outcome = "failure"
        self._emit_audit_raw(
            state, phase, outcome,
            f"Phase {phase.value} completed: {outcome}. "
            + (f"Error: {result.error}" if result.error else ""),
            result.metadata,
        )

    def _emit_audit_raw(
        self,
        state: _PipelineState,
        phase: Phase,
        outcome: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Directly append an AuditEvent dict to the audit trail."""
        try:
            event = AuditEvent(
                phase    = phase.value,
                outcome  = outcome,
                message  = message,
                metadata = metadata or {},
            )
            state.audit_trail.append(event.model_dump(mode="json"))
        except Exception as exc:
            logger.debug("[Orchestrator] AuditEvent serialisation failed: %s", exc)
            state.audit_trail.append({
                "phase": phase.value, "outcome": outcome,
                "message": message, "metadata": metadata or {},
            })

    def _record_phase(self, state: _PipelineState, result: PhaseResult) -> None:
        """Mark a phase as executed and merge its results into *state*."""
        state.phases_executed.append(result.phase.value)
        state.evidence.extend(ev for ev in result.evidence if ev not in state.evidence)
        state.issue_profiles.extend(p for p in result.issue_profiles if p not in state.issue_profiles)
        state.recommendations.extend(r for r in result.recommendations if r not in state.recommendations)
        if result.metadata:
            state.metadata.update(result.metadata)

    # -------------------------------------------------------------------------
    # Report builder
    # -------------------------------------------------------------------------

    def _build_report(
        self,
        incident_id: str,
        state: _PipelineState,
        duration: float,
        error: Optional[str] = None,
    ) -> RCAReport:
        """Assemble the final :class:`~workflow.pipeline_phases.RCAReport`."""
        root_cause = state.final_root_cause
        if not root_cause and state.issue_profiles:
            first = state.issue_profiles[0]
            root_cause = (
                getattr(first, "root_cause_hypothesis", None)
                or (first.get("root_cause_hypothesis") if isinstance(first, dict) else "")
                or ""
            )

        extra: Dict[str, Any] = {**state.metadata}
        if state.incident_card:
            extra["incident_card"] = state.incident_card
        if error:
            extra["pipeline_error"] = error

        return RCAReport(
            incident_id      = incident_id,
            phases_executed  = state.phases_executed,
            evidence         = state.evidence,
            issue_profiles   = state.issue_profiles,
            recommendations  = state.recommendations,
            audit_trail      = state.audit_trail,
            duration_seconds = round(duration, 3),
            final_root_cause = root_cause,
            metadata         = extra,
        )


# ---------------------------------------------------------------------------
# Backward-compatibility aliases  (referenced by agents/orchestrator/__init__)
# ---------------------------------------------------------------------------

SparkOrchestrator  = KratosOrchestrator
SmartOrchestrator  = KratosOrchestrator

__all__ = [
    "KratosOrchestrator",
    "SparkOrchestrator",
    "SmartOrchestrator",
    "_PipelineState",
]
