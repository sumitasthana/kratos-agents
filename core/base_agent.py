"""
core/base_agent.py
Abstract agent interface for the Kratos multi-agent RCA system.

Extracted from: src/agents/base.py
Split rule: abstract interface only (AgentType, FingerprintDomain, AgentResponse,
            AgentState, BaseAgent).  LLM config and init live in core/llm.py.

All Kratos agents inherit BaseAgent and implement:
    agent_type      @property → AgentType
    agent_name      @property → str
    description     @property → str
    system_prompt   @property → str
    analyze()       async     → AgentResponse
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict, TYPE_CHECKING

from pydantic import BaseModel, Field

from core.llm import LLMConfig, _call_llm_async, _enrich_prompt_with_context
from core.models import EvidenceObject, IncidentContext, LLMClient

if TYPE_CHECKING:
    from tools.base_tool import BaseTool
    from workflow.context_layer import AgentContext

logger = logging.getLogger(__name__)


# ============================================================================
# AGENT TYPE REGISTRY
# ============================================================================

class AgentType(str, Enum):
    """
    All agent types in the Kratos pipeline.

    Layer 0 — Coordination:
        ROUTING             orchestrates which analyzers run

    Layer 1 — Analyzers (run in parallel, each returns AnalysisResult):
        LOG_ANALYZER        Spark execution log RCA
        CODE_ANALYZER       static analysis + FDIC compliance
        DATA_PROFILER       dataset quality + schema drift
        CHANGE_ANALYZER     git commit history + churn
        INFRA_ANALYZER      infrastructure / observability metrics

    Layer 2 — Synthesis:
        TRIANGULATION       cross-agent correlation + lineage map
        RECOMMENDATION      prioritized fixes + ontology update

    Legacy (preserved for backward compatibility):
        QUERY_UNDERSTANDING used internally by SparkOrchestrator
        ROOT_CAUSE          used internally by SparkOrchestrator
        GIT_DIFF_DATAFLOW   reserved
        LINEAGE_EXTRACTION  reserved
        OPTIMIZATION        reserved
        REGRESSION          reserved
        ORCHESTRATOR        reserved
    """
    # ── Layer 0 ───────────────────────────────────────────────────────────
    ROUTING             = "routing"

    # ── Layer 1 ───────────────────────────────────────────────────────────
    LOG_ANALYZER        = "log_analyzer"
    CODE_ANALYZER       = "code_analyzer"
    DATA_PROFILER       = "data_profiler"
    CHANGE_ANALYZER     = "change_analyzer"
    INFRA_ANALYZER      = "infra_analyzer"

    # ── Layer 2 ───────────────────────────────────────────────────────────
    TRIANGULATION       = "triangulation"
    RECOMMENDATION      = "recommendation"

    # ── Legacy (backward-compat) ──────────────────────────────────────────
    QUERY_UNDERSTANDING = "query_understanding"
    ROOT_CAUSE          = "root_cause"
    GIT_DIFF_DATAFLOW   = "git_diff_dataflow"
    LINEAGE_EXTRACTION  = "lineage_extraction"
    OPTIMIZATION        = "optimization"
    REGRESSION          = "regression"
    ORCHESTRATOR        = "orchestrator"


# ============================================================================
# FINGERPRINT DOMAIN ENUM
# ============================================================================

class FingerprintDomain(str, Enum):
    """
    Identifies which fingerprint schema an agent consumes.
    Used by KratosOrchestrator to validate payload routing.
    """
    SPARK    = "spark"     # ExecutionFingerprint   → LogAnalyzerAgent
    CODE     = "code"      # CodeFingerprint        → CodeAnalyzerAgent
    DATA     = "data"      # DataFingerprint        → DataProfilerAgent
    CHANGE   = "change"    # ChangeFingerprint      → ChangeAnalyzerAgent
    INFRA    = "infra"     # Dict[str, Any]         → InfraAnalyzerAgent
    ISSUE    = "issue"     # IssueProfile           → TriangulationAgent / RecommendationAgent
    GENERIC  = "generic"   # raw dict               → RoutingAgent


# ============================================================================
# AGENT RESPONSE  (shared output contract across all agents)
# ============================================================================

class AgentResponse(BaseModel):
    """
    Standardized response from any Kratos agent.

    Key fields used by downstream consumers:
      summary       → executive summary card (dashboard LogStatusCard)
      explanation   → full markdown narrative (dashboard ExecutiveSummary)
      key_findings  → flat list parsed by _group_flat_findings()
      metadata      → domain-specific structured data
                      RootCauseAgent  → {"health_score": {"score": 85, "breakdown": {...}}}
                      CodeAnalyzer    → {"compliance_gap_count": 3, "controls": [...]}
                      DataProfiler    → {"null_spike_columns": [...], "schema_drift": bool}
                      ChangeAnalyzer  → {"hotspot_files": [...], "burst_windows": [...]}
    """

    model_config = {"protected_namespaces": ()}

    agent_type:   AgentType = Field(..., description="Type of agent that produced this response")
    agent_name:   str       = Field(..., description="Human-readable agent name")
    success:      bool      = Field(..., description="Whether analysis completed successfully")

    # ── Main output ───────────────────────────────────────────────────────
    summary:      str       = Field(..., description="Brief summary (1–2 sentences)")
    explanation:  str       = Field(..., description="Detailed natural language explanation")

    # ── Structured findings ───────────────────────────────────────────────
    key_findings: List[str] = Field(
        default_factory=list,
        description=(
            "Bullet-point findings. "
            "Parsed by _group_flat_findings() into AgentFinding cards."
        ),
    )
    confidence:   float     = Field(default=1.0, description="Agent-reported confidence 0.0–1.0")

    # ── Free-form metadata for orchestrator / UI ──────────────────────────
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Domain-specific structured data consumed by downstream agents",
    )

    # ── Timing / cost metadata ────────────────────────────────────────────
    timestamp:           datetime      = Field(default_factory=datetime.now)
    processing_time_ms:  Optional[int] = Field(None)
    model_used:          Optional[str] = Field(None)
    tokens_used:         Optional[int] = Field(None)

    # ── Error handling ────────────────────────────────────────────────────
    error: Optional[str] = Field(None, description="Error message if success=False")

    # ── Orchestration hints ───────────────────────────────────────────────
    suggested_followup_agents: List[AgentType] = Field(
        default_factory=list,
        description="Agents that could provide additional insight",
    )


# ============================================================================
# LANGGRAPH STATE
# ============================================================================

class AgentState(TypedDict):
    """State schema for LangGraph agent workflows."""
    fingerprint_data: Dict[str, Any]
    context:          Dict[str, Any]
    analysis_result:  Optional[str]
    error:            Optional[str]


# ============================================================================
# AGENT RESULT  (new-style output from invoke())
# ============================================================================

class AgentResult(BaseModel):
    """
    Structured output from BaseAgent.invoke().

    Consumed by TriangulationAgent and RecommendationAgent in the RCA pipeline.
    """

    agent_name:      str                  = Field(..., description="Name of the producing agent")
    evidence:        List[EvidenceObject] = Field(
        default_factory=list,
        description="Structured evidence objects produced during analysis",
    )
    recommendations: List[str]            = Field(
        default_factory=list,
        description="Prioritized recommendation strings for remediation",
    )
    next_phase:      Optional[str]        = Field(
        None,
        description="Suggested next pipeline phase, e.g. 'triangulation'",
    )


# ============================================================================
# BASE AGENT  (abstract — all 7 Kratos agents inherit this)
# ============================================================================


class BaseAgent(ABC):
    """
    Abstract base class for all Kratos analysis agents.

    Contract:
      1. Receive an IncidentContext (or legacy fingerprint dict) from the orchestrator
      2. Call LLM via LangChain for reasoning
      3. Return a structured AgentResult (new) or AgentResponse (legacy)

    Subclasses MUST implement:
      agent_type    @property → AgentType
      agent_name    @property → str
      description   @property → str
      system_prompt @property → str
      invoke()      async     → AgentResult   ← new-style entrypoint

    Subclasses MAY override:
      fingerprint_domain  @property → FingerprintDomain  (default: GENERIC)
      plan()                         → List[str]
      emit_evidence()                → persist evidence to the audit trail
      cite()                         → produce a grounded regulatory citation
      analyze()                      → legacy fingerprint-dict entrypoint
    """

    def __init__(
        self,
        name: str,
        llm: LLMClient,
        tools: list[BaseTool],
    ) -> None:
        self._name       = name
        self._llm_client = llm
        self._tools      = tools
        self.llm_config  = LLMConfig()   # backward-compat for _call_llm()

    # ── Abstract properties ────────────────────────────────────────────────

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Return the AgentType enum member for this agent."""
        ...

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return human-readable name (used in dashboard headers)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this agent does."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt injected before every LLM call for this agent."""
        ...

    @abstractmethod
    async def invoke(self, context: IncidentContext) -> AgentResult:
        """
        New-style RCA pipeline entrypoint.

        Args:
            context: Shared IncidentContext carrying incident metadata,
                     failed controls, ontology snapshot, and fingerprints.

        Returns:
            AgentResult with structured evidence and recommendation strings.
        """
        ...

    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional["AgentContext"] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Backward-compatible analysis entrypoint.

        Wraps fingerprint_data in an IncidentContext, delegates to invoke(),
        and translates AgentResult back to AgentResponse for legacy orchestrators.
        """
        inc = IncidentContext(
            incident_id    = str(uuid.uuid4()),
            run_id         = str(uuid.uuid4()),
            pipeline_stage = self.agent_type.value,
            metadata       = {"fingerprint_data": fingerprint_data, **kwargs},
        )
        result = await self.invoke(inc)
        return AgentResponse(
            agent_type   = self.agent_type,
            agent_name   = self.agent_name,
            success      = True,
            summary      = f"{self.agent_name} completed.",
            explanation  = "\n".join(result.recommendations),
            key_findings = result.recommendations,
        )

    # ── Evidence and citation helpers ──────────────────────────────────────

    async def emit_evidence(self, evidence: EvidenceObject) -> None:
        """
        Emit a structured evidence record to the shared graph state.
        Override to persist to the Neo4j audit trail.
        """
        logger.debug(
            "[%s] evidence %s | %s | %s",
            self.agent_name,
            evidence.id,
            evidence.severity.value,
            evidence.description[:120],
        )

    async def cite(self, defect_id: str, regulation: str) -> str:
        """
        Format a grounded citation for a regulatory claim.
        Format: "[<defect_id>] Ref: <regulation>"
        Example: "[DEF-042] Ref: 12 CFR Part 370 §2(c)"
        """
        return f"[{defect_id}] Ref: {regulation}"

    # ── Optional overrides ─────────────────────────────────────────────────

    @property
    def fingerprint_domain(self) -> FingerprintDomain:
        """
        Declares which fingerprint domain this agent consumes.
        Override in subclass to be explicit.
        """
        return FingerprintDomain.GENERIC

    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional["AgentContext"] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Return ordered list of steps this agent will execute."""
        return [
            f"Agent  : {self.agent_name} ({self.agent_type.value})",
            f"Domain : {self.fingerprint_domain.value}",
            "Step 1 : Validate and extract relevant fingerprint layer(s)",
            "Step 2 : Enrich prompt with AgentContext findings (if available)",
            "Step 3 : Call LLM via LangChain chain",
            "Step 4 : Parse structured key_findings from LLM output",
            "Step 5 : Populate metadata dict for downstream consumers",
            "Step 6 : Return AgentResponse",
        ]

    # ── Context enrichment (delegates to core.llm helper) ─────────────────

    def _enrich_prompt_with_context(
        self,
        base_prompt: str,
        context: Optional["AgentContext"],
    ) -> str:
        """Append prior agent findings and focus areas to a prompt."""
        return _enrich_prompt_with_context(base_prompt, context, self.agent_name)

    # ── LLM call (delegates to core.llm) ──────────────────────────────────

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Invoke LLM asynchronously."""
        return await _call_llm_async(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            llm_config=self.llm_config,
            agent_name=self.agent_name,
        )

    # ── Error factory ───────────────────────────────────────────────────────

    def _create_error_response(self, error: str) -> AgentResponse:
        """Return a standardized failure AgentResponse."""
        return AgentResponse(
            agent_type  = self.agent_type,
            agent_name  = self.agent_name,
            success     = False,
            summary     = f"{self.agent_name} analysis failed",
            explanation = f"Error during analysis: {error}",
            error       = error,
        )
