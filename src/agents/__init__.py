"""
Spark Fingerprint Analysis Agents.

Multi-agent system for intelligent analysis of Spark execution fingerprints.
Each agent specializes in a specific analysis domain.

Current agents:
- QueryUnderstandingAgent: Explains physical/logical plans in natural language
- RootCauseAgent: Identifies likely root causes of anomalies
- GitDiffDataFlowAgent: Analyzes git diffs and dataflow impact

Planned agents (to be added in separate modules):
- OptimizationAgent: Suggests performance optimizations
- RegressionAgent: Explains performance regressions
- OrchestratorAgent: Routes requests to appropriate agents
"""

from .base import BaseAgent, AgentResponse, LLMConfig, AgentType
from .git_diff_dataflow import GitDiffDataFlowAgent
from .query_understanding import QueryUnderstandingAgent
from .root_cause import RootCauseAgent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "LLMConfig",
    "AgentType",
    "GitDiffDataFlowAgent",
    "QueryUnderstandingAgent",
    "RootCauseAgent",
]
