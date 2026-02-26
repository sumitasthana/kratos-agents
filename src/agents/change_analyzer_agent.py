from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base import BaseAgent, AgentType
from agents import AgentResponse, LLMConfig


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
        return (
            "You are a code-change risk analyst. Given a git commit fingerprint, "
            "identify churn hotspots, contributor silo patterns, and files at "
            "elevated regression risk. Report each issue with a severity level "
            "(CRITICAL / HIGH / MEDIUM / LOW) and a concise explanation."
        )

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        super().__init__(llm_config or LLMConfig())

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
