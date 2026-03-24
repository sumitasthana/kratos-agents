"""
agents/routing/agent.py
RoutingAgent — classifies failure patterns and selects which tools to invoke.

Layer 0 in the Kratos pipeline. Receives IncidentContext from the orchestrator,
uses an LLM to match signals against HypothesisPatternLibrary patterns, and
returns an AgentResult that tells the orchestrator which tools to run next.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentResult, AgentType, FingerprintDomain
from core.models import EvidenceObject, IncidentContext, LLMClient, Priority

if True:  # avoid circular import at module load
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hypothesis Pattern Library
# ---------------------------------------------------------------------------

HYPOTHESIS_PATTERN_LIBRARY: List[Dict[str, Any]] = [
    {
        "pattern_id": "HPL-001",
        "name": "Spark Execution Failure",
        "signals": ["spark", "oom", "executor", "shuffle", "stage failed", "task"],
        "tools": ["SparkLogTool"],
        "description": "Spark job failure due to memory pressure, data skew, or executor OOM.",
    },
    {
        "pattern_id": "HPL-002",
        "name": "Data Quality Degradation",
        "signals": ["null", "schema", "drift", "row count", "data quality", "missing"],
        "tools": ["DataQualityTool"],
        "description": "Dataset null-rate spikes, schema changes, or distribution shifts.",
    },
    {
        "pattern_id": "HPL-003",
        "name": "Code Change Regression",
        "signals": ["commit", "churn", "contributor", "git", "regression", "deploy"],
        "tools": ["DDLDiffTool", "GitDiffTool"],
        "description": "High-churn commits or single-contributor code changes correlating with failures.",
    },
    {
        "pattern_id": "HPL-004",
        "name": "Airflow Pipeline Degradation",
        "signals": ["airflow", "dag", "task", "retry", "sla", "upstream"],
        "tools": ["AirflowLogTool"],
        "description": "Airflow task failures, cascading upstream dependency failures, or SLA misses.",
    },
    {
        "pattern_id": "HPL-005",
        "name": "Full-Stack Correlation",
        "signals": ["correlation", "multi", "combined", "full"],
        "tools": ["SparkLogTool", "DataQualityTool", "DDLDiffTool", "GitDiffTool"],
        "description": "Multiple failure signals across Spark, data, and code layers.",
    },
]

# Default pattern when no signals match
_DEFAULT_TOOLS = ["SparkLogTool", "DataQualityTool"]


# ---------------------------------------------------------------------------
# RoutingAgent
# ---------------------------------------------------------------------------

class RoutingAgent(BaseAgent):
    """
    Classifies the failure pattern and selects tools to invoke.

    Reads ``context.metadata`` for available signal keys, matches them against
    :data:`HYPOTHESIS_PATTERN_LIBRARY` via an LLM, and returns an
    ``AgentResult`` with ``metadata["selected_tools"]`` and
    ``next_phase="triangulation"``.
    """

    def __init__(self, llm: LLMClient, tools: list | None = None) -> None:
        super().__init__(name="RoutingAgent", llm=llm, tools=tools or [])

    # ── Abstract property implementations ────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ROUTING

    @property
    def agent_name(self) -> str:
        return "Routing Agent"

    @property
    def description(self) -> str:
        return (
            "Classifies failure patterns and selects which analysis tools to "
            "invoke for the current incident."
        )

    @property
    def fingerprint_domain(self) -> FingerprintDomain:
        return FingerprintDomain.GENERIC

    @property
    def system_prompt(self) -> str:
        return self._build_system_prompt()

    # ── Prompt helpers ────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).resolve().parents[2]
            / "resources" / "prompts" / "routing.txt"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return (
            "You are the Kratos Routing Agent.\n"
            "Your role is to classify a pipeline failure against the Hypothesis "
            "Pattern Library and select the minimum set of analysis tools needed "
            "to diagnose the root cause.\n\n"
            "Available tools:\n"
            "- SparkLogTool: Spark execution failures, OOM, data skew\n"
            "- AirflowLogTool: Airflow task retries, SLA misses, upstream cascades\n"
            "- GitDiffTool: Data-flow pattern changes from git diffs\n"
            "- DataQualityTool: Null spikes, schema drift, distribution shifts\n"
            "- DDLDiffTool: Commit churn, contributor silos, regression risk\n\n"
            "Respond ONLY with valid JSON matching:\n"
            '{{ "pattern_id": "HPL-XXX", "pattern_name": "...", '
            '"selected_tools": ["ToolA", "ToolB"], '
            '"rationale": "...", "confidence": 0.85 }}'
        )

    def _build_user_message(self, context: IncidentContext) -> str:
        signals = list(context.metadata.keys())
        failed  = context.failed_controls
        snippet = json.dumps(
            {k: v for k, v in context.metadata.items() if not isinstance(v, list) or len(v) < 5},
            default=str,
        )[:2000]
        library_summary = json.dumps(
            [{"id": p["pattern_id"], "name": p["name"], "signals": p["signals"]}
             for p in HYPOTHESIS_PATTERN_LIBRARY],
            indent=2,
        )
        return (
            f"Incident ID : {context.incident_id}\n"
            f"Stage       : {context.pipeline_stage}\n"
            f"Failed controls: {', '.join(failed) or 'none'}\n"
            f"Available metadata keys: {', '.join(signals)}\n"
            f"Metadata preview:\n{snippet}\n\n"
            f"Hypothesis Pattern Library:\n{library_summary}\n\n"
            "Select the best matching pattern and the minimum tool set."
        )

    # ── Tool-call handling ────────────────────────────────────────────────

    def _heuristic_tools(self, context: IncidentContext) -> List[str]:
        """Fast heuristic fallback: match metadata keys to patterns."""
        meta_keys = " ".join(context.metadata.keys()).lower()
        selected = set()
        for p in HYPOTHESIS_PATTERN_LIBRARY:
            if any(sig in meta_keys for sig in p["signals"]):
                selected.update(p["tools"])
        return list(selected) or _DEFAULT_TOOLS

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        """Extract JSON from LLM response (handles markdown fences)."""
        raw = raw.strip()
        if "```" in raw:
            raw = raw.split("```")[-2].lstrip("json").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # ── invoke() ─────────────────────────────────────────────────────────

    async def invoke(self, context: IncidentContext) -> AgentResult:
        """
        Classify the incident and select tools.

        Returns AgentResult with:
          - metadata["selected_tools"]  : list of tool names
          - metadata["pattern_id"]       : matched HPL pattern
          - metadata["rationale"]        : routing reason
          - next_phase = "triangulation"
        """
        user_msg = self._build_user_message(context)
        try:
            raw = await self._call_llm(self._build_system_prompt(), user_msg)
            parsed = self._parse_llm_response(raw)
        except Exception as exc:
            logger.warning("[RoutingAgent] LLM call failed: %s — using heuristics", exc)
            parsed = {}

        selected_tools: List[str] = (
            parsed.get("selected_tools")
            or self._heuristic_tools(context)
        )
        pattern_id   = parsed.get("pattern_id", "HPL-000")
        pattern_name = parsed.get("pattern_name", "Unknown Pattern")
        rationale    = parsed.get("rationale", "Heuristic tool selection")
        confidence   = float(parsed.get("confidence", 0.7))

        evidence = EvidenceObject(
            id=f"RoutingAgent_{context.incident_id[:8]}",
            source_tool="RoutingAgent",
            severity=Priority.P4,
            description=(
                f"Pattern matched: {pattern_name} ({pattern_id}). "
                f"Tools selected: {', '.join(selected_tools)}."
            ),
            raw_payload={
                "pattern_id":     pattern_id,
                "selected_tools": selected_tools,
                "rationale":      rationale,
                "confidence":     confidence,
            },
        )
        await self.emit_evidence(evidence)

        logger.info(
            "[RoutingAgent] incident=%s pattern=%s tools=%s",
            context.incident_id,
            pattern_id,
            selected_tools,
        )

        return AgentResult(
            agent_name="Routing Agent",
            evidence=[evidence],
            next_phase="triangulation",
            metadata={
                "selected_tools": selected_tools,
                "pattern_id":     pattern_id,
                "pattern_name":   pattern_name,
                "rationale":      rationale,
                "confidence":     confidence,
            },
        )


__all__ = ["RoutingAgent", "HYPOTHESIS_PATTERN_LIBRARY"]

