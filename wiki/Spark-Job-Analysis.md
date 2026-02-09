# Spark Job Analysis

Complete guide to analyzing Apache Spark jobs with Kratos.

---

## Overview

Kratos analyzes Apache Spark event logs to provide:
- **Performance Troubleshooting** - Identify bottlenecks and slow stages
- **Query Understanding** - Explain what complex queries do
- **Root Cause Analysis** - Diagnose failures and issues
- **Optimization Recommendations** - Actionable advice to improve performance

---

## How It Works

### The Three-Layer Fingerprint

Kratos generates a comprehensive fingerprint from Spark event logs:

#### 1. Semantic Layer (WHAT Ran)
- Query structure and execution plan
- Data sources and transformations
- DAG topology and dependencies
- SQL queries and DataFrame operations

#### 2. Context Layer (HOW It Ran)
- Spark version and configuration
- Cluster resources (executors, cores, memory)
- Environment settings
- Application metadata

#### 3. Metrics Layer (HOW WELL It Ran)
- Stage and task execution times
- Data shuffle volumes
- Memory usage and spills
- Task failures and retries
- Anomaly detection

---

## Getting Started

### Prerequisites

1. **Spark Event Log File**
   - JSON format from Spark History Server
   - Contains complete execution history
   - Typical location: `spark.eventLog.dir`

2. **OpenAI API Key**
   - Required for AI-powered analysis
   - Configure in `.env` file

### Basic Usage

```bash
# Generate fingerprint
python -m src.cli fingerprint /path/to/event_log.json

# Ask questions with orchestrator
python -m src.cli orchestrate --from-log /path/to/event_log.json \
  --query "Why is my job slow?"
```

---

## Common Analysis Scenarios

### Scenario 1: Performance Troubleshooting

**Question:** "Why is my Spark job slow?"

**What Kratos Analyzes:**
- Stage durations and bottlenecks
- Data shuffle volumes
- Memory pressure and spills
- Data skew across partitions
- Task failure rates

**Sample Output:**
```
ROOT CAUSES IDENTIFIED:

1. MEMORY SPILL (Critical)
   Location: Stage 3
   Impact: 8.2GB spilled to disk
   Duration Impact: +4.5 minutes
   Root Cause: Executor memory (1GB) insufficient for join operation
   
2. DATA SKEW (High)  
   Location: Stage 4, Partition 67
   Impact: 1 partition is 42x larger than median
   Duration Impact: +3.2 minutes
   Root Cause: Uneven distribution of user_id key

3. SHUFFLE OVERHEAD (Medium)
   Location: Stage 2→3 transition
   Impact: 6.4GB shuffle volume
   Duration Impact: +2.1 minutes
   Root Cause: Unnecessary shuffle due to wide transformation

RECOMMENDATIONS:

Priority 1: Increase executor memory
  spark.executor.memory=3g
  Expected improvement: -4.5 minutes

Priority 2: Repartition to fix skew
  df.repartition(200, col("user_id"), col("date"))
  Expected improvement: -3.2 minutes

Priority 3: Add broadcast hint for small table
  df_large.join(broadcast(df_small), "key")
  Expected improvement: -2.1 minutes
```

### Scenario 2: Query Understanding

**Question:** "What does this query do?"

**What Kratos Explains:**
- Data sources being read
- Transformations applied
- Join operations and types
- Aggregations and computations
- Output destinations

**Sample Output:**
```
QUERY EXPLANATION:

PURPOSE:
  This job computes daily active users (DAU) segmented by country
  and device type for the last 7 days.

DATA FLOW:

1. READ SOURCES (Stage 0-1)
   • events_db.user_sessions (45M rows, 12GB)
     - Columns: user_id, session_start, country, device_type
   • users_db.user_profiles (2.3M rows, 450MB)
     - Columns: user_id, signup_date, subscription_tier

2. TRANSFORMATIONS (Stage 2-3)
   • Filter: session_start >= current_date - 7 days
   • Join: user_sessions ⋈ user_profiles ON user_id (Hash Join)
   • Deduplicate: DISTINCT user_id per (date, country, device)
   
3. AGGREGATIONS (Stage 4)
   • GroupBy: date, country, device_type
   • Count: DISTINCT user_id AS daily_active_users
   • Additional: AVG(session_duration), COUNT(sessions)

4. OUTPUT (Stage 5)
   • Write to: analytics_db.dau_metrics
   • Format: Parquet, partitioned by date
   • Rows written: ~1,400 (7 days × ~200 country-device combinations)

KEY OPERATIONS:
  ✓ Hash Join (inner) on user_id
  ✓ Date filter on indexed column
  ✓ Two-level aggregation (dedup + groupby)
  ✓ Partitioned write for query efficiency
```

### Scenario 3: Failure Diagnosis

**Question:** "Why did my job fail?"

**What Kratos Investigates:**
- Exception types and stack traces
- Failed task patterns
- Stage failure sequences
- Executor loss events
- Memory errors

**Sample Output:**
```
FAILURE ANALYSIS:

FAILURE SUMMARY:
  Job Status: FAILED
  Failure Stage: Stage 8
  Failed Tasks: 23 out of 450
  Retry Attempts: 4 (max retries exhausted)
  Final Exception: org.apache.spark.SparkException: Task failed

ROOT CAUSE:

1. OUT OF MEMORY ERROR (Primary)
   Exception: java.lang.OutOfMemoryError: Java heap space
   Location: Executor 3, 8, 12 (consistent pattern)
   Occurred in: Stage 8, Task 156, 234, 389
   
   Analysis:
   - Executor memory: 2GB
   - Task processing: Large JSON parsing + deserialization
   - Heap usage peaked at: 1.95GB (97% of 2GB)
   - GC time: 45% of task duration (sign of memory pressure)

2. DATA ISSUES (Contributing)
   Found: Unusually large JSON documents in partition 156
   Size: 1.8GB in single partition (avg is 45MB)
   Cause: Skewed data - single user_id has 2.4M records

RECOMMENDATIONS:

Immediate Fix:
  1. Increase executor memory:
     spark.executor.memory=4g
  
  2. Increase executor memory overhead:
     spark.executor.memoryOverhead=1g

Long-term Fix:
  3. Repartition data before processing:
     df.repartition(500, "user_id", "date")
  
  4. Add salting to reduce skew:
     df.withColumn("salt", (rand() * 10).cast("int"))
       .repartition(500, "user_id", "salt")
  
  5. Enable adaptive query execution:
     spark.sql.adaptive.enabled=true
```

### Scenario 4: Bottleneck Identification

**Question:** "Where is the bottleneck in my pipeline?"

**Sample Output:**
```
BOTTLENECK ANALYSIS:

EXECUTION TIMELINE:
  Total Duration: 18m 45s

  Stage 0: Read data          [█          ] 1m 12s   (6%)
  Stage 1: Filter             [          ] 0m 23s   (2%)
  Stage 2: Join               [████████   ] 8m 34s  (46%) ← BOTTLENECK
  Stage 3: Aggregate          [██         ] 2m 15s  (12%)
  Stage 4: Sort               [███        ] 3m 42s  (20%)
  Stage 5: Write              [██         ] 2m 39s  (14%)

PRIMARY BOTTLENECK: Stage 2 (Join Operation)

DETAILED ANALYSIS:
  Stage: 2
  Duration: 8m 34s (46% of total)
  Type: Hash Join
  Left: large_table (8.2GB, 45M rows)
  Right: dimension_table (250MB, 1.2M rows)
  Shuffle: 8.2GB
  
  Issues:
  ✗ Right table (250MB) not broadcast (< 1GB threshold)
  ✗ Join generates 8.2GB shuffle
  ✗ 450 shuffle partitions (default) not optimal for data size
  
OPTIMIZATION RECOMMENDATIONS:

1. Broadcast the right table (Estimated -6m)
   dimension_table.cache()
   large_table.join(broadcast(dimension_table), "id")
   
2. Increase broadcast threshold (Estimated -6m)
   spark.sql.autoBroadcastJoinThreshold=500000000  # 500MB
   
3. Optimize shuffle partitions (Estimated -1.5m)
   spark.sql.shuffle.partitions=200
```

---

## Understanding the Output

### Performance Metrics

| Metric | What It Means | Good | Warning | Critical |
|--------|---------------|------|---------|----------|
| **Spill to Disk** | Data written to disk due to memory pressure | 0GB | < 1GB | > 5GB |
| **Shuffle Volume** | Data transferred between executors | < 1GB | 1-10GB | > 10GB |
| **GC Time %** | Time spent in garbage collection | < 10% | 10-30% | > 30% |
| **Task Failures** | Number of failed tasks | 0 | 1-5 | > 5 |
| **Data Skew Ratio** | Largest partition / Median partition | 1-2x | 2-10x | > 10x |

### Common Issues and Patterns

#### Memory Pressure
**Symptoms:**
- Data spill to disk
- High GC time percentage
- OutOfMemoryError exceptions

**Solutions:**
- Increase `spark.executor.memory`
- Increase `spark.executor.memoryOverhead`
- Optimize partition sizes
- Use broadcast joins for small tables

#### Data Skew
**Symptoms:**
- Few tasks much slower than others
- Uneven partition sizes
- Long tail in task duration distribution

**Solutions:**
- Repartition with better key
- Add salting to skewed keys
- Use adaptive query execution
- Consider bucketing for repeated joins

#### Shuffle Overhead
**Symptoms:**
- Large shuffle volumes
- Many shuffle partitions
- Network I/O bottlenecks

**Solutions:**
- Use broadcast joins when possible
- Optimize `spark.sql.shuffle.partitions`
- Reduce wide transformations
- Coalesce after filtering

---

## Advanced Features

### Fingerprint Comparison

Compare two executions to detect regressions:

```python
from src.fingerprint import generate_fingerprint

# Generate fingerprints
baseline = generate_fingerprint("baseline_log.json")
current = generate_fingerprint("current_log.json")

# Compare semantic hashes
if baseline.semantic.semantic_hash != current.semantic.semantic_hash:
    print("Query logic changed!")

# Compare performance
baseline_duration = baseline.metrics.execution_summary.total_duration_ms
current_duration = current.metrics.execution_summary.total_duration_ms
regression_pct = ((current_duration - baseline_duration) / baseline_duration) * 100

if regression_pct > 20:
    print(f"Performance regression: +{regression_pct:.1f}%")
```

### Custom Agent Development

Build specialized agents for your use cases:

```python
from src.agents.base import BaseAgent, AgentResponse

class CustomPerformanceAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "Custom Performance Agent"
    
    async def analyze(self, fingerprint_data, context=None, **kwargs):
        # Your custom analysis logic
        metrics = fingerprint_data.get("metrics", {})
        
        # Analyze specific patterns
        findings = self._analyze_custom_metrics(metrics)
        
        return AgentResponse(
            agent_name=self.agent_name,
            summary="Custom analysis complete",
            explanation=findings,
            confidence_score=0.85
        )
```

---

## API Reference

### generate_fingerprint()

```python
from src.fingerprint import generate_fingerprint

fingerprint = generate_fingerprint(
    event_log_path: str,           # Path to Spark event log
    output_format: str = "json",   # Output format: json, markdown, yaml
    output_path: str = None,       # Optional output file path
    detail_level: str = "balanced" # Detail level: minimal, balanced, detailed
)
```

### SmartOrchestrator

```python
from src.orchestrator import SmartOrchestrator

orchestrator = SmartOrchestrator(fingerprint_data=fingerprint)
result = await orchestrator.solve_problem(
    question: str,              # User question
    context: dict = None        # Optional additional context
)
```

---

## Best Practices

### 1. Enable Event Logging
Ensure Spark event logging is enabled:
```python
spark = SparkSession.builder \
    .config("spark.eventLog.enabled", "true") \
    .config("spark.eventLog.dir", "/path/to/logs") \
    .getOrCreate()
```

### 2. Use Appropriate Detail Level
- **minimal**: Quick overview, small file size
- **balanced**: Good balance for most use cases (default)
- **detailed**: Complete information, large file size

### 3. Preserve Historical Logs
Keep event logs for trend analysis and regression detection.

### 4. Combine with Dashboard
Use the dashboard for visual exploration of analysis results.

---

## Troubleshooting

### Event Log Not Found
**Error**: `File not found: event_log.json`  
**Solution**: Verify the path and ensure event logging is enabled in Spark.

### Invalid Event Log Format
**Error**: `Invalid JSON in event log`  
**Solution**: Ensure you're using the JSON event log (not plaintext).

### API Key Error
**Error**: `OpenAI API key not found`  
**Solution**: Set `OPENAI_API_KEY` in `.env` file or environment variable.

---

## Next Steps

- **[Git Dataflow Analysis](Git-Dataflow-Analysis)** - Analyze code repositories
- **[Data Lineage Extraction](Data-Lineage-Extraction)** - Extract table/column lineage
- **[Dashboard Guide](Dashboard-Guide)** - Interactive visualization
- **[Agent System](Agent-System)** - Deep dive into AI agents

---

**Last Updated**: February 2026  
**Spark Versions Supported**: 2.4+, 3.x
