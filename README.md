# Spark Execution Fingerprint (v3)

A production-ready Python system that derives deterministic, multi-layered Execution Fingerprints from Spark system artifacts (event logs, driver logs, executor logs). Outputs LLM-optimized structured documents for runtime analysis, regression detection, and intelligent root cause analysis using AI agents.

## Overview

The system combines **three-layer fingerprinting** with **AI-powered analysis agents** for comprehensive Spark execution understanding:

### Three-Layer Fingerprint
1. **Semantic Fingerprint**: Normalized DAG + physical plan hash for detecting identical executions across runs
2. **Context Fingerprint**: Spark version, environment, cluster configuration for drift analysis
3. **Performance Metrics**: Quantified execution characteristics (duration, shuffle bytes, partition counts, anomalies) for regression detection and similarity comparison

### AI Analysis Agents (LangChain/LangGraph)
- **Query Understanding Agent**: Explains what a Spark query does in plain English
- **Root Cause Agent**: Identifies root causes of performance issues and anomalies
- **Extensible Framework**: BaseAgent interface for building custom analysis agents

## Primary Data Source

- **JSON Event Logs** (primary): Spark History Server format, structured and deterministic
- **Driver Logs** (secondary): Configuration evidence, anomalies, errors
- **Executor Logs** (optional): OOM, spills, GC events for root cause analysis

## Output Format

Structured JSON/Markdown optimized for LLM analysis:
- Hierarchical organization (facts → context → metrics)
- Evidence linking with event source references
- Natural language descriptions
- Analysis hints for anomaly focus
- Agent-generated explanations and root cause analysis

## Project Structure

```
src/
  __init__.py                    - Main entry point
  schemas.py                     - Pydantic models for all fingerprint layers
  parser.py                      - Spark event log reader with indexing
  semantic_generator.py          - DAG extraction, plan hashing
  context_generator.py           - Environment/config extraction
  metrics_generator.py           - Task/stage metrics aggregation
  fingerprint.py                 - Main orchestrator
  formatter.py                   - JSON/Markdown/YAML rendering
  dag_utils.py                   - Graph utilities and normalization
  cli.py                         - Command-line interface
  agents/
    __init__.py
    base.py                      - BaseAgent interface and AgentResponse
    query_understanding.py       - Query explanation agent
    root_cause.py                - Root cause analysis agent
    examples.py                  - Agent usage examples

tests/
  __init__.py
  test_fingerprint.py            - Unit tests for fingerprint generation
  test_agents.py                 - Agent tests
  generate_sample_log.py         - Sample event log generation

data/
  event_logs.json                - Sample Spark event log
  event_logs_rca.json            - Sample RCA event log

fingerprints/                    - Generated fingerprints (timestamped)
demo.py                          - End-to-end demo with agents
pyproject.toml, requirements.txt - Dependency management
```

## Key Features

✅ **Complete Implementation**
- All three fingerprint layers fully implemented
- JSON event log parser with indexing and error handling
- DAG extraction with topological sorting
- Physical plan normalization for SQL
- Comprehensive metrics aggregation with anomaly detection

✅ **AI-Powered Analysis**
- LangChain/LangGraph agent framework
- Query Understanding Agent: explains execution in natural language
- Root Cause Agent: identifies performance issue causes
- Extensible for custom analysis agents

✅ **LLM-Optimized Output**
- Multiple formats: JSON (APIs), Markdown (reading), YAML (alternative)
- Detail levels: summary, balanced, detailed
- Evidence linking for fact verification
- Analysis hints directing LLM focus to anomalies

✅ **Deterministic & Comparable**
- Semantic hash identical for same DAG structure
- Context layer enables version/config compatibility checking
- Metrics layer supports regression detection
- Fingerprint comparison with similarity scoring

✅ **Production Ready**
- CLI interface with flexible options
- Comprehensive error handling
- Full test coverage
- Detailed documentation and examples

## Quick Start

```bash
# Installation
pip install -r requirements.txt

# Generate fingerprint and analyze with agents
python demo.py --from-log data/event_logs_rca.json

# CLI-only (no LLM needed)
python -m src.cli data/event_logs.json --format markdown

# Python API
from src import generate_fingerprint
fp = generate_fingerprint("path/to/event_log.json")
print(fp.semantic.semantic_hash)
```

See [QUICKSTART.md](QUICKSTART.md) for detailed usage and examples.

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Installation, usage examples, CLI reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - Design deep dive, three-layer architecture, cross-layer analysis
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - Feature overview, built components, agent system
- [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation
