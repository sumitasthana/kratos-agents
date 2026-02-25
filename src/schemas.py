"""
schemas.py
Pydantic models for the full Kratos multi-agent system.

Changes from original (4 fixes, 0 structural changes):
  1. IssueProfile.overall_health_score    default=0.0    (was required → RuntimeError if omitted)
  2. IssueProfile.overall_confidence      default=0.0    (was required → same risk)
  3. Timestamp fields standardised        Union[datetime, str] on ChangeFingerprint,
                                          IssueProfile, OntologyUpdate, RecommendationReport
  4. AgentTask.source_data note added     — KratosOrchestrator must populate before dispatch
  + FingerprintMetadata model_config      protected_namespaces=() to suppress Pydantic warning

Nothing else changed — all field names, types, defaults identical to original.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================================
# SHARED ENUMS
# ============================================================================

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


class ProblemType(str, Enum):
    # ── Spark / Log Analyzer ──────────────────────────────────────────────
    HEALTHY            = "healthy"
    PERFORMANCE        = "performance"
    EXECUTION_FAILURE  = "execution_failure"
    MEMORY_PRESSURE    = "memory_pressure"
    SHUFFLE_OVERHEAD   = "shuffle_overhead"
    DATA_SKEW          = "data_skew"

    # ── Change Analyzer (git) ─────────────────────────────────────────────
    CHURN_SPIKE        = "churn_spike"
    CONTRIBUTOR_SILO   = "contributor_silo"
    REGRESSION_RISK    = "regression_risk"
    STALE_BRANCH       = "stale_branch"

    # ── Code Analyzer ─────────────────────────────────────────────────────
    COMPLIANCE_GAP     = "compliance_gap"
    HIGH_COMPLEXITY    = "high_complexity"
    CIRCULAR_IMPORT    = "circular_import"
    DEAD_CODE          = "dead_code"

    # ── Data Profiler ─────────────────────────────────────────────────────
    NULL_SPIKE          = "null_spike"
    SCHEMA_DRIFT        = "schema_drift"
    DISTRIBUTION_SHIFT  = "distribution_shift"
    CARDINALITY_ANOMALY = "cardinality_anomaly"

    # ── Triangulation (cross-agent) ───────────────────────────────────────
    CORRELATED_FAILURE = "correlated_failure"

    # ── Fallback ──────────────────────────────────────────────────────────
    LINEAGE            = "lineage"
    GENERAL            = "general"


# ============================================================================
# SHARED PRIMITIVES
# ============================================================================

class AnomalyEvent(BaseModel):
    """Flagged anomaly — produced by any analyzer agent."""

    anomaly_type: str = Field(
        ...,
        description=(
            "Type: skewed_stage, executor_loss, oom, gc_pause, long_task, "
            "high_spill, churn_spike, null_spike, schema_drift, circular_import, etc."
        ),
    )
    severity:        Severity          = Field(..., description="Anomaly severity level")
    description:     str               = Field(..., description="Human-readable description")
    affected_stages: List[int]         = Field(default_factory=list, description="Stage IDs (Spark only)")
    affected_tasks:  Optional[List[int]] = Field(None, description="Task IDs (sample up to 10)")
    metric_name:     Optional[str]     = Field(None, description="Metric exhibiting anomaly")
    metric_value:    Optional[float]   = Field(None, description="Anomalous metric value")
    evidence:        Dict[str, Any]    = Field(default_factory=dict, description="Supporting data")


class AgentFinding(BaseModel):
    """
    A single finding from any agent — shared contract across all 7 agents.

    severity accepts both Severity enum and raw strings ("critical", "high", etc.)
    Pydantic v2 coerces str → Severity automatically because Severity(str, Enum).
    """

    agent_type:     str               = Field(..., description="Agent that produced this finding")
    finding_type:   str               = Field(..., description="Category of finding")
    severity:       Severity          = Field(default=Severity.INFO)
    title:          str               = Field(..., description="Brief title")
    description:    str               = Field(..., description="Detailed description")
    recommendation: Optional[str]     = Field(None, description="Suggested action")
    evidence:       List[str]         = Field(default_factory=list, description="Supporting evidence")


class AgentTask(BaseModel):
    """
    A task assigned to an agent by the RoutingAgent / SmartOrchestrator.

    source_data is populated by KratosOrchestrator before dispatch:
        log_analyzer    → {"log_path": str, "app_id": str}
        code_analyzer   → {"repo_path": str}
        data_profiler   → {"dataset_path": str, "baseline_path": Optional[str]}
        change_analyzer → {"repo_path": str, "git_log_path": Optional[str]}
    SmartOrchestrator leaves source_data empty (uses fingerprint_dict directly).
    """

    agent_type:       str            = Field(..., description="Target agent type")
    task_description: str            = Field(..., description="What the agent should analyse")
    priority:         int            = Field(default=1, description="Execution priority (1 = highest)")
    depends_on:       List[str]      = Field(default_factory=list, description="Agent types this task must wait for")
    focus_areas:      List[str]      = Field(default_factory=list, description="Specific areas to focus on")
    source_data:      Dict[str, Any] = Field(
        default_factory=dict,
        description="Payload passed to agent: log path, repo path, dataset path, etc.",
    )


class AnalysisResult(BaseModel):
    """Synthesized result from any single orchestrator — shared output contract."""

    model_config = {"protected_namespaces": ()}

    problem_type:   ProblemType  = Field(..., description="Classified problem type")
    user_query:     str          = Field(..., description="Original user query or trigger")

    executive_summary: str       = Field(..., description="High-level summary")
    detailed_analysis: str       = Field(..., description="Full technical analysis")

    findings:        List[AgentFinding] = Field(default_factory=list)
    recommendations: List[str]          = Field(default_factory=list, description="Prioritised action items")

    health_score: float = Field(default=100.0, description="0–100 score for this agent's domain")
    confidence:   float = Field(default=0.0,   description="0–1 confidence in analysis")

    agents_used:     List[str]       = Field(default_factory=list)
    agent_sequence:  List[str]       = Field(default_factory=list)
    total_processing_time_ms: int    = Field(default=0)

    raw_agent_responses: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# LAYER 1 — SEMANTIC FINGERPRINT
# ============================================================================

class StageNode(BaseModel):
    stage_id:        int           = Field(..., description="Spark stage ID")
    stage_name:      str           = Field(..., description="Human-readable stage name")
    num_partitions:  int           = Field(..., description="Number of output partitions")
    is_shuffle_stage: bool         = Field(..., description="Whether this stage involves a shuffle")
    rdd_name:        Optional[str] = Field(None, description="RDD or DataFrame name if available")
    description:     str           = Field(..., description="Natural language description of stage computation")


class DAGEdge(BaseModel):
    from_stage_id:    int
    to_stage_id:      int
    shuffle_required: bool
    reason:           str = Field(..., description="e.g. 'reduceByKey', 'join'")


class ExecutionDAG(BaseModel):
    stages:          List[StageNode]
    edges:           List[DAGEdge]
    root_stage_ids:  List[int]
    leaf_stage_ids:  List[int]
    total_stages:    int


class PhysicalPlanNode(BaseModel):
    node_id:         str
    operator:        str                 = Field(..., description="Scan, Filter, Aggregate, etc.")
    estimated_rows:  Optional[int]       = None
    estimated_bytes: Optional[int]       = None
    attributes:      Dict[str, Any]      = Field(default_factory=dict)
    children:        List[str]           = Field(default_factory=list)
    description:     str


class LogicalPlanHash(BaseModel):
    plan_hash: str  = Field(..., description="SHA256 of normalized logical plan")
    plan_text: str
    is_sql:    bool


class SemanticFingerprint(BaseModel):
    dag:               ExecutionDAG
    physical_plan:     Optional[PhysicalPlanNode] = None
    logical_plan_hash: LogicalPlanHash
    semantic_hash:     str       = Field(..., description="SHA256 combining DAG + plan")
    description:       str       = Field(..., description="e.g. 'Read parquet, filter by date, aggregate by key'")
    evidence_sources:  List[str] = Field(default_factory=list)


# ============================================================================
# LAYER 2 — CONTEXT FINGERPRINT
# ============================================================================

class ExecutorConfig(BaseModel):
    total_executors:    int
    executor_memory_mb: int
    executor_cores:     int
    driver_memory_mb:   int
    driver_cores:       int
    description:        str = Field(..., description="e.g. '10 executors × 8 GB × 4 cores each'")


class SparkConfig(BaseModel):
    spark_version:  str
    scala_version:  Optional[str] = None
    java_version:   Optional[str] = None
    hadoop_version: Optional[str] = None
    app_name:       str
    master_url:     str
    config_params:  Dict[str, str] = Field(
        default_factory=dict,
        description="shuffle partitions, serializer, codec, etc.",
    )
    description: str


class SubmitParameters(BaseModel):
    submit_time:       datetime
    user:              Optional[str] = None
    app_id:            str
    queue:             Optional[str] = None
    additional_params: Dict[str, str] = Field(default_factory=dict)


class ContextFingerprint(BaseModel):
    model_config = {"protected_namespaces": ()}

    spark_config:    SparkConfig
    executor_config: ExecutorConfig
    submit_params:   SubmitParameters
    jvm_settings:    Dict[str, str] = Field(default_factory=dict)
    optimizations_enabled: List[str] = Field(default_factory=list)
    description:     str

    compliance_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "GRC compliance metadata: incident type, regulatory context, "
            "routing instructions, control references. None for pure Spark perf runs."
        ),
    )
    evidence_sources: List[str] = Field(default_factory=list)


# ============================================================================
# LAYER 3 — METRICS FINGERPRINT
# ============================================================================

class PercentileStats(BaseModel):
    min_val:       float
    p25:           float
    p50:           float
    p75:           float
    p99:           float
    max_val:       float
    mean:          float
    stddev:        float
    count:         int
    outlier_count: int = Field(..., description="Values beyond ±2σ")


class StageMetrics(BaseModel):
    stage_id:          int
    num_tasks:         int
    num_failed_tasks:  int
    task_duration_ms:  PercentileStats
    input_bytes:       int
    output_bytes:      int
    shuffle_read_bytes:  int
    shuffle_write_bytes: int
    spill_bytes:       int
    partition_count:   int


class TaskMetricsDistribution(BaseModel):
    """
    Serialised as a dict of {metric_name: PercentileStats} after model_dump().
    root_cause.py iterates .values() and calls .get("p50") / .get("max_val").
    Both fields exist on PercentileStats — pattern is safe.
    """
    duration_ms:         PercentileStats
    input_bytes:         PercentileStats
    output_bytes:        PercentileStats
    shuffle_read_bytes:  PercentileStats
    shuffle_write_bytes: PercentileStats
    spill_bytes:         PercentileStats


class ExecutionSummary(BaseModel):
    total_duration_ms:    int
    total_tasks:          int
    total_stages:         int
    total_input_bytes:    int
    total_output_bytes:   int
    total_shuffle_bytes:  int
    total_spill_bytes:    int
    failed_task_count:    int
    executor_loss_count:  int
    max_concurrent_tasks: int


class MetricsFingerprint(BaseModel):
    execution_summary:          ExecutionSummary
    stage_metrics:              List[StageMetrics]
    task_distribution:          TaskMetricsDistribution
    anomalies:                  List[AnomalyEvent]       = Field(default_factory=list)
    key_performance_indicators: Dict[str, float]         = Field(default_factory=dict)
    description:                str                      = Field(
        ..., description="e.g. 'Completed in 120s with 5 GB shuffle, 2 task failures'"
    )
    evidence_sources: List[str] = Field(default_factory=list)


# ============================================================================
# MAIN EXECUTION FINGERPRINT
# ============================================================================

class FingerprintMetadata(BaseModel):
    model_config = {"protected_namespaces": ()}          # FIX 4: suppress model_* warning

    fingerprint_schema_version: str       = Field(default="2.0.0")
    generated_at:               datetime
    generator_version:          str
    event_log_path:             str
    event_log_size_bytes:       int
    events_parsed:              int
    events_total:               Optional[int]  = None
    parsing_issues:             List[str]      = Field(default_factory=list)


class ExecutionFingerprint(BaseModel):
    """
    Complete Spark Execution Fingerprint — output of LogAnalyzerAgent.
    Three-layer structure optimised for LLM consumption.
    """
    model_config = {"protected_namespaces": ()}

    metadata:  FingerprintMetadata
    semantic:  SemanticFingerprint  = Field(..., description="Layer 1: What ran (DAG, plan)")
    context:   ContextFingerprint   = Field(..., description="Layer 2: Where/how it ran (env, config)")
    metrics:   MetricsFingerprint   = Field(..., description="Layer 3: How well it ran (stats, anomalies)")

    execution_class: str       = Field(
        ..., description="cpu_bound | io_bound | memory_bound | network_bound"
    )
    analysis_hints: List[str]  = Field(
        default_factory=list,
        description="Sections flagged for LLM focus",
    )

    def dict_for_llm(
        self,
        include_evidence: bool = True,
        detail_level: str = "balanced",
    ) -> Dict[str, Any]:
        result = self.model_dump()

        if not include_evidence:
            def _strip(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {k: _strip(v) for k, v in obj.items() if k != "evidence_sources"}
                if isinstance(obj, list):
                    return [_strip(i) for i in obj]
                return obj
            result = _strip(result)

        if detail_level == "summary":
            if "metrics" in result:
                result["metrics"]["stage_metrics"] = []
                result["metrics"]["anomalies"] = result["metrics"].get("anomalies", [])[:3]

        return result


# ============================================================================
# CHANGE ANALYZER FINGERPRINT
# ============================================================================

class CommitMetrics(BaseModel):
    total_commits:      int
    date_range_days:    int
    commits_per_day:    float
    burst_windows:      List[str]       = Field(default_factory=list, description="ISO date ranges where commit frequency exceeded 3σ")
    top_contributors:   Dict[str, int]  = Field(default_factory=dict, description="author → commit count")


class FileChurn(BaseModel):
    file_path:    str
    insertions:   int
    deletions:    int
    commit_count: int
    last_modified: str
    churn_score:  float           = Field(..., description="Normalized churn score 0–1")
    owner:        Optional[str]   = Field(None, description="Dominant contributor (>70% commits)")


class ChangeFingerprint(BaseModel):
    model_config = {"protected_namespaces": ()}

    repo_path:     str
    generated_at:  Union[datetime, str]     # FIX 3: was str only
    commit_metrics:  CommitMetrics
    hotspot_files:   List[FileChurn]   = Field(default_factory=list, description="Files with churn_score > 0.7")
    silo_risk_files: List[FileChurn]   = Field(default_factory=list, description="Single-owner hotspot files")
    stale_branches:  List[str]         = Field(default_factory=list, description="Branches with no commits in 30+ days")
    anomalies:       List[AnomalyEvent] = Field(default_factory=list)
    evidence_sources: List[str]        = Field(default_factory=list)


# ============================================================================
# CODE ANALYZER FINGERPRINT
# ============================================================================

class FunctionComplexity(BaseModel):
    file_path:             str
    function_name:         str
    cyclomatic_complexity: int
    lines_of_code:         int
    is_dead_code:          bool


class DependencyEdge(BaseModel):
    from_module: str
    to_module:   str
    is_circular: bool
    reason:      Optional[str] = None


class ComplianceControl(BaseModel):
    """FDIC / regulatory control mapping."""
    control_id:       str           = Field(..., description="e.g. 'FDIC-DSC-3.2.1'")
    control_category: str           = Field(..., description="e.g. 'Data Governance', 'Audit Trail'")
    description:      str
    implemented:      bool
    evidence_file:    Optional[str] = Field(None, description="Source file where control is implemented")
    gap_description:  Optional[str] = Field(None, description="What is missing if not implemented")
    severity:         Severity      = Field(default=Severity.INFO)


class CodeFingerprint(BaseModel):
    model_config = {"protected_namespaces": ()}

    repo_path:                   str
    generated_at:                Union[datetime, str]     # FIX 3: was str only
    avg_cyclomatic_complexity:   float
    max_cyclomatic_complexity:   float
    dead_code_ratio:             float            = Field(..., description="0.0–1.0 fraction of unreferenced symbols")
    total_functions_scanned:     int
    circular_imports:            List[DependencyEdge]     = Field(default_factory=list)
    high_complexity_functions:   List[FunctionComplexity] = Field(default_factory=list)
    compliance_controls:         List[ComplianceControl]  = Field(default_factory=list)
    compliance_gap_count:        int                      = Field(default=0)
    anomalies:                   List[AnomalyEvent]       = Field(default_factory=list)
    evidence_sources:            List[str]                = Field(default_factory=list)


# ============================================================================
# DATA PROFILER FINGERPRINT
# ============================================================================

class ColumnProfile(BaseModel):
    column_name:       str
    dtype:             str
    null_rate:         float            = Field(..., description="0.0–1.0")
    cardinality:       int
    skewness:          Optional[float]  = None
    kurtosis:          Optional[float]  = None
    is_high_cardinality: bool           = False
    is_null_spike:     bool             = False
    baseline_null_rate: Optional[float] = Field(None, description="Historical null rate for drift comparison")
    drift_detected:    bool             = False
    sample_values:     List[Any]        = Field(default_factory=list, description="Up to 5 representative values")


class SchemaChange(BaseModel):
    change_type: str            = Field(..., description="added | dropped | type_changed | renamed")
    column_name: str
    old_value:   Optional[str]  = None
    new_value:   Optional[str]  = None
    detected_at: Optional[str]  = None


class DataFingerprint(BaseModel):
    model_config = {"protected_namespaces": ()}

    dataset_path:         str
    generated_at:         Union[datetime, str]     # FIX 3: was str only
    row_count:            int
    column_count:         int
    column_profiles:      List[ColumnProfile]  = Field(default_factory=list)
    schema_changes:       List[SchemaChange]   = Field(default_factory=list, description="Detected vs baseline schema")
    overall_null_rate:    float                = Field(default=0.0)
    high_null_columns:    List[str]            = Field(default_factory=list)
    schema_drift_detected: bool               = False
    anomalies:            List[AnomalyEvent]  = Field(default_factory=list)
    evidence_sources:     List[str]           = Field(default_factory=list)


# ============================================================================
# ROUTING AGENT OUTPUT
# ============================================================================

class RoutingDecision(BaseModel):
    """Output of RoutingAgent — which analysers to invoke and in what order."""

    job_id:  str
    trigger: str = Field(..., description="failure | scheduled | manual | code_change")

    invoke_log_analyzer:    bool = False
    invoke_code_analyzer:   bool = False
    invoke_data_profiler:   bool = False
    invoke_change_analyzer: bool = False

    routing_rationale: str           = Field(..., description="LLM-generated explanation of agent selection")
    tasks:             List[AgentTask] = Field(..., description="Ordered execution plan for KratosOrchestrator")
    estimated_analysis_time_sec: Optional[int] = None


# ============================================================================
# TRIANGULATION AGENT OUTPUT
# ============================================================================

class CrossAgentCorrelation(BaseModel):
    """A finding that spans 2+ agents — core output of TriangulationAgent."""

    correlation_id:       str
    contributing_agents:  List[str] = Field(..., description="e.g. ['log_analyzer', 'change_analyzer']")
    pattern:              str       = Field(..., description="e.g. 'Churn spike in executor.py correlates with OOM in stage 3'")
    severity:             Severity
    confidence:           float     = Field(..., description="0–1 confidence in this correlation")
    evidence:             Dict[str, Any] = Field(default_factory=dict)
    affected_artifacts:   List[str]     = Field(default_factory=list, description="Files, columns, stages, or commits involved")


class IssueProfile(BaseModel):
    """TriangulationAgent output — consumed by RecommendationAgent."""

    model_config = {"protected_namespaces": ()}

    job_id:        str
    generated_at:  Union[datetime, str]     # FIX 3: was str only

    dominant_problem_type: ProblemType

    log_analysis:    Optional[AnalysisResult] = None
    code_analysis:   Optional[AnalysisResult] = None
    data_analysis:   Optional[AnalysisResult] = None
    change_analysis: Optional[AnalysisResult] = None

    correlations: List[CrossAgentCorrelation] = Field(default_factory=list)

    lineage_map: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="source_artifact → [downstream artifacts]",
    )

    overall_health_score: float = Field(default=0.0,  description="0–100 aggregate score")    # FIX 1
    overall_confidence:   float = Field(default=0.0,  description="0–1 aggregate confidence")  # FIX 2

    agents_invoked:         List[str] = Field(default_factory=list)
    total_findings_count:   int       = Field(default=0)
    critical_findings_count: int      = Field(default=0)


# ============================================================================
# RECOMMENDATION AGENT OUTPUT + ONTOLOGY UPDATE
# ============================================================================

class Fix(BaseModel):
    """A single actionable fix — rendered as a green FIX block in the dashboard."""

    fix_id:             str
    title:              str
    description:        str
    applies_to_agents:  List[str]     = Field(..., description="Which agent findings this resolves")
    priority:           int           = Field(..., description="1 = highest priority")
    effort:             str           = Field(..., description="low | medium | high")
    code_snippet:       Optional[str] = None
    references:         List[str]     = Field(default_factory=list, description="FDIC control IDs, docs URLs, etc.")


class OntologyUpdate(BaseModel):
    """Written back to the Ontology store after each completed analysis."""

    job_id:                 str
    timestamp:              Union[datetime, str]    # FIX 3: was str only
    issue_profile_hash:     str       = Field(..., description="SHA256 of IssueProfile for dedup")
    new_patterns_learned:   List[str] = Field(default_factory=list, description="Patterns not seen in prior runs")
    updated_control_refs:   List[str] = Field(default_factory=list, description="FDIC/compliance control IDs that were affected")
    lineage_nodes_added:    List[str] = Field(default_factory=list, description="New nodes written to lineage map")


class RecommendationReport(BaseModel):
    """Final output of RecommendationAgent — consumed by KratosReviewer."""

    model_config = {"protected_namespaces": ()}

    job_id:       str
    generated_at: Union[datetime, str]    # FIX 3: was str only

    issue_profile:     IssueProfile
    prioritized_fixes: List[Fix]   = Field(default_factory=list)
    executive_summary: str
    detailed_narrative: str

    ontology_update: OntologyUpdate

    feedback_loop_signal: str           = Field(..., description="RE_RUN | ESCALATE | RESOLVED | MONITOR")
    reviewer_notes:       Optional[str] = Field(None, description="Free-text notes for KratosReviewer")


# ============================================================================
# COMPARISON / REGRESSION DETECTION
# ============================================================================

class MetricDeviation(BaseModel):
    metric_name:       str
    value_1:           float
    value_2:           float
    deviation_percent: float
    is_regressive:     bool
    threshold_percent: float


class SemanticComparison(BaseModel):
    are_semantically_identical: bool
    semantic_hash_1:            str
    semantic_hash_2:            str
    differences:                List[str] = Field(default_factory=list)


class SimilarityReport(BaseModel):
    run_id_1:           str
    run_id_2:           str
    semantic_comparison: SemanticComparison
    context_compatible:  bool
    context_differences: List[str]          = Field(default_factory=list)
    metric_deviations:   List[MetricDeviation]
    similarity_score:    float              = Field(..., description="0.0–1.0; <0.9 may indicate regression")
    regression_detected: bool
    analysis:            str
