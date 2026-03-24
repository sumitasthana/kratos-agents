"""
agents/recommendation/agent.py
RecommendationAgent — IssueProfile(s) → prioritised Recommendation objects.

Layer 2 in the Kratos pipeline. Receives IssueProfile(s) in context.metadata,
generates Recommendation objects that MUST cite defect_id and regulation_ref,
and optionally queries the ontology for related past incidents.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

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
# Regulation reference lookup
# ---------------------------------------------------------------------------

_REGULATION_MAP: Dict[str, str] = {
    "330":   "12 CFR Part 330 - Deposit Insurance Coverage",
    "370":   "12 CFR Part 370 - Recordkeeping for Timely Deposit Insurance Determinations",
    "spark": "12 CFR Part 370 §2(c) - Data Processing Systems",
    "data":  "12 CFR Part 330 §4(a) - Beneficial Ownership Records",
    "code":  "12 CFR Part 370 §4(b) - IT System Controls",
}

_EFFORT_MAP = {
    Priority.P1: "4h",
    Priority.P2: "1 day",
    Priority.P3: "1 sprint",
    Priority.P4: "backlog",
}


class RecommendationAgent(BaseAgent):
    """
    Generates prioritised, regulation-traceable Recommendation objects.

    Each recommendation MUST cite:
      - ``defect_id``     : structured defect reference (e.g. ``DEF-042``)
      - ``regulation_ref``: regulation section (e.g. ``12 CFR Part 370 §2(c)``)

    Reads ``context.metadata["issue_profiles"]`` (list of IssueProfile objects
    or dicts).  Falls back gracefully when profiles are missing.
    """

    def __init__(self, llm: LLMClient, tools: list | None = None) -> None:
        super().__init__(
            name="RecommendationAgent",
            llm=llm,
            tools=tools or [],
        )
        self._defect_counter: int = 0

    # ── Abstract property implementations ────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.RECOMMENDATION

    @property
    def agent_name(self) -> str:
        return "Recommendation Agent"

    @property
    def description(self) -> str:
        return (
            "Generates prioritised, regulation-cited remediation recommendations "
            "from triangulated IssueProfiles."
        )

    @property
    def fingerprint_domain(self) -> FingerprintDomain:
        return FingerprintDomain.ISSUE

    @property
    def system_prompt(self) -> str:
        return self._build_system_prompt()

    # ── Prompt helpers ────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parents[2]
            / "resources" / "prompts" / "recommendation.txt"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are the Kratos Recommendation Agent.\n"
            "Your role is to produce prioritised, actionable remediation steps "
            "for each root-cause hypothesis.\n\n"
            "Rules:\n"
            "1. Every recommendation MUST cite a defect_id (e.g. DEF-042) and "
            "a regulation_ref (e.g. '12 CFR Part 370 §2(c)').\n"
            "2. Prioritise by severity: P1 (fix now) → P4 (backlog).\n"
            "3. Include an effort estimate (e.g. '4h', '1 day', '1 sprint').\n"
            "4. Base recommendations on evidence; avoid speculative fixes.\n\n"
            "Respond ONLY with valid JSON — a list of recommendation objects:\n"
            "[{{\"defect_id\": \"DEF-001\", \"action\": \"...\", "
            "\"priority\": \"P1\", \"effort_estimate\": \"4h\", "
            "\"regulation_ref\": \"12 CFR Part 370 \u00a72(c)\", "
            "\"rationale\": \"...\"}}]"
        )

    def _build_user_message(self, context: IncidentContext) -> str:
        profiles_raw: List[Any] = context.metadata.get("issue_profiles", [])
        profile_summaries = []
        for p in profiles_raw:
            if isinstance(p, dict):
                profile_summaries.append(
                    f"- Hypothesis: {p.get('root_cause_hypothesis', '?')} "
                    f"| conf={p.get('confidence', '?')} "
                    f"| reg={p.get('affected_regulation', 'N/A')}"
                )
            elif isinstance(p, IssueProfile):
                profile_summaries.append(
                    f"- Hypothesis: {p.root_cause_hypothesis} "
                    f"| conf={p.confidence} "
                    f"| reg={p.affected_regulation or 'N/A'}"
                )
        return (
            f"Incident ID : {context.incident_id}\n"
            f"Failed controls: {', '.join(context.failed_controls) or 'none'}\n\n"
            f"Issue Profiles ({len(profiles_raw)}):\n"
            + "\n".join(profile_summaries or ["  (no profiles)"])
            + "\n\nGenerate a prioritised set of remediation recommendations."
        )

    # ── Defect ID generation ──────────────────────────────────────────────

    def _next_defect_id(self) -> str:
        self._defect_counter += 1
        return f"DEF-{self._defect_counter:03d}"

    # ── Regulation inference ──────────────────────────────────────────────

    def _infer_regulation(self, issue: Any, idx: int) -> str:
        """Pick a regulation ref from the IssueProfile or default map."""
        if isinstance(issue, IssueProfile) and issue.affected_regulation:
            return issue.affected_regulation
        if isinstance(issue, dict) and issue.get("affected_regulation"):
            return issue["affected_regulation"]
        # Fallback based on index
        fallbacks = list(_REGULATION_MAP.values())
        return fallbacks[idx % len(fallbacks)]

    # ── LLM response parsing ──────────────────────────────────────────────

    def _parse_llm_recs(self, raw: str, issue_id: str) -> List[Recommendation]:
        """Parse LLM JSON response into Recommendation objects."""
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[-2].lstrip("json").strip()
        try:
            items: List[Dict] = json.loads(raw)
        except json.JSONDecodeError:
            return []

        recs: List[Recommendation] = []
        for item in items if isinstance(items, list) else []:
            try:
                pval = str(item.get("priority", "P3"))
                try:
                    priority = Priority(pval)
                except ValueError:
                    priority = Priority.P3
                recs.append(
                    Recommendation(
                        issue_profile_id=issue_id,
                        action=str(item.get("action", "Review and remediate")),
                        priority=priority,
                        effort_estimate=str(item.get("effort_estimate", "1 sprint")),
                        defect_id=str(item.get("defect_id") or self._next_defect_id()),
                        regulation_ref=str(
                            item.get("regulation_ref")
                            or "12 CFR Part 370"
                        ),
                        rationale=str(item.get("rationale", "")),
                    )
                )
            except Exception as exc:
                logger.debug("[RecommendationAgent] Could not parse rec item: %s", exc)
        return recs

    # ── Heuristic fallback recs ───────────────────────────────────────────

    def _heuristic_recs(
        self,
        profile: Any,
        issue_id: str,
    ) -> List[Recommendation]:
        """Generate basic recommendations when LLM fails."""
        evidence: List[EvidenceObject] = []
        if isinstance(profile, IssueProfile):
            evidence = profile.supporting_evidence
        elif isinstance(profile, dict):
            evidence = []

        recs: List[Recommendation] = []
        top_ev = sorted(evidence, key=lambda e: str(e.severity))[:3]
        for ev in top_ev or [EvidenceObject(
            source_tool="heuristic",
            severity=Priority.P3,
            description="General remediation required"
        )]:
            priority = ev.severity
            regulation = ev.regulation_ref or self._infer_regulation(profile, 0)
            recs.append(
                Recommendation(
                    issue_profile_id=issue_id,
                    action=f"Investigate and fix: {ev.description[:200]}",
                    priority=priority,
                    effort_estimate=_EFFORT_MAP.get(priority, "1 sprint"),
                    defect_id=self._next_defect_id(),
                    regulation_ref=regulation,
                    rationale=(
                        f"Evidence from {ev.source_tool} indicates {ev.severity.value} "
                        f"severity issue requiring remediation per {regulation}."
                    ),
                )
            )
        return recs

    # ── invoke() ─────────────────────────────────────────────────────────

    async def invoke(self, context: IncidentContext) -> AgentResult:
        """
        Generate Recommendation objects for each IssueProfile.

        Reads ``context.metadata["issue_profiles"]``.
        Returns AgentResult with:
          - recommendations : list[Recommendation]
          - evidence        : collected from all profiles
          - next_phase      : "review"
        """
        profiles_raw: List[Any] = context.metadata.get("issue_profiles", [])
        if not profiles_raw:
            logger.warning("[RecommendationAgent] No issue_profiles in context.metadata")
            return AgentResult(
                agent_name="Recommendation Agent",
                next_phase="review",
                metadata={"warning": "no_profiles"},
            )

        all_recs: List[Recommendation] = []
        all_evidence: List[EvidenceObject] = []
        user_msg = self._build_user_message(context)

        for i, profile in enumerate(profiles_raw):
            if isinstance(profile, IssueProfile):
                issue_id = profile.id
                all_evidence.extend(profile.supporting_evidence)
                regulation = self._infer_regulation(profile, i)
            elif isinstance(profile, dict):
                issue_id = profile.get("id") or str(uuid4())
                regulation = self._infer_regulation(profile, i)
            else:
                logger.warning("[RecommendationAgent] Unrecognised profile type: %s", type(profile))
                continue

            try:
                raw_llm = await self._call_llm(self._build_system_prompt(), user_msg)
                recs = self._parse_llm_recs(raw_llm, issue_id)
            except Exception as exc:
                logger.warning("[RecommendationAgent] LLM call failed: %s — using heuristics", exc)
                recs = []

            if not recs:
                recs = self._heuristic_recs(profile, issue_id)

            # Enforce regulation_ref and defect_id on every rec
            for rec in recs:
                if not rec.regulation_ref:
                    rec.regulation_ref = regulation
                if not rec.defect_id:
                    rec.defect_id = self._next_defect_id()

            all_recs.extend(recs)

        # Sort P1 first
        all_recs.sort(key=lambda r: r.priority.value)

        logger.info(
            "[RecommendationAgent] incident=%s profiles=%d recs=%d",
            context.incident_id,
            len(profiles_raw),
            len(all_recs),
        )

        return AgentResult(
            agent_name="Recommendation Agent",
            evidence=all_evidence,
            recommendations=all_recs,  # type: ignore[arg-type]
            next_phase="review",
            metadata={
                "total_recommendations": len(all_recs),
                "p1_count": sum(1 for r in all_recs if r.priority == Priority.P1),
                "p2_count": sum(1 for r in all_recs if r.priority == Priority.P2),
            },
        )


__all__ = ["RecommendationAgent"]

