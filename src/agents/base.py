"""
Base agent interface for Spark fingerprint analysis agents.

All specialized agents inherit from BaseAgent and use LangChain/LangGraph.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Import for type hints only - avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.agent_coordination import AgentContext

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of analysis agents."""
    QUERY_UNDERSTANDING = "query_understanding"
    ROOT_CAUSE = "root_cause"
    OPTIMIZATION = "optimization"
    REGRESSION = "regression"
    ORCHESTRATOR = "orchestrator"


class AgentResponse(BaseModel):
    """Standardized response from any agent."""
    
    agent_type: AgentType = Field(..., description="Type of agent that produced this response")
    agent_name: str = Field(..., description="Human-readable agent name")
    success: bool = Field(..., description="Whether analysis completed successfully")
    
    # Main output
    summary: str = Field(..., description="Brief summary of findings (1-2 sentences)")
    explanation: str = Field(..., description="Detailed natural language explanation")
    
    # Structured findings
    key_findings: List[str] = Field(default_factory=list, description="Bullet-point findings")
    confidence: float = Field(default=1.0, description="Confidence score 0.0-1.0")
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    processing_time_ms: Optional[int] = Field(None, description="Time taken to generate response")
    model_used: Optional[str] = Field(None, description="LLM model used if applicable")
    tokens_used: Optional[int] = Field(None, description="Token count if applicable")
    
    # Error handling
    error: Optional[str] = Field(None, description="Error message if success=False")
    
    # Cross-references for orchestrator
    suggested_followup_agents: List[AgentType] = Field(
        default_factory=list, 
        description="Other agents that might provide additional insights"
    )


class LLMConfig(BaseModel):
    """Configuration for LLM provider."""
    
    provider: str = Field(default="openai", description="LLM provider: openai, anthropic")
    model: str = Field(default="gpt-4o", description="Model name")
    temperature: float = Field(default=0.3, description="Sampling temperature")
    max_tokens: int = Field(default=2000, description="Max response tokens")


class AgentState(TypedDict):
    """State for LangGraph agent workflows."""
    fingerprint_data: Dict[str, Any]
    context: Dict[str, Any]
    analysis_result: Optional[str]
    error: Optional[str]


class BaseAgent(ABC):
    """
    Abstract base class for all analysis agents using LangChain/LangGraph.
    
    Each agent:
    1. Receives fingerprint data (full or partial)
    2. Uses LangChain for LLM calls
    3. Returns structured AgentResponse
    """
    
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        """
        Initialize agent with optional LLM configuration.
        
        Args:
            llm_config: LLM settings. If None, uses defaults.
        """
        self.llm_config = llm_config or LLMConfig()
        self._llm = None
    
    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Return the type of this agent."""
        pass
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return human-readable agent name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return description of what this agent does."""
        pass
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass
    
    @abstractmethod
    async def analyze(
        self, 
        fingerprint_data: Dict[str, Any], 
        context: Optional["AgentContext"] = None,
        **kwargs
    ) -> AgentResponse:
        """
        Perform analysis on fingerprint data.
        
        Args:
            fingerprint_data: Full or partial fingerprint as dict
            context: Optional AgentContext for coordinated analysis.
                     When provided, agent can access previous findings and
                     share its own findings with other agents.
            **kwargs: Agent-specific parameters
            
        Returns:
            AgentResponse with analysis results
        """
        pass
    
    def _enrich_prompt_with_context(self, base_prompt: str, context: Optional["AgentContext"]) -> str:
        """
        Enrich a prompt with context from previous agents.
        
        Args:
            base_prompt: The original prompt
            context: Optional agent context with previous findings
            
        Returns:
            Enriched prompt including previous findings if available
        """
        if not context:
            return base_prompt
        
        findings_summary = context.get_findings_summary()
        focus_areas = context.get_focus_areas()
        
        enrichment = []
        
        if findings_summary and findings_summary != "No previous findings.":
            enrichment.append(f"\n\n--- Previous Agent Findings ---\n{findings_summary}")
        
        if focus_areas:
            enrichment.append(f"\n\n--- Focus Areas ---\nPay special attention to: {', '.join(focus_areas)}")
        
        if enrichment:
            logger.info(f"[AGENT] Enriching prompt with context from {len(context.get_findings())} previous findings")
            return base_prompt + "".join(enrichment)
        
        return base_prompt
    
    def _get_llm(self) -> ChatOpenAI:
        """Get LangChain LLM instance."""
        if self._llm is None:
            logger.info(f"[LLM] Initializing {self.llm_config.provider} client...")
            logger.info(f"[LLM] Model: {self.llm_config.model}, Temperature: {self.llm_config.temperature}, Max tokens: {self.llm_config.max_tokens}")
            if self.llm_config.provider == "openai":
                self._llm = ChatOpenAI(
                    model=self.llm_config.model,
                    temperature=self.llm_config.temperature,
                    max_tokens=self.llm_config.max_tokens,
                )
            elif self.llm_config.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                self._llm = ChatAnthropic(
                    model=self.llm_config.model,
                    temperature=self.llm_config.temperature,
                    max_tokens=self.llm_config.max_tokens,
                )
            else:
                raise ValueError(f"Unsupported LLM provider: {self.llm_config.provider}")
            logger.info(f"[LLM] Client ready")
        return self._llm
    
    def _create_chain(self, system_prompt: str):
        """Create a LangChain chain with the given system prompt."""
        logger.debug(f"Creating LangChain chain with system prompt ({len(system_prompt)} chars)")
        llm = self._get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}")
        ])
        return prompt | llm | StrOutputParser()
    
    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call LLM using LangChain.
        
        Args:
            system_prompt: System/instruction prompt
            user_prompt: User message with data
            
        Returns:
            LLM response text
        """
        import time
        logger.info(f"[LLM] Preparing request...")
        logger.info(f"[LLM] System prompt: {len(system_prompt)} chars")
        logger.info(f"[LLM] User prompt: {len(user_prompt)} chars")
        logger.info(f"[LLM] Total context: ~{(len(system_prompt) + len(user_prompt)) // 4} tokens (estimated)")
        
        chain = self._create_chain(system_prompt)
        
        logger.info(f"[LLM] Sending request to {self.llm_config.model}...")
        start_time = time.time()
        response = await chain.ainvoke({"input": user_prompt})
        elapsed = time.time() - start_time
        
        logger.info(f"[LLM] Response received in {elapsed:.2f}s")
        logger.info(f"[LLM] Response length: {len(response)} chars (~{len(response) // 4} tokens)")
        return response
    
    def _create_error_response(self, error: str) -> AgentResponse:
        """Create a standardized error response."""
        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=False,
            summary="Analysis failed",
            explanation=f"Error during analysis: {error}",
            error=error
        )
