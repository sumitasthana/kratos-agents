# Moved from: src\agent_coordination.py
# Import updates applied by migrate step.
# """
# Agent Coordination System

# Provides context sharing and message passing between agents during orchestrated analysis.
# Enables agents to build on each other's findings for deeper insights.
# """

# import logging
# from dataclasses import dataclass, field
# from datetime import datetime
# from typing import Any, Dict, List, Optional
# from enum import Enum

# logger = logging.getLogger(__name__)


# class MessageType(str, Enum):
#     """Types of messages agents can pass to each other."""
    
#     FINDING = "finding"           # A discovered issue or insight
#     RECOMMENDATION = "recommendation"  # A suggested action
#     CONTEXT = "context"           # Background information
#     QUESTION = "question"         # Request for another agent's analysis
#     CORRELATION = "correlation"   # Link between findings


# @dataclass
# class AgentMessage:
#     """A message passed between agents."""
    
#     from_agent: str
#     to_agent: Optional[str]  # None = broadcast to all
#     message_type: MessageType
#     content: str
#     metadata: Dict[str, Any] = field(default_factory=dict)
#     timestamp: datetime = field(default_factory=datetime.now)
    
#     def to_dict(self) -> Dict[str, Any]:
#         """Convert to dictionary for serialization."""
#         return {
#             "from_agent": self.from_agent,
#             "to_agent": self.to_agent,
#             "message_type": self.message_type.value,
#             "content": self.content,
#             "metadata": self.metadata,
#             "timestamp": self.timestamp.isoformat()
#         }


# @dataclass
# class SharedFinding:
#     """A finding that can be shared between agents."""
    
#     agent_type: str
#     finding_type: str
#     severity: str
#     title: str
#     description: str
#     evidence: List[str] = field(default_factory=list)
#     related_stages: List[int] = field(default_factory=list)
#     related_metrics: Dict[str, Any] = field(default_factory=dict)
    
#     def to_dict(self) -> Dict[str, Any]:
#         """Convert to dictionary."""
#         return {
#             "agent_type": self.agent_type,
#             "finding_type": self.finding_type,
#             "severity": self.severity,
#             "title": self.title,
#             "description": self.description,
#             "evidence": self.evidence,
#             "related_stages": self.related_stages,
#             "related_metrics": self.related_metrics
#         }


# class AgentContext:
#     """
#     Shared context for agent coordination.
    
#     Enables agents to:
#     - Share findings with other agents
#     - Pass messages between agents
#     - Access previous agent outputs
#     - Build on each other's analysis
#     """
    
#     def __init__(self, fingerprint_data: Dict[str, Any], user_query: str):
#         """
#         Initialize agent context.
        
#         Args:
#             fingerprint_data: The execution fingerprint being analyzed
#             user_query: The user's original question
#         """
#         self.fingerprint_data = fingerprint_data
#         self.user_query = user_query
#         self.created_at = datetime.now()
        
#         # Shared state
#         self._findings: List[SharedFinding] = []
#         self._messages: List[AgentMessage] = []
#         self._agent_outputs: Dict[str, Any] = {}
#         self._focus_areas: List[str] = []
#         self._correlations: List[Dict[str, Any]] = []
        
#         logger.info(f"[CONTEXT] Initialized agent context for query: {user_query[:50]}...")
    
#     def add_finding(self, finding: SharedFinding) -> None:
#         """Add a finding to the shared context."""
#         self._findings.append(finding)
#         logger.info(f"[CONTEXT] Finding added by {finding.agent_type}: [{finding.severity}] {finding.title}")
    
#     def get_findings(self, 
#                      agent_type: Optional[str] = None,
#                      severity: Optional[str] = None,
#                      finding_type: Optional[str] = None) -> List[SharedFinding]:
#         """
#         Get findings, optionally filtered.
        
#         Args:
#             agent_type: Filter by agent that produced the finding
#             severity: Filter by severity level
#             finding_type: Filter by type of finding
#         """
#         findings = self._findings
        
#         if agent_type:
#             findings = [f for f in findings if f.agent_type == agent_type]
#         if severity:
#             findings = [f for f in findings if f.severity == severity]
#         if finding_type:
#             findings = [f for f in findings if f.finding_type == finding_type]
        
#         return findings
    
#     def get_findings_summary(self) -> str:
#         """Get a text summary of all findings for LLM context."""
#         if not self._findings:
#             return "No previous findings."
        
#         lines = ["Previous agent findings:"]
#         for f in self._findings:
#             lines.append(f"- [{f.severity.upper()}] {f.agent_type}: {f.title}")
#             if f.description:
#                 lines.append(f"  {f.description[:100]}...")
        
#         return "\n".join(lines)
    
#     def send_message(self, message: AgentMessage) -> None:
#         """Send a message to the coordination system."""
#         self._messages.append(message)
#         target = message.to_agent or "all agents"
#         logger.info(f"[CONTEXT] Message from {message.from_agent} to {target}: {message.message_type.value}")
    
#     def get_messages(self, 
#                      to_agent: Optional[str] = None,
#                      from_agent: Optional[str] = None,
#                      message_type: Optional[MessageType] = None) -> List[AgentMessage]:
#         """Get messages, optionally filtered."""
#         messages = self._messages
        
#         if to_agent:
#             messages = [m for m in messages if m.to_agent == to_agent or m.to_agent is None]
#         if from_agent:
#             messages = [m for m in messages if m.from_agent == from_agent]
#         if message_type:
#             messages = [m for m in messages if m.message_type == message_type]
        
#         return messages
    
#     def store_agent_output(self, agent_type: str, output: Any) -> None:
#         """Store an agent's complete output for reference by other agents."""
#         self._agent_outputs[agent_type] = output
#         logger.info(f"[CONTEXT] Stored output from {agent_type}")
    
#     def get_agent_output(self, agent_type: str) -> Optional[Any]:
#         """Get a previous agent's output."""
#         return self._agent_outputs.get(agent_type)
    
#     def get_all_agent_outputs(self) -> Dict[str, Any]:
#         """Get all stored agent outputs."""
#         return self._agent_outputs.copy()
    
#     def add_focus_area(self, area: str) -> None:
#         """Add a focus area for subsequent agents."""
#         if area not in self._focus_areas:
#             self._focus_areas.append(area)
#             logger.info(f"[CONTEXT] Added focus area: {area}")
    
#     def get_focus_areas(self) -> List[str]:
#         """Get current focus areas."""
#         return self._focus_areas.copy()
    
#     def add_correlation(self, finding1: str, finding2: str, relationship: str) -> None:
#         """Record a correlation between findings."""
#         correlation = {
#             "finding1": finding1,
#             "finding2": finding2,
#             "relationship": relationship,
#             "timestamp": datetime.now().isoformat()
#         }
#         self._correlations.append(correlation)
#         logger.info(f"[CONTEXT] Correlation added: {finding1} <-> {finding2}")
    
#     def get_correlations(self) -> List[Dict[str, Any]]:
#         """Get all recorded correlations."""
#         return self._correlations.copy()
    
#     def build_context_for_agent(self, agent_type: str) -> Dict[str, Any]:
#         """
#         Build a context dictionary for a specific agent.
        
#         Includes relevant findings, messages, and focus areas
#         that the agent should consider.
#         """
#         return {
#             "user_query": self.user_query,
#             "previous_findings": [f.to_dict() for f in self._findings],
#             "findings_summary": self.get_findings_summary(),
#             "messages_for_agent": [m.to_dict() for m in self.get_messages(to_agent=agent_type)],
#             "focus_areas": self._focus_areas,
#             "correlations": self._correlations,
#             "agents_completed": list(self._agent_outputs.keys())
#         }
    
#     def get_summary(self) -> Dict[str, Any]:
#         """Get a summary of the context state."""
#         return {
#             "user_query": self.user_query,
#             "findings_count": len(self._findings),
#             "messages_count": len(self._messages),
#             "agents_completed": list(self._agent_outputs.keys()),
#             "focus_areas": self._focus_areas,
#             "correlations_count": len(self._correlations)
#         }
"""
Agent Coordination System

Provides context sharing and message passing between agents during orchestrated analysis.
Enables agents to build on each other's findings for deeper insights.

Enhanced with GRC compliance tracking and incident routing.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum


logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of messages agents can pass to each other."""
    
    FINDING = "finding"           # A discovered issue or insight
    RECOMMENDATION = "recommendation"  # A suggested action
    CONTEXT = "context"           # Background information
    QUESTION = "question"         # Request for another agent's analysis
    CORRELATION = "correlation"   # Link between findings
    # NEW: GRC-specific message types
    INCIDENT_ALERT = "incident_alert"  # Critical compliance incident
    REMEDIATION_REQUIRED = "remediation_required"  # Action needed
    ROUTING_INSTRUCTION = "routing_instruction"  # Where to send results


class FindingSeverity(str, Enum):
    """Standardized severity levels for findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ComplianceDomain(str, Enum):
    """GRC compliance domains for tracking."""
    DATA_QUALITY = "data_quality"
    OPERATIONAL_RESILIENCE = "operational_resilience"
    DATA_GOVERNANCE = "data_governance"
    REGULATORY_REPORTING = "regulatory_reporting"
    SOX_COMPLIANCE = "sox_compliance"
    GDPR_COMPLIANCE = "gdpr_compliance"
    PERFORMANCE_SLA = "performance_sla"


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
    
    # NEW: GRC compliance fields
    compliance_domains: List[ComplianceDomain] = field(default_factory=list)
    regulation_impacted: Optional[str] = None
    requires_remediation: bool = False
    remediation_owner: Optional[str] = None
    
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
            "related_metrics": self.related_metrics,
            "compliance_domains": [d.value for d in self.compliance_domains],
            "regulation_impacted": self.regulation_impacted,
            "requires_remediation": self.requires_remediation,
            "remediation_owner": self.remediation_owner
        }


@dataclass
class IncidentContext:
    """Context specific to GRC compliance incidents."""
    
    incident_id: str
    incident_type: str
    severity: str
    timestamp: datetime
    affected_systems: List[str] = field(default_factory=list)
    data_impact: Optional[Dict[str, Any]] = None
    compliance_breach: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "affected_systems": self.affected_systems,
            "data_impact": self.data_impact,
            "compliance_breach": self.compliance_breach
        }


class AgentContext:
    """
    Shared context for agent coordination.
    
    Enables agents to:
    - Share findings with other agents
    - Pass messages between agents
    - Access previous agent outputs
    - Build on each other's analysis
    - Track GRC compliance incidents and routing
    """
    
    def __init__(
        self, 
        fingerprint_data: Dict[str, Any], 
        user_query: str,
        incident_context: Optional[IncidentContext] = None
    ):
        """
        Initialize agent context.
        
        Args:
            fingerprint_data: The execution fingerprint being analyzed
            user_query: The user's original question
            incident_context: Optional GRC incident details
        """
        self.fingerprint_data = fingerprint_data
        self.user_query = user_query
        self.incident_context = incident_context
        self.created_at = datetime.now()
        
        # Shared state
        self._findings: List[SharedFinding] = []
        self._messages: List[AgentMessage] = []
        self._agent_outputs: Dict[str, Any] = {}
        self._focus_areas: List[str] = []
        self._correlations: List[Dict[str, Any]] = []
        
        # NEW: GRC-specific tracking
        self._compliance_alerts: List[Dict[str, Any]] = []
        self._remediation_actions: List[Dict[str, Any]] = []
        self._routing_destinations: Set[str] = set()
        self._affected_tables: Set[str] = set()
        
        logger.info(f"[CONTEXT] Initialized agent context for query: {user_query[:50]}...")
        if incident_context:
            logger.info(f"[CONTEXT] Incident mode: {incident_context.incident_type} (severity: {incident_context.severity})")
    
    def add_finding(self, finding: SharedFinding) -> None:
        """Add a finding to the shared context."""
        self._findings.append(finding)
        logger.info(f"[CONTEXT] Finding added by {finding.agent_type}: [{finding.severity}] {finding.title}")
        
        # NEW: Auto-track compliance alerts for critical/high severity findings
        if finding.severity in [FindingSeverity.CRITICAL.value, FindingSeverity.HIGH.value]:
            if finding.compliance_domains or finding.regulation_impacted:
                self._add_compliance_alert(finding)
    
    def _add_compliance_alert(self, finding: SharedFinding) -> None:
        """Track a compliance-related alert."""
        alert = {
            "finding_title": finding.title,
            "severity": finding.severity,
            "compliance_domains": [d.value for d in finding.compliance_domains],
            "regulation": finding.regulation_impacted,
            "timestamp": datetime.now().isoformat()
        }
        self._compliance_alerts.append(alert)
        logger.warning(f"[CONTEXT] COMPLIANCE ALERT: {finding.title} (Regulation: {finding.regulation_impacted})")
    
    def get_findings(self, 
                     agent_type: Optional[str] = None,
                     severity: Optional[str] = None,
                     finding_type: Optional[str] = None,
                     compliance_domain: Optional[ComplianceDomain] = None) -> List[SharedFinding]:
        """
        Get findings, optionally filtered.
        
        Args:
            agent_type: Filter by agent that produced the finding
            severity: Filter by severity level
            finding_type: Filter by type of finding
            compliance_domain: Filter by compliance domain (NEW)
        """
        findings = self._findings
        
        if agent_type:
            findings = [f for f in findings if f.agent_type == agent_type]
        if severity:
            findings = [f for f in findings if f.severity == severity]
        if finding_type:
            findings = [f for f in findings if f.finding_type == finding_type]
        if compliance_domain:
            findings = [f for f in findings if compliance_domain in f.compliance_domains]
        
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
            if f.compliance_domains:
                domains = ", ".join([d.value for d in f.compliance_domains])
                lines.append(f"  Compliance: {domains}")
        
        return "\n".join(lines)
    
    def send_message(self, message: AgentMessage) -> None:
        """Send a message to the coordination system."""
        self._messages.append(message)
        target = message.to_agent or "all agents"
        logger.info(f"[CONTEXT] Message from {message.from_agent} to {target}: {message.message_type.value}")
        
        # NEW: Track routing instructions
        if message.message_type == MessageType.ROUTING_INSTRUCTION:
            destination = message.metadata.get("destination")
            if destination:
                self._routing_destinations.add(destination)
    
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
        
        # NEW: Extract routing and remediation info from RCA agent
        if agent_type == "root_cause" and hasattr(output, 'metadata'):
            metadata = output.metadata
            
            # Track routing destinations
            routing = metadata.get("routing", {})
            if routing.get("destination"):
                self._routing_destinations.add(routing["destination"])
            
            # Track remediation actions
            remediation = metadata.get("remediation", {})
            if remediation.get("action_items"):
                for action in remediation["action_items"]:
                    self._remediation_actions.append({
                        "priority": action.get("priority"),
                        "action": action.get("action"),
                        "owner": remediation.get("owner"),
                        "estimated_time": remediation.get("estimated_fix_time"),
                        "timestamp": datetime.now().isoformat()
                    })
    
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
    
    # ========================================================================
    # NEW: GRC Compliance Methods
    # ========================================================================
    
    def add_remediation_action(
        self, 
        action: str, 
        priority: str, 
        owner: str,
        estimated_time: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """Add a remediation action to the context."""
        remediation = {
            "action": action,
            "priority": priority,
            "owner": owner,
            "estimated_time": estimated_time,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        }
        self._remediation_actions.append(remediation)
        logger.info(f"[CONTEXT] Remediation action added: [{priority}] {action}")
    
    def get_remediation_actions(self, priority: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get remediation actions, optionally filtered by priority."""
        if priority:
            return [a for a in self._remediation_actions if a["priority"] == priority]
        return self._remediation_actions.copy()
    
    def track_affected_table(self, table_name: str) -> None:
        """Track a table affected by the incident."""
        self._affected_tables.add(table_name)
        logger.info(f"[CONTEXT] Tracking affected table: {table_name}")
    
    def get_affected_tables(self) -> List[str]:
        """Get all affected tables."""
        return list(self._affected_tables)
    
    def get_compliance_summary(self) -> Dict[str, Any]:
        """Get GRC compliance summary for reporting."""
        return {
            "compliance_alerts": len(self._compliance_alerts),
            "critical_alerts": len([a for a in self._compliance_alerts if a["severity"] == "critical"]),
            "remediation_actions": len(self._remediation_actions),
            "p0_actions": len([a for a in self._remediation_actions if a["priority"] == "P0"]),
            "routing_destinations": list(self._routing_destinations),
            "affected_tables": list(self._affected_tables),
            "regulations_impacted": list(set([
                a["regulation"] for a in self._compliance_alerts 
                if a.get("regulation")
            ]))
        }
    
    def build_context_for_agent(self, agent_type: str) -> Dict[str, Any]:
        """
        Build a context dictionary for a specific agent.
        
        Includes relevant findings, messages, and focus areas
        that the agent should consider.
        """
        context = {
            "user_query": self.user_query,
            "previous_findings": [f.to_dict() for f in self._findings],
            "findings_summary": self.get_findings_summary(),
            "messages_for_agent": [m.to_dict() for m in self.get_messages(to_agent=agent_type)],
            "focus_areas": self._focus_areas,
            "correlations": self._correlations,
            "agents_completed": list(self._agent_outputs.keys())
        }
        
        # NEW: Add GRC context if in incident mode
        if self.incident_context:
            context["incident"] = self.incident_context.to_dict()
            context["compliance_summary"] = self.get_compliance_summary()
        
        return context
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the context state."""
        summary = {
            "user_query": self.user_query,
            "findings_count": len(self._findings),
            "messages_count": len(self._messages),
            "agents_completed": list(self._agent_outputs.keys()),
            "focus_areas": self._focus_areas,
            "correlations_count": len(self._correlations)
        }
        
        # NEW: Add GRC summary if relevant
        if self.incident_context or self._compliance_alerts:
            summary["compliance"] = self.get_compliance_summary()
        
        return summary
    
    def generate_incident_report(self) -> Optional[str]:
        """
        Generate a formatted incident report for GRC compliance.
        
        Returns None if not in incident mode.
        """
        if not self.incident_context:
            return None
        
        lines = [
            "=" * 80,
            "INCIDENT ANALYSIS REPORT",
            "=" * 80,
            "",
            f"Incident ID: {self.incident_context.incident_id}",
            f"Type: {self.incident_context.incident_type}",
            f"Severity: {self.incident_context.severity}",
            f"Timestamp: {self.incident_context.timestamp.isoformat()}",
            "",
            "ANALYSIS SUMMARY",
            f"  Agents Completed: {len(self._agent_outputs)}",
            f"  Findings: {len(self._findings)}",
            f"  Compliance Alerts: {len(self._compliance_alerts)}",
            f"  Remediation Actions: {len(self._remediation_actions)}",
            "",
            "AFFECTED SYSTEMS",
            f"  Tables: {len(self._affected_tables)}",
            f"  Systems: {', '.join(self.incident_context.affected_systems) if self.incident_context.affected_systems else 'N/A'}",
            "",
            "ROUTING",
            f"  Destinations: {', '.join(self._routing_destinations) if self._routing_destinations else 'N/A'}",
            "",
            "TOP REMEDIATION ACTIONS"
        ]
        
        # Add top 5 remediation actions
        for i, action in enumerate(self._remediation_actions[:5], 1):
            lines.append(f"  {i}. [{action['priority']}] {action['action']}")
            lines.append(f"     Owner: {action['owner']} | Time: {action['estimated_time']}")
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)
