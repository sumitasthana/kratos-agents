"""
agents/orchestrator/phase_config.py
Convenience re-export so callers can do:

    from agents.orchestrator.phase_config import PhaseConfig, PHASE_REGISTRY

instead of importing from workflow.phase_registry directly.
"""
from workflow.phase_registry import PhaseConfig, PHASE_REGISTRY  # noqa: F401
from workflow.pipeline_phases import Phase, PhaseResult, RCAReport  # noqa: F401

__all__ = ["PhaseConfig", "PHASE_REGISTRY", "Phase", "PhaseResult", "RCAReport"]

