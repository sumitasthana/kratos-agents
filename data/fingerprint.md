# Spark Execution Fingerprint

## Metadata

- **Generated**: 2026-01-20 23:09:00.447537
- **Application**: data/test_event_log.json
- **Schema Version**: 1.0.0
- **Events Parsed**: 312/312

## Execution Classification: `memory_bound`

## Semantic Fingerprint (What computation)

**Semantic Hash**: `89c02eb2ebc91be7...`

**Description**: SQL query with 3 stages; 2 shuffle stages; 150 total partitions

### DAG Structure
- **Stages**: 3
- **Root Stages**: [0]
- **Leaf Stages**: [2]

#### Stages
- Stage 2: Stage 2: rdd-2 (50 tasks) (shuffle)
- Stage 1: Stage 1: rdd-1 (50 tasks) (shuffle)
- Stage 0: Stage 0: rdd-0 (50 tasks)

#### Dependencies
- Stage 0 -> Stage 1: data_dependency
- Stage 1 -> Stage 2: data_dependency

## Context Fingerprint (Where & how)

**Description**: Spark 3.4.0; 2 executors; 1024MB per executor; Optimizations: WholeStageCodegen

### Spark Configuration
- **Version**: 3.4.0
- **Application**: test-app
- **Master**: unknown

### Resource Allocation
- **Executors**: 2
- **Memory/Executor**: 1024 MB
- **Cores/Executor**: 1
- **Driver Memory**: 1024 MB

### Optimizations Enabled
- WholeStageCodegen

## Metrics & Performance

**Description**: Completed in 191.0 seconds; Shuffle: 0.1 GB

### Execution Summary
- **Duration**: 191.0 seconds
- **Tasks**: 149 (failed: 0)
- **Stages**: 3
- **Input Data**: 2.1 MB
- **Shuffle**: 96.9 MB
- **Spill**: 42.9 MB
- **Max Concurrent Tasks**: 50

### Task Duration Distribution
- **Min**: 100 ms
- **P25**: 578 ms
- **Median**: 1047 ms
- **P75**: 1421 ms
- **P99**: 1973 ms
- **Max**: 1990 ms
- **Outliers**: 0/149 tasks

### Key Performance Indicators
- **throughput_bytes_per_sec**: 11712.33
- **avg_task_duration_ms**: 1021.13
- **task_failure_rate**: 0.00
- **shuffle_to_input_ratio**: 45.40

### Stage Metrics (Top 5)

#### Stage 0
- Tasks: 49 (failed: 0)
- Duration: 1172 ms (median)
- Input: 2.1 MB
- Shuffle: 0.0 MB

#### Stage 1
- Tasks: 50 (failed: 0)
- Duration: 860 ms (median)
- Input: 0.0 MB
- Shuffle: 51.3 MB

#### Stage 2
- Tasks: 50 (failed: 0)
- Duration: 1107 ms (median)
- Input: 0.0 MB
- Shuffle: 45.6 MB

## Evidence Sources

### Semantic
- StageCompleted[0]
- StageCompleted[1]
- StageCompleted[2]
- SQLExecution[0]

### Context
- ApplicationStart
- EnvironmentUpdate
- BlockManagerAdded(3 events)

### Metrics
- TaskEnd(149 events)
- StageCompleted(3 events)
