"""
Smart Orchestrator for Spark Fingerprint Analysis

Coordinates multiple agents intelligently based on user queries and fingerprint characteristics.
Implements a two-layer architecture where this orchestrator sits on top of the existing
fingerprint infrastructure and agent implementations.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from src.schemas import (
    ExecutionFingerprint,
    ProblemType,
    AgentTask,
    AgentFinding,
    AnalysisResult,
)
from src.agent_coordination import AgentContext, SharedFinding, AgentMessage, MessageType
from src.agents import QueryUnderstandingAgent, RootCauseAgent, LLMConfig, AgentResponse
from src.agents.base import AgentType

logger = logging.getLogger(__name__)


# Keywords for problem classification
PERFORMANCE_KEYWORDS = [
    "slow", "performance", "optimize", "speed", "latency", "timeout",
    "memory", "spill", "shuffle", "skew", "bottleneck", "resource",
    "executor", "task", "stage", "failure", "failed", "crash", "oom",
    "gc", "garbage", "heap", "disk", "io", "network", "cpu"
]

LINEAGE_KEYWORDS = [
    "lineage", "data flow", "transformation", "query", "plan", "dag",
    "what does", "explain", "understand", "how does", "where does",
    "source", "sink", "input", "output", "column", "table", "join",
    "filter", "aggregate", "group", "partition", "schema"
]


class SmartOrchestrator:
    """
    Intelligent orchestrator that coordinates agents based on user queries.
    
    Takes an ExecutionFingerprint as input and routes analysis to appropriate
    agents based on problem classification and fingerprint characteristics.
    
    Features:
    - Problem classification based on keywords and fingerprint analysis
    - Intelligent agent selection and sequencing
    - Context passing between agents for deeper insights
    - Result synthesis from multiple agent outputs
    """
    
    def __init__(
        self, 
        fingerprint: ExecutionFingerprint,
        llm_config: Optional[LLMConfig] = None
    ):
        """
        Initialize orchestrator with a fingerprint.
        
        Args:
            fingerprint: The ExecutionFingerprint to analyze
            llm_config: Optional LLM configuration for agents
        """
        self.fingerprint = fingerprint
        self.fingerprint_dict = fingerprint.model_dump()
        self.llm_config = llm_config or LLMConfig()
        
        # Initialize agents
        self._agents = {
            AgentType.QUERY_UNDERSTANDING: QueryUnderstandingAgent(self.llm_config),
            AgentType.ROOT_CAUSE: RootCauseAgent(self.llm_config),
        }
        
        logger.info(f"[ORCHESTRATOR] Initialized with fingerprint for app: {fingerprint.context.spark_config.app_name}")
        logger.info(f"[ORCHESTRATOR] Available agents: {list(self._agents.keys())}")
    
    async def solve_problem(self, user_query: str) -> AnalysisResult:
        """
        Analyze the fingerprint based on user's query.
        
        This is the main entry point for orchestrated analysis.
        
        Args:
            user_query: Natural language question from the user
            
        Returns:
            AnalysisResult with synthesized findings from all relevant agents
        """
        start_time = time.time()
        
        logger.info(f"[ORCHESTRATOR] ========================================")
        logger.info(f"[ORCHESTRATOR] Starting orchestrated analysis")
        logger.info(f"[ORCHESTRATOR] Query: {user_query}")
        logger.info(f"[ORCHESTRATOR] ========================================")
        
        # Step 1: Classify the problem
        problem_type = self._classify_problem(user_query)
        logger.info(f"[ORCHESTRATOR] Problem classified as: {problem_type.value}")
        
        # Step 2: Analyze fingerprint characteristics
        fingerprint_hints = self._analyze_fingerprint_characteristics()
        logger.info(f"[ORCHESTRATOR] Fingerprint hints: {fingerprint_hints}")
        
        # Step 3: Plan agent execution
        agent_tasks = self._plan_agent_execution(problem_type, user_query, fingerprint_hints)
        logger.info(f"[ORCHESTRATOR] Planned {len(agent_tasks)} agent tasks")
        for task in agent_tasks:
            logger.info(f"[ORCHESTRATOR]   - {task.agent_type}: {task.task_description}")
        
        # Step 4: Create shared context
        context = AgentContext(self.fingerprint_dict, user_query)
        
        # Step 5: Execute agents in sequence with context sharing
        agent_responses: Dict[str, AgentResponse] = {}
        agent_sequence: List[str] = []
        
        for task in agent_tasks:
            logger.info(f"[ORCHESTRATOR] Executing agent: {task.agent_type}")
            
            response = await self._execute_agent_task(task, context)
            
            if response:
                agent_responses[task.agent_type] = response
                agent_sequence.append(task.agent_type)
                
                # Share findings with context for next agent
                self._share_findings_to_context(task.agent_type, response, context)
        
        # Step 6: Synthesize results
        logger.info(f"[ORCHESTRATOR] Synthesizing results from {len(agent_responses)} agents")
        result = self._synthesize_results(
            problem_type=problem_type,
            user_query=user_query,
            agent_responses=agent_responses,
            agent_sequence=agent_sequence,
            context=context,
            start_time=start_time
        )
        
        elapsed = int((time.time() - start_time) * 1000)
        logger.info(f"[ORCHESTRATOR] ========================================")
        logger.info(f"[ORCHESTRATOR] Analysis complete in {elapsed}ms")
        logger.info(f"[ORCHESTRATOR] Agents used: {result.agents_used}")
        logger.info(f"[ORCHESTRATOR] Findings: {len(result.findings)}")
        logger.info(f"[ORCHESTRATOR] ========================================")
        
        return result
    
    def _classify_problem(self, user_query: str) -> ProblemType:
        """
        Classify the user's problem based on keywords and query analysis.
        
        Args:
            user_query: The user's question
            
        Returns:
            ProblemType classification
        """
        query_lower = user_query.lower()
        
        # Count keyword matches
        performance_score = sum(1 for kw in PERFORMANCE_KEYWORDS if kw in query_lower)
        lineage_score = sum(1 for kw in LINEAGE_KEYWORDS if kw in query_lower)
        
        logger.info(f"[ORCHESTRATOR] Keyword scores - Performance: {performance_score}, Lineage: {lineage_score}")
        
        # Also consider fingerprint characteristics
        has_anomalies = len(self.fingerprint.metrics.anomalies) > 0
        has_failures = self.fingerprint.metrics.execution_summary.failed_task_count > 0
        
        if has_anomalies or has_failures:
            performance_score += 2  # Boost performance if issues detected
        
        # Classify based on scores
        if performance_score > lineage_score:
            return ProblemType.PERFORMANCE
        elif lineage_score > performance_score:
            return ProblemType.LINEAGE
        else:
            return ProblemType.GENERAL
    
    def _analyze_fingerprint_characteristics(self) -> Dict[str, Any]:
        """
        Analyze the fingerprint to identify key characteristics.
        
        Returns:
            Dictionary of characteristics that influence agent selection
        """
        metrics = self.fingerprint.metrics
        exec_summary = metrics.execution_summary
        
        hints = {
            "has_anomalies": len(metrics.anomalies) > 0,
            "anomaly_count": len(metrics.anomalies),
            "has_failures": exec_summary.failed_task_count > 0,
            "failure_count": exec_summary.failed_task_count,
            "has_spill": exec_summary.total_spill_bytes > 0,
            "spill_bytes": exec_summary.total_spill_bytes,
            "has_shuffle": exec_summary.total_shuffle_bytes > 0,
            "shuffle_bytes": exec_summary.total_shuffle_bytes,
            "stage_count": self.fingerprint.semantic.dag.total_stages,
            "task_count": exec_summary.total_tasks,
            "execution_class": self.fingerprint.execution_class,
        }
        
        # Identify severity
        if hints["has_failures"] or hints["anomaly_count"] >= 3:
            hints["severity"] = "critical"
        elif hints["has_spill"] or hints["anomaly_count"] >= 1:
            hints["severity"] = "warning"
        else:
            hints["severity"] = "healthy"
        
        return hints
    
    def _plan_agent_execution(
        self, 
        problem_type: ProblemType,
        user_query: str,
        fingerprint_hints: Dict[str, Any]
    ) -> List[AgentTask]:
        """
        Plan which agents to execute and in what order.
        
        Args:
            problem_type: Classified problem type
            user_query: User's question
            fingerprint_hints: Characteristics from fingerprint analysis
            
        Returns:
            Ordered list of AgentTasks to execute
        """
        tasks = []
        
        if problem_type == ProblemType.PERFORMANCE:
            # For performance issues, start with root cause analysis
            tasks.append(AgentTask(
                agent_type=AgentType.ROOT_CAUSE.value,
                task_description="Identify root causes of performance issues",
                priority=1,
                focus_areas=self._get_focus_areas_from_hints(fingerprint_hints)
            ))
            
            # Then add query understanding for context
            tasks.append(AgentTask(
                agent_type=AgentType.QUERY_UNDERSTANDING.value,
                task_description="Explain query structure to correlate with performance findings",
                priority=2,
                depends_on=[AgentType.ROOT_CAUSE.value]
            ))
            
        elif problem_type == ProblemType.LINEAGE:
            # For lineage questions, start with query understanding
            tasks.append(AgentTask(
                agent_type=AgentType.QUERY_UNDERSTANDING.value,
                task_description="Explain query execution and data flow",
                priority=1
            ))
            
            # Add root cause if there are issues
            if fingerprint_hints.get("has_anomalies") or fingerprint_hints.get("has_failures"):
                tasks.append(AgentTask(
                    agent_type=AgentType.ROOT_CAUSE.value,
                    task_description="Analyze any issues that may affect data flow",
                    priority=2,
                    depends_on=[AgentType.QUERY_UNDERSTANDING.value]
                ))
                
        else:  # GENERAL
            # Run both agents for comprehensive analysis
            tasks.append(AgentTask(
                agent_type=AgentType.QUERY_UNDERSTANDING.value,
                task_description="Explain what the query does",
                priority=1
            ))
            tasks.append(AgentTask(
                agent_type=AgentType.ROOT_CAUSE.value,
                task_description="Analyze execution health and any issues",
                priority=2,
                depends_on=[AgentType.QUERY_UNDERSTANDING.value]
            ))
        
        return tasks
    
    def _get_focus_areas_from_hints(self, hints: Dict[str, Any]) -> List[str]:
        """Extract focus areas from fingerprint hints."""
        focus_areas = []
        
        if hints.get("has_failures"):
            focus_areas.append("task_failures")
        if hints.get("has_spill"):
            focus_areas.append("memory_pressure")
        if hints.get("has_shuffle") and hints.get("shuffle_bytes", 0) > 1024 * 1024 * 1024:
            focus_areas.append("shuffle_overhead")
        
        return focus_areas
    
    async def _execute_agent_task(
        self, 
        task: AgentTask, 
        context: AgentContext
    ) -> Optional[AgentResponse]:
        """
        Execute a single agent task.
        
        Args:
            task: The task to execute
            context: Shared agent context
            
        Returns:
            AgentResponse or None if agent not found
        """
        agent_type = AgentType(task.agent_type)
        agent = self._agents.get(agent_type)
        
        if not agent:
            logger.warning(f"[ORCHESTRATOR] Agent not found: {task.agent_type}")
            return None
        
        try:
            logger.info(f"[ORCHESTRATOR] Running {agent.agent_name}...")
            
            # Build kwargs based on task
            kwargs = {}
            if task.focus_areas:
                kwargs["focus_areas"] = task.focus_areas

            try:
                plan_steps = agent.plan(self.fingerprint_dict, context=context, **kwargs)
                if plan_steps:
                    print(f"[plan] {agent.agent_name}")
                    for step in plan_steps:
                        print(f"[plan] - {step}")
            except Exception:
                pass
            
            # Execute agent with context
            response = await agent.analyze(
                self.fingerprint_dict,
                context=context,
                **kwargs
            )
            
            # Store output in context
            context.store_agent_output(task.agent_type, response)
            
            return response
            
        except Exception as e:
            logger.exception(f"[ORCHESTRATOR] Error executing {task.agent_type}: {e}")
            return None
    
    def _share_findings_to_context(
        self, 
        agent_type: str, 
        response: AgentResponse, 
        context: AgentContext
    ) -> None:
        """
        Share an agent's findings to the context for other agents.
        
        Args:
            agent_type: Type of agent that produced the response
            response: The agent's response
            context: Shared context to update
        """
        # Convert key findings to shared findings
        for finding_text in response.key_findings[:5]:  # Limit to top 5
            finding = SharedFinding(
                agent_type=agent_type,
                finding_type="key_finding",
                severity="info",
                title=finding_text[:50] + "..." if len(finding_text) > 50 else finding_text,
                description=finding_text
            )
            context.add_finding(finding)
        
        # Add focus areas based on findings
        if "memory" in response.explanation.lower() or "spill" in response.explanation.lower():
            context.add_focus_area("memory_pressure")
        if "skew" in response.explanation.lower():
            context.add_focus_area("data_skew")
        if "shuffle" in response.explanation.lower():
            context.add_focus_area("shuffle_optimization")
    
    def _synthesize_results(
        self,
        problem_type: ProblemType,
        user_query: str,
        agent_responses: Dict[str, AgentResponse],
        agent_sequence: List[str],
        context: AgentContext,
        start_time: float
    ) -> AnalysisResult:
        """
        Synthesize results from multiple agents into a unified response.
        
        Args:
            problem_type: The classified problem type
            user_query: Original user query
            agent_responses: Responses from each agent
            agent_sequence: Order agents were executed
            context: Shared context with all findings
            start_time: When analysis started
            
        Returns:
            Synthesized AnalysisResult
        """
        # Collect all findings
        all_findings: List[AgentFinding] = []
        all_recommendations: List[str] = []
        
        for agent_type, response in agent_responses.items():
            # Convert key findings to AgentFinding objects
            for i, finding_text in enumerate(response.key_findings):
                finding = AgentFinding(
                    agent_type=agent_type,
                    finding_type="analysis",
                    severity=self._infer_severity(finding_text),
                    title=f"Finding {i+1}",
                    description=finding_text
                )
                all_findings.append(finding)
        
        # Extract recommendations from explanations
        for response in agent_responses.values():
            if "recommend" in response.explanation.lower():
                # Simple extraction - could be enhanced with LLM
                lines = response.explanation.split("\n")
                for line in lines:
                    if "recommend" in line.lower() or line.strip().startswith("-"):
                        clean_line = line.strip().lstrip("-").strip()
                        if clean_line and len(clean_line) > 10:
                            all_recommendations.append(clean_line)
        
        # Build executive summary
        executive_summary = self._build_executive_summary(problem_type, agent_responses, context)
        
        # Build detailed analysis
        detailed_analysis = self._build_detailed_analysis(agent_responses)
        
        # Calculate overall confidence
        confidences = [r.confidence for r in agent_responses.values()]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Calculate total time
        total_time_ms = int((time.time() - start_time) * 1000)
        
        return AnalysisResult(
            problem_type=problem_type,
            user_query=user_query,
            executive_summary=executive_summary,
            detailed_analysis=detailed_analysis,
            findings=all_findings,
            recommendations=all_recommendations[:10],  # Top 10 recommendations
            agents_used=list(agent_responses.keys()),
            agent_sequence=agent_sequence,
            total_processing_time_ms=total_time_ms,
            confidence=avg_confidence,
            raw_agent_responses={k: v.model_dump() for k, v in agent_responses.items()}
        )
    
    def _infer_severity(self, finding_text: str) -> str:
        """Infer severity from finding text."""
        text_lower = finding_text.lower()
        
        if any(word in text_lower for word in ["critical", "severe", "failed", "crash", "oom"]):
            return "critical"
        elif any(word in text_lower for word in ["high", "significant", "major"]):
            return "high"
        elif any(word in text_lower for word in ["warning", "moderate", "medium"]):
            return "medium"
        elif any(word in text_lower for word in ["low", "minor", "small"]):
            return "low"
        else:
            return "info"
    
    def _build_executive_summary(
        self, 
        problem_type: ProblemType,
        agent_responses: Dict[str, AgentResponse],
        context: AgentContext
    ) -> str:
        """Build a high-level executive summary."""
        summaries = [r.summary for r in agent_responses.values()]
        
        if problem_type == ProblemType.PERFORMANCE:
            prefix = "Performance Analysis: "
        elif problem_type == ProblemType.LINEAGE:
            prefix = "Query Analysis: "
        else:
            prefix = "Comprehensive Analysis: "
        
        # Combine summaries
        combined = " ".join(summaries)
        
        # Add context about findings
        finding_count = len(context.get_findings())
        if finding_count > 0:
            combined += f" ({finding_count} key findings identified)"
        
        return prefix + combined
    
    def _build_detailed_analysis(self, agent_responses: Dict[str, AgentResponse]) -> str:
        """Build detailed analysis from all agent responses."""
        sections = []
        
        for agent_type, response in agent_responses.items():
            section = f"## {response.agent_name}\n\n{response.explanation}"
            sections.append(section)
        
        return "\n\n---\n\n".join(sections)
