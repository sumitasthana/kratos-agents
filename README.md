# Spark Execution Fingerprint (v3)

A Python-based system that derives deterministic, multi-layered Execution Fingerprints from Spark system artifacts (event logs, driver logs, executor logs). Outputs LLM-optimized structured documents for runtime analysis and regression detection.

## Overview

The fingerprint comprises three independent layers:

1. **Semantic Fingerprint**: Normalized DAG + physical plan hash for detecting identical executions across runs
2. **Context Fingerprint**: Spark version, environment, cluster configuration for drift analysis
3. **Performance Metrics**: Quantified execution characteristics (duration, shuffle bytes, partition counts, anomalies) for regression detection and similarity comparison

## Primary Data Source

- **JSON Event Logs** (primary): Spark History Server format, structured and deterministic
- **Driver Logs** (secondary): Configuration evidence, anomalies, errors
- **Executor Logs** (optional): OOM, spills, GC events for root cause analysis

## Output Format

Structured JSON/YAML optimized for LLM analysis:
- Hierarchical organization (facts → context → metrics)
- Evidence linking with event source references
- Natural language descriptions
- Reasoning traces
- Queryable cross-references
- Analysis hints for anomaly focus

## Project Structure

```
src/
  schemas/          - Pydantic models for fingerprint layers
  parsers/          - Event log and log file readers
  extractors/       - Semantic, context, metrics extraction
  generators/       - Fingerprint assembly and computation
  formatters/       - Output rendering (JSON, YAML, markdown)
  utils/            - Helpers, normalization, DAG utilities
tests/
  - Unit and integration tests
data/
  - Sample event logs for development/testing
```

## Development Status

- [ ] Project structure and dependencies
- [ ] Fingerprint schemas
- [ ] Event log parser
- [ ] Semantic layer generator
- [ ] Context layer generator
- [ ] Metrics layer aggregator
- [ ] Evidence linking system
- [ ] Output formatter
# kratos-v1
