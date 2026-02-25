"""
Root Cause Analysis Agent — Spark + GRC Compliance.

Mode 1: Spark Performance RCA (default).
Mode 2: GRC Compliance RCA if incident_type is not SPARK_PERFORMANCE.
"""

import logging
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseAgent, AgentResponse, AgentType, LLMConfig

logger = logging.getLogger(__name__)


# ============================================================================
# Incident / Root Cause Enums
# ============================================================================


class IncidentType(str, Enum):
    """Types of incidents that trigger GRC RCA."""
    AUDIT_FINDING       = "audit_finding"
    REGULATORY_ISSUE    = "regulatory_issue"
    DATA_QUALITY_BREACH = "data_quality_breach"
    CONTROL_FAILURE     = "control_failure"
    PRODUCTION_INCIDENT = "production_incident"
    SPARK_PERFORMANCE   = "spark_performance"


class RootCauseCategory(str, Enum):
    """GRC + Spark-specific root cause categories."""
    # GRC-specific
    DATA_PIPELINE     = "data_pipeline_issue"
    CONTROL_DESIGN    = "control_design_issue"
    CONTROL_EXECUTION = "control_execution_issue"
    PROCESS_ISSUE     = "process_issue"
    # Spark performance
    PERFORMANCE       = "performance_issue"
    CONFIGURATION     = "configuration_issue"


# ============================================================================
# HealthScore
# ============================================================================


@dataclass
class HealthScore:
    """
    Health score with confidence for GRC compliance reporting.

    Formula:
      Base 100 pts
      - Task Failures    : up to -40 pts
      - Memory Issues    : up to -25 pts
      - Shuffle Overhead : up to -20 pts
      - Data Skew        : up to -15 pts
    """
    overall_score: float        # 0–100
    confidence:    float        # 0–1
    severity:      str          # CRITICAL | HIGH | MEDIUM | LOW
    status:        str          # HEALTHY | WARNING | CRITICAL
    breakdown:     Dict[str, float]

    @classmethod
    def calculate_from_spark_metrics(cls, metrics: Dict[str, Any]) -> "HealthScore":
        exec_summary = metrics.get("execution_summary", {})

        breakdown = {
            "task_failures":    cls._calc_task_failure_penalty(exec_summary),
            "memory_pressure":  cls._calc_memory_penalty(exec_summary),
            "shuffle_overhead": cls._calc_shuffle_penalty(exec_summary),
            "data_skew":        cls._calc_skew_penalty(metrics),
        }
        overall_score = max(0.0, 100.0 - sum(breakdown.values()))

        return cls(
            overall_score=round(overall_score, 1),
            confidence=round(cls._calc_confidence(metrics), 2),
            severity=cls._map_score_to_severity(overall_score),
            status=cls._map_score_to_status(overall_score),
            breakdown=breakdown,
        )

    @staticmethod
    def _calc_task_failure_penalty(exec_summary: Dict[str, Any]) -> float:
        failed = exec_summary.get("failed_task_count", 0)
        total  = exec_summary.get("total_tasks", 1)
        rate   = failed / total if total else 0.0
        if rate >= 0.5:  return 40.0
        if rate >= 0.2:  return 30.0
        if rate >= 0.1:  return 20.0
        if rate >  0.0:  return 10.0
        return 0.0

    @staticmethod
    def _calc_memory_penalty(exec_summary: Dict[str, Any]) -> float:
        gb = exec_summary.get("total_spill_bytes", 0) / (1024 ** 3)
        if gb >= 50: return 25.0
        if gb >= 20: return 20.0
        if gb >=  5: return 15.0
        if gb >  0:  return 10.0
        return 0.0

    @staticmethod
    def _calc_shuffle_penalty(exec_summary: Dict[str, Any]) -> float:
        gb = exec_summary.get("total_shuffle_bytes", 0) / (1024 ** 3)
        if gb >= 100: return 20.0
        if gb >=  50: return 15.0
        if gb >=  20: return 10.0
        if gb >=   5: return  5.0
        return 0.0

    @staticmethod
    def _calc_skew_penalty(metrics: Dict[str, Any]) -> float:
        task_dist     = metrics.get("task_distribution", {})
        max_skew      = 1.0
        for stats in task_dist.values():
            if not isinstance(stats, dict):
                continue
            p50     = stats.get("p50", 0.0)
            max_val = stats.get("max_val", 0.0)
            if p50 > 0.0:
                max_skew = max(max_skew, max_val / p50)
        if max_skew >= 50: return 15.0
        if max_skew >= 20: return 12.0
        if max_skew >= 10: return  8.0
        if max_skew >=  5: return  5.0
        return 0.0

    @staticmethod
    def _map_score_to_severity(score: float) -> str:
        if score <= 40: return "CRITICAL"
        if score <= 60: return "HIGH"
        if score <= 80: return "MEDIUM"
        return "LOW"

    @staticmethod
    def _map_score_to_status(score: float) -> str:
        if score >= 80: return "HEALTHY"
        if score >= 60: return "WARNING"
        return "CRITICAL"

    @staticmethod
    def _calc_confidence(metrics: Dict[str, Any]) -> float:
        required = [
            "execution_summary",
            "anomalies",
            "key_performance_indicators",
            "task_distribution",
        ]
        present    = sum(1 for f in required if metrics.get(f) is not None)
        base_conf  = (present / len(required)) * 0.40
        exec_s     = metrics.get("execution_summary", {})
        if exec_s.get("total_tasks", 0) > 0:
            base_conf = min(1.0, base_conf * 1.2)
        return base_conf


# ============================================================================
# ErrorMapping
# ============================================================================


@dataclass
class ErrorMapping:
    """Structured error categorisation for GRC compliance."""
    memory_errors:        List[Dict[str, Any]]
    data_quality_errors:  List[Dict[str, Any]]
    configuration_errors: List[Dict[str, Any]]
    execution_errors:     List[Dict[str, Any]]

    @classmethod
    def from_metrics(cls, metrics: Dict[str, Any]) -> "ErrorMapping":
        exec_summary    = metrics.get("execution_summary", {})
        anomalies       = metrics.get("anomalies", [])
        memory_errors:  List[Dict[str, Any]] = []
        dq_errors:      List[Dict[str, Any]] = []
        cfg_errors:     List[Dict[str, Any]] = []
        exec_errors:    List[Dict[str, Any]] = []

        spill = exec_summary.get("total_spill_bytes", 0)
        if spill > 0:
            memory_errors.append({
                "type":     "MEMORY_SPILL",
                "severity": "HIGH" if spill >= 20 * 1024 ** 3 else "MEDIUM",
                "detail":   f"{spill / (1024 ** 3):.2f}GB spilled to disk",
                "impact":   "Performance degradation due to disk IO",
            })

        failed = exec_summary.get("failed_task_count", 0)
        if failed > 0:
            exec_errors.append({
                "type":     "TASK_FAILURE",
                "severity": "CRITICAL",
                "detail":   f"{failed} tasks failed",
                "impact":   "Job completion blocked or delayed",
            })

        for anomaly in anomalies:
            atype = anomaly.get("anomaly_type", "").lower()
            sev   = anomaly.get("severity", "MEDIUM").upper()
            desc  = anomaly.get("description", "")
            if "skew" in atype or "partition" in atype:
                dq_errors.append({
                    "type": "DATA_SKEW", "severity": sev,
                    "detail": desc, "impact": "Uneven task execution causing stragglers",
                })
            elif "memory" in atype or "spill" in atype:
                memory_errors.append({
                    "type": "MEMORY_PRESSURE", "severity": sev,
                    "detail": desc, "impact": "Insufficient memory allocation",
                })
            elif "config" in atype:
                cfg_errors.append({
                    "type": "CONFIGURATION_ISSUE", "severity": sev,
                    "detail": desc, "impact": "Suboptimal resource allocation",
                })
            else:
                exec_errors.append({
                    "type": "EXECUTION_ANOMALY", "severity": sev,
                    "detail": desc, "impact": "Runtime execution issue",
                })

        return cls(
            memory_errors=memory_errors,
            data_quality_errors=dq_errors,
            configuration_errors=cfg_errors,
            execution_errors=exec_errors,
        )

    def total(self) -> int:
        return (len(self.memory_errors) + len(self.data_quality_errors)
                + len(self.configuration_errors) + len(self.execution_errors))

    def critical(self) -> int:
        all_errors = (self.memory_errors + self.data_quality_errors
                      + self.configuration_errors + self.execution_errors)
        return sum(1 for e in all_errors if e.get("severity") == "CRITICAL")


# ============================================================================
# PerformanceMatrix
# ============================================================================


@dataclass
class PerformanceMatrix:
    """Performance evaluation matrix for regulatory reporting."""
    execution_metrics: Dict[str, Any]
    resource_metrics:  Dict[str, Any]
    data_metrics:      Dict[str, Any]
    bottlenecks:       List[Dict[str, Any]]

    @classmethod
    def from_metrics(cls, metrics: Dict[str, Any]) -> "PerformanceMatrix":
        exec_summary  = metrics.get("execution_summary", {})
        total_tasks   = exec_summary.get("total_tasks", 0)
        failed_tasks  = exec_summary.get("failed_task_count", 0)
        success_rate  = ((total_tasks - failed_tasks) / total_tasks * 100
                         if total_tasks else 0.0)

        spill_bytes   = exec_summary.get("total_spill_bytes", 0)
        shuffle_bytes = exec_summary.get("total_shuffle_bytes", 0)
        task_dist     = metrics.get("task_distribution", {})
        max_skew      = cls._extract_max_skew(task_dist)

        return cls(
            execution_metrics={
                "total_duration_sec": exec_summary.get("total_duration_ms", 0) / 1000.0,
                "task_success_rate":  round(success_rate, 2),
                "total_tasks":        total_tasks,
                "failed_tasks":       failed_tasks,
            },
            resource_metrics={
                "memory_utilization": cls._classify_memory_usage(spill_bytes),
                "disk_spill_gb":      round(spill_bytes  / (1024 ** 3), 2),
                "shuffle_write_gb":   round(shuffle_bytes / (1024 ** 3), 2),
                "executor_losses":    exec_summary.get("executor_loss_count", 0),
            },
            data_metrics={
                "max_skew_ratio": round(max_skew, 2),
                "stage_count":    len(metrics.get("stage_metrics", [])),
            },
            bottlenecks=cls._identify_bottlenecks(exec_summary, max_skew),
        )

    @staticmethod
    def _classify_memory_usage(spill_bytes: int) -> str:
        gb = spill_bytes / (1024 ** 3)
        if gb >= 20: return "OVER_CAPACITY"
        if gb >=  5: return "HIGH"
        if gb >   0: return "MODERATE"
        return "OPTIMAL"

    @staticmethod
    def _extract_max_skew(task_dist: Dict[str, Any]) -> float:
        max_skew = 1.0
        for stats in task_dist.values():
            if not isinstance(stats, dict):
                continue
            p50     = stats.get("p50", 0.0)
            max_val = stats.get("max_val", 0.0)
            if p50 > 0.0:
                max_skew = max(max_skew, max_val / p50)
        return max_skew

    @staticmethod
    def _identify_bottlenecks(
        exec_summary: Dict[str, Any],
        max_skew: float,
    ) -> List[Dict[str, Any]]:
        bottlenecks: List[Dict[str, Any]] = []
        spill_gb   = exec_summary.get("total_spill_bytes", 0)  / (1024 ** 3)
        shuffle_gb = exec_summary.get("total_shuffle_bytes", 0) / (1024 ** 3)

        if spill_gb >= 5:
            bottlenecks.append({
                "type":         "MEMORY",
                "severity":     "HIGH" if spill_gb >= 20 else "MEDIUM",
                "impact":       "Performance degradation due to disk IO",
                "metric_value": f"{spill_gb:.1f}GB",
            })
        if max_skew >= 10:
            bottlenecks.append({
                "type":         "DATA_SKEW",
                "severity":     "HIGH" if max_skew >= 20 else "MEDIUM",
                "impact":       "Uneven task execution causing stragglers",
                "metric_value": f"{max_skew:.1f}x",
            })
        if shuffle_gb >= 50:
            bottlenecks.append({
                "type":         "SHUFFLE",
                "severity":     "MEDIUM",
                "impact":       "High network overhead between executors",
                "metric_value": f"{shuffle_gb:.1f}GB",
            })
        return bottlenecks


# ============================================================================
# RemediationPlan
# ============================================================================


@dataclass
class RemediationPlan:
    """GRC-compliant remediation recommendations."""
    root_cause_category:  RootCauseCategory
    action_items:         List[Dict[str, str]]
    estimated_fix_time:   str
    owner_recommendation: str
    regulation_impacted:  Optional[str] = None

    @classmethod
    def generate(
        cls,
        root_cause:    RootCauseCategory,
        health_score:  HealthScore,
        error_mapping: ErrorMapping,
        perf_matrix:   PerformanceMatrix,
        context:       Optional[Dict] = None,
    ) -> "RemediationPlan":
        items: List[Dict[str, str]] = []

        if perf_matrix.resource_metrics["disk_spill_gb"] > 5:
            items.append({
                "priority":       "P0",
                "action":         "Increase executor memory",
                "detail":         f"Spill: {perf_matrix.resource_metrics['disk_spill_gb']:.1f}GB",
                "recommendation": "Raise spark.executor.memory to 4g or higher",
                "regulation":     "SOX (data processing integrity)",
            })
        if perf_matrix.data_metrics["max_skew_ratio"] > 10:
            items.append({
                "priority":       "P0",
                "action":         "Fix data skew",
                "detail":         f"Skew ratio: {perf_matrix.data_metrics['max_skew_ratio']:.1f}x",
                "recommendation": "Add salting or repartition by multiple columns",
                "regulation":     "Data quality compliance",
            })
        if perf_matrix.execution_metrics["failed_tasks"] > 0:
            items.append({
                "priority":       "P0",
                "action":         "Investigate task failures",
                "detail":         f"{perf_matrix.execution_metrics['failed_tasks']} tasks failed",
                "recommendation": "Review executor logs and increase retry configuration",
                "regulation":     "Operational resilience requirements",
            })

        p0_count = sum(1 for i in items if i["priority"] == "P0")
        fix_time = "4–8 hours" if p0_count > 2 else ("2–4 hours" if p0_count else "< 2 hours")

        return cls(
            root_cause_category=root_cause,
            action_items=items,
            estimated_fix_time=fix_time,
            owner_recommendation=cls._owner(root_cause),
            regulation_impacted=cls._regulation(error_mapping),
        )

    @staticmethod
    def _owner(root_cause: RootCauseCategory) -> str:
        return {
            RootCauseCategory.DATA_PIPELINE:     "Data Engineering Team",
            RootCauseCategory.CONTROL_DESIGN:    "Compliance / Risk Team",
            RootCauseCategory.CONTROL_EXECUTION: "DevOps / SRE Team",
            RootCauseCategory.PROCESS_ISSUE:     "Process Owner / Manager",
            RootCauseCategory.PERFORMANCE:       "Data Engineering Team",
            RootCauseCategory.CONFIGURATION:     "DevOps / SRE Team",
        }.get(root_cause, "Engineering Manager")

    @staticmethod
    def _regulation(error_mapping: ErrorMapping) -> str:
        if error_mapping.critical() > 0:         return "SOX, GDPR (data integrity)"
        if error_mapping.data_quality_errors:    return "Data Quality Standards"
        return "Operational Standards"


# ============================================================================
# RoutingInstructions
# ============================================================================


@dataclass
class RoutingInstructions:
    """Instructions for routing RCA results back to GRC components."""
    destination:   str
    create_ticket: bool
    notify:        List[str]
    feedback_to:   List[str]
    control_id:    Optional[str] = None

    @classmethod
    def determine(
        cls,
        root_cause:    RootCauseCategory,
        incident_type: IncidentType,
        severity:      str,
    ) -> "RoutingInstructions":
        routing_map = {
            RootCauseCategory.DATA_PIPELINE: {
                "destination": "ETL_TEAM", "create_ticket": True,
                "notify": ["data-engineering@company.com"],
                "feedback_to": ["Control Hub (D)", "Lineage Tool"],
            },
            RootCauseCategory.CONTROL_DESIGN: {
                "destination": "DISCOVERY_A", "create_ticket": True,
                "notify": ["compliance@company.com", "risk@company.com"],
                "feedback_to": ["Discovery (A)", "Control Hub (D)"],
            },
            RootCauseCategory.CONTROL_EXECUTION: {
                "destination": "CONTROL_HUB_D", "create_ticket": True,
                "notify": ["devops@company.com"],
                "feedback_to": ["Control Hub (D)"],
            },
            RootCauseCategory.PROCESS_ISSUE: {
                "destination": "PROCESS_OWNER", "create_ticket": True,
                "notify": ["operations@company.com"],
                "feedback_to": ["Process Documentation"],
            },
            RootCauseCategory.PERFORMANCE: {
                "destination": "DATA_ENGINEERING",
                "create_ticket": severity in ("CRITICAL", "HIGH"),
                "notify": ["data-engineering@company.com"],
                "feedback_to": ["Performance Monitoring"],
            },
            RootCauseCategory.CONFIGURATION: {
                "destination": "DEVOPS",
                "create_ticket": severity in ("CRITICAL", "HIGH"),
                "notify": ["devops@company.com"],
                "feedback_to": ["Config Management"],
            },
        }
        kwargs = routing_map.get(root_cause, {
            "destination": "ENGINEERING_MANAGER", "create_ticket": True,
            "notify": ["engineering@company.com"],
            "feedback_to": ["Control Hub (D)"],
        })
        return cls(**kwargs)


# ============================================================================
# LLM Prompts
# ============================================================================

ROOT_CAUSE_PROMPT = """\
You are a Spark performance expert specialising in root cause analysis.

Analyse the Spark execution fingerprint and identify the root causes of any
performance issues or anomalies.

Output rules (STRICT):
  * Begin with a one-line **Health Assessment** (Healthy / Warning / Critical).
  * For EACH issue found, use EXACTLY this labeled block — no bullets, no numbers:

      **<Issue Category>:**
      **Symptom:** <what happened — reference actual metric values>
      **Root Cause:** <why it happened>
      **Impact:** <effect on job duration, resource usage, or correctness>
      **Recommended Fix:** <specific, actionable fix with config key if applicable>

  Issue categories: Task Failures | Memory Pressure | Data Skew |
                    Shuffle Overhead | GC Pressure | Executor Loss

  * End with a **Correlations** section (one paragraph) and a
    **Recommendations** section (bullet list, prioritised).
  * If no issues are found, state: Execution is healthy — no significant issues detected.
  * Be concise. Reference real numbers from the fingerprint.
"""

GRC_RCA_PROMPT = """\
You are a data governance and compliance expert specialising in root cause
analysis for regulatory incidents.

Root cause categories (pick ONE):
  1. Data Pipeline Issue   — ETL, ingestion, transformation, or lineage problems
  2. Control Design Issue  — missing or incorrect validation logic
  3. Control Execution Issue — job failure, threshold misconfiguration
  4. Process Issue         — manual dependency, timing, or ownership gaps

Output format:
  * **Incident Classification:** Control failure / Data breach / Process gap
  * **Root Cause Category:** one of the four above
  * **Regulatory Impact:** which regulations or policies are affected
  * **Remediation Plan:** prioritised actions with owners and timelines
  * **Preventive Measures:** new controls or processes needed
"""


# ============================================================================
# RootCauseAgent
# ============================================================================


class RootCauseAgent(BaseAgent):
    """
    Dual-mode Root Cause Analysis Agent.

    Mode 1: Spark Performance RCA (default — no incident_type needed).
    Mode 2: GRC Compliance RCA when incident_type != SPARK_PERFORMANCE.
    """

    @property
    def agent_type(self) -> AgentType:
        return AgentType.ROOT_CAUSE

    @property
    def agent_name(self) -> str:
        return "Root Cause Analysis Agent"

    @property
    def description(self) -> str:
        return "Identifies root causes of Spark execution and GRC compliance incidents."

    @property
    def system_prompt(self) -> str:
        return ROOT_CAUSE_PROMPT

    # ------------------------------------------------------------------ #
    # Planning
    # ------------------------------------------------------------------ #

    def plan(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        incident_type: Optional[IncidentType] = None,
        **kwargs: Any,
    ) -> List[str]:
        is_grc = incident_type and incident_type != IncidentType.SPARK_PERFORMANCE
        if is_grc:
            return [
                "Extract metrics / execution summary from fingerprint",
                "Calculate health score (0–100) with confidence",
                "Map errors to compliance categories",
                "Generate performance matrix for regulatory reporting",
                "Classify root cause into 4 GRC categories",
                "Build remediation plan with owner assignment",
                "Determine routing (Control Hub D, Discovery A, etc.)",
                "Generate executive summary for compliance reporting",
            ]
        steps = [
            "Extract metrics / execution summary from fingerprint",
            "Scan anomalies (failures, spills, skew, shuffle, executor loss)",
            "Derive health score and performance matrix (rule-based)",
            "Build root-cause context (metrics + correlations)",
            "Call LLM to propose root causes and mitigations",
            "Parse response into prioritised findings",
        ]
        if focus_areas:
            steps.insert(2, f"Apply focus areas: {', '.join(focus_areas)}")
        return steps

    # ------------------------------------------------------------------ #
    # Mode selection
    # ------------------------------------------------------------------ #

    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        incident_type: Optional[IncidentType] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        is_grc = incident_type and incident_type != IncidentType.SPARK_PERFORMANCE
        if is_grc:
            return await self._analyze_grc_compliance(
                fingerprint_data=fingerprint_data,
                incident_type=incident_type,  # type: ignore[arg-type]
                context=context,
            )
        return await self._analyze_spark_performance(
            fingerprint_data=fingerprint_data,
            context=context,
            focus_areas=focus_areas,
        )

    # ------------------------------------------------------------------ #
    # Spark Performance RCA
    # ------------------------------------------------------------------ #

    async def _analyze_spark_performance(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        focus_areas: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        logger.info("RCA: Starting Spark Performance RCA")
        if focus_areas:
            logger.info("RCA: Focus areas: %s", ", ".join(focus_areas))
        start_time = time.time()

        try:
            metrics = self._extract_metrics(fingerprint_data)
            ctx     = self._extract_context(fingerprint_data)
            if not metrics:
                return self._create_error_response("No metrics data found in fingerprint")

            # ── Rule-based health + perf matrix ──────────────────────────
            health_score, perf_matrix = self._derive_health_and_perf(metrics)
            logger.info(
                "RCA: Health=%.1f (%s) | Bottlenecks=%d",
                health_score.overall_score,
                health_score.status,
                len(perf_matrix.bottlenecks),
            )

            # ── Build LLM context ─────────────────────────────────────────
            analysis_context = self._build_context(metrics, ctx, focus_areas)
            user_prompt      = self._build_user_prompt(analysis_context)

            logger.info("RCA: Calling LLM")
            llm_response = await self._call_llm(ROOT_CAUSE_PROMPT, user_prompt)

            return self._parse_llm_response(
                llm_response=llm_response,
                start_time=start_time,
                context=analysis_context,
                metrics=metrics,
                ctx=ctx,
                health_score=health_score,
                perf_matrix=perf_matrix,
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("RCA: Error during Spark performance analysis: %s", exc)
            return self._create_error_response(str(exc))

    # ------------------------------------------------------------------ #
    # GRC Compliance RCA
    # ------------------------------------------------------------------ #

    async def _analyze_grc_compliance(
        self,
        fingerprint_data: Dict[str, Any],
        incident_type: IncidentType,
        context: Optional[Any] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        logger.info("RCA-GRC: Starting GRC Compliance RCA — %s", incident_type.value)
        start_time = time.time()

        try:
            metrics = self._extract_metrics(fingerprint_data)
            if not metrics:
                return self._create_error_response("No metrics data found")

            health_score, perf_matrix = self._derive_health_and_perf(metrics)
            error_mapping = ErrorMapping.from_metrics(metrics)

            root_cause  = self._classify_grc_root_cause(
                metrics, health_score, error_mapping, incident_type
            )
            remediation = RemediationPlan.generate(
                root_cause=root_cause,
                health_score=health_score,
                error_mapping=error_mapping,
                perf_matrix=perf_matrix,
                context=context,
            )
            routing = RoutingInstructions.determine(
                root_cause=root_cause,
                incident_type=incident_type,
                severity=health_score.severity,
            )
            summary = self._generate_grc_executive_summary(
                incident_type=incident_type,
                root_cause=root_cause,
                health_score=health_score,
                error_mapping=error_mapping,
                remediation=remediation,
                perf_matrix=perf_matrix,
            )

            elapsed = time.time() - start_time
            logger.info("RCA-GRC: Done in %.2fs | root_cause=%s", elapsed, root_cause.value)

            key_findings: List[str] = [
                f"Health Score: {health_score.overall_score:.1f}/100 ({health_score.status})",
                f"Root Cause: {root_cause.value}",
                f"{error_mapping.total()} errors ({error_mapping.critical()} critical)",
            ]
            for item in remediation.action_items[:5]:
                key_findings.append(f"{item['priority']}: {item['action']}")

            return AgentResponse(
                agent_type=self.agent_type,
                agent_name=self.agent_name,
                success=True,
                summary=summary,
                explanation=self._build_grc_detailed_explanation(
                    incident_type=incident_type,
                    root_cause=root_cause,
                    health_score=health_score,
                    error_mapping=error_mapping,
                    perf_matrix=perf_matrix,
                    remediation=remediation,
                    routing=routing,
                ),
                key_findings=key_findings[:20],
                confidence=health_score.confidence,
                processing_time_ms=int(elapsed * 1000),
                model_used="rule-based",
                metadata={
                    "incident_type":        incident_type.value,
                    "root_cause_category":  root_cause.value,
                    "health_score":         asdict(health_score),
                    "error_mapping": {
                        "memory_errors":        error_mapping.memory_errors,
                        "data_quality_errors":  error_mapping.data_quality_errors,
                        "configuration_errors": error_mapping.configuration_errors,
                        "execution_errors":     error_mapping.execution_errors,
                    },
                    "performance_matrix": {
                        "execution":   perf_matrix.execution_metrics,
                        "resource":    perf_matrix.resource_metrics,
                        "data":        perf_matrix.data_metrics,
                        "bottlenecks": perf_matrix.bottlenecks,
                    },
                    "remediation": {
                        "action_items":       remediation.action_items,
                        "estimated_fix_time": remediation.estimated_fix_time,
                        "owner":              remediation.owner_recommendation,
                        "regulation_impacted": remediation.regulation_impacted,
                    },
                    "routing": {
                        "destination": routing.destination,
                        "feedback_to": routing.feedback_to,
                        "notify":      routing.notify,
                    },
                },
                suggested_followup_agents=(
                    [AgentType.OPTIMIZATION] if health_score.status != "HEALTHY" else []
                ),
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("RCA-GRC: Error: %s", exc)
            return self._create_error_response(str(exc))

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #

    def _derive_health_and_perf(
        self,
        metrics: Dict[str, Any],
    ) -> Tuple[HealthScore, PerformanceMatrix]:
        """Compute HealthScore + PerformanceMatrix from raw metrics dict."""
        return (
            HealthScore.calculate_from_spark_metrics(metrics),
            PerformanceMatrix.from_metrics(metrics),
        )

    def _extract_metrics(
        self, fingerprint_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if "metrics" in fingerprint_data:
            return fingerprint_data["metrics"]
        if "execution_summary" in fingerprint_data:
            return fingerprint_data
        return None

    @staticmethod
    def _extract_context(
        fingerprint_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return fingerprint_data.get("context")

    @staticmethod
    def _build_context(
        metrics:     Dict[str, Any],
        context:     Optional[Dict[str, Any]],
        focus_areas: Optional[List[str]],
    ) -> Dict[str, Any]:
        analysis: Dict[str, Any] = {
            "execution_summary": metrics.get("execution_summary", {}),
            "anomalies":         metrics.get("anomalies", []),
            "kpis":              metrics.get("key_performance_indicators", {}),
        }
        if context:
            analysis["configuration"] = {
                "executor_memory_mb": context.get("executor_config", {}).get("executor_memory_mb"),
                "executor_cores":     context.get("executor_config", {}).get("executor_cores"),
                "total_executors":    context.get("executor_config", {}).get("total_executors"),
                "spark_version":      context.get("spark_config", {}).get("spark_version"),
                "optimizations":      context.get("optimizations_enabled", []),
            }
        if focus_areas:
            analysis["focus_areas"] = focus_areas
        return analysis

    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        parts: List[str] = ["Analyse this Spark execution for root causes.\n\n"]
        summary = context.get("execution_summary", {})
        parts += [
            "Summary:\n",
            f"- Duration     : {summary.get('total_duration_ms', 0)} ms\n",
            f"- Total Tasks  : {summary.get('total_tasks', 0)}\n",
            f"- Failed Tasks : {summary.get('failed_task_count', 0)}\n",
            f"- Total Spill  : {summary.get('total_spill_bytes', 0)} bytes\n",
            f"- Total Shuffle: {summary.get('total_shuffle_bytes', 0)} bytes\n",
            f"- Executor Loss: {summary.get('executor_loss_count', 0)}\n",
        ]
        anomalies = context.get("anomalies", [])
        parts.append(f"\nAnomalies ({len(anomalies)}):\n")
        if anomalies:
            for a in anomalies:
                parts.append(
                    f"- {a.get('severity','').upper()} "
                    f"{a.get('anomaly_type','')}: {a.get('description','')}\n"
                )
        else:
            parts.append("None detected.\n")

        if "configuration" in context:
            cfg = context["configuration"]
            parts += [
                "\nConfiguration:\n",
                f"- Executors    : {cfg.get('total_executors')} × "
                f"{cfg.get('executor_memory_mb')}MB × {cfg.get('executor_cores')} cores\n",
                f"- Spark Version: {cfg.get('spark_version')}\n",
            ]
            if cfg.get("optimizations"):
                parts.append(f"- Optimizations: {', '.join(cfg['optimizations'])}\n")

        if context.get("focus_areas"):
            parts.append(f"\nFocus Areas: {', '.join(context['focus_areas'])}\n")

        return "".join(parts)

    def _parse_llm_response(
        self,
        llm_response: str,
        start_time:   float,
        context:      Dict[str, Any],
        metrics:      Dict[str, Any],
        ctx:          Optional[Dict[str, Any]],
        health_score: HealthScore,
        perf_matrix:  PerformanceMatrix,
    ) -> AgentResponse:
        processing_time = int((time.time() - start_time) * 1000)
        lines           = llm_response.strip().splitlines()

        summary      = ""
        key_findings: List[str] = []
        in_summary   = False

        for line in lines:
            trimmed = line.strip()
            lower   = trimmed.lower()
            if "health assessment" in lower or lower.startswith("summary:"):
                in_summary = True
                if ":" in trimmed:
                    summary = trimmed.split(":", 1)[1].strip()
                continue
            if trimmed.startswith("**") and in_summary:
                in_summary = False
            elif in_summary and trimmed:
                summary += " " + trimmed
            if trimmed.startswith(("- ", "• ")):
                finding = trimmed[2:].strip()
                if len(finding) > 10:
                    key_findings.append(finding)

        if not summary and lines:
            summary = lines[0].strip()

        conf = self._calculate_confidence(
            metrics=metrics, context=ctx, llm_used=True
        )

        followup: List[AgentType] = []
        if (metrics.get("anomalies")
                or metrics.get("execution_summary", {}).get("total_spill_bytes", 0) > 0):
            followup.append(AgentType.OPTIMIZATION)

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=summary or "Execution health assessed.",
            explanation=llm_response,
            key_findings=key_findings[:20],
            confidence=conf,
            processing_time_ms=processing_time,
            model_used=self.llm_config.model if hasattr(self, "llm_config") else "gpt-4",
            metadata={
                "health_score": asdict(health_score),
                "performance_matrix": {
                    "execution":   perf_matrix.execution_metrics,
                    "resource":    perf_matrix.resource_metrics,
                    "data":        perf_matrix.data_metrics,
                    "bottlenecks": perf_matrix.bottlenecks,
                },
            },
            suggested_followup_agents=followup,
        )

    # ------------------------------------------------------------------ #
    # Confidence + health helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _determine_health_status(context: Dict[str, Any]) -> str:
        anomalies    = context.get("anomalies", [])
        exec_summary = context.get("execution_summary", {})
        failed       = exec_summary.get("failed_task_count", 0)
        spill        = exec_summary.get("total_spill_bytes", 0)
        if failed > 0 or any(a.get("severity", "").lower() == "critical" for a in anomalies):
            return "Critical"
        if anomalies or spill > 0:
            return "Warning"
        return "Healthy"

    @staticmethod
    def _calculate_confidence(
        metrics:  Dict[str, Any],
        context:  Optional[Dict[str, Any]],
        llm_used: bool,
    ) -> float:
        exec_summary    = metrics.get("execution_summary", {})
        required_fields = [
            "total_tasks", "failed_task_count",
            "total_spill_bytes", "total_shuffle_bytes", "total_duration_ms",
        ]
        present = sum(
            1 for f in required_fields if exec_summary.get(f) is not None
        )
        data_completeness = (present / len(required_fields)) * 0.40
        anomaly_score     = min(0.30, len(metrics.get("anomalies", [])) * 0.05)
        llm_score         = 0.20 if llm_used else 0.0
        context_score     = 0.0
        if context:
            if context.get("anomalies"):         context_score += 0.05
            if context.get("execution_summary"): context_score += 0.05
        return min(1.0, data_completeness + anomaly_score + llm_score + context_score)

    # ------------------------------------------------------------------ #
    # GRC helpers
    # ------------------------------------------------------------------ #

    def _classify_grc_root_cause(
        self,
        metrics:       Dict[str, Any],
        health_score:  HealthScore,
        error_mapping: ErrorMapping,
        incident_type: IncidentType,
    ) -> RootCauseCategory:
        exec_summary = metrics.get("execution_summary", {})
        if (health_score.breakdown.get("task_failures", 0.0) >= 20.0
                or exec_summary.get("failed_task_count", 0) > 0):
            return RootCauseCategory.CONTROL_EXECUTION
        if error_mapping.data_quality_errors and not error_mapping.execution_errors:
            return RootCauseCategory.CONTROL_DESIGN
        if (health_score.breakdown.get("memory_pressure",  0.0) >= 15.0
                or health_score.breakdown.get("data_skew",  0.0) >= 10.0
                or health_score.breakdown.get("shuffle_overhead", 0.0) >= 15.0):
            return RootCauseCategory.DATA_PIPELINE
        return RootCauseCategory.PROCESS_ISSUE

    def _generate_grc_executive_summary(
        self,
        incident_type: IncidentType,
        root_cause:    RootCauseCategory,
        health_score:  HealthScore,
        error_mapping: ErrorMapping,
        remediation:   RemediationPlan,
        perf_matrix:   PerformanceMatrix,
    ) -> str:
        lines: List[str] = [
            "=" * 80,
            "INCIDENT ANALYSIS SUMMARY — GRC COMPLIANCE",
            "=" * 80, "",
            f"Incident Type : {incident_type.value.replace('_', ' ').title()}",
            f"Root Cause    : {root_cause.value.replace('_', ' ').title()}",
            "",
            "HEALTH ASSESSMENT",
            f"  Overall Score : {health_score.overall_score:.1f}/100",
            f"  Status        : {health_score.status}",
            f"  Severity      : {health_score.severity}",
            f"  Confidence    : {health_score.confidence:.2f}",
            "",
            "SCORE BREAKDOWN",
            f"  Task Failures   : -{health_score.breakdown.get('task_failures',    0.0):.1f} pts",
            f"  Memory Pressure : -{health_score.breakdown.get('memory_pressure',  0.0):.1f} pts",
            f"  Shuffle Overhead: -{health_score.breakdown.get('shuffle_overhead', 0.0):.1f} pts",
            f"  Data Skew       : -{health_score.breakdown.get('data_skew',        0.0):.1f} pts",
            "",
            "KEY FINDINGS",
            f"  Total errors    : {error_mapping.total()} ({error_mapping.critical()} critical)",
            f"  Task success    : {perf_matrix.execution_metrics['task_success_rate']}%",
            f"  Memory status   : {perf_matrix.resource_metrics['memory_utilization']}",
            f"  Bottlenecks     : {len(perf_matrix.bottlenecks)}",
            "",
            "REMEDIATION",
            f"  Fix time  : {remediation.estimated_fix_time}",
            f"  Owner     : {remediation.owner_recommendation}",
            f"  Regulation: {remediation.regulation_impacted or 'N/A'}",
            "",
            "IMMEDIATE ACTIONS",
        ]
        for i, action in enumerate(remediation.action_items[:3], 1):
            lines.append(f"  {i}. [{action['priority']}] {action['action']}")
            lines.append(f"     {action['recommendation']}")
        lines += ["", "=" * 80]
        return "\n".join(lines)

    def _build_grc_detailed_explanation(
        self,
        incident_type: IncidentType,
        root_cause:    RootCauseCategory,
        health_score:  HealthScore,
        error_mapping: ErrorMapping,
        perf_matrix:   PerformanceMatrix,
        remediation:   RemediationPlan,
        routing:       RoutingInstructions,
    ) -> str:
        s: List[str] = []
        s += [
            "INCIDENT CONTEXT",
            f"- Incident Type      : {incident_type.value}",
            f"- Root Cause Category: {root_cause.value}", "",
            "HEALTH ASSESSMENT",
            f"- Overall Score: {health_score.overall_score:.1f}/100",
            f"- Status       : {health_score.status}",
            f"- Severity     : {health_score.severity}",
            f"- Confidence   : {health_score.confidence:.2f}", "",
            "PERFORMANCE ANALYSIS",
            f"- Duration      : {perf_matrix.execution_metrics['total_duration_sec']:.1f}s",
            f"- Task Success  : {perf_matrix.execution_metrics['task_success_rate']}%",
            f"- Memory Spill  : {perf_matrix.resource_metrics['disk_spill_gb']:.2f}GB",
            f"- Shuffle Volume: {perf_matrix.resource_metrics['shuffle_write_gb']:.2f}GB", "",
        ]
        if perf_matrix.bottlenecks:
            s.append("BOTTLENECKS")
            for b in perf_matrix.bottlenecks:
                s.append(f"- {b['severity']} {b['type']}: {b['impact']} ({b['metric_value']})")
            s.append("")
        s.append("ERROR ANALYSIS")
        if error_mapping.memory_errors:
            s.append(f"  Memory Errors       : {len(error_mapping.memory_errors)}")
        if error_mapping.data_quality_errors:
            s.append(f"  Data Quality Errors : {len(error_mapping.data_quality_errors)}")
        if error_mapping.configuration_errors:
            s.append(f"  Configuration Errors: {len(error_mapping.configuration_errors)}")
        if error_mapping.execution_errors:
            s.append(f"  Execution Errors    : {len(error_mapping.execution_errors)}")
        s.append("")
        s.append("REMEDIATION PLAN")
        for i, action in enumerate(remediation.action_items, 1):
            s.append(f"  {i}. [{action['priority']}] {action['action']} — {action['detail']}")
            s.append(f"     Recommendation: {action['recommendation']}")
        s.append(
            f"  Owner: {remediation.owner_recommendation} | "
            f"Fix Time: {remediation.estimated_fix_time}"
        )
        s += [
            "",
            "ROUTING",
            f"- Destination: {routing.destination}",
            f"- Feedback to: {', '.join(routing.feedback_to)}",
            f"- Notify     : {', '.join(routing.notify)}",
        ]
        return "\n".join(s)
