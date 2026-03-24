"""
agents/orchestrator/agent.py
Kratos multi-agent orchestration pipeline.

Moved from: src/orchestrator.py
Import updates:
  - `from schemas import ...`          → `from src.schemas import ...`
  - `from agent_coordination import …` → `from workflow.context_layer import …`
  - `from agents import …`             → `from src.agents import …`
  - `from agents.base import AgentType`→ `from core.base_agent import AgentType`
  - `from agents.airflow_log_analyzer` → `from src.agents.airflow_log_analyzer`
  - `from agents.change_analyzer_agent`→ `from src.agents.change_analyzer_agent`
  - `from agents.infra_analyzer_agent` → `from src.agents.infra_analyzer_agent`
  - `LLMConfig`                        → `from core.llm import LLMConfig`
  - `AgentResponse`                    → `from core.base_agent import AgentResponse`

Architecture (matches RCA Workflow Architecture diagram):

    KratosControlsHub
           │
           ▼
     KratosOrchestrator  ←── top-level coordinator
           │
           ▼
      RoutingAgent        ←── decides which analyzers to invoke
           │
     ┌─────┼──────────────────────┐
     ▼     ▼          ▼           ▼
  Spark  Change    Code        Data
  Log    Analyzer  Analyzer    Profiler
  Agent  Agent     Agent       Agent
     └─────┼──────────────────────┘
           ▼
    TriangulationAgent   ←── cross-agent correlation + lineage map
           │
           ▼
   RecommendationAgent   ←── fixes + ontology update
           │
           ▼
    KratosReviewer        ←── feedback loop → ControlsHub

Backward compatibility:
  SmartOrchestrator = SparkOrchestrator  (alias preserved)
"""

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

# ── Updated imports ───────────────────────────────────────────────────────────
from core.base_agent import AgentType, AgentResponse
from core.llm import LLMConfig
from workflow.context_layer import AgentContext, SharedFinding

# Schemas still live in src/ until migrated
from src.schemas import (
    AgentFinding,
    AgentTask,
    AnalysisResult,
    AnomalyEvent,
    CrossAgentCorrelation,
    IssueProfile,
    OntologyUpdate,
    ProblemType,
    RecommendationReport,
    RoutingDecision,
    Severity,
    Fix,
    ExecutionFingerprint,
    ChangeFingerprint,
    CodeFingerprint,
    DataFingerprint,
)

# Agent implementations still in src/agents/ until migrated
from src.agents import QueryUnderstandingAgent, RootCauseAgent
from src.agents.airflow_log_analyzer import AirflowLogAnalyzerAgent
from src.agents.change_analyzer_agent import ChangeAnalyzerAgent
from src.agents.infra_analyzer_agent import InfraAnalyzerAgent

logger = logging.getLogger(__name__)


# ============================================================================
# KEYWORD BANKS
# ============================================================================

PERFORMANCE_KEYWORDS = frozenset([
    "slow", "performance", "optimize", "speed", "latency", "timeout",
    "memory", "spill", "shuffle", "skew", "bottleneck", "resource",
    "executor", "task", "stage", "failure", "failed", "crash", "oom",
    "gc", "garbage", "heap", "disk", "io", "network", "cpu",
])

LINEAGE_KEYWORDS = frozenset([
    "lineage", "data flow", "transformation", "query", "plan", "dag",
    "what does", "explain", "understand", "how does", "where does",
    "source", "sink", "input", "output", "column", "table", "join",
    "filter", "aggregate", "group", "partition", "schema",
])

_PENALTY_TO_PROBLEM_TYPE: Dict[str, str] = {
    "task_failures":    "EXECUTION_FAILURE",
    "memory_pressure":  "MEMORY_PRESSURE",
    "shuffle_overhead": "SHUFFLE_OVERHEAD",
    "data_skew":        "DATA_SKEW",
}

_PROBLEM_TYPE_PREFIX: Dict[str, str] = {
    "HEALTHY":            "Healthy Execution: ",
    "EXECUTION_FAILURE":  "Execution Failure: ",
    "MEMORY_PRESSURE":    "Memory Pressure: ",
    "SHUFFLE_OVERHEAD":   "Shuffle Overhead: ",
    "DATA_SKEW":          "Data Skew: ",
    "PERFORMANCE":        "Performance Analysis: ",
    "LINEAGE":            "Query Analysis: ",
    "CHURN_SPIKE":        "Churn Spike: ",
    "CONTRIBUTOR_SILO":   "Contributor Silo: ",
    "REGRESSION_RISK":    "Regression Risk: ",
    "COMPLIANCE_GAP":     "Compliance Gap: ",
    "HIGH_COMPLEXITY":    "High Complexity: ",
    "NULL_SPIKE":         "Null Spike: ",
    "SCHEMA_DRIFT":       "Schema Drift: ",
    "CORRELATED_FAILURE": "Correlated Failure: ",
    "GENERAL":            "Comprehensive Analysis: ",
}

_CRITICAL_WORDS = frozenset(["critical", "severe", "failed", "crash", "oom"])
_HIGH_WORDS     = frozenset(["high", "significant", "major"])
_MEDIUM_WORDS   = frozenset(["warning", "moderate", "medium"])
_LOW_WORDS      = frozenset(["low", "minor", "small"])

_NEGATION_PATTERNS = frozenset([
    "0 failed", "no failed", "no retries", "no failure", "no failures",
    "completed successfully", "all tasks completed",
    "no spill", "0 bytes spill", "zero spill", "0 bytes spilled",
    "0 bytes shuffled", "no shuffle", "no bytes shuffled",
    "broadcast join", "highly optimized", "local operations",
    "no gc pressure", "no memory pressure", "sufficient memory",
    "no oom", "no out-of-memory", "no skew", "no data skew", "no stragglers",
    "no detected", "no anomalies", "no evidence", "no signs",
    "no executor loss", "all executors", "0 executor",
    "sufficient", "stable", "efficient", "successful",
    "clean", "healthy", "optimal", "no issues",
])

_ACTION_VERBS = frozenset([
    "continue", "monitor", "maintain", "reduce", "avoid",
    "consider", "review", "evaluate", "ensure", "check",
    "combine", "reorder", "use", "implement", "optimize",
    "increase", "decrease", "tune", "enable", "disable",
    "investigate", "profile", "verify", "validate", "test",
    "raise", "repartition", "push", "examine",
])

_BARE_HEADER_KEYWORDS = frozenset([
    "task failures", "memory pressure", "data skew", "shuffle overhead",
    "gc pressure", "executor loss", "key operations", "data flow",
    "observations", "correlations", "issues found", "recommendations",
    "summary", "findings", "recommended fix", "health assessment",
    "performance consideration", "compliance gaps", "churn analysis",
    "schema changes", "null analysis", "complexity analysis",
])

_REC_LABELS      = frozenset(["recommended fix", "recommendation", "action"])
_ISSUE_LABEL_RE  = re.compile(
    r"^(Symptom|Root Cause|Impact|Recommended Fix|Recommendation|Note|Cause|Effect|Action):\s*(.*)",
    re.IGNORECASE,
)
_MD_HEADING_RE   = re.compile(r"^#{1,4}\s+")
_LEADING_BOLD_RE = re.compile(r"^\*+\s*")


# ============================================================================
# MODULE-LEVEL HELPERS
# ============================================================================

def _safe_problem_type(
    name: str, fallback: ProblemType = ProblemType.PERFORMANCE
) -> ProblemType:
    try:
        return ProblemType[name]
    except KeyError:
        logger.warning(f"[ORCHESTRATOR] Unknown ProblemType '{name}'; fallback={fallback.name}")
        return fallback


def _is_bare_header(text: str) -> bool:
    clean = text.replace("**", "").strip().rstrip(":").lower()
    if clean in _BARE_HEADER_KEYWORDS:
        return True
    if text.strip().replace("**", "").endswith(":") and len(clean) < 40:
        return True
    return False


def _clean_md(text: str) -> str:
    return text.replace("**", "").strip()


def _strip_bold_and_headings(text: str) -> str:
    text = _MD_HEADING_RE.sub("", text)
    text = _LEADING_BOLD_RE.sub("", text)
    text = text.replace("**", "")
    return text.strip()


def _infer_severity_static(text: str) -> str:
    t = text.lower()
    if any(p in t for p in _NEGATION_PATTERNS): return "info"
    if any(w in t for w in _CRITICAL_WORDS):    return "critical"
    if any(w in t for w in _HIGH_WORDS):        return "high"
    if any(w in t for w in _MEDIUM_WORDS):      return "medium"
    if any(w in t for w in _LOW_WORDS):         return "low"
    return "info"


def _group_flat_findings(
    agent_type: str,
    raw_findings: List[str],
) -> List[AgentFinding]:
    findings: List[AgentFinding] = []
    current_title: Optional[str] = None
    current_rows:  List[tuple]   = []
    issue_counter: int           = 0

    def flush() -> None:
        nonlocal issue_counter
        if not current_rows:
            return
        issue_counter += 1
        title     = current_title or ("Issue" if agent_type == "root_cause" else "Observation")
        desc_rows = [(l, v) for l, v in current_rows if l.lower() not in _REC_LABELS]
        fix_rows  = [(l, v) for l, v in current_rows if l.lower() in _REC_LABELS]
        if not desc_rows:
            return
        description    = "\n".join(f"{l}: {v}" if v else l for l, v in desc_rows)
        recommendation = "\n".join(v for _, v in fix_rows if v) or None
        severity = _infer_severity_static(title)
        if severity == "info":
            severity = _infer_severity_static(description)
        findings.append(AgentFinding(
            agent_type     = agent_type,
            finding_type   = "analysis",
            severity       = Severity(severity) if severity in Severity._value2member_map_ else Severity.INFO,
            title          = title,
            description    = description,
            recommendation = recommendation,
            evidence       = [],
        ))

    for raw in raw_findings:
        clean = _clean_md(raw)
        if not clean:
            continue
        if _is_bare_header(raw):
            flush()
            current_title = clean.rstrip(":")
            current_rows  = []
            continue
        label_match = _ISSUE_LABEL_RE.match(clean)
        if label_match:
            label = label_match.group(1).strip()
            value = label_match.group(2).strip()
            if label.lower() == "symptom" and any(
                row[0].lower() == "symptom" for row in current_rows
            ):
                flush()
                current_title = None
                current_rows  = []
            current_rows.append((label, value))
            continue
        if current_rows:
            last_label, last_value = current_rows[-1]
            current_rows[-1] = (last_label, f"{last_value} {clean}".strip())
        else:
            current_rows.append(("Note", clean))

    flush()
    return findings


def _extract_recommendations(agent_responses: Dict[str, AgentResponse]) -> List[str]:
    seen: set = set()
    recommendations: List[str] = []
    for response in agent_responses.values():
        in_rec_section = False
        for raw_line in response.explanation.split("\n"):
            line  = raw_line.strip()
            clean = _strip_bold_and_headings(line.lstrip("-").lstrip("*"))
            if _MD_HEADING_RE.match(line):
                continue
            if _is_bare_header(line) and "recommend" in clean.lower():
                in_rec_section = True
                continue
            if _is_bare_header(line) and "recommend" not in clean.lower():
                in_rec_section = False
                continue
            if not clean or len(clean) < 20:
                continue
            na_forms = {"n/a", "none needed", "no action required", "none"}
            if clean.lower() in na_forms:
                continue
            skip_prefixes = ("symptom:", "root cause:", "impact:", "recommendation: none")
            if any(clean.lower().startswith(p) for p in skip_prefixes):
                continue
            first_word    = clean.split()[0].lower().rstrip(".")
            is_actionable = (
                first_word in _ACTION_VERBS
                or in_rec_section
                or "recommend" in clean.lower()
            )
            if is_actionable:
                key = clean.lower()
                if key not in seen:
                    seen.add(key)
                    recommendations.append(clean)
    return recommendations[:10]


def _compute_confidence(
    agent_responses: Dict[str, AgentResponse],
    fingerprint:     ExecutionFingerprint,
    problem_type:    ProblemType,
) -> float:
    score    = 0.0
    exec_sum = fingerprint.metrics.execution_summary
    dag      = fingerprint.semantic.dag
    score += sum([
        (exec_sum.total_tasks > 0)               * 6,
        (dag.total_stages > 0)                   * 6,
        (exec_sum.total_duration_ms > 0)         * 6,
        (exec_sum.total_spill_bytes > 0)         * 4,
        (exec_sum.total_shuffle_bytes > 0)       * 4,
        (len(fingerprint.metrics.anomalies) > 0) * 4,
    ])
    rca_resp = agent_responses.get(AgentType.ROOT_CAUSE.value)
    if rca_resp:
        breakdown     = rca_resp.metadata.get("health_score", {}).get("breakdown", {})
        penalties     = {k: float(v) for k, v in breakdown.items()}
        total_penalty = sum(penalties.values())
        if total_penalty > 0:
            top_val = max(penalties.values())
            score  += int((top_val / total_penalty) * 30)
        else:
            score += 28
    n_succeeded = sum(1 for r in agent_responses.values() if getattr(r, "success", True))
    score += {0: 0, 1: 10, 2: 20}.get(n_succeeded, 20)
    if problem_type.name in ("EXECUTION_FAILURE", "MEMORY_PRESSURE"):
        score += 20 if (exec_sum.failed_task_count > 0 or exec_sum.total_spill_bytes > 0) else 5
    elif problem_type.name == "HEALTHY":
        score += 20 if (exec_sum.failed_task_count == 0 and exec_sum.total_spill_bytes == 0) else 10
    else:
        score += 12
    return round(max(min(score, 100) / 100.0, 0.40), 4)


def _derive_problem_type_from_health(rca_response: AgentResponse) -> ProblemType:
    metadata      = rca_response.metadata or {}
    health        = metadata.get("health_score", {})
    status        = health.get("status", "").upper()
    breakdown     = health.get("breakdown", {})
    task_failures    = float(breakdown.get("task_failures",    0.0))
    memory_pressure  = float(breakdown.get("memory_pressure",  0.0))
    shuffle_overhead = float(breakdown.get("shuffle_overhead", 0.0))
    data_skew        = float(breakdown.get("data_skew",        0.0))
    total_penalty    = task_failures + memory_pressure + shuffle_overhead + data_skew
    if status == "HEALTHY" or total_penalty == 0.0:
        return _safe_problem_type("HEALTHY", fallback=ProblemType.PERFORMANCE)
    penalties = {
        "task_failures":    task_failures,
        "memory_pressure":  memory_pressure,
        "shuffle_overhead": shuffle_overhead,
        "data_skew":        data_skew,
    }
    dominant_key    = max(penalties, key=lambda k: penalties[k])
    dominance_ratio = penalties[dominant_key] / total_penalty
    if dominance_ratio >= 0.40:
        return _safe_problem_type(
            _PENALTY_TO_PROBLEM_TYPE[dominant_key],
            fallback=ProblemType.PERFORMANCE,
        )
    return ProblemType.PERFORMANCE


def _classify_problem_from_query(user_query: str, fingerprint: ExecutionFingerprint) -> ProblemType:
    query_lower   = user_query.lower()
    perf_score    = sum(1 for kw in PERFORMANCE_KEYWORDS if kw in query_lower)
    lineage_score = sum(1 for kw in LINEAGE_KEYWORDS     if kw in query_lower)
    if (
        fingerprint.metrics.anomalies
        or fingerprint.metrics.execution_summary.failed_task_count > 0
    ):
        perf_score += 2
    if perf_score > lineage_score:
        return ProblemType.PERFORMANCE
    if lineage_score > perf_score:
        return ProblemType.LINEAGE
    return ProblemType.GENERAL


# ============================================================================
# SPARK ORCHESTRATOR
# ============================================================================

class SparkOrchestrator:
    """
    Spark-specific orchestrator — handles LogAnalyzerAgent path.
    Takes an ExecutionFingerprint, runs RootCauseAgent + QueryUnderstandingAgent,
    returns AnalysisResult.

    Previously called SmartOrchestrator. Alias preserved below.
    """

    def __init__(
        self,
        fingerprint: ExecutionFingerprint,
        llm_config:  Optional[LLMConfig] = None,
    ) -> None:
        self.fingerprint      = fingerprint
        self.fingerprint_dict = fingerprint.model_dump()
        self.llm_config       = llm_config or LLMConfig()
        self._agents: Dict[AgentType, Any] = {
            AgentType.QUERY_UNDERSTANDING: QueryUnderstandingAgent(self.llm_config),
            AgentType.ROOT_CAUSE:          RootCauseAgent(self.llm_config),
        }
        logger.info(
            f"[SPARK_ORCH] Initialized for app: "
            f"{fingerprint.context.spark_config.app_name}"
        )

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        start_time           = time.time()
        initial_problem_type = _classify_problem_from_query(user_query, self.fingerprint)
        hints   = self._analyze_fingerprint_characteristics()
        tasks   = self._plan_agent_execution(initial_problem_type, user_query, hints)
        context = AgentContext(self.fingerprint_dict, user_query)

        agent_responses: Dict[str, AgentResponse] = {}
        agent_sequence:  List[str]                = []

        for task in tasks:
            response = await self._execute_agent_task(task, context)
            if response is not None:
                agent_responses[task.agent_type] = response
                agent_sequence.append(task.agent_type)
                self._share_findings_to_context(task.agent_type, response, context)

        rca_response = agent_responses.get(AgentType.ROOT_CAUSE.value)
        final_problem_type = (
            _derive_problem_type_from_health(rca_response)
            if rca_response else initial_problem_type
        )

        result = self._synthesize_results(
            problem_type    = final_problem_type,
            user_query      = user_query,
            agent_responses = agent_responses,
            agent_sequence  = agent_sequence,
            context         = context,
            start_time      = start_time,
        )
        elapsed = int((time.time() - start_time) * 1000)
        logger.info(
            f"[SPARK_ORCH] Done in {elapsed}ms | "
            f"type={final_problem_type.value} | findings={len(result.findings)}"
        )
        return result

    def _analyze_fingerprint_characteristics(self) -> Dict[str, Any]:
        metrics      = self.fingerprint.metrics
        exec_summary = metrics.execution_summary
        spill_gb     = exec_summary.total_spill_bytes   / (1024 ** 3)
        shuffle_gb   = exec_summary.total_shuffle_bytes / (1024 ** 3)
        anomaly_count = len(metrics.anomalies)
        failure_count = exec_summary.failed_task_count
        hints: Dict[str, Any] = {
            "has_anomalies":   anomaly_count > 0,
            "anomaly_count":   anomaly_count,
            "has_failures":    failure_count > 0,
            "failure_count":   failure_count,
            "has_spill":       exec_summary.total_spill_bytes > 0,
            "spill_gb":        round(spill_gb, 2),
            "has_shuffle":     exec_summary.total_shuffle_bytes > 0,
            "shuffle_gb":      round(shuffle_gb, 2),
            "stage_count":     self.fingerprint.semantic.dag.total_stages,
            "task_count":      exec_summary.total_tasks,
            "execution_class": self.fingerprint.execution_class,
        }
        if failure_count > 0 or anomaly_count >= 3:
            hints["severity"] = "critical"
        elif exec_summary.total_spill_bytes > 0 or anomaly_count >= 1:
            hints["severity"] = "warning"
        else:
            hints["severity"] = "healthy"
        return hints

    def _plan_agent_execution(
        self,
        problem_type:      ProblemType,
        user_query:        str,
        fingerprint_hints: Dict[str, Any],
    ) -> List[AgentTask]:
        tasks: List[AgentTask] = []
        if problem_type == ProblemType.PERFORMANCE:
            tasks.append(AgentTask(
                agent_type       = AgentType.ROOT_CAUSE.value,
                task_description = "Identify root causes of performance issues",
                priority         = 1,
                focus_areas      = self._focus_areas_from_hints(fingerprint_hints),
            ))
            tasks.append(AgentTask(
                agent_type       = AgentType.QUERY_UNDERSTANDING.value,
                task_description = "Correlate query structure with performance findings",
                priority         = 2,
                depends_on       = [AgentType.ROOT_CAUSE.value],
            ))
        elif problem_type == ProblemType.LINEAGE:
            tasks.append(AgentTask(
                agent_type       = AgentType.QUERY_UNDERSTANDING.value,
                task_description = "Explain query execution and data flow",
                priority         = 1,
            ))
            if fingerprint_hints.get("has_anomalies") or fingerprint_hints.get("has_failures"):
                tasks.append(AgentTask(
                    agent_type       = AgentType.ROOT_CAUSE.value,
                    task_description = "Analyse issues affecting data flow",
                    priority         = 2,
                    depends_on       = [AgentType.QUERY_UNDERSTANDING.value],
                ))
        else:
            tasks.append(AgentTask(
                agent_type       = AgentType.QUERY_UNDERSTANDING.value,
                task_description = "Explain what the query does",
                priority         = 1,
            ))
            tasks.append(AgentTask(
                agent_type       = AgentType.ROOT_CAUSE.value,
                task_description = "Analyse execution health and any issues",
                priority         = 2,
                depends_on       = [AgentType.QUERY_UNDERSTANDING.value],
            ))
        return tasks

    def _focus_areas_from_hints(self, hints: Dict[str, Any]) -> List[str]:
        areas: List[str] = []
        if hints.get("has_failures"):              areas.append("task_failures")
        if hints.get("has_spill"):                 areas.append("memory_pressure")
        if hints.get("shuffle_gb", 0.0) > 1.0:    areas.append("shuffle_overhead")
        return areas

    async def _execute_agent_task(
        self, task: AgentTask, context: AgentContext
    ) -> Optional[AgentResponse]:
        agent_type_enum = AgentType(task.agent_type)
        agent           = self._agents.get(agent_type_enum)
        if agent is None:
            logger.warning(f"[SPARK_ORCH] No agent for: {task.agent_type}")
            return None
        kwargs: Dict[str, Any] = {}
        if task.focus_areas:
            kwargs["focus_areas"] = task.focus_areas
        try:
            plan_steps = agent.plan(self.fingerprint_dict, context=context, **kwargs)
            for step in (plan_steps or []):
                logger.info(f"[SPARK_ORCH] Plan · {step}")
        except Exception:
            pass
        try:
            response = await agent.analyze(
                self.fingerprint_dict, context=context, **kwargs
            )
            context.store_agent_output(task.agent_type, response)
            return response
        except Exception as exc:
            logger.exception(f"[SPARK_ORCH] Agent '{task.agent_type}' failed: {exc}")
            return None

    def _share_findings_to_context(
        self, agent_type: str, response: AgentResponse, context: AgentContext
    ) -> None:
        for finding_text in response.key_findings[:5]:
            title = (finding_text[:50] + "…") if len(finding_text) > 50 else finding_text
            context.add_finding(SharedFinding(
                agent_type   = agent_type,
                finding_type = "key_finding",
                severity     = "info",
                title        = title,
                description  = finding_text,
            ))
        explanation_lower = response.explanation.lower()
        focus_map = {
            "memory_pressure":      ["memory", "spill"],
            "data_skew":            ["skew"],
            "shuffle_optimization": ["shuffle"],
        }
        for focus_area, keywords in focus_map.items():
            if any(kw in explanation_lower for kw in keywords):
                context.add_focus_area(focus_area)

    def _synthesize_results(
        self,
        problem_type:    ProblemType,
        user_query:      str,
        agent_responses: Dict[str, AgentResponse],
        agent_sequence:  List[str],
        context:         AgentContext,
        start_time:      float,
    ) -> AnalysisResult:
        all_findings: List[AgentFinding] = []
        for agent_type, response in agent_responses.items():
            grouped = _group_flat_findings(agent_type, response.key_findings)
            all_findings.extend(grouped)
        all_recommendations = _extract_recommendations(agent_responses)
        confidence          = _compute_confidence(agent_responses, self.fingerprint, problem_type)
        total_time_ms       = int((time.time() - start_time) * 1000)
        rca_resp     = agent_responses.get(AgentType.ROOT_CAUSE.value)
        health_score = 100.0
        if rca_resp:
            health_score = float(
                rca_resp.metadata.get("health_score", {}).get("score", 100.0)
            )
        prefix    = _PROBLEM_TYPE_PREFIX.get(problem_type.name, "Analysis: ")
        summaries = [_strip_bold_and_headings(r.summary) for r in agent_responses.values()]
        combined  = " ".join(s for s in summaries if s)
        fc = len(context.get_findings())
        if fc:
            combined += f" ({fc} key findings identified)"
        executive_summary = prefix + combined
        detailed_analysis = "\n\n---\n\n".join(
            f"## {resp.agent_name}\n\n{resp.explanation}"
            for resp in agent_responses.values()
        )
        return AnalysisResult(
            problem_type             = problem_type,
            user_query               = user_query,
            executive_summary        = executive_summary,
            detailed_analysis        = detailed_analysis,
            findings                 = all_findings,
            recommendations          = all_recommendations,
            health_score             = health_score,
            agents_used              = list(agent_responses.keys()),
            agent_sequence           = agent_sequence,
            total_processing_time_ms = total_time_ms,
            confidence               = confidence,
            raw_agent_responses      = {k: v.model_dump() for k, v in agent_responses.items()},
        )

    @staticmethod
    def _infer_severity_static(text: str) -> str:
        return _infer_severity_static(text)

    @staticmethod
    def _infer_severity(text: str) -> str:
        return _infer_severity_static(text)


# Backward compatibility alias
SmartOrchestrator = SparkOrchestrator


# ============================================================================
# AIRFLOW LOG ANALYZER ORCHESTRATOR
# ============================================================================

class AirflowLogAnalyzerOrchestrator:
    """Thin wrapper so AirflowLogAnalyzerAgent fits the solve_problem interface."""

    def __init__(
        self,
        fingerprint: Dict[str, Any],
        llm_config: Optional[LLMConfig] = None,
    ) -> None:
        self.fingerprint = fingerprint
        self.agent       = AirflowLogAnalyzerAgent()
        self.llm_config  = llm_config or LLMConfig()

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        resp = await self.agent.analyze(fingerprint_data=self.fingerprint)
        health   = resp.metadata.get("health", "Healthy")
        severity = resp.metadata.get("severity", "low")
        health_score = 100.0 if health == "Healthy" else (70.0 if severity == "medium" else 40.0)
        finding = AgentFinding(
            agent_type   = "airflow_log_analyzer",
            finding_type = "analysis",
            severity     = Severity.INFO,
            title        = resp.summary,
            description  = "\n".join(resp.key_findings),
            recommendation = None,
            evidence       = [],
        )
        airflow_recs: List[str] = []
        if health != "Healthy" or severity in ("high", "critical"):
            airflow_recs = [
                "Investigate the upstream API returning HTTP 500 errors and add retry logic with exponential backoff.",
                "Add a circuit-breaker or dead-letter queue for the market-data source to prevent cascade failures.",
                "Set explicit Airflow task timeouts and on-failure callbacks to surface failures early.",
            ]
        return AnalysisResult(
            problem_type             = ProblemType.GENERAL,
            user_query               = user_query or "Airflow task post-execution analysis",
            executive_summary        = resp.summary,
            detailed_analysis        = resp.explanation,
            findings                 = [finding],
            recommendations          = airflow_recs,
            health_score             = health_score,
            agents_used              = ["airflow_log_analyzer"],
            agent_sequence           = ["airflow_log_analyzer"],
            total_processing_time_ms = 0,
            confidence               = resp.confidence,
            raw_agent_responses      = {"airflow_log_analyzer": resp.model_dump()},
        )


# ============================================================================
# ROUTING AGENT
# ============================================================================

class RoutingAgent:
    """
    First-layer agent: decides which analyzers to invoke based on job metadata
    and failure signals. Produces an ordered AgentTask list for KratosOrchestrator.
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self.llm_config = llm_config or LLMConfig()

    def route(
        self,
        job_id:               str,
        trigger:              str,
        user_query:           str,
        spark_log_path:       Optional[str] = None,
        repo_path:            Optional[str] = None,
        dataset_path:         Optional[str] = None,
        git_log_path:         Optional[str] = None,
        execution_fingerprint:Optional[ExecutionFingerprint] = None,
        airflow_fingerprint:  Optional[Dict[str, Any]] = None,
        infra_fingerprint:    Optional[Dict[str, Any]] = None,
    ) -> RoutingDecision:

        invoke_spark_log   = bool(spark_log_path or execution_fingerprint or trigger == "failure")
        invoke_airflow_log = bool(airflow_fingerprint)
        invoke_code        = bool(repo_path or trigger == "compliance_scan")
        invoke_data        = bool(dataset_path or trigger == "data_quality")
        invoke_change      = bool(git_log_path or trigger == "code_change")
        invoke_infra       = bool(infra_fingerprint or trigger == "infra_check")

        if not any([invoke_spark_log, invoke_airflow_log, invoke_code, invoke_data, invoke_change, invoke_infra]):
            invoke_spark_log = True

        tasks: List[AgentTask] = []
        priority = 1

        if invoke_spark_log:
            tasks.append(AgentTask(
                agent_type       = "spark_log_analyzer",
                task_description = "Analyse Spark execution log for failures, memory pressure, and performance issues",
                priority         = priority,
                source_data      = {
                    "spark_log_path":         spark_log_path,
                    "execution_fingerprint":  "pre_built" if execution_fingerprint else None,
                },
            ))
            priority += 1

        if invoke_airflow_log:
            tasks.append(AgentTask(
                agent_type       = "airflow_log_analyzer",
                task_description = "Analyse Airflow task logs for health, retries, and data ingestion behaviour",
                priority         = priority,
                source_data      = {"airflow_fingerprint": True},
            ))
            priority += 1

        if invoke_code:
            tasks.append(AgentTask(
                agent_type       = "code_analyzer",
                task_description = "Scan codebase for FDIC compliance gaps, complexity, and dead code",
                priority         = priority,
                source_data      = {"repo_path": repo_path},
            ))
            priority += 1

        if invoke_data:
            tasks.append(AgentTask(
                agent_type       = "data_profiler",
                task_description = "Profile dataset for null rates, schema drift, and distribution anomalies",
                priority         = priority,
                source_data      = {"dataset_path": dataset_path},
            ))
            priority += 1

        if invoke_change:
            tasks.append(AgentTask(
                agent_type       = "change_analyzer",
                task_description = "Analyse git commit history for churn spikes, contributor silos, and regression risk",
                priority         = priority,
                source_data      = {"git_log_path": git_log_path},
            ))
            priority += 1

        if invoke_infra:
            tasks.append(AgentTask(
                agent_type       = "infra_analyzer",
                task_description = "Analyse cluster/infrastructure metrics for resource saturation and autoscaling events",
                priority         = priority,
                source_data      = {"infra_fingerprint": "pre_built"},
            ))

        rationale_parts = []
        if invoke_spark_log:   rationale_parts.append("Spark log present → Spark LogAnalyzer")
        if invoke_airflow_log: rationale_parts.append("Airflow fingerprint → Airflow LogAnalyzer")
        if invoke_code:        rationale_parts.append("Repo path present → CodeAnalyzer")
        if invoke_data:        rationale_parts.append("Dataset path present → DataProfiler")
        if invoke_change:      rationale_parts.append("Git log present → ChangeAnalyzer")
        if invoke_infra:       rationale_parts.append("Infra fingerprint present → InfraAnalyzer")

        logger.info(f"[ROUTING] {job_id}: {' | '.join(rationale_parts)}")

        return RoutingDecision(
            job_id                 = job_id,
            trigger                = trigger,
            invoke_log_analyzer    = invoke_spark_log or invoke_airflow_log,
            invoke_code_analyzer   = invoke_code,
            invoke_data_profiler   = invoke_data,
            invoke_change_analyzer = invoke_change,
            invoke_infra_analyzer  = invoke_infra,
            routing_rationale      = " | ".join(rationale_parts),
            tasks                  = tasks,
        )


# ============================================================================
# STUB ANALYZER ORCHESTRATORS
# ============================================================================

class CodeAnalyzerOrchestrator:
    def __init__(self, repo_path: str, llm_config: Optional[LLMConfig] = None) -> None:
        self.repo_path  = repo_path
        self.llm_config = llm_config or LLMConfig()

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        logger.info(f"[CODE_ORCH] Stub — repo={self.repo_path}")
        return AnalysisResult(
            problem_type=ProblemType.GENERAL, user_query=user_query,
            executive_summary="Code Analyzer: analysis pending implementation.",
            detailed_analysis="", health_score=100.0, confidence=0.50,
        )


class DataProfilerOrchestrator:
    def __init__(self, dataset_path: str, llm_config: Optional[LLMConfig] = None) -> None:
        self.dataset_path = dataset_path
        self.llm_config   = llm_config or LLMConfig()

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        logger.info(f"[DATA_ORCH] Stub — dataset={self.dataset_path}")
        return AnalysisResult(
            problem_type=ProblemType.GENERAL, user_query=user_query,
            executive_summary="Data Profiler: analysis pending implementation.",
            detailed_analysis="", health_score=100.0, confidence=0.50,
        )


class ChangeAnalyzerOrchestrator:
    def __init__(self, git_log_path: str, llm_config: Optional[LLMConfig] = None) -> None:
        self.git_log_path = git_log_path
        self.llm_config   = llm_config or LLMConfig()
        self._agent       = ChangeAnalyzerAgent(self.llm_config)

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        import json as _json
        with open(self.git_log_path, "r", encoding="utf-8") as f:
            fingerprint_data = _json.load(f)
        resp = self._agent.analyze(fingerprint_data=fingerprint_data)
        text = (resp.summary + " " + " ".join(resp.key_findings)).lower()
        if "churn spike" in text:   problem_type = ProblemType.CHURN_SPIKE
        elif "contributor silo" in text: problem_type = ProblemType.CONTRIBUTOR_SILO
        elif "risk" in text:        problem_type = ProblemType.REGRESSION_RISK
        else:                       problem_type = ProblemType.GENERAL
        findings: List[AgentFinding] = [
            AgentFinding(
                agent_type="change_analyzer", finding_type="analysis",
                severity=Severity.HIGH if "spike" in f_txt.lower() or "silo" in f_txt.lower() else Severity.MEDIUM,
                title=f_txt[:80], description=f_txt, recommendation=None, evidence=[],
            )
            for f_txt in resp.key_findings
        ]
        return AnalysisResult(
            problem_type=problem_type, user_query=user_query,
            executive_summary=resp.summary, detailed_analysis=resp.explanation,
            findings=findings, recommendations=[], health_score=100.0 if problem_type == ProblemType.GENERAL else 70.0,
            confidence=resp.confidence, agents_used=["change_analyzer"],
            agent_sequence=["change_analyzer"], total_processing_time_ms=0,
            raw_agent_responses={"change_analyzer": resp.model_dump()},
        )


class InfraAnalyzerOrchestrator:
    def __init__(self, infra_fingerprint: Dict[str, Any], llm_config: Optional[LLMConfig] = None) -> None:
        self.infra_fingerprint = infra_fingerprint
        self.llm_config        = llm_config or LLMConfig()
        self._agent            = InfraAnalyzerAgent(self.llm_config)

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        resp       = self._agent.analyze(fingerprint_data=self.infra_fingerprint)
        cluster_id = self.infra_fingerprint.get("cluster_id", "unknown")
        logger.info(f"[INFRA_ORCH] cluster={cluster_id}")
        text = (resp.summary + " " + " ".join(resp.key_findings)).lower()
        if "critical" in text and ("memory" in text or "oom" in text):
            problem_type = ProblemType.MEMORY_PRESSURE
        elif "critical" in text or "severe resource" in text:
            problem_type = ProblemType.RESOURCE_PRESSURE
        elif "high" in text and ("cpu" in text or "executor" in text or "scale" in text):
            problem_type = ProblemType.RESOURCE_PRESSURE
        else:
            problem_type = ProblemType.GENERAL
        findings: List[AgentFinding] = [
            AgentFinding(
                agent_type="infra_analyzer", finding_type="infra_metric",
                severity=Severity.CRITICAL if f_txt.startswith("CRITICAL") else
                         Severity.HIGH     if f_txt.startswith("HIGH")     else
                         Severity.MEDIUM   if f_txt.startswith("MEDIUM")   else Severity.INFO,
                title=f_txt[:80], description=f_txt, recommendation=None, evidence=[],
            )
            for f_txt in resp.key_findings
        ]
        meta_sev = resp.metadata.get("severity", "low")
        health_score = {"critical": 40.0, "high": 65.0, "medium": 80.0, "low": 100.0}.get(meta_sev, 100.0)
        return AnalysisResult(
            problem_type=problem_type, user_query=user_query,
            executive_summary=resp.summary, detailed_analysis=resp.explanation,
            findings=findings, recommendations=[], health_score=health_score,
            confidence=resp.confidence, agents_used=["infra_analyzer"],
            agent_sequence=["infra_analyzer"], total_processing_time_ms=0,
            raw_agent_responses={"infra_analyzer": resp.model_dump()},
        )


# ============================================================================
# TRIANGULATION AGENT
# ============================================================================

class TriangulationAgent:
    """Cross-agent correlation engine that merges all AnalysisResults into an IssueProfile."""

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self.llm_config = llm_config or LLMConfig()

    def triangulate(
        self,
        job_id:        str,
        log_result:    Optional[AnalysisResult] = None,
        code_result:   Optional[AnalysisResult] = None,
        data_result:   Optional[AnalysisResult] = None,
        change_result: Optional[AnalysisResult] = None,
        infra_result:  Optional[AnalysisResult] = None,
    ) -> IssueProfile:
        correlations: List[CrossAgentCorrelation] = []
        all_results = {
            "log_analyzer":    log_result,
            "code_analyzer":   code_result,
            "data_profiler":   data_result,
            "change_analyzer": change_result,
            "infra_analyzer":  infra_result,
        }
        active_results = {k: v for k, v in all_results.items() if v is not None}

        if log_result and change_result:
            log_has_failure  = log_result.problem_type in (ProblemType.EXECUTION_FAILURE, ProblemType.MEMORY_PRESSURE)
            change_has_churn = change_result.problem_type in (ProblemType.CHURN_SPIKE, ProblemType.REGRESSION_RISK)
            if log_has_failure and change_has_churn:
                correlations.append(CrossAgentCorrelation(
                    correlation_id="churn+fail", contributing_agents=["log_analyzer", "change_analyzer"],
                    pattern="Recent high-churn commits correlate with Spark execution failures.",
                    severity=Severity.CRITICAL, confidence=0.82,
                    evidence={"log_problem": log_result.problem_type.value, "change_problem": change_result.problem_type.value},
                    affected_artifacts=[],
                ))

        if log_result and infra_result:
            if (
                log_result.problem_type in (ProblemType.EXECUTION_FAILURE, ProblemType.MEMORY_PRESSURE, ProblemType.PERFORMANCE)
                and infra_result.problem_type in (ProblemType.RESOURCE_PRESSURE, ProblemType.MEMORY_PRESSURE)
            ):
                correlations.append(CrossAgentCorrelation(
                    correlation_id="infra+exec", contributing_agents=["log_analyzer", "infra_analyzer"],
                    pattern="Cluster-level resource saturation coincides with Spark execution issues.",
                    severity=Severity.CRITICAL, confidence=0.84,
                    evidence={"log_problem": log_result.problem_type.value, "infra_problem": infra_result.problem_type.value},
                    affected_artifacts=[],
                ))

        scores        = [r.health_score for r in active_results.values()]
        overall_health = sum(scores) / len(scores) if scores else 100.0

        if correlations:
            dominant = ProblemType.CORRELATED_FAILURE
        else:
            problem_counts: Dict[str, int] = {}
            for r in active_results.values():
                pt = r.problem_type.value
                problem_counts[pt] = problem_counts.get(pt, 0) + 1
            dominant_name = max(problem_counts, key=lambda k: problem_counts[k]) if problem_counts else "GENERAL"
            dominant = _safe_problem_type(dominant_name.upper(), fallback=ProblemType.GENERAL)

        lineage_map: Dict[str, List[str]] = {
            name: [f.title for f in result.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
            for name, result in active_results.items()
            if any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in result.findings)
        }

        total_findings    = sum(len(r.findings) for r in active_results.values())
        critical_findings = sum(1 for r in active_results.values() for f in r.findings if f.severity == Severity.CRITICAL)
        confidences       = [r.confidence for r in active_results.values()]
        overall_conf      = sum(confidences) / len(confidences) if confidences else 0.50

        logger.info(
            f"[TRIANGULATION] {job_id}: {len(correlations)} correlations | "
            f"dominant={dominant.value} | health={overall_health:.1f}"
        )

        return IssueProfile(
            job_id                  = job_id,
            generated_at            = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            dominant_problem_type   = dominant,
            log_analysis            = log_result,
            code_analysis           = code_result,
            data_analysis           = data_result,
            change_analysis         = change_result,
            infra_analysis          = infra_result,
            correlations            = correlations,
            lineage_map             = lineage_map,
            overall_health_score    = round(overall_health, 2),
            overall_confidence      = round(overall_conf, 4),
            agents_invoked          = list(active_results.keys()),
            total_findings_count    = total_findings,
            critical_findings_count = critical_findings,
        )


# ============================================================================
# RECOMMENDATION AGENT
# ============================================================================

class RecommendationAgent:
    """Terminal agent: IssueProfile → RecommendationReport with prioritized fixes."""

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self.llm_config = llm_config or LLMConfig()

    def recommend(self, issue_profile: IssueProfile) -> RecommendationReport:
        fixes: List[Fix] = []
        fix_counter = 1

        agent_result_map = {
            "log_analyzer":    issue_profile.log_analysis,
            "code_analyzer":   issue_profile.code_analysis,
            "data_profiler":   issue_profile.data_analysis,
            "change_analyzer": issue_profile.change_analysis,
            "infra_analyzer":  issue_profile.infra_analysis,
        }
        for agent_name, result in agent_result_map.items():
            if result is None:
                continue
            for i, rec_text in enumerate(result.recommendations[:3]):
                fixes.append(Fix(
                    fix_id            = f"FIX-{fix_counter:03d}",
                    title             = f"{agent_name.replace('_', ' ').title()} Fix {i + 1}",
                    description       = rec_text,
                    applies_to_agents = [agent_name],
                    priority          = fix_counter,
                    effort            = "medium",
                    code_snippet      = None,
                    references        = [],
                ))
                fix_counter += 1

        for correlation in issue_profile.correlations:
            fixes.append(Fix(
                fix_id            = f"FIX-{fix_counter:03d}",
                title             = f"Cross-Agent: {correlation.pattern[:60]}",
                description       = correlation.pattern,
                applies_to_agents = correlation.contributing_agents,
                priority          = fix_counter,
                effort            = "high",
                code_snippet      = None,
                references        = [],
            ))
            fix_counter += 1

        fixes.sort(key=lambda f: f.priority)

        if issue_profile.critical_findings_count > 0:
            signal = "ESCALATE"
        elif issue_profile.overall_health_score < 60:
            signal = "RE_RUN"
        elif issue_profile.overall_health_score >= 90:
            signal = "RESOLVED"
        else:
            signal = "MONITOR"

        profile_hash = hashlib.sha256(
            json.dumps(issue_profile.model_dump(), default=str).encode()
        ).hexdigest()[:16]

        ontology_update = OntologyUpdate(
            job_id               = issue_profile.job_id,
            timestamp            = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            issue_profile_hash   = profile_hash,
            new_patterns_learned = [c.pattern for c in issue_profile.correlations],
            updated_control_refs = [
                f.title for f in (issue_profile.code_analysis.findings if issue_profile.code_analysis else [])
                if "FDIC" in f.title or "compliance" in f.title.lower()
            ],
            lineage_nodes_added  = list(issue_profile.lineage_map.keys()),
        )

        agent_labels = ", ".join(a.replace("_", " ").title() for a in issue_profile.agents_invoked)
        exec_summary = (
            f"{issue_profile.dominant_problem_type.value.replace('_', ' ').title()} detected "
            f"across {len(issue_profile.agents_invoked)} analyzer(s) ({agent_labels}). "
            f"Health score: {issue_profile.overall_health_score:.0f}/100. "
            f"{len(fixes)} fixes generated. Signal: {signal}."
        )
        logger.info(f"[RECOMMENDATION] {issue_profile.job_id}: {len(fixes)} fixes | signal={signal}")

        return RecommendationReport(
            job_id             = issue_profile.job_id,
            generated_at       = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            issue_profile      = issue_profile,
            prioritized_fixes  = fixes,
            executive_summary  = exec_summary,
            detailed_narrative = (
                f"Analysis ran {len(issue_profile.agents_invoked)} agents. "
                f"{issue_profile.total_findings_count} total findings, "
                f"{issue_profile.critical_findings_count} critical. "
                f"{len(issue_profile.correlations)} cross-agent correlations identified."
            ),
            ontology_update      = ontology_update,
            feedback_loop_signal = signal,
            reviewer_notes       = None,
        )


# ============================================================================
# KRATOS ORCHESTRATOR  (top-level coordinator)
# ============================================================================

_RT2CK: Dict[str, str] = {
    "spark_log_analyzer":   "log_analyzer",
    "airflow_log_analyzer": "log_analyzer",
    "code_analyzer":        "code_analyzer",
    "data_profiler":        "data_profiler",
    "change_analyzer":      "change_analyzer",
    "infra_analyzer":       "infra_analyzer",
}

_CK_LABEL: Dict[str, str] = {
    "log_analyzer":    "Spark / Log Analyzer",
    "code_analyzer":   "Code Analyzer",
    "data_profiler":   "Data Profiler",
    "change_analyzer": "Change Analyzer",
    "infra_analyzer":  "Infra Analyzer",
}


async def _timed_coro(coro: Any) -> tuple:
    t = time.time()
    result = await coro
    return result, int((time.time() - t) * 1000)


class KratosOrchestrator:
    """
    Top-level multi-agent coordinator.

    Accepts a routing decision, runs per-domain orchestrators in parallel,
    feeds results to TriangulationAgent, and returns a RecommendationReport.
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None) -> None:
        self.llm_config = llm_config or LLMConfig()
        self._triangulation  = TriangulationAgent(self.llm_config)
        self._recommendation = RecommendationAgent(self.llm_config)

    async def run(
        self,
        job_id:     str,
        decision:   RoutingDecision,
        user_query: str,
        # Optional pre-built fingerprints / paths
        execution_fingerprint: Optional[ExecutionFingerprint] = None,
        spark_log_path:        Optional[str] = None,
        airflow_fingerprint:   Optional[Dict[str, Any]] = None,
        repo_path:             Optional[str] = None,
        dataset_path:          Optional[str] = None,
        git_log_path:          Optional[str] = None,
        infra_fingerprint:     Optional[Dict[str, Any]] = None,
    ) -> RecommendationReport:

        coros: Dict[str, Any] = {}

        for task in decision.tasks:
            at = task.agent_type

            if at == "spark_log_analyzer" and execution_fingerprint:
                orch = SparkOrchestrator(execution_fingerprint, self.llm_config)
                coros["log_analyzer"] = _timed_coro(orch.solve_problem(user_query))

            elif at == "airflow_log_analyzer" and airflow_fingerprint:
                orch = AirflowLogAnalyzerOrchestrator(airflow_fingerprint, self.llm_config)
                coros["log_analyzer"] = _timed_coro(orch.solve_problem(user_query))

            elif at == "code_analyzer" and repo_path:
                orch = CodeAnalyzerOrchestrator(repo_path, self.llm_config)
                coros["code_analyzer"] = _timed_coro(orch.solve_problem(user_query))

            elif at == "data_profiler" and dataset_path:
                orch = DataProfilerOrchestrator(dataset_path, self.llm_config)
                coros["data_profiler"] = _timed_coro(orch.solve_problem(user_query))

            elif at == "change_analyzer" and git_log_path:
                orch = ChangeAnalyzerOrchestrator(git_log_path, self.llm_config)
                coros["change_analyzer"] = _timed_coro(orch.solve_problem(user_query))

            elif at == "infra_analyzer" and infra_fingerprint:
                orch = InfraAnalyzerOrchestrator(infra_fingerprint, self.llm_config)
                coros["infra_analyzer"] = _timed_coro(orch.solve_problem(user_query))

        results_with_timing = await asyncio.gather(*coros.values(), return_exceptions=True)
        domain_results: Dict[str, AnalysisResult] = {}
        for chain_key, outcome in zip(coros.keys(), results_with_timing):
            if isinstance(outcome, Exception):
                logger.error(f"[KRATOS_ORCH] {chain_key} failed: {outcome}")
            else:
                result, elapsed = outcome
                domain_results[chain_key] = result
                logger.info(f"[KRATOS_ORCH] {chain_key} finished in {elapsed}ms")

        issue_profile = self._triangulation.triangulate(
            job_id        = job_id,
            log_result    = domain_results.get("log_analyzer"),
            code_result   = domain_results.get("code_analyzer"),
            data_result   = domain_results.get("data_profiler"),
            change_result = domain_results.get("change_analyzer"),
            infra_result  = domain_results.get("infra_analyzer"),
        )

        report = self._recommendation.recommend(issue_profile)
        logger.info(
            f"[KRATOS_ORCH] {job_id} complete | "
            f"health={issue_profile.overall_health_score:.1f} | "
            f"signal={report.feedback_loop_signal}"
        )
        return report
