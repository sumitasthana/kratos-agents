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
    async def analyze(self, fingerprint_data: Dict[str, Any], **kwargs) -> AgentResponse:
        """
        Perform analysis on fingerprint data.
        
        Args:
            fingerprint_data: Full or partial fingerprint as dict
            **kwargs: Agent-specific parameters
            
        Returns:
            AgentResponse with analysis results
        """
        pass
    
    def _get_llm(self) -> ChatOpenAI:
        """Get LangChain LLM instance."""
        if self._llm is None:
            logger.debug(f"Initializing LLM: provider={self.llm_config.provider}, model={self.llm_config.model}")
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
            logger.info(f"LLM initialized: {self.llm_config.model}")
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
        logger.info(f"Calling LLM with prompt ({len(user_prompt)} chars)")
        logger.debug(f"User prompt preview: {user_prompt[:200]}...")
        chain = self._create_chain(system_prompt)
        response = await chain.ainvoke({"input": user_prompt})
        logger.info(f"LLM response received ({len(response)} chars)")
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
