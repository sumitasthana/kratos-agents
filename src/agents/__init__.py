"""
Spark Fingerprint Analysis Agents.

Multi-agent system for intelligent analysis of Spark execution fingerprints.
Each agent specializes in a specific analysis domain.

Agents:
- QueryUnderstandingAgent: Explains physical/logical plans in natural language
- (Future) RootCauseAgent: Identifies root causes of anomalies
- (Future) OptimizationAgent: Suggests performance optimizations
- (Future) RegressionAgent: Explains performance regressions
- (Future) OrchestratorAgent: Routes requests to appropriate agents
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
