"""
Agent Coordination System

Provides context sharing and message passing between agents during orchestrated analysis.
Enables agents to build on each other's findings for deeper insights.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of messages agents can pass to each other."""
    
    FINDING = "finding"           # A discovered issue or insight
    RECOMMENDATION = "recommendation"  # A suggested action
    CONTEXT = "context"           # Background information
    QUESTION = "question"         # Request for another agent's analysis
    CORRELATION = "correlation"   # Link between findings


@dataclass
class AgentMessage:
    """A message passed between agents."""
    
    from_agent: str
    to_agent: Optional[str]  # None = broadcast to all
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class SharedFinding:
    """A finding that can be shared between agents."""
    
    agent_type: str
    finding_type: str
    severity: str
    title: str
    description: str
    evidence: List[str] = field(default_factory=list)
    related_stages: List[int] = field(default_factory=list)
    related_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_type": self.agent_type,
            "finding_type": self.finding_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "related_stages": self.related_stages,
            "related_metrics": self.related_metrics
        }


class AgentContext:
    """
    Shared context for agent coordination.
    
    Enables agents to:
    - Share findings with other agents
    - Pass messages between agents
    - Access previous agent outputs
    - Build on each other's analysis
    """
    
    def __init__(self, fingerprint_data: Dict[str, Any], user_query: str):
        """
        Initialize agent context.
        
        Args:
            fingerprint_data: The execution fingerprint being analyzed
            user_query: The user's original question
        """
        self.fingerprint_data = fingerprint_data
        self.user_query = user_query
        self.created_at = datetime.now()
        
        # Shared state
        self._findings: List[SharedFinding] = []
        self._messages: List[AgentMessage] = []
        self._agent_outputs: Dict[str, Any] = {}
        self._focus_areas: List[str] = []
        self._correlations: List[Dict[str, Any]] = []
        
        logger.info(f"[CONTEXT] Initialized agent context for query: {user_query[:50]}...")
    
    def add_finding(self, finding: SharedFinding) -> None:
        """Add a finding to the shared context."""
        self._findings.append(finding)
        logger.info(f"[CONTEXT] Finding added by {finding.agent_type}: [{finding.severity}] {finding.title}")
    
    def get_findings(self, 
                     agent_type: Optional[str] = None,
                     severity: Optional[str] = None,
                     finding_type: Optional[str] = None) -> List[SharedFinding]:
        """
        Get findings, optionally filtered.
        
        Args:
            agent_type: Filter by agent that produced the finding
            severity: Filter by severity level
            finding_type: Filter by type of finding
        """
        findings = self._findings
        
        if agent_type:
            findings = [f for f in findings if f.agent_type == agent_type]
        if severity:
            findings = [f for f in findings if f.severity == severity]
        if finding_type:
            findings = [f for f in findings if f.finding_type == finding_type]
        
        return findings
    
    def get_findings_summary(self) -> str:
        """Get a text summary of all findings for LLM context."""
        if not self._findings:
            return "No previous findings."
        
        lines = ["Previous agent findings:"]
        for f in self._findings:
            lines.append(f"- [{f.severity.upper()}] {f.agent_type}: {f.title}")
            if f.description:
                lines.append(f"  {f.description[:100]}...")
        
        return "\n".join(lines)
    
    def send_message(self, message: AgentMessage) -> None:
        """Send a message to the coordination system."""
        self._messages.append(message)
        target = message.to_agent or "all agents"
        logger.info(f"[CONTEXT] Message from {message.from_agent} to {target}: {message.message_type.value}")
    
    def get_messages(self, 
                     to_agent: Optional[str] = None,
                     from_agent: Optional[str] = None,
                     message_type: Optional[MessageType] = None) -> List[AgentMessage]:
        """Get messages, optionally filtered."""
        messages = self._messages
        
        if to_agent:
            messages = [m for m in messages if m.to_agent == to_agent or m.to_agent is None]
        if from_agent:
            messages = [m for m in messages if m.from_agent == from_agent]
        if message_type:
            messages = [m for m in messages if m.message_type == message_type]
        
        return messages
    
    def store_agent_output(self, agent_type: str, output: Any) -> None:
        """Store an agent's complete output for reference by other agents."""
        self._agent_outputs[agent_type] = output
        logger.info(f"[CONTEXT] Stored output from {agent_type}")
    
    def get_agent_output(self, agent_type: str) -> Optional[Any]:
        """Get a previous agent's output."""
        return self._agent_outputs.get(agent_type)
    
    def get_all_agent_outputs(self) -> Dict[str, Any]:
        """Get all stored agent outputs."""
        return self._agent_outputs.copy()
    
    def add_focus_area(self, area: str) -> None:
        """Add a focus area for subsequent agents."""
        if area not in self._focus_areas:
            self._focus_areas.append(area)
            logger.info(f"[CONTEXT] Added focus area: {area}")
    
    def get_focus_areas(self) -> List[str]:
        """Get current focus areas."""
        return self._focus_areas.copy()
    
    def add_correlation(self, finding1: str, finding2: str, relationship: str) -> None:
        """Record a correlation between findings."""
        correlation = {
            "finding1": finding1,
            "finding2": finding2,
            "relationship": relationship,
            "timestamp": datetime.now().isoformat()
        }
        self._correlations.append(correlation)
        logger.info(f"[CONTEXT] Correlation added: {finding1} <-> {finding2}")
    
    def get_correlations(self) -> List[Dict[str, Any]]:
        """Get all recorded correlations."""
        return self._correlations.copy()
    
    def build_context_for_agent(self, agent_type: str) -> Dict[str, Any]:
        """
        Build a context dictionary for a specific agent.
        
        Includes relevant findings, messages, and focus areas
        that the agent should consider.
        """
        return {
            "user_query": self.user_query,
            "previous_findings": [f.to_dict() for f in self._findings],
            "findings_summary": self.get_findings_summary(),
            "messages_for_agent": [m.to_dict() for m in self.get_messages(to_agent=agent_type)],
            "focus_areas": self._focus_areas,
            "correlations": self._correlations,
            "agents_completed": list(self._agent_outputs.keys())
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the context state."""
        return {
            "user_query": self.user_query,
            "findings_count": len(self._findings),
            "messages_count": len(self._messages),
            "agents_completed": list(self._agent_outputs.keys()),
            "focus_areas": self._focus_areas,
            "correlations_count": len(self._correlations)
        }
