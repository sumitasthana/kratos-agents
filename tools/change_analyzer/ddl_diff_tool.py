# Moved from: src\agents\change_analyzer_agent.py
# Import updates applied by migrate step.
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentType
from core.base_agent import AgentResponse, AgentResult
from core.models import IncidentContext
from core.llm import LLMConfig
from core.instructions import load_prompt_content


class ChangeAnalyzerAgent(BaseAgent):
    """
    Analyzes git churn and contributor patterns for RCA.

    Expected fingerprint_data shape (flexible, no hard schema):

        {
          "repo_name": "fdic-controls",
          "window_days": 30,
          "commits": [
            {
              "hash": "...",
              "author": "alice",
              "timestamp": "2026-02-20T10:15:00Z",
              "files": [
                {"path": "etl/pricing.py", "added": 120, "deleted": 10},
                ...
              ]
            },
            ...
          ],
          "reference": {  # optional older window for comparison
            "window_days": 30,
            "commits": [...]
          }
        }
    """

    agent_type: AgentType = AgentType.CHANGE_ANALYZER
    agent_name: str = "Change Analyzer"

    @property
    def description(self) -> str:
        return (
            "Analyzes git commit history to detect churn spikes, contributor silos, "
            "and regression risk from recent code changes."
        )

    @property
    def system_prompt(self) -> str:
        # Loaded from prompts/change_analyzer.yaml
        return load_prompt_content("change_analyzer")

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        # Heuristic agent — no LLM client needed.
        # Bypasses BaseAgent.__init__(name, llm, tools) which requires a real LLM.
        self.llm_config = llm_config or LLMConfig()
        self._name = type(self).agent_name  # uses class-level attribute
        self._llm_client = None
        self._tools = []

    async def invoke(self, context: IncidentContext) -> AgentResult:
        """Heuristic invoke — delegates to :meth:`analyze`."""
        fingerprint_data = (
            context.metadata.get("fingerprint_data")
            or context.metadata.get("change_fingerprint")
            or context.metadata
        )
        response = self.analyze(fingerprint_data=fingerprint_data)
        return AgentResult(
            agent_name=self.agent_name,
            evidence=[],
            recommendations=list(response.key_findings or []),
        )

    def analyze(self, fingerprint_data: Dict[str, Any], **_: Any) -> AgentResponse:
        try:
            parsed = self._parse_fingerprint(fingerprint_data)
        except Exception as exc:
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=False,
                summary=f"Failed to parse change fingerprint: {exc}",
                explanation=str(exc),
                key_findings=[],
                confidence=0.3,
                metadata={"error": str(exc)},
            )

        repo_name = parsed["repo_name"]
        commits = parsed["commits"]
        ref = parsed["reference"]

        findings: List[str] = []
        sections: List[str] = []

        # Basic churn stats
        churn_lines, churn_findings = self._analyze_churn(commits, ref)
        sections.append("## Churn\n\n" + "\n".join(churn_lines))

        # Contributor patterns
        contrib_lines, contrib_findings = self._analyze_contributors(commits)
        sections.append("\n\n## Contributors\n\n" + "\n".join(contrib_lines))

        findings.extend(churn_findings)
        findings.extend(contrib_findings)

        severity, label, confidence = self._score(findings)

        summary = f"Change analysis for repo '{repo_name}': {label}."
        explanation = "\n".join(sections).strip()

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary,
            explanation=explanation,
            key_findings=findings,
            confidence=confidence,
            metadata={
                "repo_name": repo_name,
                "severity": severity,
                "label": label,
            },
        )

    # ---- helpers (all simple heuristics) ---------------------------------

    def _parse_fingerprint(self, data: Dict[str, Any]) -> Dict[str, Any]:
        repo_name = str(data.get("repo_name") or "repo")
        commits = data.get("commits") or []
        reference = data.get("reference") or None
        return {
            "repo_name": repo_name,
            "commits": commits,
            "reference": reference,
        }

    def _analyze_churn(
        self,
        commits: List[Dict[str, Any]],
        reference: Optional[Dict[str, Any]],
    ):
        lines: List[str] = []
        findings: List[str] = []

        total_commits = len(commits)
        total_loc = 0
        for c in commits:
            for f in c.get("files", []):
                total_loc += int(f.get("added", 0)) + int(f.get("deleted", 0))

        lines.append(f"- Commits in window: {total_commits}")
        lines.append(f"- Lines changed (added+deleted): {total_loc}")

        # Simple churn spike if reference present
        if reference:
            ref_commits = reference.get("commits") or []
            ref_loc = 0
            for c in ref_commits:
                for f in c.get("files", []):
                    ref_loc += int(f.get("added", 0)) + int(f.get("deleted", 0))

            lines.append(f"- Reference commits: {len(ref_commits)}, lines changed: {ref_loc}")

            if ref_loc > 0:
                ratio = total_loc / ref_loc
                if ratio >= 2.0:
                    msg = (
                        f"Churn spike: lines changed increased by {ratio:.1f}x "
                        f"vs reference window ({ref_loc} → {total_loc})."
                    )
                    lines.append(f"- {msg}")
                    findings.append(msg)

        return lines, findings

    def _analyze_contributors(self, commits: List[Dict[str, Any]]):
        lines: List[str] = []
        findings: List[str] = []

        author_counts: Dict[str, int] = {}
        for c in commits:
            author = str(c.get("author") or "unknown")
            author_counts[author] = author_counts.get(author, 0) + 1

        if not author_counts:
            lines.append("- No commits in window.")
            return lines, findings

        total = sum(author_counts.values())
        sorted_authors = sorted(author_counts.items(), key=lambda kv: kv[1], reverse=True)
        top_author, top_count = sorted_authors[0]
        frac = top_count / total

        lines.append(
            "- Top contributors: "
            + ", ".join(f"{a}={cnt}" for a, cnt in sorted_authors[:5])
        )

        if frac >= 0.8 and total >= 5:
            msg = (
                f"Contributor silo risk: author '{top_author}' owns "
                f"{frac:.0%} of commits in this window."
            )
            lines.append(f"- {msg}")
            findings.append(msg)

        return lines, findings

    def _score(self, findings: List[str]):
        if not findings:
            return ("low", "Stable change patterns", 0.9)
        if len(findings) <= 2:
            return ("medium", "Elevated change risk (churn or silo)", 0.8)
        return ("high", "Significant change risk", 0.7)


# ── BaseTool adapter ─────────────────────────────────────────────────────────

import logging  # noqa: E402
from tools.base_tool import BaseTool, agent_response_to_evidence  # noqa: E402
from core.models import IncidentContext, EvidenceObject  # noqa: E402

_logger = logging.getLogger(__name__)


class DDLDiffTool(BaseTool):
    """
    BaseTool-conforming wrapper around ``ChangeAnalyzerAgent``.

    Reads ``context.metadata["change_fingerprint"]`` (a dict with ``repo_name``,
    ``commits`` list, and optional ``reference`` window) and returns
    EvidenceObjects describing churn spikes and contributor silos.
    """

    def __init__(self) -> None:
        self._agent = ChangeAnalyzerAgent()

    @property
    def name(self) -> str:
        return "DDLDiffTool"

    @property
    def description(self) -> str:
        return (
            "Analyzes git commit history to detect churn spikes, contributor silos, "
            "and regression risk from recent code changes."
        )

    def _parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Unique incident identifier",
                },
                "change_fingerprint": {
                    "type": "object",
                    "description": (
                        "Change fingerprint: repo_name, commits list, churn hotspots, "
                        "contributor concentration, and reference time window"
                    ),
                },
            },
            "required": ["incident_id"],
        }

    async def run(self, context: IncidentContext) -> list[EvidenceObject]:
        change_data = (
            context.metadata.get("change_fingerprint")
            or context.metadata.get("fingerprint")
            or {}
        )
        if not isinstance(change_data, dict):
            _logger.warning("%s: change_fingerprint is not a dict, returning empty", self.name)
            return []
        try:
            response = self._agent.analyze(fingerprint_data=change_data)
            return agent_response_to_evidence(
                response,
                tool_name=self.name,
                regulation_ref=context.metadata.get("regulation_ref"),
            )
        except Exception as exc:
            _logger.warning("%s.run failed: %s", self.name, exc, exc_info=True)
            return []

