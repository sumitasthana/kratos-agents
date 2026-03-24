"""
tools/base_tool.py
Abstract base for all Kratos analysis tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from core.models import EvidenceObject, IncidentContext


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
                "parameters": {
                    "type": "object",
                    "properties": {
                        "incident_id": {
                            "type":        "string",
                            "description": "Incident identifier to analyse",
                        },
                    },
                    "required": ["incident_id"],
                },
            },
        }

    def register(self, registry: Dict[str, Any]) -> None:
        """Register this tool in a name-keyed tool registry."""
        registry[self.name] = self
