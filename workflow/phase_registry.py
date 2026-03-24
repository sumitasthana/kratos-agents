"""
workflow/phase_registry.py
PhaseConfig dataclass + PHASE_REGISTRY for the 7-phase Kratos pipeline.

Design notes
------------
- ``agent_class`` is populated lazily (inside :func:`_build_registry`) to
  avoid circular imports at module load time.
- Tool names are the exact keys used in ``tools.TOOL_REGISTRY``.
- Callers that need just the Phase enum can import from workflow.pipeline_phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from workflow.pipeline_phases import Phase


# ============================================================================
# PHASE CONFIG
# ============================================================================

@dataclass
class PhaseConfig:
    """
    Per-phase static configuration consumed by KratosOrchestrator.

    Attributes
    ----------
    phase:
        The :class:`~workflow.pipeline_phases.Phase` this config describes.
    agent_class:
        Concrete :class:`~core.base_agent.BaseAgent` subclass to instantiate,
        or *None* for non-agent phases (INTAKE, LOGS_FIRST, INCIDENT_CARD, PERSIST).
    tools:
        Tool names to pass to the agent; keys must match ``TOOL_REGISTRY``.
    max_concurrency:
        Maximum number of simultaneous coroutines (1 = sequential).
    timeout_seconds:
        Hard wall-clock limit enforced via ``asyncio.wait_for``.
    retry_on_failure:
        Whether the orchestrator should retry once on transient failure.
    next_phase:
        The phase to transition to on success, or *None* for terminal phases.
    """
    phase:             Phase
    agent_class:       Optional[Type[Any]]   # Type[BaseAgent] resolved at runtime
    tools:             List[str]             = field(default_factory=list)
    max_concurrency:   int                   = 1
    timeout_seconds:   int                   = 60
    retry_on_failure:  bool                  = False
    next_phase:        Optional[Phase]        = None


# ============================================================================
# PHASE REGISTRY
# ============================================================================

def _build_registry() -> Dict[Phase, PhaseConfig]:
    """
    Build PHASE_REGISTRY with lazy agent imports to prevent circular deps.

    Importing agent classes here (not at module top-level) means that
    ``workflow.phase_registry`` can be imported without pulling in the full
    agent tree, while still giving callers real class objects at runtime.
    """
    # Deferred imports — no circular risk because routing/triangulation/
    # recommendation agents do not import from workflow.phase_registry.
    from agents.routing.agent        import RoutingAgent
    from agents.triangulation.agent  import TriangulationAgent
    from agents.recommendation.agent import RecommendationAgent

    return {
        Phase.INTAKE: PhaseConfig(
            phase              = Phase.INTAKE,
            agent_class        = None,
            tools              = [],
            max_concurrency    = 1,
            timeout_seconds    = 30,
            retry_on_failure   = False,
            next_phase         = Phase.LOGS_FIRST,
        ),
        Phase.LOGS_FIRST: PhaseConfig(
            phase              = Phase.LOGS_FIRST,
            agent_class        = None,  # tools run directly
            tools              = ["SparkLogTool", "AirflowLogTool"],
            max_concurrency    = 2,
            timeout_seconds    = 120,
            retry_on_failure   = True,
            next_phase         = Phase.ROUTE,
        ),
        Phase.ROUTE: PhaseConfig(
            phase              = Phase.ROUTE,
            agent_class        = RoutingAgent,
            tools              = [
                "SparkLogTool", "AirflowLogTool",
                "GitDiffTool",  "DataQualityTool", "DDLDiffTool",
            ],
            max_concurrency    = 1,
            timeout_seconds    = 60,
            retry_on_failure   = True,
            next_phase         = Phase.BACKTRACK,
        ),
        Phase.BACKTRACK: PhaseConfig(
            phase              = Phase.BACKTRACK,
            agent_class        = TriangulationAgent,
            tools              = [],  # uses routing-selected tools
            max_concurrency    = 7,   # parallel tool invocations
            timeout_seconds    = 180,
            retry_on_failure   = True,
            next_phase         = Phase.INCIDENT_CARD,
        ),
        Phase.INCIDENT_CARD: PhaseConfig(
            phase              = Phase.INCIDENT_CARD,
            agent_class        = None,  # LLM call inline
            tools              = [],
            max_concurrency    = 1,
            timeout_seconds    = 60,
            retry_on_failure   = False,
            next_phase         = Phase.RECOMMEND,
        ),
        Phase.RECOMMEND: PhaseConfig(
            phase              = Phase.RECOMMEND,
            agent_class        = RecommendationAgent,
            tools              = [],
            max_concurrency    = 1,
            timeout_seconds    = 90,
            retry_on_failure   = True,
            next_phase         = Phase.PERSIST,
        ),
        Phase.PERSIST: PhaseConfig(
            phase              = Phase.PERSIST,
            agent_class        = None,
            tools              = [],
            max_concurrency    = 1,
            timeout_seconds    = 30,
            retry_on_failure   = False,
            next_phase         = None,
        ),
    }


PHASE_REGISTRY: Dict[Phase, PhaseConfig] = _build_registry()


__all__ = ["PhaseConfig", "PHASE_REGISTRY"]

