"""
tools/base_tool.py
Abstract base for all Kratos analysis tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4
from typing import TYPE_CHECKING, Any, Dict, List

from core.models import EvidenceObject, IncidentContext, Priority

if TYPE_CHECKING:
    pass  # no circular imports needed here


class BaseTool(ABC):
    """
    Abstract base for every Kratos analysis tool.

    Tools receive an IncidentContext (carrying fingerprints, failed controls,
    and ontology snapshots) and return a list of EvidenceObjects that feed
    the shared evidence chain.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used in the tool registry."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description used in LLM function-calling schema."""
        ...

    @abstractmethod
    async def run(self, context: IncidentContext) -> list[EvidenceObject]:
        """
        Execute the tool against the given incident context.

        Args:
            context: Shared pipeline context with fingerprints and metadata.

        Returns:
            List of EvidenceObject instances for the evidence chain.
        """
        ...

    def schema(self) -> Dict[str, Any]:
        """Return an OpenAI function-calling schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name":        self.name,
                "description": self.description,
                "parameters":  self._parameters_schema(),
            },
        }

    @abstractmethod
    def _parameters_schema(self) -> dict:
        """
        Return the JSON Schema ``parameters`` object for this tool.

        Must follow the OpenAI function-calling format::

            {
                "type": "object",
                "properties": { ... },
                "required": [ ... ],
            }
        """
        ...

    def register(self, registry: Dict[str, Any]) -> None:
        """Register this tool in a name-keyed tool registry."""
        registry[self.name] = self


# ---------------------------------------------------------------------------
# Shared helper: AgentResponse → list[EvidenceObject]
# ---------------------------------------------------------------------------

def agent_response_to_evidence(
    response: Any,
    tool_name: str,
    defect_id: str | None = None,
    regulation_ref: str | None = None,
) -> List[EvidenceObject]:
    """
    Convert a legacy ``AgentResponse`` into a list of ``EvidenceObject`` items
    for the shared Kratos evidence chain.

    Args:
        response:      AgentResponse (or any object with .summary / .confidence /
                       .key_findings / .metadata attributes).
        tool_name:     Name of the wrapping BaseTool (set as source_tool).
        defect_id:     Optional structured defect identifier forwarded as-is.
        regulation_ref: Optional regulation reference forwarded as-is.

    Returns:
        A single-element list containing the mapped EvidenceObject.
        Returns an empty list when ``response.success`` is False.
    """
    if not getattr(response, "success", True):
        return []

    conf: float = float(getattr(response, "confidence", 0.5) or 0.5)
    if conf >= 0.9:
        sev = Priority.P1
    elif conf >= 0.75:
        sev = Priority.P2
    elif conf >= 0.6:
        sev = Priority.P3
    else:
        sev = Priority.P4

    summary: str = str(getattr(response, "summary", "") or "Agent analysis complete")
    findings: list = list(getattr(response, "key_findings", None) or [])

    description = summary
    if findings:
        preview = "; ".join(str(f) for f in findings[:3])
        description = f"{summary} | {preview}"

    raw: dict = {
        "agent_type": str(getattr(response, "agent_type", "") or ""),
        "confidence": conf,
        "key_findings": findings[:10],
    }
    meta = getattr(response, "metadata", None)
    if isinstance(meta, dict):
        raw["metadata"] = dict(list(meta.items())[:20])

    return [
        EvidenceObject(
            id=f"{tool_name}_{uuid4().hex[:8]}",
            source_tool=tool_name,
            severity=sev,
            description=description[:500],
            defect_id=defect_id,
            regulation_ref=regulation_ref,
            raw_payload=raw,
        )
    ]

