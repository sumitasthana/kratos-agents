# Quick Start Guide

## Installation

```bash
# Create a Python 3.9+ environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# For agent features (LLM-based analysis), set OpenAI API key
export OPENAI_API_KEY="your-key-here"
```

## Generate a Fingerprint

### From Python

```python
from src import generate_fingerprint

# Generate and save fingerprint
fingerprint = generate_fingerprint(
    event_log_path="/path/to/event_log.json",
    output_format="json",
    output_path="fingerprint.json",
    detail_level="balanced"
)

# Access the fingerprint object
print(fingerprint.semantic.semantic_hash)
print(fingerprint.context.description)
print(fingerprint.metrics.execution_summary.total_duration_ms)
```

### From Command Line

```bash
# Generate JSON fingerprint (default output: runs/fingerprints/)
python -m src.cli fingerprint /path/to/event_log.json

# Generate markdown with summary detail level
python -m src.cli fingerprint /path/to/event_log.json --format markdown --level summary

# Exclude evidence linking for conciseness
python -m src.cli fingerprint /path/to/event_log.json --no-evidence

# Optional: write to an explicit output path
python -m src.cli fingerprint /path/to/event_log.json --output fingerprint.json
```

## Analyze with AI Agents

### Query Understanding Agent

Explains what a Spark query does in plain English:

```python
import asyncio
from src.agents import QueryUnderstandingAgent
from src import generate_fingerprint

async def explain_query():
    # Generate fingerprint
    fingerprint = generate_fingerprint("event_logs.json")
    
    # Create agent
    agent = QueryUnderstandingAgent(
        model="gpt-4o",
        temperature=0.3
    )
    
    # Get explanation
    response = await agent.analyze(
        fingerprint_data=fingerprint.model_dump(),
        include_dag=True,
        include_plan=True
    )
    
    print(f"Summary: {response.summary}")
    print(f"\nExplanation:\n{response.explanation}")
    
    if response.key_findings:
        print("\nKey Findings:")
        for finding in response.key_findings:
            print(f"  - {finding}")

# Run async agent
asyncio.run(explain_query())
```

### Root Cause Agent

Identifies root causes of performance issues:

```python
import asyncio
from src.agents import RootCauseAgent
from src import generate_fingerprint

async def analyze_issues():
    # Generate fingerprint
    fingerprint = generate_fingerprint("event_logs_rca.json")
    
    # Create agent
    agent = RootCauseAgent(
        model="gpt-4o",
        temperature=0.3
    )
    
    # Analyze execution
    response = await agent.analyze(
        fingerprint_data=fingerprint.model_dump(),
        focus_areas=["memory", "data_skew", "failures"]
    )
    
    print(f"Health: {response.summary}")
    print(f"\nAnalysis:\n{response.explanation}")
    
    if response.key_findings:
        print("\nActionable Recommendations:")
        for i, finding in enumerate(response.key_findings, 1):
            print(f"  {i}. {finding}")

# Run async agent
asyncio.run(analyze_issues())
```

### Full End-to-End Demo

```bash
# Run complete analysis (generates fingerprint first)
python -m src.cli orchestrate --from-log /path/to/event_log.json --query "Why is my Spark job slow?"

# Or run from an existing fingerprint
python -m src.cli orchestrate --fingerprint /path/to/fingerprint.json --query "Explain what this query does"

# Git workflow: clone -> extract git_artifacts -> git-dataflow
python -m src.cli git-clone https://github.com/Byte-Farmer/kratos-v1.git --dest kratos-v1
python -m src.cli git-log .\runs\cloned_repos\kratos-v1
python -m src.cli git-dataflow --latest --dir .\runs\git_artifacts --llm

# Optional: include docs (README.md, etc.) in git-dataflow
python -m src.cli git-dataflow --latest --dir .\runs\git_artifacts --llm --include-docs
```

## Output Formats

### JSON (Default)

Structured output optimized for programmatic consumption:
```json
{
  "metadata": { ... },
  "semantic": {
    "semantic_hash": "abc123...",
    "dag": { ... },
    "physical_plan": { ... }
  },
  "context": { ... },
  "metrics": { ... },
  "execution_class": "io_bound",
  "analysis_hints": [...]
}
```

### Markdown

Human-readable report with sections for each layer:
- Metadata
- Execution Classification & Analysis Hints
- Semantic fingerprint (DAG, plan structure)
- Context (Spark version, resources, config)
- Metrics (duration, shuffle, spill, KPIs)
- Stage breakdown
- Detected anomalies
- Evidence sources

### YAML

Alternative structured format:
```bash
python -m src.cli fingerprint /path/to/event_log.json --format yaml
```

## Understanding the Fingerprint

### Semantic Layer
**What**: The computation itself, independent of environment
- **Semantic Hash**: Deterministic identifier - identical hashes mean identical DAGs
- **DAG Structure**: Stages and their dependencies
- **Physical Plan**: SQL execution plan (if SQL query)
- **Use**: Detect identical executions, understand computation structure

### Context Layer  
**Where & How**: Environment and configuration
- **Spark Version**: Critical for behavior changes
- **Resources**: Executor count, memory, cores
- **Configuration**: JVM settings, optimizations enabled
- **Use**: Explain performance differences, detect environment drift

### Metrics Layer
**How Well**: Performance characteristics and anomalies
- **Execution Summary**: Total duration, task counts, bytes processed
- **Task Distribution**: Percentiles of task duration, skewness, outliers
- **Stage Metrics**: Per-stage breakdown
- **Anomalies**: Detected issues (skew, spill, failures) flagged for investigation
- **KPIs**: Throughput, efficiency, failure rate
- **Use**: Regression detection, similarity comparison, anomaly investigation

## Example Workflows

### Workflow 1: Detect Regression

```python
from src import generate_fingerprint

# Generate fingerprints for two runs
fp1 = generate_fingerprint("run1_event_log.json")
fp2 = generate_fingerprint("run2_event_log.json")

# Compare semantic fingerprints
if fp1.semantic.semantic_hash == fp2.semantic.semantic_hash:
    print("Same computation structure")
    
    # Check if metrics degraded
    duration1 = fp1.metrics.execution_summary.total_duration_ms
    duration2 = fp2.metrics.execution_summary.total_duration_ms
    
    if duration2 > duration1 * 1.1:  # > 10% slower
        print(f"REGRESSION: {duration2/duration1:.1f}x slower")
        print(f"Anomalies: {len(fp2.metrics.anomalies)}")
else:
    print("Different computation - not comparable")
```

### Workflow 2: Analyze Performance Bottleneck

```python
fingerprint = generate_fingerprint("event_log.json")

metrics = fingerprint.metrics
exec_summary = metrics.execution_summary

# Check what's consuming time/resources
spill_ratio = exec_summary.total_spill_bytes / exec_summary.total_input_bytes
shuffle_ratio = exec_summary.total_shuffle_bytes / exec_summary.total_input_bytes

print(f"Spill ratio: {spill_ratio:.1%}")
print(f"Shuffle ratio: {shuffle_ratio:.1%}")

# Check for anomalies
for anomaly in metrics.anomalies:
    print(f"{anomaly.severity}: {anomaly.description}")
```

### Workflow 3: LLM-Powered Analysis

```python
import asyncio
from src import generate_fingerprint
from src.agents import QueryUnderstandingAgent, RootCauseAgent

async def analyze_with_llm():
    fingerprint = generate_fingerprint("event_log.json")
    
    # Get query explanation
    query_agent = QueryUnderstandingAgent(model="gpt-4o")
    query_response = await query_agent.analyze(fingerprint.model_dump())
    print("What the query does:")
    print(query_response.explanation)
    
    # Get root cause analysis
    rca_agent = RootCauseAgent(model="gpt-4o")
    rca_response = await rca_agent.analyze(fingerprint.model_dump())
    print("\nPerformance Analysis:")
    print(rca_response.explanation)

asyncio.run(analyze_with_llm())
```

### Workflow 4: Batch Processing

```python
from pathlib import Path
from src import generate_fingerprint
from datetime import datetime

# Process all event logs in a directory
log_dir = Path("runs/spark_event_logs")
for log_file in log_dir.glob("*.json"):
    print(f"Processing {log_file.name}...")
    
    try:
        fp = generate_fingerprint(str(log_file))
        
        # Save fingerprint with timestamp
        output_name = f"fingerprints/fp_{log_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_name, 'w') as f:
            f.write(fp.model_dump_json(indent=2))
        
        print(f"  [PASS] Duration: {fp.metrics.execution_summary.total_duration_ms/1000:.1f}s")
        print(f"  [PASS] Anomalies: {len(fp.metrics.anomalies)}")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
```

## Testing

### Generate Sample Event Log

```python
from tests.generate_sample_log import generate_sample_event_log

generate_sample_event_log("runs/spark_event_logs/sample.json", num_stages=5, tasks_per_stage=100)
```

### Run Tests

```bash
cd tests
python -m pytest test_fingerprint.py -v
python -m pytest test_agents.py -v
```

## Troubleshooting

### Agent Errors

**"OpenAI API Error"**
- Ensure `OPENAI_API_KEY` environment variable is set
- Check API key is valid: `echo $OPENAI_API_KEY`
- Run with `--no-llm` flag to use rule-based analysis instead

**"Timeout waiting for agent response"**
- Increase timeout in agent config: `timeout_seconds=60`
- Check OpenAI API status: https://status.openai.com

### Fingerprint Errors

**"No SparkListenerApplicationStart event found"**
- Event log may be corrupted or incomplete
- Ensure you're using a complete Spark History Server event log
- Check log file size and permissions

**"No events found in event log"**
- Event log may be empty or in wrong format
- Verify it's a JSON event log (one JSON object per line)
- Not compatible with compressed logs (use uncompressed)

### Import Errors

- Ensure you're running from project root: `cd spark_lineage_analyzer/v3`
- Check Python version >= 3.9: `python --version`
- Reinstall dependencies: `pip install -r requirements.txt`

## Performance Notes

- Parsing typical 10MB event log: ~100ms
- Generating fingerprint: ~500ms
- Agent analysis (with LLM): ~5-10 seconds (network dependent)
- Memory usage: Proportional to task count (linear scaling)
- For large logs (>100MB), consider processing stages in parallel

## Architecture

```
src/
  __init__.py             → Public API entry point
  schemas.py              → Pydantic models for all layers
  parser.py               → JSON event log reader and indexing
  dag_utils.py            → DAG manipulation and hashing
  semantic_generator.py   → Extract semantic layer
  context_generator.py    → Extract context layer
  metrics_generator.py    → Extract metrics layer
  fingerprint.py          → Orchestrator
  formatter.py            → Output rendering
  cli.py                  → Command-line interface
  agents/
    base.py               → BaseAgent interface and common types
    query_understanding.py → Query explanation agent
    root_cause.py         → Root cause analysis agent
    examples.py           → Agent usage examples
```

## Next Steps

1. **Fingerprint your applications**: Generate fingerprints from real event logs
2. **Compare executions**: Use semantic hashes to detect regressions
3. **AI-powered analysis**: Enable agents for intelligent insights
4. **Integration**: Build dashboards, APIs, or observability integrations
5. **Custom agents**: Extend BaseAgent for domain-specific analysis

## Documentation

- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - Deep design documentation
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - Feature and implementation details
- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation
