"""
Smart Orchestrator for Spark Fingerprint Analysis

Coordinates multiple agents based on user queries and fingerprint characteristics.
Two-layer architecture: orchestrator sits on top of fingerprint infrastructure + agents.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

from src.schemas import (
    ExecutionFingerprint,
    ProblemType,
    AgentTask,
    AgentFinding,
    AnalysisResult,
)
from src.agent_coordination import AgentContext, SharedFinding
from src.agents import QueryUnderstandingAgent, RootCauseAgent, LLMConfig, AgentResponse
from src.agents.base import AgentType


logger = logging.getLogger(__name__)


# ── Keyword banks ──────────────────────────────────────────────────────────────

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

# Maps health breakdown keys → ProblemType enum members
_PENALTY_TO_PROBLEM_TYPE: Dict[str, str] = {
    "task_failures":    "EXECUTION_FAILURE",
    "memory_pressure":  "MEMORY_PRESSURE",
    "shuffle_overhead": "SHUFFLE_OVERHEAD",
    "data_skew":        "DATA_SKEW",
}

# Plain-text summary prefix per problem type (no emoji — icon assigned by frontend)
_PROBLEM_TYPE_PREFIX: Dict[str, str] = {
    "HEALTHY":           "Healthy Execution: ",
    "EXECUTION_FAILURE": "Execution Failure: ",
    "MEMORY_PRESSURE":   "Memory Pressure: ",
    "SHUFFLE_OVERHEAD":  "Shuffle Overhead: ",
    "DATA_SKEW":         "Data Skew: ",
    "PERFORMANCE":       "Performance Analysis: ",
    "LINEAGE":           "Query Analysis: ",
    "GENERAL":           "Comprehensive Analysis: ",
}

_CRITICAL_WORDS = frozenset(["critical", "severe", "failed", "crash", "oom"])
_HIGH_WORDS     = frozenset(["high", "significant", "major"])
_MEDIUM_WORDS   = frozenset(["warning", "moderate", "medium"])
_LOW_WORDS      = frozenset(["low", "minor", "small"])

# Negation patterns — findings describing absence of issues → always "info".
# Checked BEFORE keyword banks to prevent false positives like:
#   "No failed tasks"  → matches "failed" → incorrectly CRITICAL
#   "0 bytes shuffled" → matches nothing  → correctly INFO
_NEGATION_PATTERNS = frozenset([
    "0 failed", "no failed", "no retries", "no failure", "no failures",
    "completed successfully", "all tasks completed",
    "no spill", "0 bytes spill", "zero spill", "0 bytes spilled",
    "0 bytes shuffled", "no shuffle", "no bytes shuffled",
    "broadcast join", "highly optimized", "local operations",
    "no gc pressure", "no memory pressure", "sufficient memory",
    "no oom", "no out-of-memory",
    "no skew", "no data skew", "no stragglers",
    "no detected", "no anomalies", "no evidence", "no signs",
    "no executor loss", "all executors", "0 executor",
    "sufficient", "stable", "efficient", "successful",
    "clean", "healthy", "optimal", "no issues",
])

# Action verbs that mark genuinely actionable recommendation lines
_ACTION_VERBS = frozenset([
    "continue", "monitor", "maintain", "reduce", "avoid",
    "consider", "review", "evaluate", "ensure", "check",
    "combine", "reorder", "use", "implement", "optimize",
    "increase", "decrease", "tune", "enable", "disable",
    "investigate", "profile", "verify", "validate", "test",
    "raise", "repartition", "push", "examine",
])

# Known bare section-header keywords emitted by the LLM
_BARE_HEADER_KEYWORDS = frozenset([
    "task failures", "memory pressure", "data skew", "shuffle overhead",
    "gc pressure", "executor loss", "key operations", "data flow",
    "observations", "correlations", "issues found", "recommendations",
    "summary", "findings", "recommended fix", "health assessment",
    "performance consideration",
])

# Labels that mark a recommendation row inside a finding body
_REC_LABELS = frozenset(["recommended fix", "recommendation", "action"])

# Labeled-row prefixes the LLM uses inside finding bodies
_ISSUE_LABEL_RE = re.compile(
    r"^(Symptom|Root Cause|Impact|Recommended Fix|Recommendation|Note|Cause|Effect|Action):\s*(.*)",
    re.IGNORECASE,
)

# Markdown heading lines — always skipped when extracting recommendations
_MD_HEADING_RE = re.compile(r"^#{1,4}\s+")

# Stray leading bold markers like "** This Spark job..."
_LEADING_BOLD_RE = re.compile(r"^\*+\s*")


# ── Module-level helpers ───────────────────────────────────────────────────────


def _safe_problem_type(name: str, fallback: ProblemType = ProblemType.PERFORMANCE) -> ProblemType:
    """Return ProblemType[name] or fallback if the member does not exist."""
    try:
        return ProblemType[name]
    except KeyError:
        logger.warning(
            f"[ORCHESTRATOR] ProblemType has no member '{name}'; "
            f"falling back to {fallback.name}"
        )
        return fallback


def _is_bare_header(text: str) -> bool:
    """
    Return True when a line is a bare section label with no standalone content.
    Examples that return True:
        "**Task Failures:**"  |  "Recommended Fix:"  |  "Observations:"
    """
    clean = text.replace("**", "").strip().rstrip(":").lower()
    if clean in _BARE_HEADER_KEYWORDS:
        return True
    # Short colon-terminated line with no sentence structure
    if text.strip().replace("**", "").endswith(":") and len(clean) < 40:
        return True
    return False


def _clean_md(text: str) -> str:
    """Strip markdown bold markers and surrounding whitespace."""
    return text.replace("**", "").strip()


def _strip_bold_and_headings(text: str) -> str:
    """
    Remove stray leading bold markers ("** sentence...") and inline
    markdown bold (**word**) from a summary or recommendation string.
    Also removes markdown heading prefixes (### 2. Title).
    """
    text = _MD_HEADING_RE.sub("", text)
    text = _LEADING_BOLD_RE.sub("", text)
    text = text.replace("**", "")
    return text.strip()


def _infer_severity_static(text: str) -> str:
    """
    Infer severity from text content.
    Negation check runs first to prevent false positives.
    """
    t = text.lower()
    if any(p in t for p in _NEGATION_PATTERNS): return "info"
    if any(w in t for w in _CRITICAL_WORDS):    return "critical"
    if any(w in t for w in _HIGH_WORDS):        return "high"
    if any(w in t for w in _MEDIUM_WORDS):      return "medium"
    if any(w in t for w in _LOW_WORDS):         return "low"
    return "info"


# ── Finding grouper ────────────────────────────────────────────────────────────


def _group_flat_findings(
    agent_type:   str,
    raw_findings: List[str],
) -> List[AgentFinding]:
    """
    Convert the LLM's flat key_findings list into structured AgentFinding cards.

    The LLM emits findings in two shapes:

    Shape A — explicit section headers present:
        ["**Task Failures:**",
         "**Symptom:** 3 tasks failed",
         "**Impact:** retries triggered",
         "**Recommended Fix:** Increase executor memory",
         "**Memory Pressure:**",
         "**Symptom:** 8 GB spilled", ...]

    Shape B — no section headers, just Symptom/Root Cause/Impact runs:
        ["**Symptom:** 3 tasks failed",
         "**Root Cause:** OOM",
         "**Impact:** retries triggered",
         "**Recommended Fix:** Increase executor memory",
         "**Symptom:** 8 GB spilled",   ← new issue group starts here
         "**Root Cause:** low memory", ...]

    Grouping rules:
    - A bare header line (Shape A) flushes the current card and starts a new one.
    - A repeated "Symptom:" label (Shape B) also flushes and starts a new card.
    - Rows with labels in _REC_LABELS go into finding.recommendation, not description.
    - Cards with no description rows are discarded.
    - Severity is inferred from title first; falls back to description if title is generic.
    """
    findings:      List[AgentFinding] = []
    current_title: Optional[str]      = None
    current_rows:  List[tuple]        = []   # (label, value) pairs
    issue_counter: int                = 0

    def flush() -> None:
        nonlocal issue_counter
        if not current_rows:
            return
        issue_counter += 1
        title = current_title or ("Issue" if agent_type == "root_cause" else "Observation")

        # Split rows: diagnostic → description, fix/recommendation → recommendation field
        desc_rows = [(l, v) for l, v in current_rows if l.lower() not in _REC_LABELS]
        fix_rows  = [(l, v) for l, v in current_rows if l.lower() in _REC_LABELS]

        if not desc_rows:
            return  # nothing meaningful to show

        description    = "\n".join(f"{l}: {v}" if v else l for l, v in desc_rows)
        recommendation = "\n".join(v for _, v in fix_rows if v) or None

        # Infer severity from title; if generic, use description (never recommendation text)
        severity = _infer_severity_static(title)
        if severity == "info":
            severity = _infer_severity_static(description)

        findings.append(AgentFinding(
            agent_type     = agent_type,
            finding_type   = "analysis",
            severity       = severity,
            title          = title,
            description    = description,
            recommendation = recommendation,
            evidence       = [],
        ))

    for raw in raw_findings:
        clean = _clean_md(raw)
        if not clean:
            continue

        # ── Shape A: bare section header → flush + start new card ────────────
        if _is_bare_header(raw):
            flush()
            current_title = clean.rstrip(":")
            current_rows  = []
            continue

        # ── Labeled row: "Symptom: ...", "Root Cause: ...", etc. ─────────────
        label_match = _ISSUE_LABEL_RE.match(clean)
        if label_match:
            label = label_match.group(1).strip()
            value = label_match.group(2).strip()

            # Shape B: a second "Symptom:" means a new issue — flush current card
            if label.lower() == "symptom" and any(
                row[0].lower() == "symptom" for row in current_rows
            ):
                flush()
                current_title = None
                current_rows  = []

            current_rows.append((label, value))
            continue

        # ── Plain text line (note, continuation, etc.) ────────────────────────
        if current_rows:
            last_label, last_value = current_rows[-1]
            current_rows[-1] = (last_label, f"{last_value} {clean}".strip())
        else:
            current_rows.append(("Note", clean))

    flush()
    return findings


# ── Recommendation extractor ───────────────────────────────────────────────────


def _extract_recommendations(agent_responses: Dict[str, AgentResponse]) -> List[str]:
    """
    Extract genuinely actionable recommendations from all agent explanations.

    Filters out:
    - Markdown heading lines  (### 2. High Spill ...)
    - Bare section headers    (**Recommendations:**)
    - N/A / "None needed"     lines
    - Symptom/Impact/Root Cause label lines
    - Duplicates              (case-insensitive)

    Keeps lines that:
    - Start with an action verb
    - Appear inside a "Recommendations" section
    - Explicitly contain the word "recommend"
    """
    seen:            set       = set()
    recommendations: List[str] = []

    for response in agent_responses.values():
        in_rec_section = False

        for raw_line in response.explanation.split("\n"):
            line  = raw_line.strip()
            clean = _strip_bold_and_headings(line.lstrip("-").lstrip("*"))

            # Always skip markdown heading lines (### 1. Task Failures)
            if _MD_HEADING_RE.match(line):
                continue

            # Track entry/exit of a "Recommendations" section
            if _is_bare_header(line) and "recommend" in clean.lower():
                in_rec_section = True
                continue
            if _is_bare_header(line) and "recommend" not in clean.lower():
                in_rec_section = False
                continue

            if not clean or len(clean) < 20:
                continue

            # Skip N/A and "None needed" lines
            na_forms = {"n/a", "none needed", "no action required", "none"}
            if clean.lower() in na_forms:
                continue
            if clean.lower().startswith(("n/a", "none needed")):
                continue

            # Skip bare diagnostic label lines
            skip_prefixes = ("symptom:", "root cause:", "impact:", "recommendation: none")
            if any(clean.lower().startswith(p) for p in skip_prefixes):
                continue

            first_word = clean.split()[0].lower().rstrip(".")
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


# ── Confidence scoring ─────────────────────────────────────────────────────────


def _compute_confidence(
    agent_responses: Dict[str, AgentResponse],
    fingerprint:     ExecutionFingerprint,
    problem_type:    ProblemType,
) -> float:
    """
    Compute a meaningful confidence score (0.0–1.0) from four signals:

      1. Data completeness  (0–30 pts) — how much signal is in the fingerprint
      2. Signal strength    (0–30 pts) — how decisive the dominant penalty is
      3. Agent agreement    (0–20 pts) — how many agents ran successfully
      4. Cause clarity      (0–20 pts) — does numeric evidence match problem_type

    Floor: 0.40 for any completed analysis.
    """
    score = 0.0

    # ── 1. Data completeness ──────────────────────────────────────────────────
    exec_sum = fingerprint.metrics.execution_summary
    dag      = fingerprint.semantic.dag

    score += sum([
        (exec_sum.total_tasks > 0)              * 6,
        (dag.total_stages > 0)                  * 6,
        (exec_sum.total_duration_ms > 0)        * 6,
        (exec_sum.total_spill_bytes > 0)        * 4,
        (exec_sum.total_shuffle_bytes > 0)      * 4,
        (len(fingerprint.metrics.anomalies) > 0) * 4,
    ])  # max 30

    # ── 2. Signal strength — how decisive is the dominant penalty? ────────────
    rca_resp = agent_responses.get(AgentType.ROOT_CAUSE.value)
    if rca_resp:
        breakdown = (
            rca_resp.metadata
            .get("health_score", {})
            .get("breakdown", {})
        )
        penalties     = {k: float(v) for k, v in breakdown.items()}
        total_penalty = sum(penalties.values())

        if total_penalty > 0:
            top_val         = max(penalties.values())
            dominance_ratio = top_val / total_penalty
            score += int(dominance_ratio * 30)        # max 30
        else:
            score += 28  # HEALTHY — very clear signal

    # ── 3. Agent agreement ────────────────────────────────────────────────────
    n_succeeded = sum(
        1 for r in agent_responses.values()
        if getattr(r, "success", True)  # treat missing attr as success
    )
    score += {0: 0, 1: 10, 2: 20}.get(n_succeeded, 20)  # max 20

    # ── 4. Cause clarity ──────────────────────────────────────────────────────
    failure_count = exec_sum.failed_task_count
    spill_bytes   = exec_sum.total_spill_bytes

    if problem_type.name in ("EXECUTION_FAILURE", "MEMORY_PRESSURE"):
        score += 20 if (failure_count > 0 or spill_bytes > 0) else 5
    elif problem_type.name == "HEALTHY":
        score += 20 if (failure_count == 0 and spill_bytes == 0) else 10
    else:
        # SHUFFLE_OVERHEAD, DATA_SKEW, PERFORMANCE, LINEAGE — inferred, moderate certainty
        score += 12

    # Normalise to [0.0, 1.0] with a floor of 0.40
    return round(max(min(score, 100) / 100.0, 0.40), 4)


# ── Health-score → ProblemType derivation ─────────────────────────────────────


def _derive_problem_type_from_health(rca_response: AgentResponse) -> ProblemType:
    """
    Derive the final ProblemType from the RCA agent's health-score metadata.

    Priority order:
      1. HEALTHY           — status == HEALTHY or total_penalty == 0
      2. EXECUTION_FAILURE — task_failure penalty dominates (>= 40% of total)
      3. MEMORY_PRESSURE   — memory_pressure penalty dominates
      4. SHUFFLE_OVERHEAD  — shuffle_overhead penalty dominates
      5. DATA_SKEW         — data_skew penalty dominates
      6. PERFORMANCE       — multiple equal causes; no single dominant
    """
    metadata  = rca_response.metadata or {}
    health    = metadata.get("health_score", {})
    status    = health.get("status", "").upper()
    breakdown = health.get("breakdown", {})

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


def _classify_problem_from_query(
    user_query:  str,
    fingerprint: ExecutionFingerprint,
) -> ProblemType:
    """
    Keyword + fingerprint heuristic for initial query classification.
    Used ONLY before RCA runs; overridden by _derive_problem_type_from_health.
    """
    query_lower = user_query.lower()

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


# ── Orchestrator ───────────────────────────────────────────────────────────────


class SmartOrchestrator:
    """
    Intelligent orchestrator coordinating agents based on user queries.

    Pipeline:
      1. Keyword-classify the query          → initial ProblemType
      2. Analyse fingerprint characteristics → hints dict
      3. Plan agent execution order          → List[AgentTask]
      4. Run agents with shared context
      5. Derive FINAL problem_type from RCA health-score metadata
      6. Synthesize AnalysisResult
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
            f"[ORCHESTRATOR] Initialized for app: "
            f"{fingerprint.context.spark_config.app_name}"
        )
        logger.info(f"[ORCHESTRATOR] Registered agents: {[a.value for a in self._agents]}")

    # ── Public entry point ─────────────────────────────────────────────────────

    async def solve_problem(self, user_query: str) -> AnalysisResult:
        """Run the full orchestration pipeline and return an AnalysisResult."""
        start_time = time.time()
        _sep = "═" * 55
        logger.info(f"[ORCHESTRATOR] {_sep}")
        logger.info(f"[ORCHESTRATOR] Query : {user_query}")
        logger.info(f"[ORCHESTRATOR] {_sep}")

        # Step 1: Initial keyword classification
        initial_problem_type = _classify_problem_from_query(user_query, self.fingerprint)
        logger.info(f"[ORCHESTRATOR] Initial classification : {initial_problem_type.value}")

        # Step 2: Fingerprint characteristics
        hints = self._analyze_fingerprint_characteristics()
        logger.info(f"[ORCHESTRATOR] Fingerprint hints : {hints}")

        # Step 3: Plan
        tasks = self._plan_agent_execution(initial_problem_type, user_query, hints)
        logger.info(f"[ORCHESTRATOR] Planned {len(tasks)} task(s)")
        for t in tasks:
            logger.info(f"[ORCHESTRATOR]   · {t.agent_type}: {t.task_description}")

        # Step 4: Shared context
        context = AgentContext(self.fingerprint_dict, user_query)

        # Step 5: Execute agents
        agent_responses: Dict[str, AgentResponse] = {}
        agent_sequence:  List[str]                = []

        for task in tasks:
            response = await self._execute_agent_task(task, context)
            if response is not None:
                agent_responses[task.agent_type] = response
                agent_sequence.append(task.agent_type)
                self._share_findings_to_context(task.agent_type, response, context)

        # Step 6: Derive final problem_type from RCA health metadata
        rca_response = agent_responses.get(AgentType.ROOT_CAUSE.value)
        if rca_response is not None:
            final_problem_type = _derive_problem_type_from_health(rca_response)
            logger.info(
                f"[ORCHESTRATOR] Final problem_type (health score): "
                f"{final_problem_type.value}"
            )
        else:
            final_problem_type = initial_problem_type
            logger.info(
                f"[ORCHESTRATOR] No RCA response; keeping initial: "
                f"{final_problem_type.value}"
            )

        # Step 7: Synthesize
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
            f"[ORCHESTRATOR] Done in {elapsed} ms | "
            f"type={final_problem_type.value} | "
            f"findings={len(result.findings)}"
        )
        return result

    # ── Fingerprint analysis ───────────────────────────────────────────────────

    def _analyze_fingerprint_characteristics(self) -> Dict[str, Any]:
        metrics      = self.fingerprint.metrics
        exec_summary = metrics.execution_summary

        spill_gb      = exec_summary.total_spill_bytes   / (1024 ** 3)
        shuffle_gb    = exec_summary.total_shuffle_bytes / (1024 ** 3)
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

    # ── Agent planning ─────────────────────────────────────────────────────────

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

        else:  # GENERAL / fallback
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
        if hints.get("has_failures"):
            areas.append("task_failures")
        if hints.get("has_spill"):
            areas.append("memory_pressure")
        if hints.get("shuffle_gb", 0.0) > 1.0:
            areas.append("shuffle_overhead")
        return areas

    # ── Agent execution ────────────────────────────────────────────────────────

    async def _execute_agent_task(
        self,
        task:    AgentTask,
        context: AgentContext,
    ) -> Optional[AgentResponse]:
        agent_type_enum = AgentType(task.agent_type)
        agent           = self._agents.get(agent_type_enum)

        if agent is None:
            logger.warning(f"[ORCHESTRATOR] No agent registered for: {task.agent_type}")
            return None

        kwargs: Dict[str, Any] = {}
        if task.focus_areas:
            kwargs["focus_areas"] = task.focus_areas

        # Log plan steps (best-effort; agents may not implement plan())
        try:
            plan_steps = agent.plan(self.fingerprint_dict, context=context, **kwargs)
            if plan_steps:
                logger.info(f"[ORCHESTRATOR] Plan — {agent.agent_name}:")
                for step in plan_steps:
                    logger.info(f"[ORCHESTRATOR]   · {step}")
        except Exception:
            pass

        try:
            response = await agent.analyze(
                self.fingerprint_dict,
                context  = context,
                **kwargs,
            )
            context.store_agent_output(task.agent_type, response)
            return response
        except Exception as exc:
            logger.exception(f"[ORCHESTRATOR] Agent '{task.agent_type}' failed: {exc}")
            return None

    def _share_findings_to_context(
        self,
        agent_type: str,
        response:   AgentResponse,
        context:    AgentContext,
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

    # ── Result synthesis ───────────────────────────────────────────────────────

    def _synthesize_results(
        self,
        problem_type:    ProblemType,
        user_query:      str,
        agent_responses: Dict[str, AgentResponse],
        agent_sequence:  List[str],
        context:         AgentContext,
        start_time:      float,
    ) -> AnalysisResult:

        # Findings: group flat LLM key_findings into structured cards.
        # Shape A (bare headers) and Shape B (Symptom/Root Cause/Impact runs) handled.
        # Recommended Fix rows land in finding.recommendation, not finding.description.
        all_findings: List[AgentFinding] = []
        for agent_type, response in agent_responses.items():
            grouped = _group_flat_findings(agent_type, response.key_findings)
            all_findings.extend(grouped)
            logger.info(
                f"[ORCHESTRATOR] {agent_type}: "
                f"{len(response.key_findings)} raw → {len(grouped)} cards"
            )

        # Recommendations: actionable lines only, deduplicated.
        # Heading lines and bare labels filtered out.
        all_recommendations = _extract_recommendations(agent_responses)
        logger.info(
            f"[ORCHESTRATOR] {len(all_recommendations)} actionable recommendations"
        )

        # Confidence: computed from real fingerprint signals, not agent-reported value.
        confidence    = _compute_confidence(agent_responses, self.fingerprint, problem_type)
        total_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"[ORCHESTRATOR] Computed confidence: {confidence}")

        return AnalysisResult(
            problem_type             = problem_type,
            user_query               = user_query,
            executive_summary        = self._build_executive_summary(
                                           problem_type, agent_responses, context
                                       ),
            detailed_analysis        = self._build_detailed_analysis(agent_responses),
            findings                 = all_findings,
            recommendations          = all_recommendations,
            agents_used              = list(agent_responses.keys()),
            agent_sequence           = agent_sequence,
            total_processing_time_ms = total_time_ms,
            confidence               = confidence,
            raw_agent_responses      = {k: v.model_dump() for k, v in agent_responses.items()},
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _infer_severity_static(text: str) -> str:
        """Public-static alias — delegates to module-level function."""
        return _infer_severity_static(text)

    @staticmethod
    def _infer_severity(text: str) -> str:
        """Instance-accessible alias — delegates to module-level function."""
        return _infer_severity_static(text)

    def _build_executive_summary(
        self,
        problem_type:    ProblemType,
        agent_responses: Dict[str, AgentResponse],
        context:         AgentContext,
    ) -> str:
        prefix = _PROBLEM_TYPE_PREFIX.get(problem_type.name, "Analysis: ")

        # Strip stray bold markers ("** This Spark job...") and markdown headings
        summaries = [
            _strip_bold_and_headings(r.summary)
            for r in agent_responses.values()
        ]
        combined = " ".join(s for s in summaries if s)

        finding_count = len(context.get_findings())
        if finding_count:
            combined += f" ({finding_count} key findings identified)"

        return prefix + combined

    @staticmethod
    def _build_detailed_analysis(agent_responses: Dict[str, AgentResponse]) -> str:
        return "\n\n---\n\n".join(
            f"## {resp.agent_name}\n\n{resp.explanation}"
            for resp in agent_responses.values()
        )
