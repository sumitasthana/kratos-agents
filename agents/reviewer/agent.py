"""
agents/reviewer/agent.py
ReviewerAgent (Kratos Reviewer) — validates the full RCA report.

Final stage in the Kratos pipeline. Reads the complete set of evidence,
IssueProfiles, and Recommendations and runs a structured validation checklist.
Flags uncited claims, low-confidence issues, missing evidence domains, and
recommendations without regulation references.

If gaps are found it returns ``next_phase="routing"`` so the orchestrator
can loop back.  A clean report returns ``next_phase="done"``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentResult, AgentType, FingerprintDomain
from core.models import (
    EvidenceObject,
    IncidentContext,
    IssueProfile,
    LLMClient,
    Priority,
    Recommendation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    criterion: str
    passed:    bool
    detail:    str = ""


@dataclass
class ValidationReport:
    checks:     List[CheckResult]  = field(default_factory=list)
    gap_count:  int                = 0
    feedback:   List[str]          = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.gap_count == 0


# ---------------------------------------------------------------------------
# ReviewerAgent
# ---------------------------------------------------------------------------

class ReviewerAgent(BaseAgent):
    """
    Validates the full RCA report and emits pass/fail per criterion.

    Validation checklist (run in :meth:`_run_checklist`):

      1. Every recommendation cites ``regulation_ref``.
      2. Every recommendation cites ``defect_id``.
      3. Every IssueProfile has at least one supporting ``EvidenceObject``.
      4. No IssueProfile has confidence < ``MIN_CONFIDENCE``.
      5. At least ``MIN_EVIDENCE_DOMAINS`` distinct ``source_tool`` values.
      6. LLM coherence check: rationale is consistent with evidence (soft).

    ``context.metadata`` must contain:
      - ``evidence``         : list[EvidenceObject | dict]
      - ``issue_profiles``   : list[IssueProfile | dict]
      - ``recommendations``  : list[Recommendation | dict]
    """

    MIN_CONFIDENCE:       float = 0.5
    MIN_EVIDENCE_DOMAINS: int   = 1

    def __init__(self, llm: LLMClient, tools: list | None = None) -> None:
        super().__init__(name="ReviewerAgent", llm=llm, tools=tools or [])

    # -- Abstract property implementations ------------------------------------

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ROUTING  # reviewer re-routes; use ROUTING enum

    @property
    def agent_name(self) -> str:
        return "Reviewer Agent"

    @property
    def description(self) -> str:
        return (
            "Validates the complete RCA report: checks that every claim has "
            "evidence, every recommendation cites regulation, and confidence is "
            "above threshold. Loops back to routing when gaps are found."
        )

    @property
    def fingerprint_domain(self) -> FingerprintDomain:
        return FingerprintDomain.ISSUE

    @property
    def system_prompt(self) -> str:
        return self._build_system_prompt()

    # -- Prompt helpers -------------------------------------------------------

    def _build_system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parents[2]
            / "resources" / "prompts" / "reviewer.txt"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are the Kratos Reviewer Agent.\n"
            "Your role is audit compliance checking for an RCA report.\n\n"
            "Review the provided evidence, issue profiles, and recommendations.\n"
            "Check:\n"
            "1. Every recommendation cites regulation_ref and defect_id.\n"
            "2. Every issue hypothesis is backed by at least one evidence item.\n"
            "3. No hypothesis has confidence below 0.5 unless flagged.\n"
            "4. At least two distinct evidence sources are present.\n"
            "5. The rationale is coherent with the evidence.\n\n"
            "Respond ONLY with valid JSON:\n"
            '{{"overall_pass": true, "gaps": ["gap description", ...], '
            '"feedback": ["suggestion", ...]}}'

        )

    def _build_user_message(self, context: IncidentContext) -> str:
        ev_count  = len(context.metadata.get("evidence", []))
        pro_count = len(context.metadata.get("issue_profiles", []))
        rec_count = len(context.metadata.get("recommendations", []))
        tools_used = list({
            (e.get("source_tool") if isinstance(e, dict) else getattr(e, "source_tool", "?"))
            for e in context.metadata.get("evidence", [])
        })
        recs_summary = [
            f"- [{r.get('defect_id') if isinstance(r, dict) else getattr(r, 'defect_id', '?')}] "
            f"{r.get('action') if isinstance(r, dict) else getattr(r, 'action', '?')}"
            for r in context.metadata.get("recommendations", [])[:6]
        ]
        return (
            f"Incident ID : {context.incident_id}\n"
            f"Failed controls: {', '.join(context.failed_controls) or 'none'}\n\n"
            f"Report summary:\n"
            f"  Evidence items    : {ev_count} (sources: {', '.join(tools_used) or 'none'})\n"
            f"  Issue profiles    : {pro_count}\n"
            f"  Recommendations   : {rec_count}\n\n"
            f"First 6 recommendations:\n"
            + "\n".join(recs_summary or ["  (none)"])
            + "\n\nPerform your audit compliance check."
        )

    # -- Validation checklist -------------------------------------------------

    def _run_checklist(self, context: IncidentContext) -> ValidationReport:
        """
        Deterministic structural validation (no LLM needed).

        Returns a :class:`ValidationReport` with per-criterion pass/fail.
        """
        evidence: List[Any] = context.metadata.get("evidence", [])
        profiles: List[Any] = context.metadata.get("issue_profiles", [])
        recs:     List[Any] = context.metadata.get("recommendations", [])

        checks:   List[CheckResult] = []
        gaps:     List[str]         = []
        feedback: List[str]         = []

        # Check 1: all recs cite regulation_ref
        missing_reg = [
            str(getattr(r, "defect_id", r.get("defect_id", "?") if isinstance(r, dict) else "?"))
            for r in recs
            if not (getattr(r, "regulation_ref", None) or (isinstance(r, dict) and r.get("regulation_ref")))
        ]
        c1_pass = len(missing_reg) == 0
        checks.append(CheckResult(
            criterion="All recommendations cite regulation_ref",
            passed=c1_pass,
            detail=f"Missing in: {missing_reg}" if not c1_pass else "OK",
        ))
        if not c1_pass:
            gaps.append(f"Recommendations missing regulation_ref: {missing_reg}")
            feedback.append("Add regulation_ref to all recommendations before finalising.")

        # Check 2: all recs cite defect_id
        missing_def = [
            str(getattr(r, "action", r.get("action", "?") if isinstance(r, dict) else "?"))[:60]
            for r in recs
            if not (getattr(r, "defect_id", None) or (isinstance(r, dict) and r.get("defect_id")))
        ]
        c2_pass = len(missing_def) == 0
        checks.append(CheckResult(
            criterion="All recommendations cite defect_id",
            passed=c2_pass,
            detail=f"Missing defect_id in: {missing_def}" if not c2_pass else "OK",
        ))
        if not c2_pass:
            gaps.append(f"Recommendations missing defect_id: {missing_def}")
            feedback.append("Assign DEF-XXX identifiers to uncited recommendations.")

        # Check 3: every IssueProfile has evidence
        unsupported = [
            str(getattr(p, "id", p.get("id", "?") if isinstance(p, dict) else "?"))
            for p in profiles
            if not (
                getattr(p, "supporting_evidence", None)
                or (isinstance(p, dict) and p.get("supporting_evidence"))
            )
        ]
        c3_pass = len(unsupported) == 0
        checks.append(CheckResult(
            criterion="Every IssueProfile has supporting evidence",
            passed=c3_pass,
            detail=f"Unsupported profiles: {unsupported}" if not c3_pass else "OK",
        ))
        if not c3_pass:
            gaps.append(f"IssueProfiles lack evidence: {unsupported}")
            feedback.append("Collect additional evidence before these profiles can be acted upon.")

        # Check 4: confidence threshold
        low_conf = [
            str(getattr(p, "id", p.get("id", "?") if isinstance(p, dict) else "?"))
            for p in profiles
            if float(
                getattr(p, "confidence",
                        p.get("confidence", 1.0) if isinstance(p, dict) else 1.0)
            ) < self.MIN_CONFIDENCE
        ]
        c4_pass = len(low_conf) == 0
        checks.append(CheckResult(
            criterion=f"All IssueProfile confidence >= {self.MIN_CONFIDENCE}",
            passed=c4_pass,
            detail=f"Low-confidence profiles: {low_conf}" if not c4_pass else "OK",
        ))
        if not c4_pass:
            gaps.append(f"Low-confidence IssueProfiles (< {self.MIN_CONFIDENCE}): {low_conf}")
            feedback.append(
                "Run additional analyzers to increase confidence before closing the incident."
            )

        # Check 5: evidence domain diversity
        source_tools = {
            (e.get("source_tool") if isinstance(e, dict) else getattr(e, "source_tool", None))
            for e in evidence
        } - {None}
        c5_pass = len(source_tools) >= self.MIN_EVIDENCE_DOMAINS
        checks.append(CheckResult(
            criterion=f"At least {self.MIN_EVIDENCE_DOMAINS} distinct evidence source(s)",
            passed=c5_pass,
            detail=(
                f"Sources found: {source_tools}" if c5_pass
                else f"Only {len(source_tools)} source(s): {source_tools}"
            ),
        ))
        if not c5_pass:
            gaps.append(f"Fewer than {self.MIN_EVIDENCE_DOMAINS} distinct evidence domains.")
            feedback.append(
                "Invoke additional analysis tools (e.g. DataQualityTool, DDLDiffTool) "
                "to broaden evidence coverage."
            )

        gap_count = sum(1 for c in checks if not c.passed)
        return ValidationReport(checks=checks, gap_count=gap_count, feedback=feedback)

    # -- invoke() -------------------------------------------------------------

    async def invoke(self, context: IncidentContext) -> AgentResult:
        """
        Validate the full RCA report and decide whether to loop back.

        Returns AgentResult with:
          - metadata["validation_report"]  : per-criterion pass/fail dict
          - metadata["gaps"]               : list of gap descriptions
          - metadata["feedback"]           : list of improvement suggestions
          - next_phase = "done" | "routing"
        """
        # Step 1: Deterministic structural checklist
        val_report = self._run_checklist(context)

        logger.info(
            "[ReviewerAgent] incident=%s checks=%d gaps=%d passed=%s",
            context.incident_id,
            len(val_report.checks),
            val_report.gap_count,
            val_report.passed,
        )

        # Step 2: LLM coherence check — SKIP when deterministic checks all pass
        # This saves ~2,000 tokens per run (the reviewer system prompt is 8.5KB).
        llm_gaps:     List[str] = []
        llm_feedback: List[str] = []
        if val_report.gap_count > 0:
            # Only call LLM when there are gaps to get improvement suggestions
            try:
                user_msg = self._build_user_message(context)
                raw_llm  = await self._call_llm(self._build_system_prompt(), user_msg)
                raw_str  = raw_llm.strip()
                if "```" in raw_str:
                    raw_str = raw_str.split("```")[-2].lstrip("json").strip()
                llm_parsed: Dict[str, Any] = json.loads(raw_str)
                llm_gaps     = llm_parsed.get("gaps", [])
                llm_feedback = llm_parsed.get("feedback", [])
            except Exception as exc:
                logger.debug("[ReviewerAgent] LLM coherence check skipped: %s", exc)
        else:
            logger.info("[ReviewerAgent] All checks passed — skipping LLM coherence call (saves ~2K tokens)")

        all_gaps     = [c.detail for c in val_report.checks if not c.passed] + llm_gaps
        all_feedback = val_report.feedback + llm_feedback

        # Step 3: Emit audit evidence
        severity = Priority.P2 if val_report.gap_count > 0 else Priority.P4
        audit_ev = EvidenceObject(
            id=f"ReviewerAgent_{context.incident_id[:8]}",
            source_tool="ReviewerAgent",
            severity=severity,
            description=(
                f"Audit: {len(val_report.checks)} checks, {val_report.gap_count} gaps. "
                f"{'PASS' if val_report.passed else 'FAIL -- routing back.'}"
            ),
            raw_payload={
                "checks": [
                    {"criterion": c.criterion, "passed": c.passed, "detail": c.detail}
                    for c in val_report.checks
                ],
                "gaps":     all_gaps,
                "feedback": all_feedback,
            },
        )
        await self.emit_evidence(audit_ev)

        next_phase = "done" if val_report.passed else "routing"

        return AgentResult(
            agent_name="Reviewer Agent",
            evidence=[audit_ev],
            next_phase=next_phase,
            metadata={
                "passed":    val_report.passed,
                "gap_count": val_report.gap_count,
                "gaps":      all_gaps,
                "feedback":  all_feedback,
                "validation_report": [
                    {"criterion": c.criterion, "passed": c.passed, "detail": c.detail}
                    for c in val_report.checks
                ],
            },
        )


# Keep backward-compat alias
KratosReviewer = ReviewerAgent

__all__ = ["ReviewerAgent", "KratosReviewer"]

