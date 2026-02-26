"""
demo_fixtures.py — Curated fingerprint builders for the Demo RCA flow.

These builders are importable outside of pytest (no pytest.skip dependency).
They read real-style log files from ``logs/test_fixtures/`` relative to the
repository root and construct the fingerprint objects consumed by
``KratosOrchestrator.run()``.

Intended callers
----------------
- ``rca_api.py``  — POST /api/run_rca_from_logs
- ``tests/test_smoke_all_agents.py`` — delegates its real-log builders here
  so there is no duplicated fingerprint logic.

Log file layout expected under ``<repo_root>/logs/test_fixtures/``::

    logs/test_fixtures/
      spark/          spark_failure_spill.jsonl
      airflow/        airflow_retries_failure.log
      data_quality/   ohlcv_null_spike.log
      infra/          node_pressure_oom.log
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator

from schemas import (
    ContextFingerprint,
    DAGEdge,
    ExecutionDAG,
    ExecutionFingerprint,
    ExecutionSummary,
    ExecutorConfig,
    FingerprintMetadata,
    LogicalPlanHash,
    MetricsFingerprint,
    PercentileStats,
    SemanticFingerprint,
    SparkConfig,
    StageNode,
    SubmitParameters,
    TaskMetricsDistribution,
)

# ─────────────────────────────────────────────────────────────────────────────
# Root paths
# ─────────────────────────────────────────────────────────────────────────────

#: Absolute path to ``logs/test_fixtures/`` from whichever repo checkout this
#: module lives in.  Resolves correctly whether called from ``src/`` or tests/.
LOG_ROOT: Path = Path(__file__).parent.parent / "logs" / "test_fixtures"


def load_demo_log(category: str, filename: str) -> str:
    """
    Read a demo log file and return its text content.

    Parameters
    ----------
    category : str
        Sub-folder: ``"spark"``, ``"airflow"``, ``"data_quality"``, ``"infra"``.
    filename : str
        Bare filename inside that folder.

    Raises
    ------
    FileNotFoundError
        When the file does not exist under ``LOG_ROOT``.
    """
    path = LOG_ROOT / category / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Demo log not found: {path}\n"
            f"Place it under logs/test_fixtures/{category}/{filename}"
        )
    return path.read_text(encoding="utf-8")


@contextmanager
def temp_json_file(data: Dict[str, Any]) -> Generator[str, None, None]:
    """
    Context manager that writes *data* to a NamedTemporaryFile as JSON and
    yields the file path.  The file is removed when the context exits.

    Used by API handlers that need to pass a data fingerprint dict to
    ``DataProfilerOrchestrator`` (which expects a filesystem path).
    """
    fp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    try:
        json.dump(data, fp)
        fp.flush()
        fp.close()
        yield fp.name
    finally:
        try:
            os.unlink(fp.name)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint builders
# ─────────────────────────────────────────────────────────────────────────────

def build_spark_fingerprint_from_real_log() -> ExecutionFingerprint:
    """
    Build an ``ExecutionFingerprint`` from ``spark/spark_failure_spill.jsonl``.

    Signals present in that log
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - ``Spilling`` entries → 512 MB disk spill
    - ``FetchFailed`` → shuffle abort on stage 3
    - ``aborting job`` → 4 tasks failed
    - Executor ``ip-10-0-1-23`` evicted (OOM)
    """
    _ps = lambda **kw: PercentileStats(**kw)  # noqa: E731

    raw = load_demo_log("spark", "spark_failure_spill.jsonl")
    has_spill = "Spilling" in raw
    has_fetch = "FetchFailed" in raw
    has_abort = "aborting job" in raw

    return ExecutionFingerprint(
        metadata=FingerprintMetadata(
            fingerprint_schema_version="2.0.0",
            generated_at=datetime.now(timezone.utc),
            generator_version="demo-fixture",
            event_log_path="logs/test_fixtures/spark/spark_failure_spill.jsonl",
            event_log_size_bytes=len(raw.encode()),
            events_parsed=raw.count("\n"),
        ),
        semantic=SemanticFingerprint(
            dag=ExecutionDAG(
                stages=[
                    StageNode(
                        stage_id=3,
                        stage_name="shuffle_map_ohlcv",
                        num_partitions=8,
                        is_shuffle_stage=True,
                        rdd_name=None,
                        description="ShuffleMapStage for OHLCV pipeline — failed with FetchFailed",
                    ),
                ],
                edges=[],
                root_stage_ids=[3],
                leaf_stage_ids=[3],
                total_stages=1,
            ),
            physical_plan=None,
            logical_plan_hash=LogicalPlanHash(
                plan_hash="real-log-spill",
                plan_text="OHLCV shuffle stage — FetchFailed abort",
                is_sql=False,
            ),
            semantic_hash="real-log-spill-hash",
            description="Real spark log: spill + FetchFailed abort on stage 3",
            evidence_sources=[],
        ),
        context=ContextFingerprint(
            spark_config=SparkConfig(
                spark_version="3.5.1",
                scala_version=None,
                java_version=None,
                hadoop_version=None,
                app_name="ohlcv_spark_pipeline",
                master_url="k8s://https://kratos-spark-cluster",
                config_params={},
                description="K8s Spark cluster — kratos-spark-cluster",
            ),
            executor_config=ExecutorConfig(
                total_executors=3,
                executor_memory_mb=4096,
                executor_cores=2,
                driver_memory_mb=2048,
                driver_cores=1,
                description="3 executors — executor-3 on ip-10-0-1-23 evicted",
            ),
            submit_params=SubmitParameters(
                submit_time=datetime(2026, 2, 25, 9, 0, 0, tzinfo=timezone.utc),
                user=None,
                app_id="app-20260225090001-0001",
                queue=None,
                additional_params={},
            ),
            jvm_settings={},
            optimizations_enabled=[],
            description="Real-log context: k8s cluster under memory pressure",
            compliance_context=None,
            evidence_sources=[],
        ),
        metrics=MetricsFingerprint(
            execution_summary=ExecutionSummary(
                total_duration_ms=130_000,
                total_tasks=18,
                total_stages=1,
                total_input_bytes=0,
                total_output_bytes=0,
                total_shuffle_bytes=536_870_912,
                total_spill_bytes=536_870_912 if has_spill else 0,
                failed_task_count=4 if has_abort else 0,
                executor_loss_count=1 if has_fetch else 0,
                max_concurrent_tasks=8,
            ),
            stage_metrics=[],
            task_distribution=TaskMetricsDistribution(
                duration_ms=_ps(
                    min_val=100, p25=500, p50=2000, p75=8000, p99=60000,
                    max_val=70000, mean=5000, stddev=12000, count=18, outlier_count=4,
                ),
                input_bytes=_ps(
                    min_val=0, p25=0, p50=0, p75=0, p99=0,
                    max_val=0, mean=0, stddev=0, count=18, outlier_count=0,
                ),
                output_bytes=_ps(
                    min_val=0, p25=0, p50=0, p75=0, p99=0,
                    max_val=0, mean=0, stddev=0, count=18, outlier_count=0,
                ),
                shuffle_read_bytes=_ps(
                    min_val=0, p25=1024, p50=4096, p75=16384, p99=536_870_912,
                    max_val=536_870_912, mean=10240, stddev=50000, count=18, outlier_count=1,
                ),
                shuffle_write_bytes=_ps(
                    min_val=0, p25=1024, p50=4096, p75=16384, p99=536_870_912,
                    max_val=536_870_912, mean=10240, stddev=50000, count=18, outlier_count=1,
                ),
                spill_bytes=_ps(
                    min_val=0, p25=0, p50=0, p75=536_870_912, p99=536_870_912,
                    max_val=536_870_912, mean=268_435_456, stddev=268_435_456,
                    count=18, outlier_count=2,
                ),
            ),
            anomalies=[],
            key_performance_indicators={},
            description="Real log: 4 failed tasks, 512 MB spill, FetchFailed on executor-3",
            evidence_sources=[],
        ),
        execution_class="memory_bound",
        analysis_hints=(
            ["spill_detected", "fetch_failed", "executor_loss"] if has_fetch else []
        ),
    )


def build_airflow_fingerprint_from_real_log() -> Dict[str, Any]:
    """
    Build an Airflow fingerprint dict from ``airflow/airflow_retries_failure.log``.

    Signals present in that log
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - 3 attempts, 2× ``UP_FOR_RETRY``
    - ``All retries exhausted`` → final ``FAILED`` state
    - DAG: ``ohlcv_spark_pipeline``, task: ``load_ohlcv_prices``
    """
    raw = load_demo_log("airflow", "airflow_retries_failure.log")
    retry_count = raw.count("UP_FOR_RETRY")
    final_state = "failed" if "All retries exhausted" in raw else "success"
    log_lines = [line for line in raw.splitlines() if line.strip()]

    return {
        "dag_id":         "ohlcv_spark_pipeline",
        "task_id":        "load_ohlcv_prices",
        "execution_date": "2026-02-25T09:00:00+00:00",
        "try_number":     3,
        "max_retries":    3,
        "retry_count":    retry_count,
        "final_state":    final_state,
        "log_lines":      log_lines,
    }


def build_dq_fingerprint_from_real_log() -> Dict[str, Any]:
    """
    Build a data-quality fingerprint dict from ``data_quality/ohlcv_null_spike.log``.

    Signals present in that log
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - TSLA volume ``null_ratio`` 236× baseline
    - ``ANOMALY DETECTED`` marker
    - ``BigQueryTimeoutError`` on AMD symbol
    """
    raw = load_demo_log("data_quality", "ohlcv_null_spike.log")
    cols = [
        {"name": "symbol", "dtype": "object",  "null_rate": 0.00},
        {"name": "open",   "dtype": "float64", "null_rate": 0.00},
        {"name": "high",   "dtype": "float64", "null_rate": 0.0063,  "mean": 195.0},
        {"name": "low",    "dtype": "float64", "null_rate": 0.00,    "mean": 190.0},
        {"name": "close",  "dtype": "float64", "null_rate": 0.0056,  "mean": 192.0},
        {"name": "volume", "dtype": "int64",   "null_rate": 0.0236,  "mean": 38_000_000},
    ]
    baseline_cols = [
        {"name": "symbol", "dtype": "object",  "null_rate": 0.00},
        {"name": "open",   "dtype": "float64", "null_rate": 0.00},
        {"name": "high",   "dtype": "float64", "null_rate": 0.0003,  "mean": 193.0},
        {"name": "low",    "dtype": "float64", "null_rate": 0.00,    "mean": 188.0},
        {"name": "close",  "dtype": "float64", "null_rate": 0.0003,  "mean": 191.0},
        {"name": "volume", "dtype": "int64",   "null_rate": 0.0001,  "mean": 37_500_000},
    ]
    return {
        "dataset_name": "ohlcv_minute",
        "symbol":       "TSLA",
        "row_count":    1440,
        "columns":      cols,
        "has_anomaly":  "ANOMALY DETECTED" in raw,
        "has_timeout":  "BigQueryTimeoutError" in raw,
        "reference": {
            "dataset_name": "ohlcv_minute_baseline",
            "row_count":    1440,
            "columns":      baseline_cols,
        },
    }


def build_infra_fingerprint_from_real_log() -> Dict[str, Any]:
    """
    Build an infra fingerprint dict from ``infra/node_pressure_oom.log``.

    Signals present in that log
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - ``cpu=0.97``, ``mem_ratio=0.98`` → node ``ip-10-0-1-23``
    - OOM kill + pod evictions
    - Queue depth 1 200, Kafka consumer lag 152 340
    - Crash loop (``restart_count=4``)
    """
    raw = load_demo_log("infra", "node_pressure_oom.log")
    return {
        "cluster_id":             "kratos-spark-cluster",
        "environment":            "production",
        "node":                   "ip-10-0-1-23",
        "time_window":            "2026-02-25T09:00:00Z / 2026-02-25T09:35:00Z",
        "cpu_utilization":        97.0,
        "memory_utilization":     98.0,
        "disk_io_utilization":    99.0,
        "network_io_utilization": 45.0,
        "total_workers":          3,
        "available_workers":      0,
        "queued_tasks":           1200,
        "oom_kill_detected":      "out of memory" in raw,
        "pod_evictions":          raw.count("marked for termination"),
        "crash_loop_detected":    "crash loop backoff" in raw,
        "kafka_consumer_lag":     152_340,
        "autoscale_events":       [],
        "alert_count":            8,
        "error_count":            12,
    }
