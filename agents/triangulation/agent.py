"""
agents/triangulation/agent.py
TriangulationAgent — cross-correlates EvidenceObjects into IssueProfiles.

Layer 2 in the Kratos pipeline. Receives an IncidentContext enriched with
evidence lists from multiple tools, aligns signals by timestamp, detects
causal chains and contradictions, and produces IssueProfile(s).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.base_agent import BaseAgent, AgentResult, AgentType, FingerprintDomain
from core.models import (
    EvidenceObject,
    IncidentContext,
    IssueProfile,
    LLMClient,
    Priority,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority → numeric weight for correlation scoring
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHT: Dict[str, float] = {
    Priority.P1.value: 1.0,
    Priority.P2.value: 0.75,
    Priority.P3.value: 0.5,
    Priority.P4.value: 0.25,
}


class TriangulationAgent(BaseAgent):
    """
    Cross-correlates evidence from multiple tools into IssueProfile(s).

    Algorithm:
      1. Group evidence by source tool.
      2. Align evidence by timestamp (nearest-match within WINDOW_SECONDS).
      3. Score pairwise correlations by severity weight and temporal proximity.
      4. Call LLM to synthesise findings into a root-cause hypothesis.
      5. Return one IssueProfile per distinct causal cluster.

    ``context.metadata["evidence"]`` must be a list of serialised EvidenceObject
    dicts.  Missing / malformed evidence returns an empty AgentResult.
    """

    #: Two evidence items are considered “temporally aligned” if their
    #: timestamps are within this many seconds of each other.
    WINDOW_SECONDS: float = 300.0

    def __init__(self, llm: LLMClient, tools: list | None = None) -> None:
        super().__init__(name="TriangulationAgent", llm=llm, tools=tools or [])

    # ── Abstract property implementations ────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.TRIANGULATION

    @property
    def agent_name(self) -> str:
        return "Triangulation Agent"

    @property
    def description(self) -> str:
        return (
            "Cross-correlates evidence from multiple analysis tools to produce "
            "triangulated IssueProfiles with confidence scores."
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
            / "resources" / "prompts" / "triangulation.txt"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are the Kratos Triangulation Agent.\n"
            "Your role is to cross-correlate evidence from multiple analysis "
            "tools and synthesise a single root-cause hypothesis.\n\n"
            "Rules:\n"
            "1. Identify the primary causal chain (which event triggered which).\n"
            "2. Flag contradictions where two pieces of evidence disagree.\n"
            "3. Assign a confidence score (0.0–1.0) based on evidence quality.\n"
            "4. If evidence is insufficient, say so explicitly.\n\n"
            "Respond ONLY with valid JSON matching:\n"
            '{{ "root_cause_hypothesis": "...", "confidence": 0.85, '
            '"causal_chain": ["event A caused B", ...], '
            '"contradictions": ["..."], '
            '"affected_regulation": "12 CFR Part 370" }}'
        )

    def _build_user_message(self, context: IncidentContext) -> str:
        evidence_list: List[Dict] = context.metadata.get("evidence", [])
        summary_lines = [
            f"- [{e.get('source_tool','?')}] {e.get('severity','?')}: {e.get('description','')[:120]}"
            for e in evidence_list
        ]
        return (
            f"Incident ID : {context.incident_id}\n"
            f"Stage       : {context.pipeline_stage}\n"
            f"Failed controls: {', '.join(context.failed_controls) or 'none'}\n\n"
            f"Evidence ({len(evidence_list)} items):\n"
            + "\n".join(summary_lines or ["  (no evidence collected)"])
            + "\n\nSynthesise a root-cause hypothesis for this incident."
        )

    # ── Cross-correlation logic ───────────────────────────────────────────

    @staticmethod
    def _parse_ts(ev: Dict[str, Any]) -> Optional[datetime]:
        """Parse timestamp from an evidence dict."""
        ts = ev.get("timestamp")
        if not ts:
            return None
        try:
            if isinstance(ts, datetime):
                return ts
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    def _align_by_timestamp(
        self,
        evidence: List[Dict[str, Any]],
    ) -> List[Tuple[Dict, Dict]]:
        """
        Return pairs of evidence items whose timestamps are within
        :attr:`WINDOW_SECONDS` of each other (different source tools only).
        """
        timed = [(e, self._parse_ts(e)) for e in evidence if self._parse_ts(e)]
        timed.sort(key=lambda x: x[1])  # type: ignore[key-return-value]
        pairs: List[Tuple[Dict, Dict]] = []
        for i, (ea, ta) in enumerate(timed):
            for eb, tb in timed[i + 1:]:
                if ea.get("source_tool") == eb.get("source_tool"):
                    continue
                if abs((tb - ta).total_seconds()) <= self.WINDOW_SECONDS:  # type: ignore
                    pairs.append((ea, eb))
        return pairs

    def _score_alignment(self, aligned: List[Tuple[Dict, Dict]]) -> float:
        """
        Score cross-tool alignment: higher weight for more severe pairs.
        Returns 0.0 – 1.0.
        """
        if not aligned:
            return 0.5
        total = sum(
            _SEVERITY_WEIGHT.get(a.get("severity", "P4"), 0.25)
            + _SEVERITY_WEIGHT.get(b.get("severity", "P4"), 0.25)
            for a, b in aligned
        )
        return min(total / (len(aligned) * 2), 1.0)

    # ── invoke() ─────────────────────────────────────────────────────────

    async def invoke(self, context: IncidentContext) -> AgentResult:
        """
        Cross-correlate evidence and produce IssueProfile(s).

        Reads ``context.metadata["evidence"]`` (list of EvidenceObject dicts).
        Returns AgentResult with:
          - issue_profiles: [IssueProfile, ...]
          - evidence:       pass-through evidence
          - next_phase:     "recommendation"
        """
        raw_evidence: List[Dict] = context.metadata.get("evidence", [])
        if not raw_evidence:
            logger.warning("[TriangulationAgent] No evidence in context.metadata — returning empty")
            return AgentResult(
                agent_name="Triangulation Agent",
                next_phase="recommendation",
                metadata={"warning": "no_evidence"},
            )

        # Rebuild EvidenceObject list from dicts (tolerant parsing)
        evidence_objs: List[EvidenceObject] = []
        for e in raw_evidence:
            try:
                if isinstance(e, EvidenceObject):
                    evidence_objs.append(e)
                else:
                    evidence_objs.append(EvidenceObject(**e))
            except Exception as exc:
                logger.debug("[TriangulationAgent] Skipping malformed evidence: %s", exc)

        # Step 1: temporal alignment
        aligned_pairs = self._align_by_timestamp(raw_evidence)
        alignment_score = self._score_alignment(aligned_pairs)
        logger.info(
            "[TriangulationAgent] %d evidence items, %d aligned pairs, score=%.2f",
            len(evidence_objs), len(aligned_pairs), alignment_score,
        )

        # Step 2: LLM synthesis
        user_msg = self._build_user_message(context)
        try:
            raw_llm = await self._call_llm(self._build_system_prompt(), user_msg)
            llm_parsed: Dict[str, Any] = {}
            raw_stripped = raw_llm.strip()
            if "```" in raw_stripped:
                raw_stripped = raw_stripped.split("```")[-2].lstrip("json").strip()
            try:
                llm_parsed = json.loads(raw_stripped)
            except json.JSONDecodeError:
                logger.debug("[TriangulationAgent] LLM response not JSON, using evidence heuristics")
        except Exception as exc:
            logger.warning("[TriangulationAgent] LLM call failed: %s", exc)
            llm_parsed = {}

        # Step 3: Build IssueProfile
        root_cause = llm_parsed.get(
            "root_cause_hypothesis",
            self._heuristic_hypothesis(evidence_objs),
        )
        llm_conf = float(llm_parsed.get("confidence", 0.0))
        confidence = max(llm_conf, alignment_score, 0.4)
        affected_reg = llm_parsed.get("affected_regulation") or self._infer_regulation(context)

        profile = IssueProfile(
            root_cause_hypothesis=root_cause,
            supporting_evidence=evidence_objs,
            confidence=round(confidence, 3),
            affected_regulation=affected_reg,
        )

        logger.info(
            "[TriangulationAgent] IssueProfile created | confidence=%.2f | regulation=%s",
            confidence, affected_reg,
        )

        return AgentResult(
            agent_name="Triangulation Agent",
            evidence=evidence_objs,
            issue_profiles=[profile],
            next_phase="recommendation",
            metadata={
                "aligned_pairs":   len(aligned_pairs),
                "alignment_score": alignment_score,
                "causal_chain":    llm_parsed.get("causal_chain", []),
                "contradictions":  llm_parsed.get("contradictions", []),
            },
        )

    # ── Heuristic helpers ─────────────────────────────────────────────────

    @staticmethod
    def _heuristic_hypothesis(evidence: List[EvidenceObject]) -> str:
        """Build a hypothesis from the highest-severity evidence items."""
        critical = [e for e in evidence if e.severity == Priority.P1]
        high     = [e for e in evidence if e.severity == Priority.P2]
        candidates = (critical or high or evidence)[:3]
        if not candidates:
            return "Insufficient evidence to determine root cause."
        descs = "; ".join(e.description[:100] for e in candidates)
        return f"Primary signals: {descs}"

    @staticmethod
    def _infer_regulation(context: IncidentContext) -> Optional[str]:
        """Infer regulation from failed controls (CTRL-330-x → 12 CFR Part 330)."""
        for ctrl in context.failed_controls:
            if "330" in ctrl:
                return "12 CFR Part 330"
            if "370" in ctrl:
                return "12 CFR Part 370"
        return None

