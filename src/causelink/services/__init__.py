"""
causelink/services/__init__.py

Public surface for the causelink.services package.

Phase H — Dashboard-facing RCA output.

Exports:
  dashboard_schema:
    NodeStatus, StopReason, TraversalMode
    NodeEvaluationResult, LineageWalkNode, AgentAnalysisChainEntry
    BacktrackingResult, RcaDashboardSummary

  node_evaluators:
    NodeEvaluatorRegistry, EvidenceScoper

  ontology_backtracking:
    OntologyBacktrackingService
    backtrack_with_early_stop  (module-level convenience function)
"""

from causelink.services.dashboard_schema import (
    AgentAnalysisChainEntry,
    BacktrackingResult,
    LineageWalkNode,
    NodeEvaluationResult,
    NodeStatus,
    RcaDashboardSummary,
    StopReason,
    TraversalMode,
)
from causelink.services.node_evaluators import (
    EvidenceScoper,
    NodeEvaluatorRegistry,
)
from causelink.services.ontology_backtracking import (
    OntologyBacktrackingService,
    backtrack_with_early_stop,
)

__all__ = [
    # Enums
    "NodeStatus",
    "StopReason",
    "TraversalMode",
    # Schema models
    "NodeEvaluationResult",
    "LineageWalkNode",
    "AgentAnalysisChainEntry",
    "BacktrackingResult",
    "RcaDashboardSummary",
    # Evaluators
    "EvidenceScoper",
    "NodeEvaluatorRegistry",
    # Service
    "OntologyBacktrackingService",
    "backtrack_with_early_stop",
]
