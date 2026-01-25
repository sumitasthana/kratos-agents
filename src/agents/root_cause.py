"""
Root Cause Analysis Agent.

Analyzes Spark execution anomalies and metrics to identify root causes
of performance issues. Uses LangChain for LLM interactions.

Helps users understand:
- Why tasks failed or were slow
- What caused memory spills
- Sources of data skew
- Executor failures and their impact
- Correlation between anomalies and configuration
"""

import logging
import time
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END

from .base import BaseAgent, AgentResponse, AgentType, LLMConfig, AgentState

logger = logging.getLogger(__name__)


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


class RootCauseAgent(BaseAgent):
    """
    Agent that performs root cause analysis on Spark execution issues.
    
    Analyzes:
    - Anomalies detected in metrics layer
    - Task/stage failure patterns
    - Memory pressure indicators (spill)
    - Data skew patterns
    - Configuration mismatches
    
    Produces actionable root cause explanations.
    """
    
    @property
    def agent_type(self) -> AgentType:
        return AgentType.ROOT_CAUSE
    
    @property
    def agent_name(self) -> str:
        return "Root Cause Analysis Agent"
    
    @property
    def description(self) -> str:
        return "Identifies root causes of Spark execution anomalies and performance issues"
    
    @property
    def system_prompt(self) -> str:
        return ROOT_CAUSE_PROMPT

    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        **kwargs
    ) -> List[str]:
        steps = [
            "Extract metrics + execution summary from fingerprint",
            "Scan anomalies (failures, spills, skew, shuffle, executor loss)",
        ]
        if focus_areas:
            steps.append(f"Apply focus areas: {', '.join(focus_areas)}")
        steps.extend(
            [
                "Build root-cause context (metrics + correlations)",
                "Call LLM to propose root causes + mitigations",
                "Parse response into prioritized findings",
            ]
        )
        return steps
    
    async def analyze(
        self, 
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        **kwargs
    ) -> AgentResponse:
        """
        Analyze fingerprint for root causes of issues.
        
        Args:
            fingerprint_data: Full fingerprint or metrics layer
            context: Optional AgentContext for coordinated analysis
            focus_areas: Optional list of areas to focus on (e.g., ["spill", "skew"])
            
        Returns:
            AgentResponse with root cause analysis
        """
        logger.info(f"[RCA] === Starting Root Cause Analysis ===")
        if focus_areas:
            logger.info(f"[RCA] Focus areas: {', '.join(focus_areas)}")
        start_time = time.time()
        
        try:
            # Extract relevant data
            logger.info("[RCA] Step 1/4: Extracting metrics and context from fingerprint...")
            metrics = self._extract_metrics(fingerprint_data)
            context = self._extract_context(fingerprint_data)
            
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
            analysis_context = self._build_context(metrics, context, focus_areas)
            logger.info(f"[RCA] Context includes: {', '.join(analysis_context.keys())}")
            
            # Call LLM for interpretation
            user_prompt = self._build_user_prompt(analysis_context)
            logger.info(f"[RCA] Step 4/4: Calling LLM for root cause interpretation...")
            llm_response = await self._call_llm(ROOT_CAUSE_PROMPT, user_prompt)
            
            # Parse response into structured format
            logger.info("[RCA] Parsing LLM response into structured findings...")
            response = self._parse_llm_response(llm_response, start_time, analysis_context)
            
            elapsed = time.time() - start_time
            logger.info(f"[RCA] === Analysis Complete ===")
            logger.info(f"[RCA] Total time: {elapsed:.2f}s")
            logger.info(f"[RCA] Findings: {len(response.key_findings)}")
            logger.info(f"[RCA] Confidence: {response.confidence:.0%}")
            return response
            
        except Exception as e:
            logger.exception(f"Error during root cause analysis: {e}")
            return self._create_error_response(str(e))
    
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
        context: Dict[str, Any]
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
        
        # Determine suggested followup agents
        followup = []
        if anomalies or exec_summary.get("total_spill_bytes", 0) > 0:
            followup.append(AgentType.OPTIMIZATION)
        
        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary.strip(),
            explanation=llm_response,
            key_findings=key_findings[:10],
            confidence=0.85,
            processing_time_ms=processing_time,
            model_used=self.llm_config.model,
            suggested_followup_agents=followup
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
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=f"Execution health: {health}. {len(anomalies)} anomalies, {failed_tasks} failures, {spill_bytes:,} bytes spilled.",
                explanation="\n".join(explanation_parts),
                key_findings=key_findings,
                confidence=0.6,
                processing_time_ms=processing_time,
                suggested_followup_agents=[AgentType.OPTIMIZATION] if health != "Healthy" else []
            )
            
        except Exception as e:
            return self._create_error_response(str(e))
