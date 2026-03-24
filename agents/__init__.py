"""agents/ — Kratos multi-agent pipeline modules.

Public surface
--------------
AGENT_REGISTRY   : Dict[str, Type[BaseAgent]] — populated by register_all_agents()
register_all_agents() : lazy importer that fills AGENT_REGISTRY without circular imports
"""
from __future__ import annotations

from typing import Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from core.base_agent import BaseAgent

# Registry is populated lazily so that expensive imports happen on first use.
AGENT_REGISTRY: Dict[str, "Type[BaseAgent]"] = {}


def register_all_agents() -> Dict[str, "Type[BaseAgent]"]:
    """
    Import all concrete agent classes and populate :data:`AGENT_REGISTRY`.

    Safe to call multiple times — subsequent calls are idempotent.

    Returns
    -------
    AGENT_REGISTRY
        Mapping of class-name → class, e.g. {"RoutingAgent": RoutingAgent}.
    """
    from agents.routing.agent import RoutingAgent
    from agents.triangulation.agent import TriangulationAgent
    from agents.recommendation.agent import RecommendationAgent
    from agents.reviewer.agent import ReviewerAgent

    for cls in (RoutingAgent, TriangulationAgent, RecommendationAgent, ReviewerAgent):
        AGENT_REGISTRY[cls.__name__] = cls  # type: ignore[assignment]

    return AGENT_REGISTRY


__all__ = ["AGENT_REGISTRY", "register_all_agents"]

