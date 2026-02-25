"""
base.py
Base agent interface for the full Kratos multi-agent system.

Agent coverage:
  Existing (Spark):
    QUERY_UNDERSTANDING, ROOT_CAUSE

  New (Kratos full pipeline):
    ROUTING         — decides which analyzers to invoke
    LOG_ANALYZER    — Spark execution fingerprint RCA (wraps existing ROOT_CAUSE + QUERY_UNDERSTANDING)
    CODE_ANALYZER   — static analysis, FDIC compliance controls
    DATA_PROFILER   — null rates, schema drift, distribution anomalies
    CHANGE_ANALYZER — git commit history, churn, contributor silos
    TRIANGULATION   — cross-agent correlation + lineage map
    RECOMMENDATION  — prioritized fixes + ontology update

All agents inherit BaseAgent and follow the same LangChain/LangGraph pattern.
AgentResponse is the shared output contract across all agents.
"""

import logging
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.agent_coordination import AgentContext

logger = logging.getLogger(__name__)

_DOTENV_LOADED = False


# ============================================================================
# AGENT TYPE REGISTRY
# ============================================================================

class AgentType(str, Enum):
    """
    All agent types in the Kratos pipeline.

    Layer 0 — Coordination:
        ROUTING             orchestrates which analyzers run

    Layer 1 — Analyzers  (run in parallel, each returns AnalysisResult):
        LOG_ANALYZER        Spark execution log RCA
        CODE_ANALYZER       static analysis + FDIC compliance
        DATA_PROFILER       dataset quality + schema drift
        CHANGE_ANALYZER     git commit history + churn
        INFRA_ANALYZER      infrastructure / observability metrics (CPU, mem, network, autoscaling)

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
    Used by KratosOrchestrator to route the correct payload.
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
            "Parsed by _group_flat_findings() into AgentFinding cards. "
            "Shape A: bare section headers + labeled rows. "
            "Shape B: repeated Symptom/Root Cause/Impact runs."
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
# LLM CONFIGURATION
# ============================================================================

class LLMConfig(BaseModel):
    """LLM provider configuration. Shared across all agents."""

    model_config = {"protected_namespaces": ()}

    provider:    str   = Field(default="openai",  description="openai | anthropic")
    model:       str   = Field(default="gpt-4.1", description="Model name")
    temperature: float = Field(default=0.2,       description="Sampling temperature")
    max_tokens:  int   = Field(default=2000,      description="Max response tokens")


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
# BASE AGENT  (abstract — all 7 Kratos agents inherit this)
# ============================================================================

class BaseAgent(ABC):
    """
    Abstract base class for all Kratos analysis agents.

    Contract:
      1. Accept a payload dict (ExecutionFingerprint, CodeFingerprint, etc.)
      2. Call LLM via LangChain for reasoning
      3. Return a structured AgentResponse

    Subclasses must implement:
      agent_type    @property → AgentType
      agent_name    @property → str
      description   @property → str
      system_prompt @property → str
      analyze()     async     → AgentResponse

    Subclasses may override:
      fingerprint_domain  @property → FingerprintDomain  (default: GENERIC)
      plan()                         → List[str]           (default: generic steps)
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self.llm_config = llm_config or LLMConfig()
        self._llm       = None

    # ── Abstract properties ────────────────────────────────────────────────

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Return the AgentType enum member for this agent."""
        pass

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return human-readable name (used in dashboard headers)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description of what this agent does."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt injected before every LLM call for this agent."""
        pass

    @abstractmethod
    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional["AgentContext"] = None,
        **kwargs,
    ) -> AgentResponse:
        """
        Core analysis method.

        Args:
            fingerprint_data: Domain fingerprint as dict.
                              Key depends on agent:
                                LogAnalyzerAgent    → ExecutionFingerprint.model_dump()
                                CodeAnalyzerAgent   → CodeFingerprint.model_dump()
                                DataProfilerAgent   → DataFingerprint.model_dump()
                                ChangeAnalyzerAgent → ChangeFingerprint.model_dump()
                                TriangulationAgent  → IssueProfile.model_dump()
            context:          Optional AgentContext for cross-agent findings sharing.
            **kwargs:         Agent-specific params (e.g. focus_areas for RootCauseAgent).

        Returns:
            AgentResponse with analysis results.
        """
        pass

    # ── Optional overrides ─────────────────────────────────────────────────

    @property
    def fingerprint_domain(self) -> FingerprintDomain:
        """
        Declares which fingerprint domain this agent consumes.
        Used by KratosOrchestrator to validate payload routing.
        Override in subclass to be explicit.
        """
        return FingerprintDomain.GENERIC

    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional["AgentContext"] = None,
        **kwargs,
    ) -> List[str]:
        """
        Return ordered list of steps this agent will execute.
        Used by orchestrator for logging. Override for agent-specific plans.
        """
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

    # ── Context enrichment ──────────────────────────────────────────────────

    def _enrich_prompt_with_context(
        self,
        base_prompt: str,
        context: Optional["AgentContext"],
    ) -> str:
        """
        Append prior agent findings and focus areas to a prompt.
        Called inside analyze() before the LLM call.
        """
        if not context:
            return base_prompt

        findings_summary = context.get_findings_summary()
        focus_areas      = context.get_focus_areas()
        enrichment       = []

        if findings_summary and findings_summary != "No previous findings.":
            enrichment.append(
                f"\n\n--- Previous Agent Findings ---\n{findings_summary}"
            )

        if focus_areas:
            enrichment.append(
                f"\n\n--- Focus Areas ---\n"
                f"Pay special attention to: {', '.join(focus_areas)}"
            )

        if enrichment:
            logger.info(
                f"[{self.agent_name}] Enriching prompt with "
                f"{len(context.get_findings())} prior finding(s)"
            )
            return base_prompt + "".join(enrichment)

        return base_prompt

    # ── LLM internals ──────────────────────────────────────────────────────

    def _get_llm(self) -> ChatOpenAI:
        """Lazy-initialize and return a LangChain LLM instance."""
        if self._llm is None:
            global _DOTENV_LOADED
            if not _DOTENV_LOADED:
                repo_root     = Path(__file__).resolve().parents[2]
                load_dotenv(repo_root / ".env", override=False)
                _DOTENV_LOADED = True

            logger.info(
                f"[LLM] Initializing {self.llm_config.provider} | "
                f"model={self.llm_config.model} | "
                f"temp={self.llm_config.temperature} | "
                f"max_tokens={self.llm_config.max_tokens}"
            )

            if self.llm_config.provider == "openai":
                self._llm = ChatOpenAI(
                    model       = self.llm_config.model,
                    temperature = self.llm_config.temperature,
                    max_tokens  = self.llm_config.max_tokens,
                )
            elif self.llm_config.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                self._llm = ChatAnthropic(
                    model       = self.llm_config.model,
                    temperature = self.llm_config.temperature,
                    max_tokens  = self.llm_config.max_tokens,
                )
            else:
                raise ValueError(
                    f"Unsupported LLM provider: {self.llm_config.provider}. "
                    f"Supported: openai, anthropic"
                )
            logger.info("[LLM] Client ready")
        return self._llm

    def _create_chain(self, system_prompt: str):
        """Build a LangChain chain: ChatPromptTemplate | LLM | StrOutputParser."""
        llm    = self._get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        return prompt | llm | StrOutputParser()

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Invoke LLM asynchronously via LangChain.

        Logs:
          - Prompt sizes and estimated token counts
          - Elapsed time and response size

        Returns:
            Raw LLM response string.
        """
        import time

        est_tokens = (len(system_prompt) + len(user_prompt)) // 4
        logger.info(
            f"[{self.agent_name}] LLM call | "
            f"sys={len(system_prompt)}c | "
            f"usr={len(user_prompt)}c | "
            f"~{est_tokens} tokens"
        )

        chain      = self._create_chain(system_prompt)
        start      = time.time()
        response   = await chain.ainvoke({"input": user_prompt})
        elapsed    = time.time() - start

        logger.info(
            f"[{self.agent_name}] Response in {elapsed:.2f}s | "
            f"{len(response)}c (~{len(response) // 4} tokens)"
        )
        return response

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
