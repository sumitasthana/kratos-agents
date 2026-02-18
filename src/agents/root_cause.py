# """
# Root Cause Analysis Agent.

# Analyzes Spark execution anomalies and metrics to identify root causes
# of performance issues. Uses LangChain for LLM interactions.

# Helps users understand:
# - Why tasks failed or were slow
# - What caused memory spills
# - Sources of data skew
# - Executor failures and their impact
# - Correlation between anomalies and configuration
# """

# import logging
# import time
# from typing import Any, Dict, List, Optional

# from langgraph.graph import StateGraph, END

# from .base import BaseAgent, AgentResponse, AgentType, LLMConfig, AgentState

# logger = logging.getLogger(__name__)


# ROOT_CAUSE_PROMPT = """You are a Spark performance expert specializing in root cause analysis.

# Your task is to analyze a Spark execution fingerprint and identify the root causes of any performance issues or anomalies.

# Guidelines:
# 1. Start with a brief assessment of overall execution health
# 2. For each anomaly or issue detected, explain:
#    - What happened (the symptom)
#    - Why it happened (the root cause)
#    - The impact on execution
#    - Recommended fix or mitigation
# 3. Correlate issues with configuration when relevant (e.g., spill due to low executor memory)
# 4. Prioritize issues by severity and impact
# 5. If no significant issues are found, confirm the execution was healthy

# Focus areas:
# - **Task Failures**: Why did tasks fail? Retries? Data issues?
# - **Memory Pressure**: Spill to disk indicates insufficient memory
# - **Data Skew**: Uneven partition sizes cause stragglers
# - **Shuffle Overhead**: Large shuffles indicate potential optimization opportunities
# - **GC Pressure**: High GC time indicates memory configuration issues
# - **Executor Loss**: Why did executors die?

# Output format:
# - **Health Assessment**: Overall status (Healthy / Warning / Critical)
# - **Issues Found**: List of issues with root cause analysis
# - **Correlations**: How issues relate to each other or configuration
# - **Recommendations**: Prioritized fixes

# Be specific and actionable. Reference actual metrics from the fingerprint."""


# class RootCauseAgent(BaseAgent):
#     """
#     Agent that performs root cause analysis on Spark execution issues.
    
#     Analyzes:
#     - Anomalies detected in metrics layer
#     - Task/stage failure patterns
#     - Memory pressure indicators (spill)
#     - Data skew patterns
#     - Configuration mismatches
    
#     Produces actionable root cause explanations.
#     """
    
#     @property
#     def agent_type(self) -> AgentType:
#         return AgentType.ROOT_CAUSE
    
#     @property
#     def agent_name(self) -> str:
#         return "Root Cause Analysis Agent"
    
#     @property
#     def description(self) -> str:
#         return "Identifies root causes of Spark execution anomalies and performance issues"
    
#     @property
#     def system_prompt(self) -> str:
#         return ROOT_CAUSE_PROMPT

#     def plan(
#         self,
#         fingerprint_data: Dict[str, Any],
#         context: Optional[Any] = None,
#         focus_areas: Optional[List[str]] = None,
#         **kwargs
#     ) -> List[str]:
#         steps = [
#             "Extract metrics + execution summary from fingerprint",
#             "Scan anomalies (failures, spills, skew, shuffle, executor loss)",
#         ]
#         if focus_areas:
#             steps.append(f"Apply focus areas: {', '.join(focus_areas)}")
#         steps.extend(
#             [
#                 "Build root-cause context (metrics + correlations)",
#                 "Call LLM to propose root causes + mitigations",
#                 "Parse response into prioritized findings",
#             ]
#         )
#         return steps
    
#     async def analyze(
#         self, 
#         fingerprint_data: Dict[str, Any],
#         context: Optional[Any] = None,
#         focus_areas: Optional[List[str]] = None,
#         **kwargs
#     ) -> AgentResponse:
#         """
#         Analyze fingerprint for root causes of issues.
        
#         Args:
#             fingerprint_data: Full fingerprint or metrics layer
#             context: Optional AgentContext for coordinated analysis
#             focus_areas: Optional list of areas to focus on (e.g., ["spill", "skew"])
            
#         Returns:
#             AgentResponse with root cause analysis
#         """
#         logger.info(f"[RCA] === Starting Root Cause Analysis ===")
#         if focus_areas:
#             logger.info(f"[RCA] Focus areas: {', '.join(focus_areas)}")
#         start_time = time.time()
        
#         try:
#             # Extract relevant data
#             logger.info("[RCA] Step 1/4: Extracting metrics and context from fingerprint...")
#             metrics = self._extract_metrics(fingerprint_data)
#             context = self._extract_context(fingerprint_data)
            
#             if not metrics:
#                 logger.error("[RCA] No metrics data found in fingerprint")
#                 return self._create_error_response("No metrics data found in fingerprint")
            
#             # Log execution summary
#             exec_summary = metrics.get("execution_summary", {})
#             logger.info(f"[RCA] Execution summary:")
#             logger.info(f"[RCA]   - Total tasks: {exec_summary.get('total_tasks', 0)}")
#             logger.info(f"[RCA]   - Failed tasks: {exec_summary.get('failed_task_count', 0)}")
#             logger.info(f"[RCA]   - Total spill: {exec_summary.get('total_spill_bytes', 0):,} bytes")
#             logger.info(f"[RCA]   - Total shuffle: {exec_summary.get('total_shuffle_bytes', 0):,} bytes")
            
#             anomalies = metrics.get("anomalies", [])
#             logger.info(f"[RCA] Step 2/4: Analyzing {len(anomalies)} detected anomalies...")
#             for i, a in enumerate(anomalies, 1):
#                 logger.info(f"[RCA]   Anomaly {i}: [{a.get('severity', 'unknown').upper()}] {a.get('anomaly_type')}: {a.get('description', '')[:50]}")
            
#             # Build context for LLM
#             logger.info("[RCA] Step 3/4: Building analysis context for LLM...")
#             analysis_context = self._build_context(metrics, context, focus_areas)
#             logger.info(f"[RCA] Context includes: {', '.join(analysis_context.keys())}")
            
#             # Call LLM for interpretation
#             user_prompt = self._build_user_prompt(analysis_context)
#             logger.info(f"[RCA] Step 4/4: Calling LLM for root cause interpretation...")
#             llm_response = await self._call_llm(ROOT_CAUSE_PROMPT, user_prompt)
            
#             # Parse response into structured format
#             logger.info("[RCA] Parsing LLM response into structured findings...")
#             response = self._parse_llm_response(llm_response, start_time, analysis_context)
            
#             elapsed = time.time() - start_time
#             logger.info(f"[RCA] === Analysis Complete ===")
#             logger.info(f"[RCA] Total time: {elapsed:.2f}s")
#             logger.info(f"[RCA] Findings: {len(response.key_findings)}")
#             logger.info(f"[RCA] Confidence: {response.confidence:.0%}")
#             return response
            
#         except Exception as e:
#             logger.exception(f"Error during root cause analysis: {e}")
#             return self._create_error_response(str(e))
    
#     def _extract_metrics(self, fingerprint_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
#         """Extract metrics layer from fingerprint data."""
#         if "metrics" in fingerprint_data:
#             return fingerprint_data["metrics"]
#         elif "execution_summary" in fingerprint_data:
#             return fingerprint_data
#         return None
    
#     def _extract_context(self, fingerprint_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
#         """Extract context layer for correlation analysis."""
#         return fingerprint_data.get("context")
    
#     def _build_context(
#         self, 
#         metrics: Dict[str, Any],
#         context: Optional[Dict[str, Any]],
#         focus_areas: Optional[List[str]]
#     ) -> Dict[str, Any]:
#         """Build context dict for LLM prompt."""
#         analysis = {
#             "execution_summary": metrics.get("execution_summary", {}),
#             "anomalies": metrics.get("anomalies", []),
#             "kpis": metrics.get("key_performance_indicators", {}),
#         }
        
#         # Add stage metrics summary
#         stage_metrics = metrics.get("stage_metrics", [])
#         if stage_metrics:
#             analysis["stage_summary"] = self._summarize_stages(stage_metrics)
        
#         # Add task distribution highlights
#         task_dist = metrics.get("task_distribution", {})
#         if task_dist:
#             analysis["task_distribution"] = self._extract_distribution_highlights(task_dist)
        
#         # Add context for correlation
#         if context:
#             analysis["configuration"] = {
#                 "executor_memory_mb": context.get("executor_config", {}).get("executor_memory_mb"),
#                 "executor_cores": context.get("executor_config", {}).get("executor_cores"),
#                 "total_executors": context.get("executor_config", {}).get("total_executors"),
#                 "spark_version": context.get("spark_config", {}).get("spark_version"),
#                 "optimizations": context.get("optimizations_enabled", []),
#             }
        
#         if focus_areas:
#             analysis["focus_areas"] = focus_areas
        
#         return analysis
    
#     def _summarize_stages(self, stage_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#         """Create concise stage summaries highlighting issues."""
#         summaries = []
#         for stage in stage_metrics:
#             summary = {
#                 "stage_id": stage.get("stage_id"),
#                 "num_tasks": stage.get("num_tasks"),
#                 "failed_tasks": stage.get("num_failed_tasks", 0),
#                 "spill_bytes": stage.get("spill_bytes", 0),
#                 "shuffle_read": stage.get("shuffle_read_bytes", 0),
#                 "shuffle_write": stage.get("shuffle_write_bytes", 0),
#             }
            
#             # Flag problematic stages
#             if summary["failed_tasks"] > 0:
#                 summary["issue"] = "task_failures"
#             elif summary["spill_bytes"] > 100_000_000:  # 100MB
#                 summary["issue"] = "high_spill"
            
#             summaries.append(summary)
#         return summaries
    
#     def _extract_distribution_highlights(self, task_dist: Dict[str, Any]) -> Dict[str, Any]:
#         """Extract key distribution metrics that indicate issues."""
#         highlights = {}
        
#         for metric_name, stats in task_dist.items():
#             if not isinstance(stats, dict):
#                 continue
            
#             # Check for skew (high max vs median ratio)
#             p50 = stats.get("p50", 0)
#             max_val = stats.get("max_val", 0)
#             if p50 > 0 and max_val > p50 * 10:
#                 highlights[metric_name] = {
#                     "skew_ratio": max_val / p50,
#                     "median": p50,
#                     "max": max_val,
#                     "outliers": stats.get("outlier_count", 0),
#                 }
        
#         return highlights
    
#     def _build_user_prompt(self, context: Dict[str, Any]) -> str:
#         """Build the user prompt with context data."""
#         prompt_parts = [
#             "Analyze this Spark execution for root causes of any issues:\n"
#         ]
        
#         # Execution summary
#         summary = context.get("execution_summary", {})
#         prompt_parts.append("\n**Execution Summary**:\n")
#         prompt_parts.append(f"- Duration: {summary.get('total_duration_ms', 0)}ms\n")
#         prompt_parts.append(f"- Total Tasks: {summary.get('total_tasks', 0)}\n")
#         prompt_parts.append(f"- Failed Tasks: {summary.get('failed_task_count', 0)}\n")
#         prompt_parts.append(f"- Total Spill: {summary.get('total_spill_bytes', 0):,} bytes\n")
#         prompt_parts.append(f"- Total Shuffle: {summary.get('total_shuffle_bytes', 0):,} bytes\n")
#         prompt_parts.append(f"- Executor Losses: {summary.get('executor_loss_count', 0)}\n")
        
#         # Anomalies
#         anomalies = context.get("anomalies", [])
#         if anomalies:
#             prompt_parts.append(f"\n**Detected Anomalies** ({len(anomalies)}):\n")
#             for a in anomalies:
#                 prompt_parts.append(
#                     f"- [{a.get('severity', 'unknown').upper()}] {a.get('anomaly_type')}: "
#                     f"{a.get('description')}\n"
#                 )
#                 if a.get("affected_stages"):
#                     prompt_parts.append(f"  Affected stages: {a['affected_stages']}\n")
#         else:
#             prompt_parts.append("\n**Detected Anomalies**: None\n")
        
#         # Task distribution issues
#         dist_highlights = context.get("task_distribution", {})
#         if dist_highlights:
#             prompt_parts.append("\n**Distribution Issues**:\n")
#             for metric, data in dist_highlights.items():
#                 prompt_parts.append(
#                     f"- {metric}: skew ratio {data['skew_ratio']:.1f}x "
#                     f"(median: {data['median']}, max: {data['max']}, outliers: {data['outliers']})\n"
#                 )
        
#         # Configuration context
#         config = context.get("configuration", {})
#         if config:
#             prompt_parts.append("\n**Configuration**:\n")
#             prompt_parts.append(f"- Executors: {config.get('total_executors')} × {config.get('executor_memory_mb')}MB × {config.get('executor_cores')} cores\n")
#             prompt_parts.append(f"- Spark Version: {config.get('spark_version')}\n")
#             if config.get("optimizations"):
#                 prompt_parts.append(f"- Optimizations: {', '.join(config['optimizations'])}\n")
        
#         # Focus areas
#         if context.get("focus_areas"):
#             prompt_parts.append(f"\n**Focus Areas**: {', '.join(context['focus_areas'])}\n")
        
#         return "".join(prompt_parts)
    
#     def _parse_llm_response(
#         self, 
#         llm_response: str, 
#         start_time: float,
#         context: Dict[str, Any]
#     ) -> AgentResponse:
#         """Parse LLM response into structured AgentResponse."""
#         processing_time = int((time.time() - start_time) * 1000)
        
#         # Extract sections from response
#         lines = llm_response.strip().split("\n")
#         summary = ""
#         key_findings = []
        
#         # Determine health status from anomalies
#         anomalies = context.get("anomalies", [])
#         exec_summary = context.get("execution_summary", {})
        
#         if exec_summary.get("failed_task_count", 0) > 0 or any(a.get("severity") == "critical" for a in anomalies):
#             health = "Critical"
#         elif anomalies or exec_summary.get("total_spill_bytes", 0) > 0:
#             health = "Warning"
#         else:
#             health = "Healthy"
        
#         # Parse summary from response
#         in_summary = False
#         for line in lines:
#             line_lower = line.lower().strip()
#             if "health assessment" in line_lower or "summary" in line_lower:
#                 in_summary = True
#                 if ":" in line:
#                     summary = line.split(":", 1)[1].strip()
#                 continue
#             elif line.startswith("**") and in_summary:
#                 in_summary = False
#             elif in_summary and line.strip():
#                 summary += " " + line.strip()
            
#             # Extract bullet points as key findings
#             if line.strip().startswith("- ") or line.strip().startswith("• "):
#                 finding = line.strip()[2:].strip()
#                 if finding and len(finding) > 10:
#                     key_findings.append(finding)
        
#         # Fallback summary
#         if not summary:
#             summary = f"Execution health: {health}. {len(anomalies)} anomalies detected."
        
#         # Determine suggested followup agents
#         followup = []
#         if anomalies or exec_summary.get("total_spill_bytes", 0) > 0:
#             followup.append(AgentType.OPTIMIZATION)
        
#         return AgentResponse(
#             agent_type=self.agent_type,
#             agent_name=self.agent_name,
#             success=True,
#             summary=summary.strip(),
#             explanation=llm_response,
#             key_findings=key_findings[:10],
#             confidence=0.85,
#             processing_time_ms=processing_time,
#             model_used=self.llm_config.model,
#             suggested_followup_agents=followup
#         )
    
#     async def analyze_without_llm(self, fingerprint_data: Dict[str, Any]) -> AgentResponse:
#         """
#         Analyze fingerprint using only rule-based extraction (no LLM call).
#         """
#         start_time = time.time()
        
#         try:
#             metrics = self._extract_metrics(fingerprint_data)
#             context = self._extract_context(fingerprint_data)
            
#             if not metrics:
#                 return self._create_error_response("No metrics data found")
            
#             explanation_parts = []
#             key_findings = []
            
#             # Analyze execution summary
#             summary = metrics.get("execution_summary", {})
#             failed_tasks = summary.get("failed_task_count", 0)
#             spill_bytes = summary.get("total_spill_bytes", 0)
#             shuffle_bytes = summary.get("total_shuffle_bytes", 0)
            
#             # Determine health
#             if failed_tasks > 0:
#                 health = "Critical"
#                 key_findings.append(f"{failed_tasks} task failures detected")
#             elif spill_bytes > 0:
#                 health = "Warning"
#                 key_findings.append(f"Memory spill detected: {spill_bytes:,} bytes")
#             else:
#                 health = "Healthy"
            
#             explanation_parts.append(f"**Health Assessment**: {health}")
            
#             # Analyze anomalies
#             anomalies = metrics.get("anomalies", [])
#             if anomalies:
#                 explanation_parts.append(f"\n**Anomalies Detected**: {len(anomalies)}")
#                 for a in anomalies:
#                     explanation_parts.append(f"- [{a.get('severity', 'unknown').upper()}] {a.get('description')}")
#                     key_findings.append(a.get('description', 'Unknown anomaly'))
            
#             # Configuration correlation
#             if context and spill_bytes > 0:
#                 exec_mem = context.get("executor_config", {}).get("executor_memory_mb", 0)
#                 if exec_mem > 0:
#                     explanation_parts.append(f"\n**Configuration Correlation**:")
#                     explanation_parts.append(f"- Executor memory: {exec_mem}MB - may be insufficient given spill volume")
#                     key_findings.append(f"Consider increasing executor memory (currently {exec_mem}MB)")
            
#             processing_time = int((time.time() - start_time) * 1000)
            
#             return AgentResponse(
#                 agent_type=self.agent_type,
#                 agent_name=self.agent_name,
#                 success=True,
#                 summary=f"Execution health: {health}. {len(anomalies)} anomalies, {failed_tasks} failures, {spill_bytes:,} bytes spilled.",
#                 explanation="\n".join(explanation_parts),
#                 key_findings=key_findings,
#                 confidence=0.6,
#                 processing_time_ms=processing_time,
#                 suggested_followup_agents=[AgentType.OPTIMIZATION] if health != "Healthy" else []
#             )
            
#         except Exception as e:
#             return self._create_error_response(str(e))
"""
Root Cause Analysis Agent - Extended for GRC Compliance

Now supports TWO modes:
1. Spark Performance RCA (existing)
2. GRC Compliance RCA (new - Component E)
"""

import logging
import time
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, asdict

from .base import BaseAgent, AgentResponse, AgentType, LLMConfig, AgentState

logger = logging.getLogger(__name__)

# ============================================================================
# NEW: GRC Compliance RCA Types
# ============================================================================

class IncidentType(Enum):
    """Types of incidents that trigger GRC RCA"""
    AUDIT_FINDING = "audit_finding"
    REGULATORY_ISSUE = "regulatory_issue"
    DATA_QUALITY_BREACH = "data_quality_breach"
    CONTROL_FAILURE = "control_failure"
    PRODUCTION_INCIDENT = "production_incident"
    # Existing Spark performance incidents
    SPARK_PERFORMANCE = "spark_performance"

class RootCauseCategory(Enum):
    """GRC-specific root cause categories"""
    DATA_PIPELINE = "data_pipeline_issue"
    CONTROL_DESIGN = "control_design_issue"
    CONTROL_EXECUTION = "control_execution_issue"
    PROCESS_ISSUE = "process_issue"
    # Existing Spark categories
    PERFORMANCE = "performance_issue"
    CONFIGURATION = "configuration_issue"

@dataclass
class HealthScore:
    """
    Health score with confidence for GRC compliance reporting.
    
    Formula:
    - Base: 100 points
    - Task Failures: -40 pts (critical)
    - Memory Issues: -25 pts (high)
    - Shuffle Overhead: -20 pts (medium)
    - Data Skew: -15 pts (medium)
    """
    overall_score: float  # 0-100
    confidence: float     # 0-1
    severity: str         # CRITICAL, HIGH, MEDIUM, LOW
    status: str           # HEALTHY, WARNING, CRITICAL
    breakdown: Dict[str, float]  # Component scores
    
    @classmethod
    def calculate_from_spark_metrics(cls, metrics: Dict[str, Any]) -> 'HealthScore':
        """Calculate health score from Spark fingerprint metrics"""
        exec_summary = metrics.get("execution_summary", {})
        
        # Component penalties
        task_failure_penalty = cls._calc_task_failure_penalty(exec_summary)
        memory_penalty = cls._calc_memory_penalty(exec_summary)
        shuffle_penalty = cls._calc_shuffle_penalty(exec_summary)
        skew_penalty = cls._calc_skew_penalty(metrics)
        
        breakdown = {
            "task_failures": task_failure_penalty,
            "memory_pressure": memory_penalty,
            "shuffle_overhead": shuffle_penalty,
            "data_skew": skew_penalty
        }
        
        overall_score = max(0, 100 - sum(breakdown.values()))
        
        # Map to severity and status
        severity = cls._map_score_to_severity(overall_score)
        status = cls._map_score_to_status(overall_score)
        
        # Calculate confidence based on data completeness
        confidence = cls._calc_confidence(metrics)
        
        return cls(
            overall_score=round(overall_score, 1),
            confidence=round(confidence, 2),
            severity=severity,
            status=status,
            breakdown=breakdown
        )
    
    @staticmethod
    def _calc_task_failure_penalty(exec_summary: Dict) -> float:
        """Up to 40 points for task failures"""
        failed = exec_summary.get("failed_task_count", 0)
        total = exec_summary.get("total_tasks", 1)
        failure_rate = failed / total if total > 0 else 0
        
        if failure_rate > 0.5:
            return 40.0
        elif failure_rate > 0.2:
            return 30.0
        elif failure_rate > 0.1:
            return 20.0
        elif failure_rate > 0:
            return 10.0
        return 0.0
    
    @staticmethod
    def _calc_memory_penalty(exec_summary: Dict) -> float:
        """Up to 25 points for memory issues"""
        spill_bytes = exec_summary.get("total_spill_bytes", 0)
        spill_gb = spill_bytes / (1024**3)
        
        if spill_gb > 50:
            return 25.0
        elif spill_gb > 20:
            return 20.0
        elif spill_gb > 5:
            return 15.0
        elif spill_gb > 0:
            return 10.0
        return 0.0
    
    @staticmethod
    def _calc_shuffle_penalty(exec_summary: Dict) -> float:
        """Up to 20 points for shuffle overhead"""
        shuffle_bytes = exec_summary.get("total_shuffle_bytes", 0)
        shuffle_gb = shuffle_bytes / (1024**3)
        
        if shuffle_gb > 100:
            return 20.0
        elif shuffle_gb > 50:
            return 15.0
        elif shuffle_gb > 20:
            return 10.0
        elif shuffle_gb > 5:
            return 5.0
        return 0.0
    
    @staticmethod
    def _calc_skew_penalty(metrics: Dict) -> float:
        """Up to 15 points for data skew"""
        task_dist = metrics.get("task_distribution", {})
        max_skew_ratio = 1.0
        
        # Find max skew ratio across all metrics
        for metric_stats in task_dist.values():
            if isinstance(metric_stats, dict):
                p50 = metric_stats.get("p50", 0)
                max_val = metric_stats.get("max_val", 0)
                if p50 > 0:
                    skew_ratio = max_val / p50
                    max_skew_ratio = max(max_skew_ratio, skew_ratio)
        
        if max_skew_ratio > 50:
            return 15.0
        elif max_skew_ratio > 20:
            return 12.0
        elif max_skew_ratio > 10:
            return 8.0
        elif max_skew_ratio > 5:
            return 5.0
        return 0.0
    
    @staticmethod
    def _map_score_to_severity(score: float) -> str:
        if score < 40:
            return "CRITICAL"
        elif score < 60:
            return "HIGH"
        elif score < 80:
            return "MEDIUM"
        return "LOW"
    
    @staticmethod
    def _map_score_to_status(score: float) -> str:
        if score >= 80:
            return "HEALTHY"
        elif score >= 60:
            return "WARNING"
        return "CRITICAL"
    
    @staticmethod
    def _calc_confidence(metrics: Dict) -> float:
        """Confidence based on data completeness"""
        required_fields = ["execution_summary", "anomalies", "key_performance_indicators"]
        present = sum(1 for f in required_fields if metrics.get(f))
        
        base_confidence = present / len(required_fields)
        
        # Boost if we have task-level data
        exec_summary = metrics.get("execution_summary", {})
        if exec_summary.get("total_tasks", 0) > 0:
            base_confidence = min(1.0, base_confidence * 1.2)
        
        return base_confidence

@dataclass
class ErrorMapping:
    """Structured error categorization for GRC compliance"""
    memory_errors: List[Dict[str, Any]]
    data_quality_errors: List[Dict[str, Any]]
    configuration_errors: List[Dict[str, Any]]
    execution_errors: List[Dict[str, Any]]
    
    @classmethod
    def from_metrics(cls, metrics: Dict[str, Any]) -> 'ErrorMapping':
        """Extract and categorize errors from metrics"""
        exec_summary = metrics.get("execution_summary", {})
        anomalies = metrics.get("anomalies", [])
        
        memory_errors = []
        data_quality_errors = []
        config_errors = []
        execution_errors = []
        
        # Categorize from execution summary
        spill_bytes = exec_summary.get("total_spill_bytes", 0)
        if spill_bytes > 0:
            memory_errors.append({
                "type": "MEMORY_SPILL",
                "severity": "HIGH" if spill_bytes > 20*1024**3 else "MEDIUM",
                "detail": f"{spill_bytes/(1024**3):.2f}GB spilled to disk",
                "impact": "Performance degradation due to disk I/O"
            })
        
        failed_tasks = exec_summary.get("failed_task_count", 0)
        if failed_tasks > 0:
            execution_errors.append({
                "type": "TASK_FAILURE",
                "severity": "CRITICAL",
                "detail": f"{failed_tasks} tasks failed",
                "impact": "Job completion blocked or delayed"
            })
        
        # Categorize from anomalies
        for anomaly in anomalies:
            anom_type = anomaly.get("anomaly_type", "").lower()
            severity = anomaly.get("severity", "medium").upper()
            description = anomaly.get("description", "")
            
            if "skew" in anom_type or "partition" in anom_type:
                data_quality_errors.append({
                    "type": "DATA_SKEW",
                    "severity": severity,
                    "detail": description,
                    "impact": "Uneven task execution causing stragglers"
                })
            elif "memory" in anom_type or "spill" in anom_type:
                memory_errors.append({
                    "type": "MEMORY_PRESSURE",
                    "severity": severity,
                    "detail": description,
                    "impact": "Insufficient memory allocation"
                })
            elif "config" in anom_type:
                config_errors.append({
                    "type": "CONFIGURATION_ISSUE",
                    "severity": severity,
                    "detail": description,
                    "impact": "Suboptimal resource allocation"
                })
            else:
                execution_errors.append({
                    "type": "EXECUTION_ANOMALY",
                    "severity": severity,
                    "detail": description,
                    "impact": "Runtime execution issue"
                })
        
        return cls(
            memory_errors=memory_errors,
            data_quality_errors=data_quality_errors,
            configuration_errors=config_errors,
            execution_errors=execution_errors
        )
    
    def total_error_count(self) -> int:
        return (len(self.memory_errors) + 
                len(self.data_quality_errors) + 
                len(self.configuration_errors) + 
                len(self.execution_errors))
    
    def critical_count(self) -> int:
        all_errors = (self.memory_errors + self.data_quality_errors + 
                      self.configuration_errors + self.execution_errors)
        return sum(1 for e in all_errors if e.get("severity") == "CRITICAL")

@dataclass
class PerformanceMatrix:
    """Performance evaluation matrix for regulatory reporting"""
    execution_metrics: Dict[str, Any]
    resource_metrics: Dict[str, Any]
    data_metrics: Dict[str, Any]
    bottlenecks: List[Dict[str, Any]]
    
    @classmethod
    def from_metrics(cls, metrics: Dict[str, Any]) -> 'PerformanceMatrix':
        """Build performance matrix from fingerprint metrics"""
        exec_summary = metrics.get("execution_summary", {})
        
        # Execution metrics
        total_tasks = exec_summary.get("total_tasks", 0)
        failed_tasks = exec_summary.get("failed_task_count", 0)
        success_rate = ((total_tasks - failed_tasks) / total_tasks * 100) if total_tasks > 0 else 0
        
        execution_metrics = {
            "total_duration_sec": exec_summary.get("total_duration_ms", 0) / 1000,
            "task_success_rate": round(success_rate, 2),
            "total_tasks": total_tasks,
            "failed_tasks": failed_tasks
        }
        
        # Resource metrics
        spill_bytes = exec_summary.get("total_spill_bytes", 0)
        shuffle_bytes = exec_summary.get("total_shuffle_bytes", 0)
        
        resource_metrics = {
            "memory_utilization": cls._classify_memory_usage(spill_bytes),
            "disk_spill_gb": round(spill_bytes / (1024**3), 2),
            "shuffle_write_gb": round(shuffle_bytes / (1024**3), 2),
            "executor_losses": exec_summary.get("executor_loss_count", 0)
        }
        
        # Data metrics (from task distribution)
        task_dist = metrics.get("task_distribution", {})
        max_skew = cls._extract_max_skew(task_dist)
        
        data_metrics = {
            "max_skew_ratio": round(max_skew, 2),
            "stage_count": len(metrics.get("stage_metrics", [])),
        }
        
        # Identify bottlenecks
        bottlenecks = cls._identify_bottlenecks(exec_summary, max_skew)
        
        return cls(
            execution_metrics=execution_metrics,
            resource_metrics=resource_metrics,
            data_metrics=data_metrics,
            bottlenecks=bottlenecks
        )
    
    @staticmethod
    def _classify_memory_usage(spill_bytes: int) -> str:
        spill_gb = spill_bytes / (1024**3)
        if spill_gb > 20:
            return "OVER_CAPACITY"
        elif spill_gb > 5:
            return "HIGH"
        elif spill_gb > 0:
            return "MODERATE"
        return "OPTIMAL"
    
    @staticmethod
    def _extract_max_skew(task_dist: Dict) -> float:
        max_skew = 1.0
        for metric_stats in task_dist.values():
            if isinstance(metric_stats, dict):
                p50 = metric_stats.get("p50", 0)
                max_val = metric_stats.get("max_val", 0)
                if p50 > 0:
                    skew = max_val / p50
                    max_skew = max(max_skew, skew)
        return max_skew
    
    @staticmethod
    def _identify_bottlenecks(exec_summary: Dict, max_skew: float) -> List[Dict]:
        bottlenecks = []
        
        spill_gb = exec_summary.get("total_spill_bytes", 0) / (1024**3)
        if spill_gb > 5:
            bottlenecks.append({
                "type": "MEMORY",
                "severity": "HIGH" if spill_gb > 20 else "MEDIUM",
                "impact": "Performance degradation due to disk I/O",
                "metric_value": f"{spill_gb:.1f}GB"
            })
        
        if max_skew > 10:
            bottlenecks.append({
                "type": "DATA_SKEW",
                "severity": "HIGH" if max_skew > 20 else "MEDIUM",
                "impact": "Uneven task execution causing stragglers",
                "metric_value": f"{max_skew:.1f}x"
            })
        
        shuffle_gb = exec_summary.get("total_shuffle_bytes", 0) / (1024**3)
        if shuffle_gb > 50:
            bottlenecks.append({
                "type": "SHUFFLE",
                "severity": "MEDIUM",
                "impact": "High network overhead between executors",
                "metric_value": f"{shuffle_gb:.1f}GB"
            })
        
        return bottlenecks

@dataclass
class RemediationPlan:
    """GRC-compliant remediation recommendations"""
    root_cause_category: RootCauseCategory
    action_items: List[Dict[str, str]]
    estimated_fix_time: str
    owner_recommendation: str
    regulation_impacted: Optional[str] = None
    
    @classmethod
    def generate(
        cls,
        root_cause: RootCauseCategory,
        health_score: HealthScore,
        error_mapping: ErrorMapping,
        perf_matrix: PerformanceMatrix,
        context: Optional[Dict] = None
    ) -> 'RemediationPlan':
        """Generate remediation plan based on root cause and metrics"""
        action_items = []
        
        # Memory issues
        if perf_matrix.resource_metrics["disk_spill_gb"] > 5:
            action_items.append({
                "priority": "P0",
                "action": "Increase executor memory",
                "detail": f"Current spill: {perf_matrix.resource_metrics['disk_spill_gb']:.1f}GB",
                "recommendation": "Increase spark.executor.memory to 4g or higher",
                "regulation": "SOX (data processing integrity)"
            })
        
        # Data skew
        if perf_matrix.data_metrics["max_skew_ratio"] > 10:
            action_items.append({
                "priority": "P0",
                "action": "Fix data skew",
                "detail": f"Skew ratio: {perf_matrix.data_metrics['max_skew_ratio']:.1f}x",
                "recommendation": "Add salting or repartition by multiple columns",
                "regulation": "Data quality compliance"
            })
        
        # Task failures
        if perf_matrix.execution_metrics["failed_tasks"] > 0:
            action_items.append({
                "priority": "P0",
                "action": "Investigate task failures",
                "detail": f"{perf_matrix.execution_metrics['failed_tasks']} tasks failed",
                "recommendation": "Review executor logs and increase retry configuration",
                "regulation": "Operational resilience requirements"
            })
        
        # Estimate fix time
        p0_count = sum(1 for item in action_items if item["priority"] == "P0")
        if p0_count > 2:
            fix_time = "4-8 hours"
        elif p0_count > 0:
            fix_time = "2-4 hours"
        else:
            fix_time = "< 2 hours"
        
        # Determine owner
        owner = cls._determine_owner(root_cause)
        
        return cls(
            root_cause_category=root_cause,
            action_items=action_items,
            estimated_fix_time=fix_time,
            owner_recommendation=owner,
            regulation_impacted=cls._determine_regulation(error_mapping)
        )
    
    @staticmethod
    def _determine_owner(root_cause: RootCauseCategory) -> str:
        owner_map = {
            RootCauseCategory.DATA_PIPELINE: "Data Engineering Team",
            RootCauseCategory.CONTROL_DESIGN: "Compliance/Risk Team",
            RootCauseCategory.CONTROL_EXECUTION: "DevOps/SRE Team",
            RootCauseCategory.PROCESS_ISSUE: "Process Owner/Manager",
            RootCauseCategory.PERFORMANCE: "Data Engineering Team",
            RootCauseCategory.CONFIGURATION: "DevOps/SRE Team"
        }
        return owner_map.get(root_cause, "Engineering Manager")
    
    @staticmethod
    def _determine_regulation(error_mapping: ErrorMapping) -> str:
        if error_mapping.critical_count() > 0:
            return "SOX, GDPR (data integrity)"
        elif error_mapping.data_quality_errors:
            return "Data Quality Standards"
        return "Operational Standards"

@dataclass
class RoutingInstructions:
    """Instructions for routing RCA results back to GRC components"""
    destination: str
    create_ticket: bool
    notify: List[str]
    feedback_to: List[str]
    control_id: Optional[str] = None
    
    @classmethod
    def determine(
        cls,
        root_cause: RootCauseCategory,
        incident_type: IncidentType,
        severity: str
    ) -> 'RoutingInstructions':
        """Determine routing based on root cause and incident type"""
        
        routing_map = {
            RootCauseCategory.DATA_PIPELINE: {
                "destination": "ETL_TEAM",
                "create_ticket": True,
                "notify": ["data-engineering@company.com"],
                "feedback_to": ["Control Hub (D)", "Lineage Tool"]
            },
            RootCauseCategory.CONTROL_DESIGN: {
                "destination": "DISCOVERY_A",
                "create_ticket": True,
                "notify": ["compliance@company.com", "risk@company.com"],
                "feedback_to": ["Discovery (A)", "Control Hub (D)"]
            },
            RootCauseCategory.CONTROL_EXECUTION: {
                "destination": "CONTROL_HUB_D",
                "create_ticket": True,
                "notify": ["devops@company.com"],
                "feedback_to": ["Control Hub (D)"]
            },
            RootCauseCategory.PROCESS_ISSUE: {
                "destination": "PROCESS_OWNER",
                "create_ticket": True,
                "notify": ["operations@company.com"],
                "feedback_to": ["Process Documentation"]
            },
            RootCauseCategory.PERFORMANCE: {
                "destination": "DATA_ENGINEERING",
                "create_ticket": severity in ["CRITICAL", "HIGH"],
                "notify": ["data-engineering@company.com"],
                "feedback_to": ["Performance Monitoring"]
            }
        }
        
        default_routing = {
            "destination": "ENGINEERING_MANAGER",
            "create_ticket": True,
            "notify": ["engineering@company.com"],
            "feedback_to": ["Control Hub (D)"]
        }
        
        return cls(**(routing_map.get(root_cause, default_routing)))

# ============================================================================
# EXISTING: Spark Performance RCA Prompts
# ============================================================================

ROOT_CAUSE_PROMPT = """You are a Spark performance expert specializing in root cause analysis.

Your task is to analyze a Spark execution fingerprint and identify the root causes of any performance issues or anomalies.

Guidelines:
1. Start with a brief assessment of overall execution health
2. For each anomaly or issue detected, explain:
   - What happened (the symptom)
   - Why it happened (the root cause)
   - The impact on execution
   - Recommended fix or mitigation
3. Correlate issues with configuration when relevant (e.g., spill due to low executor memory)
4. Prioritize issues by severity and impact
5. If no significant issues are found, confirm the execution was healthy

Focus areas:
- **Task Failures**: Why did tasks fail? Retries? Data issues?
- **Memory Pressure**: Spill to disk indicates insufficient memory
- **Data Skew**: Uneven partition sizes cause stragglers
- **Shuffle Overhead**: Large shuffles indicate potential optimization opportunities
- **GC Pressure**: High GC time indicates memory configuration issues
- **Executor Loss**: Why did executors die?

Output format:
- **Health Assessment**: Overall status (Healthy / Warning / Critical)
- **Issues Found**: List of issues with root cause analysis
- **Correlations**: How issues relate to each other or configuration
- **Recommendations**: Prioritized fixes

Be specific and actionable. Reference actual metrics from the fingerprint."""

# NEW: GRC Compliance RCA Prompt
GRC_RCA_PROMPT = """You are a data governance and compliance expert specializing in root cause analysis for regulatory incidents.

Your task is to analyze a data pipeline incident and identify root causes from a compliance perspective.

Guidelines:
1. Classify the root cause into ONE category:
   - Data Pipeline Issue (ETL, ingestion, transformation, lineage problems)
   - Control Design Issue (missing or incorrect validation logic)
   - Control Execution Issue (job failure, threshold misconfiguration)
   - Process Issue (manual dependency, timing, ownership gaps)

2. For each issue, explain:
   - What control failed and why
   - The regulatory impact (which regulations/policies affected)
   - Data integrity or quality impact
   - Downstream systems affected

3. Assess compliance risk:
   - Severity (CRITICAL/HIGH/MEDIUM/LOW)
   - Duration of the issue
   - Scope (how many systems/controls affected)
   - Consumer/stakeholder impact

4. Provide regulatory-grade remediation:
   - Immediate containment actions
   - Root cause fix with timeline
   - Preventive controls to add
   - Documentation requirements

Output format:
- **Incident Classification**: Control failure / Data breach / Process gap
- **Root Cause Category**: One of the four categories above
- **Regulatory Impact**: Which regulations/policies are violated
- **Remediation Plan**: Prioritized actions with owners and timelines
- **Preventive Measures**: New controls or processes needed

Reference specific metrics, error types, and compliance requirements."""


class RootCauseAgent(BaseAgent):
    """
    Dual-mode Root Cause Analysis Agent.
    
    Mode 1: Spark Performance RCA (existing functionality)
    Mode 2: GRC Compliance RCA (Component E - new)
    
    Automatically detects mode based on input parameters.
    """
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.ROOT_CAUSE
    
    @property
    def agent_name(self) -> str:
        return "Root Cause Analysis Agent"
    
    @property
    def description(self) -> str:
        return "Identifies root causes of Spark execution and GRC compliance incidents"
    
    @property
    def system_prompt(self) -> str:
        # Default to Spark performance prompt
        return ROOT_CAUSE_PROMPT
    
    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        incident_type: Optional[IncidentType] = None,
        **kwargs
    ) -> List[str]:
        """Generate analysis plan based on mode"""
        
        # Detect mode
        is_grc_mode = incident_type and incident_type != IncidentType.SPARK_PERFORMANCE
        
        if is_grc_mode:
            steps = [
                "Extract metrics + execution summary from fingerprint",
                "Calculate health score (0-100) with confidence",
                "Map errors to compliance categories",
                "Generate performance matrix for regulatory reporting",
                "Classify root cause (4 GRC categories)",
                "Build remediation plan with owner assignment",
                "Determine routing (Control Hub D / Discovery A)",
                "Generate executive summary for compliance reporting"
            ]
        else:
            # Existing Spark performance plan
            steps = [
                "Extract metrics + execution summary from fingerprint",
                "Scan anomalies (failures, spills, skew, shuffle, executor loss)",
            ]
            if focus_areas:
                steps.append(f"Apply focus areas: {', '.join(focus_areas)}")
            steps.extend([
                "Build root-cause context (metrics + correlations)",
                "Call LLM to propose root causes + mitigations",
                "Parse response into prioritized findings",
            ])
        
        return steps
    
    async def analyze(
        self, 
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        incident_type: Optional[IncidentType] = None,
        **kwargs
    ) -> AgentResponse:
        """
        Analyze fingerprint for root causes.
        
        Automatically routes to:
        - GRC mode if incident_type is provided (Component E)
        - Spark performance mode otherwise (existing)
        """
        
        # Detect mode
        is_grc_mode = incident_type and incident_type != IncidentType.SPARK_PERFORMANCE
        
        if is_grc_mode:
            return await self._analyze_grc_compliance(
                fingerprint_data, 
                incident_type, 
                context, 
                **kwargs
            )
        else:
            return await self._analyze_spark_performance(
                fingerprint_data,
                context,
                focus_areas,
                **kwargs
            )
    
    # ========================================================================
    # NEW: GRC Compliance RCA Mode
    # ========================================================================
    
    async def _analyze_grc_compliance(
        self,
        fingerprint_data: Dict[str, Any],
        incident_type: IncidentType,
        context: Optional[Any] = None,
        **kwargs
    ) -> AgentResponse:
        """Component E: GRC Compliance RCA"""
        logger.info(f"[RCA-GRC] === Starting GRC Compliance RCA ===")
        logger.info(f"[RCA-GRC] Incident Type: {incident_type.value}")
        start_time = time.time()
        
        try:
            # Step 1: Extract metrics
            logger.info("[RCA-GRC] Step 1/8: Extracting metrics from fingerprint...")
            metrics = self._extract_metrics(fingerprint_data)
            if not metrics:
                return self._create_error_response("No metrics data found")
            
            # Step 2: Calculate health score
            logger.info("[RCA-GRC] Step 2/8: Calculating health score...")
            health_score = HealthScore.calculate_from_spark_metrics(metrics)
            logger.info(f"[RCA-GRC]   Score: {health_score.overall_score}/100")
            logger.info(f"[RCA-GRC]   Status: {health_score.status}")
            logger.info(f"[RCA-GRC]   Severity: {health_score.severity}")
            logger.info(f"[RCA-GRC]   Confidence: {health_score.confidence*100:.0f}%")
            
            # Step 3: Map errors
            logger.info("[RCA-GRC] Step 3/8: Mapping errors to compliance categories...")
            error_mapping = ErrorMapping.from_metrics(metrics)
            logger.info(f"[RCA-GRC]   Total errors: {error_mapping.total_error_count()}")
            logger.info(f"[RCA-GRC]   Critical: {error_mapping.critical_count()}")
            
            # Step 4: Generate performance matrix
            logger.info("[RCA-GRC] Step 4/8: Generating performance matrix...")
            perf_matrix = PerformanceMatrix.from_metrics(metrics)
            logger.info(f"[RCA-GRC]   Bottlenecks identified: {len(perf_matrix.bottlenecks)}")
            
            # Step 5: Classify root cause
            logger.info("[RCA-GRC] Step 5/8: Classifying root cause category...")
            root_cause = self._classify_grc_root_cause(
                metrics, 
                health_score, 
                error_mapping,
                incident_type
            )
            logger.info(f"[RCA-GRC]   Root Cause: {root_cause.value}")
            
            # Step 6: Generate remediation plan
            logger.info("[RCA-GRC] Step 6/8: Generating remediation plan...")
            remediation = RemediationPlan.generate(
                root_cause,
                health_score,
                error_mapping,
                perf_matrix,
                context
            )
            logger.info(f"[RCA-GRC]   Action items: {len(remediation.action_items)}")
            logger.info(f"[RCA-GRC]   Owner: {remediation.owner_recommendation}")
            logger.info(f"[RCA-GRC]   Est. fix time: {remediation.estimated_fix_time}")
            
            # Step 7: Determine routing
            logger.info("[RCA-GRC] Step 7/8: Determining routing instructions...")
            routing = RoutingInstructions.determine(
                root_cause,
                incident_type,
                health_score.severity
            )
            logger.info(f"[RCA-GRC]   Destination: {routing.destination}")
            logger.info(f"[RCA-GRC]   Feedback to: {', '.join(routing.feedback_to)}")
            
            # Step 8: Generate executive summary
            logger.info("[RCA-GRC] Step 8/8: Generating executive summary...")
            summary = self._generate_grc_executive_summary(
                incident_type,
                root_cause,
                health_score,
                error_mapping,
                remediation,
                perf_matrix
            )
            
            # Build key findings
            key_findings = []
            key_findings.append(f"Health Score: {health_score.overall_score}/100 ({health_score.status})")
            key_findings.append(f"Root Cause: {root_cause.value}")
            key_findings.append(f"{error_mapping.total_error_count()} errors detected ({error_mapping.critical_count()} critical)")
            for item in remediation.action_items[:5]:
                key_findings.append(f"[{item['priority']}] {item['action']}")
            
            elapsed = time.time() - start_time
            logger.info(f"[RCA-GRC] === Analysis Complete in {elapsed:.2f}s ===")
            
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=summary,
                explanation=self._build_grc_detailed_explanation(
                    incident_type, root_cause, health_score, 
                    error_mapping, perf_matrix, remediation, routing
                ),
                key_findings=key_findings,
                confidence=health_score.confidence,
                processing_time_ms=int(elapsed * 1000),
                model_used=self.llm_config.model if hasattr(self, 'llm_config') else "rule-based",
                metadata={
                    "incident_type": incident_type.value,
                    "root_cause_category": root_cause.value,
                    "health_score": asdict(health_score),
                    "error_mapping": {
                        "memory_errors": error_mapping.memory_errors,
                        "data_quality_errors": error_mapping.data_quality_errors,
                        "configuration_errors": error_mapping.configuration_errors,
                        "execution_errors": error_mapping.execution_errors
                    },
                    "performance_matrix": {
                        "execution": perf_matrix.execution_metrics,
                        "resource": perf_matrix.resource_metrics,
                        "data": perf_matrix.data_metrics,
                        "bottlenecks": perf_matrix.bottlenecks
                    },
                    "remediation": {
                        "action_items": remediation.action_items,
                        "estimated_fix_time": remediation.estimated_fix_time,
                        "owner": remediation.owner_recommendation,
                        "regulation_impacted": remediation.regulation_impacted
                    },
                    "routing": {
                        "destination": routing.destination,
                        "feedback_to": routing.feedback_to,
                        "notify": routing.notify
                    }
                },
                suggested_followup_agents=[AgentType.OPTIMIZATION] if health_score.status != "HEALTHY" else []
            )
            
        except Exception as e:
            logger.exception(f"[RCA-GRC] Error during GRC compliance analysis: {e}")
            return self._create_error_response(str(e))
    
    def _classify_grc_root_cause(
        self,
        metrics: Dict[str, Any],
        health_score: HealthScore,
        error_mapping: ErrorMapping,
        incident_type: IncidentType
    ) -> RootCauseCategory:
        """Classify into one of 4 GRC root cause categories"""
        
        exec_summary = metrics.get("execution_summary", {})
        
        # Decision tree for GRC classification
        
        # 1. Data Pipeline Issues (ETL, ingestion, transformation)
        if (health_score.breakdown.get("memory_pressure", 0) > 15 or
            health_score.breakdown.get("data_skew", 0) > 10 or
            health_score.breakdown.get("shuffle_overhead", 0) > 15):
            return RootCauseCategory.DATA_PIPELINE
        
        # 2. Control Execution Issues (job failed, threshold misconfigured)
        if (health_score.breakdown.get("task_failures", 0) > 20 or
            exec_summary.get("failed_task_count", 0) > 0):
            return RootCauseCategory.CONTROL_EXECUTION
        
        # 3. Control Design Issues (missing/wrong validation logic)
        if error_mapping.data_quality_errors and not error_mapping.execution_errors:
            return RootCauseCategory.CONTROL_DESIGN
        
        # 4. Process Issues (manual dependency, timing, ownership)
        return RootCauseCategory.PROCESS_ISSUE
    
    def _generate_grc_executive_summary(
        self,
        incident_type: IncidentType,
        root_cause: RootCauseCategory,
        health_score: HealthScore,
        error_mapping: ErrorMapping,
        remediation: RemediationPlan,
        perf_matrix: PerformanceMatrix
    ) -> str:
        """Generate concise executive summary for GRC compliance"""
        
        summary_lines = [
            "=" * 80,
            "INCIDENT ANALYSIS SUMMARY (GRC COMPLIANCE)",
            "=" * 80,
            "",
            f"Incident Type: {incident_type.value.replace('_', ' ').title()}",
            f"Root Cause: {root_cause.value.replace('_', ' ').title()}",
            "",
            "HEALTH ASSESSMENT",
            f"  Overall Score: {health_score.overall_score}/100",
            f"  Status: {health_score.status}",
            f"  Severity: {health_score.severity}",
            f"  Confidence: {health_score.confidence*100:.0f}%",
            "",
            "SCORE BREAKDOWN",
            f"  Task Failures: -{health_score.breakdown.get('task_failures', 0):.0f} pts",
            f"  Memory Pressure: -{health_score.breakdown.get('memory_pressure', 0):.0f} pts",
            f"  Shuffle Overhead: -{health_score.breakdown.get('shuffle_overhead', 0):.0f} pts",
            f"  Data Skew: -{health_score.breakdown.get('data_skew', 0):.0f} pts",
            "",
            "KEY FINDINGS",
            f"  Total errors: {error_mapping.total_error_count()} ({error_mapping.critical_count()} critical)",
            f"  Task success rate: {perf_matrix.execution_metrics['task_success_rate']}%",
            f"  Memory utilization: {perf_matrix.resource_metrics['memory_utilization']}",
            f"  Bottlenecks identified: {len(perf_matrix.bottlenecks)}",
            "",
            "REMEDIATION",
            f"  Estimated fix time: {remediation.estimated_fix_time}",
            f"  Owner: {remediation.owner_recommendation}",
            f"  Regulation impacted: {remediation.regulation_impacted or 'N/A'}",
            "",
            "IMMEDIATE ACTIONS"
        ]
        
        for i, action in enumerate(remediation.action_items[:3], 1):
            summary_lines.append(f"  {i}. [{action['priority']}] {action['action']}")
            summary_lines.append(f"     → {action['recommendation']}")
        
        summary_lines.append("")
        summary_lines.append("=" * 80)
        
        return "\n".join(summary_lines)
    
    def _build_grc_detailed_explanation(
        self,
        incident_type: IncidentType,
        root_cause: RootCauseCategory,
        health_score: HealthScore,
        error_mapping: ErrorMapping,
        perf_matrix: PerformanceMatrix,
        remediation: RemediationPlan,
        routing: RoutingInstructions
    ) -> str:
        """Build detailed explanation for GRC reporting"""
        
        sections = []
        
        # Error breakdown
        sections.append("**ERROR ANALYSIS**")
        if error_mapping.memory_errors:
            sections.append(f"\nMemory Errors ({len(error_mapping.memory_errors)}):")
            for err in error_mapping.memory_errors:
                sections.append(f"  - [{err['severity']}] {err['type']}: {err['detail']}")
        
        if error_mapping.data_quality_errors:
            sections.append(f"\nData Quality Errors ({len(error_mapping.data_quality_errors)}):")
            for err in error_mapping.data_quality_errors:
                sections.append(f"  - [{err['severity']}] {err['type']}: {err['detail']}")
        
        if error_mapping.execution_errors:
            sections.append(f"\nExecution Errors ({len(error_mapping.execution_errors)}):")
            for err in error_mapping.execution_errors:
                sections.append(f"  - [{err['severity']}] {err['type']}: {err['detail']}")
        
        # Performance analysis
        sections.append("\n**PERFORMANCE METRICS**")
        sections.append(f"Duration: {perf_matrix.execution_metrics['total_duration_sec']:.1f}s")
        sections.append(f"Task Success Rate: {perf_matrix.execution_metrics['task_success_rate']}%")
        sections.append(f"Memory Spill: {perf_matrix.resource_metrics['disk_spill_gb']:.2f}GB")
        sections.append(f"Shuffle Volume: {perf_matrix.resource_metrics['shuffle_write_gb']:.2f}GB")
        
        # Bottlenecks
        if perf_matrix.bottlenecks:
            sections.append("\n**BOTTLENECKS**")
            for bottleneck in perf_matrix.bottlenecks:
                sections.append(f"  - [{bottleneck['severity']}] {bottleneck['type']}: {bottleneck['impact']}")
                sections.append(f"    Value: {bottleneck['metric_value']}")
        
        # Routing
        sections.append("\n**ROUTING INSTRUCTIONS**")
        sections.append(f"Destination: {routing.destination}")
        sections.append(f"Feedback to: {', '.join(routing.feedback_to)}")
        sections.append(f"Notify: {', '.join(routing.notify)}")
        
        return "\n".join(sections)
    
    # ========================================================================
    # EXISTING: Spark Performance RCA Mode
    # ========================================================================
    
    async def _analyze_spark_performance(
        self, 
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        **kwargs
    ) -> AgentResponse:
        """Existing Spark performance RCA (unchanged)"""
        logger.info(f"[RCA] === Starting Root Cause Analysis ===")
        if focus_areas:
            logger.info(f"[RCA] Focus areas: {', '.join(focus_areas)}")
        start_time = time.time()
        
        try:
            # Extract relevant data
            logger.info("[RCA] Step 1/4: Extracting metrics and context from fingerprint...")
            metrics = self._extract_metrics(fingerprint_data)
            ctx = self._extract_context(fingerprint_data)
            
            if not metrics:
                logger.error("[RCA] No metrics data found in fingerprint")
                return self._create_error_response("No metrics data found in fingerprint")
            
            # Log execution summary
            exec_summary = metrics.get("execution_summary", {})
            logger.info(f"[RCA] Execution summary:")
            logger.info(f"[RCA]   - Total tasks: {exec_summary.get('total_tasks', 0)}")
            logger.info(f"[RCA]   - Failed tasks: {exec_summary.get('failed_task_count', 0)}")
            logger.info(f"[RCA]   - Total spill: {exec_summary.get('total_spill_bytes', 0):,} bytes")
            logger.info(f"[RCA]   - Total shuffle: {exec_summary.get('total_shuffle_bytes', 0):,} bytes")
            
            anomalies = metrics.get("anomalies", [])
            logger.info(f"[RCA] Step 2/4: Analyzing {len(anomalies)} detected anomalies...")
            for i, a in enumerate(anomalies, 1):
                logger.info(f"[RCA]   Anomaly {i}: [{a.get('severity', 'unknown').upper()}] {a.get('anomaly_type')}: {a.get('description', '')[:50]}")
            
            # Build context for LLM
            logger.info("[RCA] Step 3/4: Building analysis context for LLM...")
            analysis_context = self._build_context(metrics, ctx, focus_areas)
            logger.info(f"[RCA] Context includes: {', '.join(analysis_context.keys())}")
            
            # Call LLM for interpretation
            user_prompt = self._build_user_prompt(analysis_context)
            logger.info(f"[RCA] Step 4/4: Calling LLM for root cause interpretation...")
            llm_response = await self._call_llm(ROOT_CAUSE_PROMPT, user_prompt)
            
            # Parse response into structured format
            logger.info("[RCA] Parsing LLM response into structured findings...")
            response = self._parse_llm_response(llm_response, start_time, analysis_context, metrics, ctx)
            
            elapsed = time.time() - start_time
            logger.info(f"[RCA] === Analysis Complete ===")
            logger.info(f"[RCA] Total time: {elapsed:.2f}s")
            logger.info(f"[RCA] Findings: {len(response.key_findings)}")
            logger.info(f"[RCA] Confidence: {response.confidence:.0%}")
            return response
            
        except Exception as e:
            logger.exception(f"Error during root cause analysis: {e}")
            return self._create_error_response(str(e))
    
    # ========================================================================
    # NEW: Dynamic Confidence Calculation
    # ========================================================================
    
    def _calculate_confidence(
        self,
        metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        llm_used: bool,
        anomalies_detected: int
    ) -> float:
        """
        Calculate confidence score (0.0-1.0) based on data quality and analysis depth.
        
        Factors:
        1. Data completeness (40%)
        2. LLM usage (30%)
        3. Anomaly detection quality (20%)
        4. Configuration context (10%)
        """
        confidence = 0.0
        
        # 1. Data completeness (40 points)
        exec_summary = metrics.get("execution_summary", {})
        required_fields = [
            "total_tasks",
            "failed_task_count",
            "total_spill_bytes",
            "total_shuffle_bytes",
            "total_duration_ms"
        ]
        present_fields = sum(1 for f in required_fields if exec_summary.get(f) is not None)
        data_completeness = (present_fields / len(required_fields)) * 0.40
        confidence += data_completeness
        
        # Boost if we have detailed metrics
        if metrics.get("stage_metrics"):
            confidence += 0.05
        if metrics.get("task_distribution"):
            confidence += 0.05
        
        # 2. LLM usage (30 points)
        if llm_used:
            confidence += 0.30  # Full LLM analysis
        else:
            confidence += 0.10  # Rule-based only
        
        # 3. Anomaly detection quality (20 points)
        if anomalies_detected > 0:
            # More anomalies = more data to analyze = higher confidence
            anomaly_score = min(anomalies_detected / 5.0, 1.0) * 0.20
            confidence += anomaly_score
        else:
            # No anomalies is also a valid finding
            confidence += 0.15
        
        # 4. Configuration context (10 points)
        if context:
            if context.get("executor_config"):
                confidence += 0.05
            if context.get("spark_config"):
                confidence += 0.05
        
        # Cap at 0.95 (never 100% certain)
        return round(min(confidence, 0.95), 2)
    
    # ========================================================================
    # Helper methods (shared by both modes)
    # ========================================================================
    
    def _extract_metrics(self, fingerprint_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract metrics layer from fingerprint data."""
        if "metrics" in fingerprint_data:
            return fingerprint_data["metrics"]
        elif "execution_summary" in fingerprint_data:
            return fingerprint_data
        return None
    
    def _extract_context(self, fingerprint_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract context layer for correlation analysis."""
        return fingerprint_data.get("context")
    
    def _build_context(
        self, 
        metrics: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        focus_areas: Optional[List[str]]
    ) -> Dict[str, Any]:
        """Build context dict for LLM prompt."""
        analysis = {
            "execution_summary": metrics.get("execution_summary", {}),
            "anomalies": metrics.get("anomalies", []),
            "kpis": metrics.get("key_performance_indicators", {}),
        }
        
        # Add stage metrics summary
        stage_metrics = metrics.get("stage_metrics", [])
        if stage_metrics:
            analysis["stage_summary"] = self._summarize_stages(stage_metrics)
        
        # Add task distribution highlights
        task_dist = metrics.get("task_distribution", {})
        if task_dist:
            analysis["task_distribution"] = self._extract_distribution_highlights(task_dist)
        
        # Add context for correlation
        if context:
            analysis["configuration"] = {
                "executor_memory_mb": context.get("executor_config", {}).get("executor_memory_mb"),
                "executor_cores": context.get("executor_config", {}).get("executor_cores"),
                "total_executors": context.get("executor_config", {}).get("total_executors"),
                "spark_version": context.get("spark_config", {}).get("spark_version"),
                "optimizations": context.get("optimizations_enabled", []),
            }
        
        if focus_areas:
            analysis["focus_areas"] = focus_areas
        
        return analysis
    
    def _summarize_stages(self, stage_metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create concise stage summaries highlighting issues."""
        summaries = []
        for stage in stage_metrics:
            summary = {
                "stage_id": stage.get("stage_id"),
                "num_tasks": stage.get("num_tasks"),
                "failed_tasks": stage.get("num_failed_tasks", 0),
                "spill_bytes": stage.get("spill_bytes", 0),
                "shuffle_read": stage.get("shuffle_read_bytes", 0),
                "shuffle_write": stage.get("shuffle_write_bytes", 0),
            }
            
            # Flag problematic stages
            if summary["failed_tasks"] > 0:
                summary["issue"] = "task_failures"
            elif summary["spill_bytes"] > 100_000_000:  # 100MB
                summary["issue"] = "high_spill"
            
            summaries.append(summary)
        return summaries
    
    def _extract_distribution_highlights(self, task_dist: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key distribution metrics that indicate issues."""
        highlights = {}
        
        for metric_name, stats in task_dist.items():
            if not isinstance(stats, dict):
                continue
            
            # Check for skew (high max vs median ratio)
            p50 = stats.get("p50", 0)
            max_val = stats.get("max_val", 0)
            if p50 > 0 and max_val > p50 * 10:
                highlights[metric_name] = {
                    "skew_ratio": max_val / p50,
                    "median": p50,
                    "max": max_val,
                    "outliers": stats.get("outlier_count", 0),
                }
        
        return highlights
    
    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        """Build the user prompt with context data."""
        prompt_parts = [
            "Analyze this Spark execution for root causes of any issues:\n"
        ]
        
        # Execution summary
        summary = context.get("execution_summary", {})
        prompt_parts.append("\n**Execution Summary**:\n")
        prompt_parts.append(f"- Duration: {summary.get('total_duration_ms', 0)}ms\n")
        prompt_parts.append(f"- Total Tasks: {summary.get('total_tasks', 0)}\n")
        prompt_parts.append(f"- Failed Tasks: {summary.get('failed_task_count', 0)}\n")
        prompt_parts.append(f"- Total Spill: {summary.get('total_spill_bytes', 0):,} bytes\n")
        prompt_parts.append(f"- Total Shuffle: {summary.get('total_shuffle_bytes', 0):,} bytes\n")
        prompt_parts.append(f"- Executor Losses: {summary.get('executor_loss_count', 0)}\n")
        
        # Anomalies
        anomalies = context.get("anomalies", [])
        if anomalies:
            prompt_parts.append(f"\n**Detected Anomalies** ({len(anomalies)}):\n")
            for a in anomalies:
                prompt_parts.append(
                    f"- [{a.get('severity', 'unknown').upper()}] {a.get('anomaly_type')}: "
                    f"{a.get('description')}\n"
                )
                if a.get("affected_stages"):
                    prompt_parts.append(f"  Affected stages: {a['affected_stages']}\n")
        else:
            prompt_parts.append("\n**Detected Anomalies**: None\n")
        
        # Task distribution issues
        dist_highlights = context.get("task_distribution", {})
        if dist_highlights:
            prompt_parts.append("\n**Distribution Issues**:\n")
            for metric, data in dist_highlights.items():
                prompt_parts.append(
                    f"- {metric}: skew ratio {data['skew_ratio']:.1f}x "
                    f"(median: {data['median']}, max: {data['max']}, outliers: {data['outliers']})\n"
                )
        
        # Configuration context
        config = context.get("configuration", {})
        if config:
            prompt_parts.append("\n**Configuration**:\n")
            prompt_parts.append(f"- Executors: {config.get('total_executors')} × {config.get('executor_memory_mb')}MB × {config.get('executor_cores')} cores\n")
            prompt_parts.append(f"- Spark Version: {config.get('spark_version')}\n")
            if config.get("optimizations"):
                prompt_parts.append(f"- Optimizations: {', '.join(config['optimizations'])}\n")
        
        # Focus areas
        if context.get("focus_areas"):
            prompt_parts.append(f"\n**Focus Areas**: {', '.join(context['focus_areas'])}\n")
        
        return "".join(prompt_parts)
    
    def _parse_llm_response(
        self, 
        llm_response: str, 
        start_time: float,
        context: Dict[str, Any],
        metrics: Dict[str, Any],
        ctx: Optional[Dict[str, Any]]
    ) -> AgentResponse:
        """Parse LLM response into structured AgentResponse."""
        processing_time = int((time.time() - start_time) * 1000)
        
        # Extract sections from response
        lines = llm_response.strip().split("\n")
        summary = ""
        key_findings = []
        
        # Determine health status from anomalies
        anomalies = context.get("anomalies", [])
        exec_summary = context.get("execution_summary", {})
        
        if exec_summary.get("failed_task_count", 0) > 0 or any(a.get("severity") == "critical" for a in anomalies):
            health = "Critical"
        elif anomalies or exec_summary.get("total_spill_bytes", 0) > 0:
            health = "Warning"
        else:
            health = "Healthy"
        
        # Parse summary from response
        in_summary = False
        for line in lines:
            line_lower = line.lower().strip()
            if "health assessment" in line_lower or "summary" in line_lower:
                in_summary = True
                if ":" in line:
                    summary = line.split(":", 1)[1].strip()
                continue
            elif line.startswith("**") and in_summary:
                in_summary = False
            elif in_summary and line.strip():
                summary += " " + line.strip()
            
            # Extract bullet points as key findings
            if line.strip().startswith("- ") or line.strip().startswith("• "):
                finding = line.strip()[2:].strip()
                if finding and len(finding) > 10:
                    key_findings.append(finding)
        
        # Fallback summary
        if not summary:
            summary = f"Execution health: {health}. {len(anomalies)} anomalies detected."
        # ✅ CALCULATE DYNAMIC CONFIDENCE
        conf = self._calculate_confidence(
            metrics=metrics,
            context=ctx,
            llm_used=True,
            anomalies_detected=len(anomalies)
        )
        # Determine suggested followup agents
        followup = []
        if anomalies or exec_summary.get("total_spill_bytes", 0) > 0:
            followup.append(AgentType.OPTIMIZATION)

        # ✅ NEW: derive health score + performance matrix for Spark mode
        health_score = HealthScore.calculate_from_spark_metrics(metrics)
        perf_matrix  = PerformanceMatrix.from_metrics(metrics)

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary.strip(),
            explanation=llm_response,
            key_findings=key_findings[:10],
            confidence=conf,  # dynamic
            processing_time_ms=processing_time,
            model_used=self.llm_config.model if hasattr(self, 'llm_config') else "gpt-4",
            metadata={
                "health_score": asdict(health_score),
                "performance_matrix": {
                    "execution":  perf_matrix.execution_metrics,
                    "resource":   perf_matrix.resource_metrics,
                    "data":       perf_matrix.data_metrics,
                    "bottlenecks": perf_matrix.bottlenecks,
                },
            },
            suggested_followup_agents=followup,
        )
    
    async def analyze_without_llm(self, fingerprint_data: Dict[str, Any]) -> AgentResponse:
        """
        Analyze fingerprint using only rule-based extraction (no LLM call).
        """
        start_time = time.time()
        
        try:
            metrics = self._extract_metrics(fingerprint_data)
            context = self._extract_context(fingerprint_data)
            
            if not metrics:
                return self._create_error_response("No metrics data found")
            
            explanation_parts = []
            key_findings = []
            
            # Analyze execution summary
            summary = metrics.get("execution_summary", {})
            failed_tasks = summary.get("failed_task_count", 0)
            spill_bytes = summary.get("total_spill_bytes", 0)
            shuffle_bytes = summary.get("total_shuffle_bytes", 0)
            
            # Determine health
            if failed_tasks > 0:
                health = "Critical"
                key_findings.append(f"{failed_tasks} task failures detected")
            elif spill_bytes > 0:
                health = "Warning"
                key_findings.append(f"Memory spill detected: {spill_bytes:,} bytes")
            else:
                health = "Healthy"
            
            explanation_parts.append(f"**Health Assessment**: {health}")
            
            # Analyze anomalies
            anomalies = metrics.get("anomalies", [])
            if anomalies:
                explanation_parts.append(f"\n**Anomalies Detected**: {len(anomalies)}")
                for a in anomalies:
                    explanation_parts.append(f"- [{a.get('severity', 'unknown').upper()}] {a.get('description')}")
                    key_findings.append(a.get('description', 'Unknown anomaly'))
            
            # Configuration correlation
            if context and spill_bytes > 0:
                exec_mem = context.get("executor_config", {}).get("executor_memory_mb", 0)
                if exec_mem > 0:
                    explanation_parts.append(f"\n**Configuration Correlation**:")
                    explanation_parts.append(f"- Executor memory: {exec_mem}MB - may be insufficient given spill volume")
                    key_findings.append(f"Consider increasing executor memory (currently {exec_mem}MB)")
            
            # ✅ CALCULATE DYNAMIC CONFIDENCE
            conf = self._calculate_confidence(
                metrics=metrics,
                context=context,
                llm_used=False,  # No LLM = lower confidence
                anomalies_detected=len(anomalies)
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=f"Execution health: {health}. {len(anomalies)} anomalies, {failed_tasks} failures, {spill_bytes:,} bytes spilled.",
                explanation="\n".join(explanation_parts),
                key_findings=key_findings,
                confidence=conf,  # ✅ Now dynamic!
                processing_time_ms=processing_time,
                suggested_followup_agents=[AgentType.OPTIMIZATION] if health != "Healthy" else []
            )
            
        except Exception as e:
            return self._create_error_response(str(e))
