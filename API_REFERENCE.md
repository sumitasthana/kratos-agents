# API Reference

Complete API documentation for Spark Execution Fingerprint v3.

## Table of Contents

1. [Fingerprint API](#fingerprint-api)
2. [Schema Models](#schema-models)
3. [Agent API](#agent-api)
4. [Formatter API](#formatter-api)
5. [Parser API](#parser-api)
6. [CLI API](#cli-api)
7. [Utilities](#utilities)

---

## Fingerprint API

### `generate_fingerprint()`

Main entry point for generating fingerprints.

```python
def generate_fingerprint(
    event_log_path: str,
    output_format: str = "json",
    output_path: Optional[str] = None,
    detail_level: str = "balanced"
) -> ExecutionFingerprint
```

**Parameters:**
- `event_log_path` (str): Path to Spark event log JSON file
- `output_format` (str): Output format - "json", "yaml", "markdown" (default: "json")
- `output_path` (str, optional): Path to save output file (if None, not saved)
- `detail_level` (str): Detail level - "summary", "balanced", "detailed" (default: "balanced")

**Returns:**
- `ExecutionFingerprint`: Complete fingerprint object with all three layers

**Raises:**
- `ValueError`: If event log is invalid, empty, or missing critical events
- `FileNotFoundError`: If event log path doesn't exist

**Example:**
```python
from src import generate_fingerprint

fp = generate_fingerprint(
    "data/event_logs.json",
    output_format="json",
    output_path="fingerprint.json",
    detail_level="balanced"
)
print(fp.semantic.semantic_hash)
print(fp.metrics.execution_summary.total_duration_ms)
```

---

### `ExecutionFingerprintGenerator`

Advanced class for fine-grained fingerprint generation control.

```python
class ExecutionFingerprintGenerator:
    def __init__(
        self,
        event_log_path: str,
        generator_version: str = "3.0.0"
    )
    
    def generate(self) -> ExecutionFingerprint
    
    def _classify_execution(self, metrics: MetricsFingerprint) -> str
    
    def _generate_analysis_hints(
        self,
        semantic: SemanticFingerprint,
        context: ContextFingerprint,
        metrics: MetricsFingerprint
    ) -> List[str]
```

**Methods:**

#### `generate()`
Generate complete execution fingerprint.

**Returns:**
- `ExecutionFingerprint`: Complete fingerprint

**Example:**
```python
from src.fingerprint import ExecutionFingerprintGenerator

gen = ExecutionFingerprintGenerator("event_log.json")
fp = gen.generate()

# Access layers
print(f"DAG: {fp.semantic.dag.total_stages} stages")
print(f"Duration: {fp.metrics.execution_summary.total_duration_ms}ms")
print(f"Anomalies: {len(fp.metrics.anomalies)}")
```

---

## Schema Models

All data structures use Pydantic for validation and serialization.

### `ExecutionFingerprint`

Complete fingerprint containing all three layers.

```python
class ExecutionFingerprint(BaseModel):
    metadata: FingerprintMetadata
    semantic: SemanticFingerprint
    context: ContextFingerprint
    metrics: MetricsFingerprint
    execution_class: str
    analysis_hints: List[str]
```

**Fields:**
- `metadata`: Generation timestamp, schema version, event log info
- `semantic`: DAG, physical plan, deterministic hash
- `context`: Spark version, resources, configuration
- `metrics`: Performance metrics, anomalies, KPIs
- `execution_class`: "cpu_bound", "io_bound", "memory_bound", "network_bound", "balanced", "unstable"
- `analysis_hints`: Pre-computed analysis suggestions for LLM

### `SemanticFingerprint`

Computation structure - what was executed.

```python
class SemanticFingerprint(BaseModel):
    dag: ExecutionDAG
    physical_plan: Optional[PhysicalPlanNode]
    logical_plan_hash: Optional[LogicalPlanHash]
    semantic_hash: str
    description: str
    evidence_sources: List[str]
```

**Fields:**
- `dag`: ExecutionDAG with stages, edges, topology
- `physical_plan`: SQL operator tree (normalized)
- `logical_plan_hash`: SHA256 hash of logical plan
- `semantic_hash`: Final deterministic fingerprint
- `description`: Natural language summary
- `evidence_sources`: Source events for verification

### `ExecutionDAG`

Directed acyclic graph of execution stages.

```python
class ExecutionDAG(BaseModel):
    stages: List[StageNode]
    edges: List[DAGEdge]
    root_stage_ids: List[int]
    leaf_stage_ids: List[int]
    total_stages: int
```

**Fields:**
- `stages`: List of StageNode objects in execution order
- `edges`: Dependencies between stages
- `root_stage_ids`: Entry points (no dependencies)
- `leaf_stage_ids`: Final stages (no dependents)
- `total_stages`: Total stage count

### `StageNode`

Single stage in execution DAG.

```python
class StageNode(BaseModel):
    stage_id: int
    stage_name: str
    num_partitions: int
    is_shuffle_stage: bool
    rdd_name: Optional[str]
    description: str
```

**Fields:**
- `stage_id`: Unique Spark stage ID
- `stage_name`: Human-readable name
- `num_partitions`: Output partition count
- `is_shuffle_stage`: Whether shuffle is involved
- `rdd_name`: RDD or DataFrame name
- `description`: Natural language description

### `ContextFingerprint`

Environment and configuration - where/how it ran.

```python
class ContextFingerprint(BaseModel):
    spark_config: SparkConfig
    executor_config: ExecutorConfig
    submit_params: SubmitParameters
    jvm_settings: Dict[str, str]
    optimizations_enabled: List[str]
    description: str
    evidence_sources: List[str]
```

**Fields:**
- `spark_config`: Spark version, deployment mode, parameters
- `executor_config`: Resource allocation (cores, memory)
- `submit_params`: Application metadata (user, queue, timestamp)
- `jvm_settings`: JVM flags and options
- `optimizations_enabled`: Enabled Spark optimizations
- `description`: Natural language summary
- `evidence_sources`: Source events

### `SparkConfig`

Spark configuration parameters.

```python
class SparkConfig(BaseModel):
    spark_version: str
    scala_version: Optional[str]
    java_version: Optional[str]
    hadoop_version: Optional[str]
    app_name: str
    master_url: str
    config_params: Dict[str, str]
```

**Fields:**
- `spark_version`: e.g., "3.4.0"
- `scala_version`: Scala version used
- `java_version`: Java version
- `hadoop_version`: Hadoop version
- `app_name`: Application name
- `master_url`: "yarn://", "k8s://", "standalone://", etc.
- `config_params`: Critical Spark configuration dictionary

**Example:**
```python
fp = generate_fingerprint("event_log.json")
config = fp.context.spark_config

print(f"Spark {config.spark_version}")
print(f"App: {config.app_name}")
print(f"Shuffle partitions: {config.config_params.get('spark.shuffle.partitions')}")
```

### `ExecutorConfig`

Executor and driver resource configuration.

```python
class ExecutorConfig(BaseModel):
    total_executors: int
    executor_memory_mb: int
    executor_cores: int
    driver_memory_mb: int
    driver_cores: int
    description: str
```

**Fields:**
- `total_executors`: Number of executors (excluding driver)
- `executor_memory_mb`: Memory per executor in MB
- `executor_cores`: CPU cores per executor
- `driver_memory_mb`: Driver memory in MB
- `driver_cores`: Driver CPU cores
- `description`: Natural language summary

### `MetricsFingerprint`

Performance metrics - how well it ran.

```python
class MetricsFingerprint(BaseModel):
    execution_summary: ExecutionSummary
    stage_metrics: List[StageMetrics]
    task_distribution: TaskMetricsDistribution
    anomalies: List[AnomalyEvent]
    key_performance_indicators: Dict[str, float]
    description: str
    evidence_sources: List[str]
```

**Fields:**
- `execution_summary`: Aggregate execution statistics
- `stage_metrics`: Per-stage breakdown
- `task_distribution`: Task-level percentile statistics
- `anomalies`: Detected performance issues
- `key_performance_indicators`: Computed KPIs
- `description`: Natural language summary
- `evidence_sources`: Source events

### `ExecutionSummary`

High-level execution statistics.

```python
class ExecutionSummary(BaseModel):
    total_duration_ms: int
    total_tasks: int
    total_stages: int
    total_input_bytes: int
    total_output_bytes: int
    total_shuffle_bytes: int
    total_spill_bytes: int
    failed_task_count: int
    executor_loss_count: int
    max_concurrent_tasks: int
```

**Fields:**
- `total_duration_ms`: Wall-clock time in milliseconds
- `total_tasks`: Total number of tasks executed
- `total_stages`: Total number of stages
- `total_input_bytes`: Total input data read
- `total_output_bytes`: Total output data written
- `total_shuffle_bytes`: Total data shuffled (read + write)
- `total_spill_bytes`: Total data spilled to disk (memory pressure indicator)
- `failed_task_count`: Number of failed tasks
- `executor_loss_count`: Number of executor failures
- `max_concurrent_tasks`: Peak parallelism

**Example:**
```python
fp = generate_fingerprint("event_log.json")
summary = fp.metrics.execution_summary

print(f"Duration: {summary.total_duration_ms / 1000:.1f}s")
print(f"Tasks: {summary.total_tasks}")
print(f"Input: {summary.total_input_bytes / (1024**3):.1f}GB")
print(f"Spill: {summary.total_spill_bytes / (1024**3):.1f}GB")
```

### `StageMetrics`

Per-stage performance metrics.

```python
class StageMetrics(BaseModel):
    stage_id: int
    num_tasks: int
    num_partitions: int
    duration_ms: int
    input_bytes: int
    output_bytes: int
    shuffle_read_bytes: int
    shuffle_write_bytes: int
    spill_bytes: int
    failed_task_count: int
    task_duration_stats: PercentileStats
    input_bytes_stats: PercentileStats
```

**Fields:**
- `stage_id`: Spark stage ID
- `num_tasks`: Number of tasks in this stage
- `num_partitions`: Output partitions
- `duration_ms`: Total stage duration
- `input_bytes`: Data read
- `output_bytes`: Data produced
- `shuffle_read_bytes`: Data read from shuffle
- `shuffle_write_bytes`: Data written to shuffle
- `spill_bytes`: Data spilled to disk
- `failed_task_count`: Failed tasks in this stage
- `task_duration_stats`: Duration percentiles (min, p25, p50, p75, p99, max, mean, stddev)
- `input_bytes_stats`: Input size percentiles

### `AnomalyEvent`

Detected performance anomaly.

```python
class AnomalyEvent(BaseModel):
    anomaly_type: str
    severity: str
    description: str
    affected_stages: Optional[List[int]]
    affected_tasks: Optional[List[int]]
    metric_name: Optional[str]
    metric_value: Optional[float]
    evidence: Dict[str, Any]
```

**Fields:**
- `anomaly_type`: "skewed_stage", "task_failures", "high_spill", "high_shuffle", etc.
- `severity`: "low", "medium", "high", "critical"
- `description`: Natural language explanation
- `affected_stages`: Which stages affected
- `affected_tasks`: Sample affected task IDs
- `metric_name`: Name of anomalous metric
- `metric_value`: Value indicating anomaly
- `evidence`: Supporting data

**Example:**
```python
fp = generate_fingerprint("event_log.json")

for anomaly in fp.metrics.anomalies:
    print(f"[{anomaly.severity.upper()}] {anomaly.anomaly_type}")
    print(f"  {anomaly.description}")
    if anomaly.affected_stages:
        print(f"  Stages: {anomaly.affected_stages}")
```

### `PercentileStats`

Percentile-based statistics for a metric.

```python
class PercentileStats(BaseModel):
    min: float
    p25: float
    p50: float  # median
    p75: float
    p99: float
    max: float
    mean: float
    stddev: float
    count: int
    outlier_count: int
```

**Fields:**
- `min`: Minimum value
- `p25`, `p50`, `p75`, `p99`: Percentiles
- `max`: Maximum value
- `mean`: Average
- `stddev`: Standard deviation
- `count`: Number of data points
- `outlier_count`: Values beyond ±2σ

---

## Agent API

### Agent Classes

#### `QueryUnderstandingAgent`

Explains what a Spark query/job does.

```python
class QueryUnderstandingAgent(BaseAgent):
    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        include_dag: bool = True,
        include_plan: bool = True,
        **kwargs
    ) -> AgentResponse
```

**Methods:**

##### `analyze()`
Generate query explanation.

**Parameters:**
- `fingerprint_data`: Serialized fingerprint dictionary
- `include_dag`: Include DAG in analysis (default: True)
- `include_plan`: Include physical plan (default: True)

**Returns:**
- `AgentResponse`: Structured response with explanation

**Example:**
```python
import asyncio
from src.agents import QueryUnderstandingAgent
from src import generate_fingerprint

async def explain():
    fp = generate_fingerprint("event_log.json")
    
    agent = QueryUnderstandingAgent(model="gpt-4o")
    response = await agent.analyze(fp.model_dump())
    
    print(response.summary)
    print(response.explanation)
    for finding in response.key_findings:
        print(f"  - {finding}")

asyncio.run(explain())
```

---

#### `RootCauseAgent`

Identifies performance issue root causes.

```python
class RootCauseAgent(BaseAgent):
    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        focus_areas: Optional[List[str]] = None,
        **kwargs
    ) -> AgentResponse
```

**Methods:**

##### `analyze()`
Perform root cause analysis.

**Parameters:**
- `fingerprint_data`: Serialized fingerprint dictionary
- `focus_areas`: Areas to focus on - ["memory", "data_skew", "failures", "config"] (default: all)

**Returns:**
- `AgentResponse`: Analysis results with recommendations

**Example:**
```python
import asyncio
from src.agents import RootCauseAgent
from src import generate_fingerprint

async def diagnose():
    fp = generate_fingerprint("event_log.json")
    
    agent = RootCauseAgent(model="gpt-4o")
    response = await agent.analyze(
        fp.model_dump(),
        focus_areas=["memory", "data_skew"]
    )
    
    print(f"Health: {response.summary}")
    for i, finding in enumerate(response.key_findings, 1):
        print(f"{i}. {finding}")

asyncio.run(diagnose())
```

---

### `BaseAgent`

Abstract base class for all agents.

```python
class BaseAgent(ABC):
    def __init__(self, llm_config: Optional[LLMConfig] = None):
        """Initialize agent with LLM configuration."""
    
    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Agent type enum."""
    
    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name."""
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Agent description."""
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for LLM."""
    
    @abstractmethod
    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        **kwargs
    ) -> AgentResponse:
        """Run analysis and return structured response."""
```

**Methods:**

To create custom agents, inherit from `BaseAgent` and implement:
1. `agent_type` property
2. `agent_name` property
3. `description` property
4. `system_prompt` property
5. `analyze()` method

---

### `AgentResponse`

Standardized response from any agent.

```python
class AgentResponse(BaseModel):
    agent_type: AgentType
    agent_name: str
    success: bool
    
    summary: str
    explanation: str
    
    key_findings: List[str]
    confidence: float
    
    timestamp: datetime
    processing_time_ms: Optional[int]
    model_used: Optional[str]
    tokens_used: Optional[int]
    
    error: Optional[str]
    
    suggested_followup_agents: List[AgentType]
```

**Fields:**
- `agent_type`: AgentType enum value
- `agent_name`: Human-readable name
- `success`: Whether analysis succeeded
- `summary`: 1-2 sentence summary
- `explanation`: Detailed explanation
- `key_findings`: Bullet-point insights
- `confidence`: 0.0-1.0 confidence score
- `timestamp`: When response generated
- `processing_time_ms`: Execution time
- `model_used`: LLM model name
- `tokens_used`: Token count (if applicable)
- `error`: Error message if failed
- `suggested_followup_agents`: Recommended next agents

---

### `LLMConfig`

Configuration for LLM provider.

```python
class LLMConfig(BaseModel):
    provider: str = "openai"  # "openai", "anthropic"
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 2000
```

**Example:**
```python
from src.agents.base import LLMConfig
from src.agents import QueryUnderstandingAgent

config = LLMConfig(
    provider="openai",
    model="gpt-4o",
    temperature=0.3,
    max_tokens=2000
)

agent = QueryUnderstandingAgent(llm_config=config)
```

---

### `AgentType`

Enumeration of agent types.

```python
class AgentType(str, Enum):
    QUERY_UNDERSTANDING = "query_understanding"
    ROOT_CAUSE = "root_cause"
    OPTIMIZATION = "optimization"
    REGRESSION = "regression"
    ORCHESTRATOR = "orchestrator"
```

---

## Formatter API

### `FingerprintFormatter`

Output formatting utility.

```python
class FingerprintFormatter:
    @staticmethod
    def to_json(
        fingerprint: ExecutionFingerprint,
        include_evidence: bool = True,
        indent: int = 2
    ) -> str
    
    @staticmethod
    def to_markdown(
        fingerprint: ExecutionFingerprint,
        include_evidence: bool = True
    ) -> str
    
    @staticmethod
    def to_yaml(
        fingerprint: ExecutionFingerprint,
        include_evidence: bool = True
    ) -> str
    
    @staticmethod
    def save_json(
        fingerprint: ExecutionFingerprint,
        output_path: str,
        include_evidence: bool = True
    ) -> None
    
    @staticmethod
    def save_markdown(
        fingerprint: ExecutionFingerprint,
        output_path: str,
        include_evidence: bool = True
    ) -> None
```

**Methods:**

##### `to_json()`
Convert fingerprint to JSON string.

**Parameters:**
- `fingerprint`: ExecutionFingerprint object
- `include_evidence`: Include evidence sources (default: True)
- `indent`: JSON indentation (default: 2)

**Returns:**
- JSON string

**Example:**
```python
from src import generate_fingerprint
from src.formatter import FingerprintFormatter

fp = generate_fingerprint("event_log.json")
json_str = FingerprintFormatter.to_json(fp)
print(json_str)
```

##### `to_markdown()`
Convert fingerprint to Markdown string.

**Parameters:**
- `fingerprint`: ExecutionFingerprint object
- `include_evidence`: Include evidence sources (default: True)

**Returns:**
- Markdown string

**Example:**
```python
md = FingerprintFormatter.to_markdown(fp, include_evidence=True)
print(md)
```

##### `save_json()`
Save fingerprint as JSON file.

**Parameters:**
- `fingerprint`: ExecutionFingerprint object
- `output_path`: File path to save
- `include_evidence`: Include evidence sources (default: True)

**Example:**
```python
FingerprintFormatter.save_json(fp, "fingerprint.json")
```

---

## Parser API

### `EventLogParser`

Parse Spark event logs.

```python
class EventLogParser:
    def __init__(self, event_log_path: str)
    
    def parse(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]
    
    def get_parse_errors(self) -> List[Tuple[int, str]]
```

**Methods:**

##### `parse()`
Parse event log file.

**Returns:**
- Tuple of (events list, metadata dict)

**Raises:**
- `FileNotFoundError`: If file doesn't exist
- `ValueError`: If file is not valid JSON

**Example:**
```python
from src.parser import EventLogParser

parser = EventLogParser("event_log.json")
events, metadata = parser.parse()

print(f"Events: {len(events)}")
print(f"Metadata: {metadata}")
```

##### `get_parse_errors()`
Get list of parsing errors.

**Returns:**
- List of (line_number, error_message) tuples

---

### `EventIndex`

Indexed access to parsed events.

```python
class EventIndex:
    def __init__(self, events: List[Dict[str, Any]])
    
    def get_by_type(self, event_type: str) -> List[Dict[str, Any]]
    
    def get_by_id(self, event_id: int) -> Optional[Dict[str, Any]]
```

**Methods:**

##### `get_by_type()`
Get all events of a specific type.

**Parameters:**
- `event_type`: Event type string (e.g., "SparkListenerTaskEnd")

**Returns:**
- List of matching events

**Example:**
```python
from src.parser import EventLogParser, EventIndex

parser = EventLogParser("event_log.json")
events, _ = parser.parse()
index = EventIndex(events)

task_events = index.get_by_type("SparkListenerTaskEnd")
print(f"Tasks: {len(task_events)}")
```

---

## CLI API

### Command-Line Interface

```bash
python -m src.cli EVENT_LOG_PATH [OPTIONS]
```

**Arguments:**
- `EVENT_LOG_PATH`: Path to Spark event log

**Options:**
- `-o, --output PATH`: Output file path
- `-f, --format {json,yaml,markdown}`: Output format (default: json)
- `-l, --level {summary,balanced,detailed}`: Detail level (default: balanced)
- `--no-evidence`: Exclude evidence sources
- `--help`: Show help

**Examples:**

```bash
# Generate JSON fingerprint
python -m src.cli data/event_log.json

# Generate Markdown report
python -m src.cli data/event_log.json --format markdown --output report.md

# Generate detailed summary
python -m src.cli data/event_log.json --format json --level detailed --output fp_detailed.json

# Without evidence (smaller output)
python -m src.cli data/event_log.json --no-evidence
```

---

## Utilities

### DAG Utilities

```python
from src.dag_utils import (
    normalize_dag,
    topological_sort,
    compute_plan_hash,
    extract_plan_tree
)
```

#### `normalize_dag()`
Normalize DAG for deterministic hashing.

#### `topological_sort()`
Topologically sort DAG stages.

#### `compute_plan_hash()`
Compute SHA256 hash of physical plan.

#### `extract_plan_tree()`
Extract plan tree from SQL execution event.

---

## Dependencies

See `requirements.txt`:

```
pydantic>=2.0
pandas>=2.0
pyspark>=3.3
pyyaml>=6.0
pytest>=7.0
pytest-asyncio>=0.23
python-dotenv>=1.0
langchain>=0.3
langchain-openai>=0.2
langgraph>=0.2
```

---

## Error Handling

### Common Exceptions

```python
# File not found
try:
    fp = generate_fingerprint("missing.json")
except FileNotFoundError:
    print("Event log not found")

# Invalid event log
try:
    fp = generate_fingerprint("corrupt.json")
except ValueError as e:
    print(f"Invalid event log: {e}")

# Agent analysis failed
try:
    response = await agent.analyze(fp.model_dump())
except Exception as e:
    print(f"Agent error: {e}")
    # Check response.error field for details
```

---

## Version

Current version: **3.0.0**

## License

See LICENSE file in repository.

## Support

For issues and questions, see README.md or documentation files.
