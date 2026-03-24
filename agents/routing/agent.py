"""
agents/routing/agent.py
Routing agent — decides which analyzers to invoke given job metadata.

Re-exported from agents.orchestrator.agent to avoid duplication.
The class definition lives in agents/orchestrator/agent.py alongside
KratosOrchestrator so that all inter-agent references resolve without
circular imports.
"""

from agents.orchestrator.agent import RoutingAgent  # noqa: F401

__all__ = ["RoutingAgent"]
