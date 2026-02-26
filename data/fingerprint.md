# Spark Execution Fingerprint

## Metadata

- **Generated**: 2026-02-26 16:31:30.891417
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

**Description**: Spark 3.4.0; 2 executors; 1024MB per executor; Optimizations: WholeStageCodegen, BroadcastJoin, Bucketing

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
- BroadcastJoin
- Bucketing

## Metrics & Performance

**Description**: Completed in 191.0 seconds; Shuffle: 0.1 GB

### Execution Summary
- **Duration**: 191.0 seconds
- **Tasks**: 149 (failed: 0)
- **Stages**: 3
- **Input Data**: 2.4 MB
- **Shuffle**: 95.8 MB
- **Spill**: 50.1 MB
- **Max Concurrent Tasks**: 50

### Task Duration Distribution
- **Min**: 127 ms
- **P25**: 519 ms
- **Median**: 1094 ms
- **P75**: 1507 ms
- **P99**: 1967 ms
- **Max**: 1997 ms
- **Outliers**: 0/149 tasks

### Key Performance Indicators
- **throughput_bytes_per_sec**: 13239.38
- **avg_task_duration_ms**: 1043.57
- **task_failure_rate**: 0.00
- **shuffle_to_input_ratio**: 39.73

### Stage Metrics (Top 5)

#### Stage 0
- Tasks: 50 (failed: 0)
- Duration: 1287 ms (median)
- Input: 2.4 MB
- Shuffle: 0.0 MB

#### Stage 1
- Tasks: 50 (failed: 0)
- Duration: 988 ms (median)
- Input: 0.0 MB
- Shuffle: 49.5 MB

#### Stage 2
- Tasks: 49 (failed: 0)
- Duration: 1033 ms (median)
- Input: 0.0 MB
- Shuffle: 46.3 MB

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
