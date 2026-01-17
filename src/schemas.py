"""
Pydantic models for Spark Execution Fingerprint layers.

Three-layer structure:
1. Semantic: DAG, physical plan, stage dependencies
2. Context: Environment, Spark version, configuration
3. Metrics: Task/stage statistics, anomalies, performance characteristics

Each layer includes evidence linking for LLM traceability.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================================
# SEMANTIC LAYER: DAG, Plan Structure, Stage Dependencies
# ============================================================================


class StageNode(BaseModel):
    """Represents a single stage in the execution DAG."""

    stage_id: int = Field(..., description="Spark stage ID")
    stage_name: str = Field(..., description="Human-readable stage name")
    num_partitions: int = Field(..., description="Number of output partitions")
    is_shuffle_stage: bool = Field(..., description="Whether this stage involves a shuffle")
    rdd_name: Optional[str] = Field(None, description="RDD or DataFrame name if available")
    description: str = Field(
        ..., description="Natural language description of what this stage computes"
    )


class DAGEdge(BaseModel):
    """Represents a dependency between two stages."""

    from_stage_id: int = Field(..., description="Source stage ID")
    to_stage_id: int = Field(..., description="Target stage ID")
    shuffle_required: bool = Field(..., description="Whether edge requires shuffle")
    reason: str = Field(..., description="Why this dependency exists (e.g., 'reduceByKey', 'join')")


class ExecutionDAG(BaseModel):
    """
    Normalized execution DAG - deterministic representation of stage dependencies.
    Extracted from event log, independent of runtime variations.
    """

    stages: List[StageNode] = Field(..., description="All stages in execution order")
    edges: List[DAGEdge] = Field(..., description="Dependencies between stages")
    root_stage_ids: List[int] = Field(..., description="Entry point stage IDs")
    leaf_stage_ids: List[int] = Field(..., description="Final output stage IDs")
    total_stages: int = Field(..., description="Total stage count")


class PhysicalPlanNode(BaseModel):
    """
    Node in normalized physical plan tree (SQL only).
    Extracted from SparkListenerSQLExecutionStart events.
    """

    node_id: str = Field(..., description="Unique node identifier")
    operator: str = Field(..., description="Spark operator (Scan, Filter, Aggregate, etc.)")
    estimated_rows: Optional[int] = Field(None, description="Estimated output rows")
    estimated_bytes: Optional[int] = Field(None, description="Estimated output bytes")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Operator-specific attributes")
    children: List[str] = Field(default_factory=list, description="Child node IDs")
    description: str = Field(..., description="Natural language description of this operator")


class LogicalPlanHash(BaseModel):
    """Hash of logical plan structure for equality checking."""

    plan_hash: str = Field(..., description="SHA256 hash of normalized logical plan")
    plan_text: str = Field(..., description="Serialized plan for verification")
    is_sql: bool = Field(..., description="Whether plan is from SQL query (vs RDD/DataFrame)")


class SemanticFingerprint(BaseModel):
    """
    Semantic layer: captures *what* computation was executed, independent of environment/performance.
    Deterministic and hashable - identical semantic fingerprints = identical computation.
    """

    dag: ExecutionDAG = Field(..., description="Stage DAG structure")
    physical_plan: Optional[PhysicalPlanNode] = Field(
        None, description="Root of normalized physical plan (SQL only)"
    )
    logical_plan_hash: LogicalPlanHash = Field(
        ..., description="Hash of logical plan for equality detection"
    )
    semantic_hash: str = Field(
        ..., description="SHA256 hash combining DAG + plan - deterministic execution identity"
    )
    description: str = Field(
        ..., description="Natural language summary of computation (e.g., 'Read parquet, filter by date, aggregate by key')"
    )

    # Evidence linking
    evidence_sources: List[str] = Field(
        default_factory=list, description="Event log event IDs supporting this fingerprint"
    )


# ============================================================================
# CONTEXT LAYER: Environment, Version, Configuration
# ============================================================================


class ExecutorConfig(BaseModel):
    """Executor resource allocation and configuration."""

    total_executors: int = Field(..., description="Total executor count")
    executor_memory_mb: int = Field(..., description="Memory per executor in MB")
    executor_cores: int = Field(..., description="Cores per executor")
    driver_memory_mb: int = Field(..., description="Driver memory in MB")
    driver_cores: int = Field(..., description="Driver cores")
    description: str = Field(
        ..., description="Natural language summary (e.g., '10 executors × 8GB × 4 cores each')"
    )


class SparkConfig(BaseModel):
    """Spark configuration relevant to execution and performance."""

    spark_version: str = Field(..., description="Spark version (e.g., '3.4.0')")
    scala_version: Optional[str] = Field(None, description="Scala version if applicable")
    java_version: Optional[str] = Field(None, description="Java version")
    hadoop_version: Optional[str] = Field(None, description="Hadoop version")
    app_name: str = Field(..., description="Spark application name")
    master_url: str = Field(..., description="Spark master URL or deployment mode")
    config_params: Dict[str, str] = Field(
        default_factory=dict,
        description="Critical spark config params: shuffle partitions, serializer, codec, etc.",
    )
    description: str = Field(
        ..., description="Natural language description of key config choices"
    )


class SubmitParameters(BaseModel):
    """Application submission parameters."""

    submit_time: datetime = Field(..., description="Timestamp when app was submitted")
    user: Optional[str] = Field(None, description="User who submitted the app")
    app_id: str = Field(..., description="Spark application ID")
    queue: Optional[str] = Field(None, description="YARN/cluster queue if applicable")
    additional_params: Dict[str, str] = Field(
        default_factory=dict, description="Other submission parameters"
    )


class ContextFingerprint(BaseModel):
    """
    Context layer: captures *where* and *how* computation ran.
    Used for environment drift analysis and explaining performance differences.
    """

    spark_config: SparkConfig = Field(..., description="Spark version and critical config")
    executor_config: ExecutorConfig = Field(..., description="Resource allocation")
    submit_params: SubmitParameters = Field(..., description="Submission metadata")
    jvm_settings: Dict[str, str] = Field(
        default_factory=dict,
        description="JVM flags relevant to performance (Xmx, GC settings, serialization)",
    )
    optimizations_enabled: List[str] = Field(
        default_factory=list,
        description="Performance optimizations active (adaptive query execution, columnar, etc.)",
    )
    description: str = Field(
        ..., description="Natural language summary of environment and configuration choices"
    )

    # Evidence linking
    evidence_sources: List[str] = Field(
        default_factory=list, description="Event log sections or driver log lines supporting this"
    )


# ============================================================================
# METRICS LAYER: Performance Characteristics, Anomalies, Statistics
# ============================================================================


class PercentileStats(BaseModel):
    """Summary statistics with percentiles for a metric."""

    min_val: float = Field(..., description="Minimum value")
    p25: float = Field(..., description="25th percentile")
    p50: float = Field(..., description="Median (50th percentile)")
    p75: float = Field(..., description="75th percentile")
    p99: float = Field(..., description="99th percentile")
    max_val: float = Field(..., description="Maximum value")
    mean: float = Field(..., description="Arithmetic mean")
    stddev: float = Field(..., description="Standard deviation")
    count: int = Field(..., description="Number of samples")
    outlier_count: int = Field(..., description="Count of values beyond ±2σ")


class AnomalyEvent(BaseModel):
    """Flagged anomaly for LLM analysis."""

    anomaly_type: str = Field(
        ...,
        description="Type: skewed_stage, executor_loss, oom, gc_pause, long_task, high_spill, etc.",
    )
    severity: str = Field(..., description="low, medium, high, critical")
    description: str = Field(..., description="Human-readable description of anomaly")
    affected_stages: List[int] = Field(default_factory=list, description="Stage IDs with anomaly")
    affected_tasks: Optional[List[int]] = Field(
        None, description="Task IDs if specific (sample up to 10)"
    )
    metric_name: Optional[str] = Field(None, description="Metric exhibiting anomaly")
    metric_value: Optional[float] = Field(None, description="Anomalous metric value")
    evidence: Dict[str, Any] = Field(
        default_factory=dict, description="Supporting data: event counts, examples, etc."
    )


class StageMetrics(BaseModel):
    """Aggregated metrics for a single stage."""

    stage_id: int = Field(..., description="Stage ID")
    num_tasks: int = Field(..., description="Total tasks in stage")
    num_failed_tasks: int = Field(..., description="Failed task count")
    task_duration_ms: PercentileStats = Field(..., description="Task execution duration stats")
    input_bytes: int = Field(..., description="Input bytes read by stage")
    output_bytes: int = Field(..., description="Output bytes produced by stage")
    shuffle_read_bytes: int = Field(..., description="Bytes read from shuffle")
    shuffle_write_bytes: int = Field(..., description="Bytes written to shuffle")
    spill_bytes: int = Field(..., description="Total spill bytes (memory pressure indicator)")
    partition_count: int = Field(..., description="Number of output partitions")


class TaskMetricsDistribution(BaseModel):
    """Distribution of task-level metrics across all tasks."""

    duration_ms: PercentileStats = Field(..., description="Task execution duration distribution")
    input_bytes: PercentileStats = Field(..., description="Input bytes per task")
    output_bytes: PercentileStats = Field(..., description="Output bytes per task")
    shuffle_read_bytes: PercentileStats = Field(..., description="Shuffle read bytes per task")
    shuffle_write_bytes: PercentileStats = Field(..., description="Shuffle write bytes per task")
    spill_bytes: PercentileStats = Field(..., description="Spill bytes per task")


class ExecutionSummary(BaseModel):
    """High-level execution summary."""

    total_duration_ms: int = Field(..., description="Total execution time in milliseconds")
    total_tasks: int = Field(..., description="Total tasks executed")
    total_stages: int = Field(..., description="Total stages executed")
    total_input_bytes: int = Field(..., description="Total input bytes read from sources")
    total_output_bytes: int = Field(..., description="Total output bytes written")
    total_shuffle_bytes: int = Field(..., description="Total shuffle bytes (read + write)")
    total_spill_bytes: int = Field(..., description="Total spill bytes across all tasks")
    failed_task_count: int = Field(..., description="Number of failed tasks")
    executor_loss_count: int = Field(..., description="Number of executor loss events")
    max_concurrent_tasks: int = Field(..., description="Peak parallelism")


class MetricsFingerprint(BaseModel):
    """
    Metrics layer: captures *how well* computation ran and quantifies performance characteristics.
    Used for regression detection, similarity comparison, and anomaly highlighting.
    """

    execution_summary: ExecutionSummary = Field(..., description="High-level execution stats")
    stage_metrics: List[StageMetrics] = Field(..., description="Per-stage metrics breakdown")
    task_distribution: TaskMetricsDistribution = Field(
        ..., description="Distribution of task-level metrics"
    )
    anomalies: List[AnomalyEvent] = Field(
        default_factory=list, description="Detected anomalies for LLM focus"
    )
    key_performance_indicators: Dict[str, float] = Field(
        default_factory=dict,
        description="KPIs: throughput (bytes/sec), efficiency (useful work %), etc.",
    )
    description: str = Field(
        ..., description="Natural language summary of performance (e.g., 'Completed in 120s with 5GB shuffle, 2 task failures')"
    )

    # Evidence linking
    evidence_sources: List[str] = Field(
        default_factory=list, description="Event IDs supporting metrics"
    )


# ============================================================================
# MAIN EXECUTION FINGERPRINT
# ============================================================================


class FingerprintMetadata(BaseModel):
    """Metadata about the fingerprint itself."""

    fingerprint_schema_version: str = Field(
        default="1.0.0", description="Version of fingerprint schema (for forward compatibility)"
    )
    generated_at: datetime = Field(..., description="Timestamp when fingerprint was generated")
    generator_version: str = Field(..., description="Version of fingerprint generator software")
    event_log_path: str = Field(..., description="Source event log file path")
    event_log_size_bytes: int = Field(..., description="Event log file size in bytes")
    events_parsed: int = Field(..., description="Number of events successfully parsed")
    events_total: Optional[int] = Field(None, description="Total events in log (if known)")
    parsing_issues: List[str] = Field(
        default_factory=list, description="Any warnings or issues during parsing"
    )


class ExecutionFingerprint(BaseModel):
    """
    Complete Spark Execution Fingerprint: three-layer analysis of application run.
    Optimized for LLM consumption with evidence linking and reasoning traces.
    """

    metadata: FingerprintMetadata = Field(..., description="Fingerprint generation metadata")
    semantic: SemanticFingerprint = Field(
        ..., description="Layer 1: What computation was executed (DAG, plan, hash)"
    )
    context: ContextFingerprint = Field(
        ..., description="Layer 2: Where and how it ran (environment, config)"
    )
    metrics: MetricsFingerprint = Field(
        ..., description="Layer 3: How well it performed (statistics, anomalies)"
    )

    # Cross-layer analysis
    execution_class: str = Field(
        ..., description="Classification: cpu_bound, io_bound, memory_bound, network_bound, etc."
    )
    analysis_hints: List[str] = Field(
        default_factory=list,
        description="Sections flagged for LLM focus (anomalies, regressions, constraints)",
    )

    def dict_for_llm(self, include_evidence: bool = True, detail_level: str = "balanced") -> Dict[str, Any]:
        """
        Export fingerprint optimized for LLM analysis.

        Args:
            include_evidence: Whether to include raw event references
            detail_level: 'summary' (minimal), 'balanced' (default), 'detailed' (full)

        Returns:
            Dictionary suitable for JSON serialization and LLM consumption
        """
        result = self.dict()

        if not include_evidence:
            # Strip evidence references for conciseness
            def remove_evidence(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {k: remove_evidence(v) for k, v in obj.items() if k != "evidence_sources"}
                elif isinstance(obj, list):
                    return [remove_evidence(item) for item in obj]
                return obj

            result = remove_evidence(result)

        # Adjust detail level
        if detail_level == "summary":
            # Keep only top-level summaries, drop stage details
            if "metrics" in result and "stage_metrics" in result["metrics"]:
                result["metrics"]["stage_metrics"] = []
            if "anomalies" in result and result["metrics"]["anomalies"]:
                # Keep only top 3 anomalies
                result["metrics"]["anomalies"] = result["metrics"]["anomalies"][:3]

        return result


# ============================================================================
# COMPARISON RESULTS
# ============================================================================


class SemanticComparison(BaseModel):
    """Result of comparing two semantic fingerprints."""

    are_semantically_identical: bool = Field(
        ..., description="Do DAG hashes match? (True = identical computation)"
    )
    semantic_hash_1: str = Field(...)
    semantic_hash_2: str = Field(...)
    differences: List[str] = Field(
        default_factory=list, description="If not identical, what differs (DAG structure, plan)"
    )


class MetricDeviation(BaseModel):
    """Deviation in a single metric between two runs."""

    metric_name: str = Field(...)
    value_1: float = Field(...)
    value_2: float = Field(...)
    deviation_percent: float = Field(...)
    is_regressive: bool = Field(..., description="True if metric worsened")
    threshold_percent: float = Field(..., description="Tolerance threshold used")


class SimilarityReport(BaseModel):
    """Detailed comparison of two executions."""

    run_id_1: str = Field(...)
    run_id_2: str = Field(...)
    semantic_comparison: SemanticComparison = Field(...)
    context_compatible: bool = Field(..., description="Do Spark versions/configs match?")
    context_differences: List[str] = Field(
        default_factory=list, description="Config/version differences"
    )
    metric_deviations: List[MetricDeviation] = Field(...)
    similarity_score: float = Field(
        ..., description="0.0 to 1.0; 1.0 = identical, <0.9 may indicate regression"
    )
    regression_detected: bool = Field(...)
    analysis: str = Field(..., description="Natural language analysis of comparison")


# ============================================================================
# ORCHESTRATION LAYER: Problem Classification and Agent Coordination
# ============================================================================


class ProblemType(str, Enum):
    """Classification of user problem types for agent routing."""
    
    PERFORMANCE = "performance"  # Slow queries, resource issues, optimization
    LINEAGE = "lineage"          # Data flow, transformations, query understanding
    GENERAL = "general"          # General questions, mixed concerns


class AgentTask(BaseModel):
    """A task assigned to an agent by the orchestrator."""
    
    agent_type: str = Field(..., description="Type of agent to execute this task")
    task_description: str = Field(..., description="What the agent should analyze")
    priority: int = Field(default=1, description="Execution priority (1=highest)")
    depends_on: List[str] = Field(default_factory=list, description="Agent types this task depends on")
    focus_areas: List[str] = Field(default_factory=list, description="Specific areas to focus on")


class AgentFinding(BaseModel):
    """A single finding from an agent's analysis."""
    
    agent_type: str = Field(..., description="Agent that produced this finding")
    finding_type: str = Field(..., description="Category of finding")
    severity: str = Field(default="info", description="Severity: critical, high, medium, low, info")
    title: str = Field(..., description="Brief title of the finding")
    description: str = Field(..., description="Detailed description")
    recommendation: Optional[str] = Field(None, description="Suggested action")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence")


class AnalysisResult(BaseModel):
    """Synthesized result from orchestrated agent analysis."""
    
    problem_type: ProblemType = Field(..., description="Classified problem type")
    user_query: str = Field(..., description="Original user query")
    
    # Synthesis
    executive_summary: str = Field(..., description="High-level summary for executives")
    detailed_analysis: str = Field(..., description="Full technical analysis")
    
    # Structured findings
    findings: List[AgentFinding] = Field(default_factory=list, description="All findings from agents")
    recommendations: List[str] = Field(default_factory=list, description="Prioritized recommendations")
    
    # Agent coordination metadata
    agents_used: List[str] = Field(default_factory=list, description="Agents that contributed")
    agent_sequence: List[str] = Field(default_factory=list, description="Order agents were executed")
    
    # Metrics
    total_processing_time_ms: int = Field(default=0, description="Total orchestration time")
    confidence: float = Field(default=0.0, description="Overall confidence score")
    
    # Raw agent responses for debugging
    raw_agent_responses: Dict[str, Any] = Field(default_factory=dict, description="Raw responses from each agent")
