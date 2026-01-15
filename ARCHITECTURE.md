# Spark Execution Fingerprint: Architecture & Design

## Overview

The Spark Execution Fingerprint is a deterministic, multi-layered analysis of a Spark application run. It extracts structured information from Spark system artifacts (event logs, driver logs, executor logs) and produces LLM-optimized output for analysis and comparison.

**Core Design Principle**: Three independent but complementary layers that answer different questions:
1. **Semantic**: What computation was executed?
2. **Context**: Where and how did it run?
3. **Metrics**: How well did it perform?

---

## Layer 1: Semantic Fingerprint

### Purpose
Captures the **computation itself** — independent of environment, resource allocation, or runtime variations. Two runs with identical semantic fingerprints executed the same logical computation, even if performance differed.

### What It Contains

#### Execution DAG (Directed Acyclic Graph)
- **Stages**: Spark execution stages with metadata
  - `stage_id`: Unique identifier
  - `num_partitions`: Output partitions
  - `is_shuffle_stage`: Whether stage involves shuffle
  - `rdd_name`: RDD/DataFrame name
  - Description: Human-readable explanation

- **Edges**: Dependencies between stages
  - `from_stage_id → to_stage_id`: Direction of dependency
  - `shuffle_required`: Whether edge involves shuffle
  - `reason`: Why dependency exists (e.g., `reduceByKey`, `join`)

- **Topology**: Root and leaf stages for quick traversal

#### Physical Plan (SQL Only)
Extracted from `SparkListenerSQLExecutionStart` events:
- Normalized operator tree (Scan, Filter, Aggregate, Join, etc.)
- Statistics (estimated rows, bytes)
- Preserved structure but normalized to remove runtime cosmetics

#### Logical Plan Hash
- **plan_hash**: SHA256 of normalized plan structure
  - Deterministic: identical plans → identical hash
  - Robust: cosmetic changes (column ordering) don't affect hash
  - Independent of runtime

#### Semantic Hash
Final deterministic identifier combining:
- DAG structure (stage count, edge topology)
- Logical plan hash
- Normalized for repeatability

### Data Structure Example

```python
SemanticFingerprint:
  dag:
    stages: [StageNode(...), ...]  # Topologically ordered
    edges: [DAGEdge(...), ...]      # Stage dependencies
    root_stage_ids: [0, 1, ...]     # Entry points
    leaf_stage_ids: [4, 5, ...]     # Final stages
  
  physical_plan: PhysicalPlanNode(...)  # SQL plan tree
  logical_plan_hash: LogicalPlanHash(...)
  semantic_hash: "a1b2c3d4e5f6..."    # Final deterministic ID
  description: "Read parquet, filter, aggregate by key, write"
  evidence_sources: ["StageCompleted[0]", "StageCompleted[1]", ...]
```

### Use Cases

1. **Detect Identical Executions**: Compare semantic hashes across runs
   ```python
   if fp1.semantic.semantic_hash == fp2.semantic.semantic_hash:
       print("Same computation structure")
   ```

2. **Understand Computation**: Export DAG for visualization
   ```python
   for stage in fp.semantic.dag.stages:
       print(f"{stage.stage_id}: {stage.description}")
   ```

3. **Plan Normalization**: Identify equivalent logical plans
   ```python
   if fp1.logical_plan_hash == fp2.logical_plan_hash:
       print("Equivalent queries (different syntax)")
   ```

### Evidence Linking
- References to source events: `StageCompleted[stage_id]`, `SQLExecution[execution_id]`
- Allows LLM to trace facts back to raw event log
- Supports drill-down into detailed logs for explanation

---

## Layer 2: Context Fingerprint

### Purpose
Captures **environment and configuration** — all the non-computation factors that affect behavior and performance. Explains *where* and *how* the computation ran.

### What It Contains

#### Spark Configuration
- **spark_version**: Exact Spark version (e.g., "3.4.0")
- **scala_version**, **java_version**, **hadoop_version**: Runtime versions
- **app_name**: Application name
- **master_url**: Deployment mode (standalone, YARN, K8s, etc.)
- **config_params**: Dictionary of critical Spark configs:
  - `spark.shuffle.partitions`: Number of shuffle partitions
  - `spark.sql.adaptive.enabled`: AQE enabled?
  - `spark.serializer`: Serialization codec
  - `spark.io.compression.codec`: Compression
  - etc.

#### Executor Configuration
- **total_executors**: Number of executors (excluding driver)
- **executor_memory_mb**: Memory per executor
- **executor_cores**: Cores per executor
- **driver_memory_mb**: Driver memory
- **driver_cores**: Driver cores
- **description**: Natural language summary (e.g., "10 executors × 8GB × 4 cores each")

#### JVM Settings
- GC settings: `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis`, etc.
- Memory settings: `-Xmx`, `-Xms`
- Serialization: `sun.io.serialization.extendedDebugInfo`
- Other JVM flags

#### Enabled Optimizations
List of performance optimizations detected:
- AdaptiveQueryExecution (AQE)
- ColumnarExecution
- WholeStageCodegen
- DynamicPartitionPruning
- BroadcastJoin
- etc.

#### Submission Parameters
- **submit_time**: When app was submitted
- **user**: User who submitted
- **app_id**: Spark application ID
- **queue**: YARN queue (if applicable)

### Data Structure Example

```python
ContextFingerprint:
  spark_config: SparkConfig(
    spark_version="3.4.0",
    scala_version="2.12.17",
    java_version="11.0.20",
    hadoop_version="3.3.6",
    app_name="MyETLJob",
    master_url="yarn://cluster",
    config_params={
      "spark.shuffle.partitions": "200",
      "spark.sql.adaptive.enabled": "true",
      ...
    }
  )
  
  executor_config: ExecutorConfig(
    total_executors=10,
    executor_memory_mb=8192,
    executor_cores=4,
    driver_memory_mb=4096,
    driver_cores=1,
    description="10 executors × 8GB × 4 cores each; Driver: 4GB × 1 core"
  )
  
  jvm_settings={
    "spark.executor.extraJavaOptions": "-XX:+UseG1GC -XX:MaxGCPauseMillis=20",
    ...
  }
  
  optimizations_enabled=["AdaptiveQueryExecution", "BroadcastJoin"],
  
  description="Spark 3.4.0 on YARN; 10×8GB executors; AQE enabled"
  evidence_sources=["ApplicationStart", "EnvironmentUpdate", "BlockManagerAdded(10 events)"]
```

### Use Cases

1. **Environment Drift Detection**: Compare contexts across runs
   ```python
   if fp1.context.spark_config.spark_version != fp2.context.spark_config.spark_version:
       print("Spark version changed - could explain performance difference")
   ```

2. **Configuration Analysis**: Explain performance choices
   ```python
   for opt in fp.context.optimizations_enabled:
       print(f"Optimization enabled: {opt}")
   ```

3. **Resource Adequacy**: Check if resources are sufficient
   ```python
   if fp.metrics.execution_summary.total_spill_bytes > 1000000000:
       print("High spill - consider increasing executor memory")
   ```

### Evidence Linking
- References to events providing context info
- Supports validation of configuration claims
- Helps LLM understand configuration rationale

---

## Layer 3: Metrics Fingerprint

### Purpose
Captures **performance characteristics** — quantified execution metrics and anomalies. Answers "how well did it perform?" and "what went wrong?"

### What It Contains

#### Execution Summary
High-level aggregates across entire execution:
- **total_duration_ms**: Wall-clock time from start to finish
- **total_tasks**: Total number of tasks executed
- **total_stages**: Total number of stages
- **total_input_bytes**: Input data read from sources
- **total_output_bytes**: Output data written
- **total_shuffle_bytes**: Data shuffled (read + write)
- **total_spill_bytes**: Data spilled to disk (memory pressure indicator)
- **failed_task_count**: Number of failed tasks
- **executor_loss_count**: Number of executor failures
- **max_concurrent_tasks**: Peak parallelism

#### Task Distribution
Percentile-based statistics for all tasks:
```
PercentileStats:
  min, p25, p50 (median), p75, p99, max
  mean, stddev
  outlier_count (values beyond ±2σ)
```

Tracked per metric:
- **duration_ms**: How long tasks took
- **input_bytes**: Data read per task
- **output_bytes**: Data produced per task
- **shuffle_read_bytes**: Shuffle input per task
- **shuffle_write_bytes**: Shuffle output per task
- **spill_bytes**: Disk spill per task

#### Stage Metrics
Per-stage breakdown:
- Stage ID and task count
- Task duration distribution (percentiles)
- Input/output/shuffle/spill bytes
- Failed task count
- Partition count

#### Detected Anomalies
Flagged issues for LLM focus:

```python
AnomalyEvent:
  anomaly_type: str  # "skewed_stage", "task_failures", "high_spill", etc.
  severity: str      # "low", "medium", "high", "critical"
  description: str   # Human-readable explanation
  affected_stages: List[int]  # Which stages affected
  affected_tasks: Optional[List[int]]  # Which tasks (sample)
  metric_name: Optional[str]   # What metric
  metric_value: Optional[float]  # Value indicating anomaly
  evidence: Dict[str, Any]     # Supporting data
```

#### Key Performance Indicators (KPIs)
Computed metrics for quick assessment:
- **throughput_bytes_per_sec**: Data processing rate
- **avg_task_duration_ms**: Average task execution time
- **task_failure_rate**: Fraction of failed tasks
- **shuffle_to_input_ratio**: Relative amount of data shuffled

### Data Structure Example

```python
MetricsFingerprint:
  execution_summary: ExecutionSummary(
    total_duration_ms=120000,
    total_tasks=5000,
    total_stages=10,
    total_input_bytes=10737418240,  # 10 GB
    total_shuffle_bytes=5368709120,  # 5 GB
    total_spill_bytes=268435456,     # 256 MB - memory pressure!
    failed_task_count=2,
    ...
  )
  
  task_distribution: TaskMetricsDistribution(
    duration_ms=PercentileStats(
      min=50, p25=200, p50=500, p75=1000, p99=5000, max=30000,
      mean=650, stddev=2000, count=5000, outlier_count=42
    ),
    ...
  )
  
  stage_metrics=[
    StageMetrics(stage_id=0, num_tasks=500, ...),
    StageMetrics(stage_id=1, num_tasks=500, ...),
    ...
  ]
  
  anomalies=[
    AnomalyEvent(
      anomaly_type="high_spill",
      severity="medium",
      description="Total spill: 256 MB - memory pressure detected",
      metric_value=268435456
    ),
    AnomalyEvent(
      anomaly_type="skewed_stage",
      severity="low",
      description="Stage 3 has high task skew: max 30s vs median 500ms",
      affected_stages=[3],
      metric_value=60.0
    )
  ]
  
  key_performance_indicators={
    "throughput_bytes_per_sec": 89478485.0,
    "avg_task_duration_ms": 650.0,
    "task_failure_rate": 0.0004,
    "shuffle_to_input_ratio": 0.5
  }
  
  description="Completed in 120 seconds; Shuffle: 5GB; Spill: 256MB; 2 failed tasks; 3 anomalies detected"
```

### Use Cases

1. **Regression Detection**: Compare performance across runs
   ```python
   duration_delta = (fp2.metrics.execution_summary.total_duration_ms - 
                     fp1.metrics.execution_summary.total_duration_ms)
   if duration_delta > fp1.metrics.execution_summary.total_duration_ms * 0.1:
       print(f"REGRESSION: {duration_delta/1000:.1f}s slower")
   ```

2. **Bottleneck Analysis**: Identify what's consuming resources
   ```python
   spill_gb = fp.metrics.execution_summary.total_spill_bytes / (1024**3)
   shuffle_gb = fp.metrics.execution_summary.total_shuffle_bytes / (1024**3)
   print(f"Spill: {spill_gb:.1f}GB → memory pressure")
   print(f"Shuffle: {shuffle_gb:.1f}GB → network/disk bottleneck")
   ```

3. **Anomaly Investigation**: Focus on detected issues
   ```python
   for anomaly in fp.metrics.anomalies:
       print(f"{anomaly.severity}: {anomaly.description}")
       if anomaly.affected_stages:
           print(f"  Investigate stages: {anomaly.affected_stages}")
   ```

4. **LLM Analysis**: Feed metrics for intelligent interpretation
   ```python
   # LLM can see all metrics and make inferences
   "Total spill 256MB with 10GB input → 2.5% memory pressure"
   "10 stages with varying durations → possible skew in data distribution"
   ```

### Anomaly Detection

Automatic detection for LLM focus:

| Anomaly | Detection | Severity |
|---------|-----------|----------|
| Task Failures | failure_count > 0 | high if > 1% of tasks |
| Skewed Stage | max_duration > 10 × median | medium if > 50× |
| High Spill | total_spill > 100MB | medium |
| High Shuffle | total_shuffle > 1GB | low (informational) |

### Evidence Linking
- Event counts: "5000 TaskEnd events"
- Stage references: "StageCompleted(10 events)"
- Metric sources for traceability

---

## Cross-Layer Analysis

### Execution Classification
Based on metrics characteristics, fingerprint is classified as:
- **cpu_bound**: Long task durations, high computation
- **io_bound**: Large input/output bytes, relatively short tasks
- **memory_bound**: High spill ratio indicates memory pressure
- **network_bound**: High shuffle ratio indicates network bottleneck
- **balanced**: Mixed characteristics
- **unstable**: High failure rate

### Analysis Hints
LLM-focused annotations:
- "⚠️ 3 anomalies detected - investigate impact"
- "🔴 High memory spill - consider increasing executor memory"
- "🟡 Large shuffle volume - optimize join logic"
- "🟢 No optimizations detected - enable AQE"

---

## Fingerprint Output

### JSON Format
Structured, programmatic consumption:
```json
{
  "metadata": { ... },
  "semantic": { ... },
  "context": { ... },
  "metrics": { ... },
  "execution_class": "io_bound",
  "analysis_hints": [...]
}
```

### Markdown Format
Human/LLM-readable report with sections for each layer

### YAML Format
Alternative structured format

### Detail Levels
- **summary**: Top-level facts only, minimal detail
- **balanced**: Default, includes key metrics and top anomalies
- **detailed**: Full breakdowns, all stages, raw evidence

---

## Fingerprint Comparison

### Semantic Comparison
```python
if fp1.semantic.semantic_hash == fp2.semantic.semantic_hash:
    # Same computation - can compare metrics
```

### Similarity Scoring
Compute deviation across key metrics:
- Duration change ±10%?
- Shuffle bytes ±5%?
- Spill bytes ±2%?

### Regression Detection
```python
SimilarityReport:
  are_semantically_identical: bool
  context_compatible: bool
  metric_deviations: [MetricDeviation(...), ...]
  similarity_score: float  # 0.0-1.0
  regression_detected: bool
```

---

## Implementation Architecture

```
ExecutionFingerprint
├── Semantic Layer
│   ├── ExecutionDAG (stages, edges, topology)
│   ├── PhysicalPlanNode (SQL plan tree)
│   ├── LogicalPlanHash (plan hash)
│   └── Semantic Hash (final deterministic ID)
│
├── Context Layer
│   ├── SparkConfig (version, settings)
│   ├── ExecutorConfig (resources)
│   ├── JVMSettings (performance tuning)
│   └── SubmitParameters (app metadata)
│
├── Metrics Layer
│   ├── ExecutionSummary (aggregates)
│   ├── TaskMetricsDistribution (percentiles)
│   ├── StageMetrics (per-stage breakdown)
│   ├── AnomalyEvent[] (detected issues)
│   └── KPIs (performance indicators)
│
└── Metadata
    ├── Generated timestamp
    ├── Schema version
    └── Parsing issues/warnings
```

---

## Evidence Linking

All fingerprint facts are traceable to source events:

```python
semantic.evidence_sources = [
  "StageCompleted[0]",
  "StageCompleted[1]",
  "SQLExecution[0]"
]

context.evidence_sources = [
  "ApplicationStart",
  "EnvironmentUpdate",
  "BlockManagerAdded(10 events)"
]

metrics.evidence_sources = [
  "TaskEnd(5000 events)",
  "StageCompleted(10 events)",
  "ExecutorMetrics(42 events)"
]
```

This enables LLM to:
1. Verify facts by checking event log
2. Request drill-down into specific events
3. Build reasoning chains from artifacts

---

## Design Philosophy

### Determinism
- Same execution → same semantic hash
- Reproducible across different event log parsers
- Independent of cosmetic changes (column names, etc.)

### Explainability
- Natural language descriptions at every level
- Evidence linking to source artifacts
- Reasoning traces for LLM interpretation

### LLM Optimization
- Hierarchical organization for progressive disclosure
- Analysis hints directing focus to anomalies
- Multiple output formats (JSON for APIs, Markdown for reading)
- Balanced detail level by default

### Layered Independence
- Each layer can be generated/analyzed independently
- Layers answer different questions
- Combined for comprehensive analysis

---

## Agent-Based Analysis System

### Purpose
Beyond the three-layer fingerprint, AI agents provide **intelligent interpretation** of fingerprint data:
- **Natural language explanations** of what executions do
- **Root cause analysis** for performance issues
- **Actionable recommendations** for optimization
- **Cross-agent coordination** for comprehensive insights

### Agent Framework Architecture

```
Fingerprint Data
      ↓
   Agent Framework (LangChain/LangGraph)
      ↓
   [Choose Agent Type]
      ├─→ Query Understanding Agent
      ├─→ Root Cause Agent
      └─→ Custom Agents (extensible)
      ↓
   LLM Provider
      ├─→ OpenAI
      ├─→ Anthropic
      └─→ Custom Models
      ↓
   AgentResponse (structured)
      ├─→ Summary
      ├─→ Explanation
      ├─→ Key Findings
      ├─→ Confidence & Metadata
      └─→ Suggested Follow-ups
```

### Built-In Agents

#### Query Understanding Agent
**Purpose**: Explain what a Spark query/job does in plain English

**Analyzes**:
- Physical plan structure (operators, joins, scans)
- Logical DAG topology (stages, dependencies)
- Data flow from input to output
- Optimization strategies (broadcast joins, etc.)

**Produces**:
```
Summary: "This query reads parquet data, filters by date, aggregates by region, and writes results"

Explanation:
1. Scan: Read 100GB parquet from s3://data/events
2. Filter: Keep only events from last 7 days (90% cardinality reduction)
3. Aggregate: Group by region, compute sum/count (20M distinct regions)
4. Write: Save results as 500 partitions

Key Operations:
- Broadcast join with region dimension table
- Sort-merge join with order data
- Columnar execution enabled

Observations:
- No data skew detected
- Broadcast join optimization recommended
```

**Best For**:
- Understanding what code does
- Documentation and communication
- Training and learning
- Validation that optimization is correct

#### Root Cause Agent
**Purpose**: Identify root causes of performance issues and anomalies

**Analyzes**:
- Detected anomalies (skew, spill, failures)
- Performance metrics relative to baseline
- Configuration mismatches
- Resource constraints
- Correlation between issues

**Produces**:
```
Health Assessment: ⚠️ Warning (2 issues detected)

Issues Found:
1. HIGH PRIORITY: Memory Spill (512MB detected)
   Root Cause: Executor memory (4GB) insufficient for shuffle output (5GB)
   Impact: 20% slowdown due to disk I/O
   Fix: Increase executor memory to 8GB or reduce partition size

2. MEDIUM PRIORITY: Data Skew in Stage 3
   Root Cause: Join key distribution uneven (max 500K rows vs avg 50K)
   Impact: Straggler tasks extending total time
   Fix: Pre-filter or use salting to redistribute skewed key

Correlations:
- Spill exacerbated by skewed partitions (fewer large partitions)
- GC pressure increased by memory pressure

Recommendations (Prioritized):
1. Increase executor memory: 4GB → 8GB
2. Add skew detection before join
3. Consider dynamic partition pruning
```

**Best For**:
- Performance troubleshooting
- Finding optimization opportunities
- Health checks and monitoring
- Automated issue detection

### Implementing Custom Agents

Extend the `BaseAgent` interface:

```python
from src.agents.base import BaseAgent, AgentResponse, AgentType
from typing import Any, Dict
import asyncio

class CustomAnalysisAgent(BaseAgent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.CUSTOM
    
    @property
    def agent_name(self) -> str:
        return "My Custom Agent"
    
    @property
    def description(self) -> str:
        return "Analyzes X aspect of Spark fingerprints"
    
    @property
    def system_prompt(self) -> str:
        return """You are a Spark expert analyzing..."""
    
    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        **kwargs
    ) -> AgentResponse:
        # Your custom analysis logic
        start_time = time.time()
        
        # Extract relevant data from fingerprint
        metrics = fingerprint_data.get("metrics", {})
        
        # Run analysis (with LLM or rule-based)
        findings = await self._run_analysis(metrics)
        
        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            success=True,
            summary=findings["summary"],
            explanation=findings["explanation"],
            key_findings=findings["findings"],
            confidence=0.95,
            processing_time_ms=int((time.time() - start_time) * 1000),
            model_used="gpt-4o"
        )
```

### Agent Response Format

All agents return standardized `AgentResponse`:

```python
AgentResponse(
    agent_type: AgentType,              # Type enum
    agent_name: str,                    # Human name
    success: bool,                      # Did analysis succeed?
    
    # Main output
    summary: str,                       # 1-2 sentence summary
    explanation: str,                   # Detailed explanation
    
    # Structured findings
    key_findings: List[str],            # Bullet-point insights
    confidence: float,                  # 0.0-1.0 confidence
    
    # Metadata
    timestamp: datetime,                # When generated
    processing_time_ms: int,            # Execution time
    model_used: str,                    # LLM model name
    tokens_used: int,                   # LLM tokens consumed
    
    # Error handling
    error: Optional[str],               # Error message if failed
    
    # Cross-references
    suggested_followup_agents: List[AgentType]  # Next agents to run
)
```

### Agent Orchestration Patterns

#### Sequential Analysis
```python
async def analyze_sequentially():
    fp = generate_fingerprint("event_log.json")
    
    # First understand what it does
    query_agent = QueryUnderstandingAgent()
    query_response = await query_agent.analyze(fp.model_dump())
    
    # Then diagnose any issues
    rca_agent = RootCauseAgent()
    rca_response = await rca_agent.analyze(fp.model_dump())
    
    # Follow up on specific recommendations
    if "skew" in rca_response.explanation:
        skew_agent = SkewAnalysisAgent()
        skew_response = await skew_agent.analyze(fp.model_dump())
```

#### Parallel Analysis
```python
async def analyze_parallel():
    fp = generate_fingerprint("event_log.json")
    data = fp.model_dump()
    
    # Run multiple agents in parallel
    results = await asyncio.gather(
        QueryUnderstandingAgent().analyze(data),
        RootCauseAgent().analyze(data),
        OptimizationAgent().analyze(data)
    )
    
    for result in results:
        print(f"{result.agent_name}: {result.summary}")
```

#### Hierarchical Analysis
```python
# Master orchestrator agent coordinates analysis
async def orchestrate():
    fp = generate_fingerprint("event_log.json")
    
    orchestrator = OrchestratorAgent()
    orchestration_plan = await orchestrator.plan(fp.model_dump())
    
    # Execute plan with appropriate agents
    results = {}
    for agent_type in orchestration_plan.agents_to_run:
        agent = get_agent(agent_type)
        results[agent_type] = await agent.analyze(fp.model_dump())
    
    # Synthesize findings
    synthesis = await orchestrator.synthesize(results)
```

### LLM Configuration

Agents are configurable for different LLM providers:

```python
from src.agents.base import LLMConfig

# OpenAI
config = LLMConfig(
    provider="openai",
    model="gpt-4o",
    temperature=0.3,
    max_tokens=2000
)

# Anthropic
config = LLMConfig(
    provider="anthropic",
    model="claude-3-opus",
    temperature=0.3,
    max_tokens=2000
)

# Custom
agent = QueryUnderstandingAgent(llm_config=config)
response = await agent.analyze(fingerprint_data)
```

### Integration with Fingerprints

**Fingerprints contain data; agents provide interpretation:**

```
Fingerprint (What happened?)
├── Semantic: What computation ran?
├── Context: Where/how did it run?
└── Metrics: How well did it perform?
        ↓
   [Agent feeds on fingerprint]
        ↓
Agent (Why did it happen? What should we do?)
├── Query Agent: Explains the "what"
├── RCA Agent: Diagnoses the "why"
└── Optimization Agent: Recommends the "how"
```

**Advantages**:
- Agents can reference evidence in fingerprint
- Fingerprints remain LLM-agnostic (work without agents)
- Agents can be swapped/upgraded independently
- Fingerprints serve as structured context for LLM reasoning

### Agent Failure & Graceful Degradation

If LLM unavailable, agents can fall back to rule-based analysis:

```python
async def analyze_with_fallback():
    agent = QueryUnderstandingAgent()
    
    try:
        # Try LLM-based analysis
        response = await agent.analyze(fingerprint_data, use_llm=True)
    except LLMException:
        # Fall back to rule-based
        logger.warning("LLM unavailable, using rule-based analysis")
        response = agent.analyze_rule_based(fingerprint_data)
    
    return response
```

---

## Next: Using Fingerprints and Agents

See [QUICKSTART.md](QUICKSTART.md) for:
- Installation and setup
- Command-line usage
- Python API examples
- Integration patterns
- Testing and validation
