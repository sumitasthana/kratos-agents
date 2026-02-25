"""
End-to-end smoke tests for all five Kratos analysis paths.

Each test has two layers:
  1. Direct-agent call — fast heuristic check, no LLM required.
  2. KratosOrchestrator.run — full pipeline integration check.

Run with:
    pytest tests/test_smoke_all_agents.py -v -s

Import paths rely on `pythonpath = ["src"]` in pyproject.toml (pytest 7+).
No sys.path manipulation is needed in this file.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from agents.airflow_log_analyzer import AirflowLogAnalyzerAgent
from agents.base import AgentType, LLMConfig
from agents.change_analyzer_agent import ChangeAnalyzerAgent
from agents.data_profiler_agent import DataProfilerAgent
from agents.infra_analyzer_agent import InfraAnalyzerAgent
from orchestrator import KratosOrchestrator, SparkOrchestrator
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

# Apply the asyncio mark to every test in this module (pytest-asyncio ≥ 0.23).
pytestmark = pytest.mark.asyncio(loop_scope="function")


# ─────────────────────────────────────────────────────────────────────────────
# Module-level Airflow log lines (shared by both Airflow helper and test)
# ─────────────────────────────────────────────────────────────────────────────

_AIRFLOW_LOG_LINES: List[str] = [
    "[2026-02-25, 10:15:00 +0000] {taskinstance.py:1332} INFO - Starting attempt 1 of 2",
    "[2026-02-25, 10:15:00 +0000] {taskinstance.py:1353} INFO - Executing"
    " <Task(PythonOperator): load_prices> on 2026-02-25 10:15:00+00:00",
    "[2026-02-25, 10:15:00 +0000] {taskinstance.py:1541} INFO - Running task instance:"
    " prices_dag.load_prices scheduled__2026-02-25T10:15:00+00:00 try_number 1",
    "[2026-02-25, 10:15:00 +0000] {standard_task_runner.py:55} INFO - Started process 21789 to run task",
    "[2026-02-25, 10:15:00 +0000] {standard_task_runner.py:82} INFO - Running:"
    " ['airflow', 'tasks', 'run', 'prices_dag', 'load_prices',"
    " '2026-02-25T10:15:00+00:00', '--job-id', '11234', '--pool', 'default_pool',"
    " '--raw', '--subdir', 'DAGS_FOLDER/prices_dag.py', '--cfg-path', '/tmp/tmpm8c1z9q0']",
    "[2026-02-25, 10:15:00 +0000] {standard_task_runner.py:83} INFO - Job 11234: Subtask load_prices",
    "[2026-02-25, 10:15:01 +0000] {logging_mixin.py:137} INFO - Running"
    " <TaskInstance: prices_dag.load_prices scheduled__2026-02-25T10:15:00+00:00 [running]>"
    " on host airflow-worker-0",
    "[2026-02-25, 10:15:01 +0000] {taskinstance.py:2607} INFO - Exporting env vars:"
    " AIRFLOW_CTX_DAG_ID=prices_dag AIRFLOW_CTX_TASK_ID=load_prices"
    " AIRFLOW_CTX_EXECUTION_DATE=2026-02-25T10:15:00+00:00"
    " AIRFLOW_CTX_DAG_RUN_ID=scheduled__2026-02-25T10:15:00+00:00",
    "[2026-02-25, 10:15:02 +0000] {logging_mixin.py:137} INFO - Importing DAG from DAGS_FOLDER/prices_dag.py",
    "[2026-02-25, 10:15:03 +0000] {logging_mixin.py:137} INFO - Downloading prices for symbol=NVDA date=2026-02-24",
    "[2026-02-25, 10:15:04 +0000] {logging_mixin.py:137} INFO - Requesting data from"
    " https://api.example.com/prices?symbol=NVDA&date=2026-02-24",
    "[2026-02-25, 10:15:05 +0000] {logging_mixin.py:137} INFO - Fetched 390 OHLCV records",
    "[2026-02-25, 10:15:05 +0000] {logging_mixin.py:137} INFO - Normalizing schema:"
    " timezone=America/New_York, freq=1min",
    "[2026-02-25, 10:15:06 +0000] {logging_mixin.py:137} INFO - Writing data to"
    " s3://quant-data/prices/nvda/2026-02-24.parquet",
    "[2026-02-25, 10:15:07 +0000] {logging_mixin.py:137} INFO - Successfully wrote"
    " 390 rows (390 inserts, 0 updates)",
    "[2026-02-25, 10:15:07 +0000] {python.py:179} INFO - Done. Returned value:"
    " {'rows': 390, 'symbol': 'NVDA', 'date': '2026-02-24'}",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2100} INFO - Marking task as SUCCESS."
    " dag_id=prices_dag, task_id=load_prices, execution_date=2026-02-25 10:15:00+00:00",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2151} INFO - 1 downstream tasks"
    " scheduled from follow-on schedule check",
    "[2026-02-25, 10:15:07 +0000] {local_task_job.py:222} INFO - Task exited with return code 0",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2741} INFO - 0 rows deleted from"
    " task_reschedule for task 'load_prices'",
    "[2026-02-25, 10:15:07 +0000] {taskinstance.py:2793} INFO - Finished task:"
    " prices_dag.load_prices scheduled__2026-02-25T10:15:00+00:00",
]


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint builders (public so wrappers / other tests can re-use them)
# ─────────────────────────────────────────────────────────────────────────────

def build_spark_execution_fingerprint() -> ExecutionFingerprint:
    """
    Happy-path Spark job: 2 stages, zero task failures, minimal shuffle spill.
    Matches the values carried over from the original smoke_test.py.
    """
    _ps = lambda **kw: PercentileStats(**kw)  # noqa: E731  (local brevity alias)

    return ExecutionFingerprint(
        metadata=FingerprintMetadata(
            fingerprint_schema_version="2.0.0",
            generated_at=datetime.now(timezone.utc),
            generator_version="smoke-test",
            event_log_path="dummy",
            event_log_size_bytes=1234,
            events_parsed=10,
        ),
        semantic=SemanticFingerprint(
            dag=ExecutionDAG(
                stages=[
                    StageNode(
                        stage_id=0,
                        stage_name="read_customers",
                        num_partitions=4,
                        is_shuffle_stage=False,
                        rdd_name=None,
                        description="Read customers parquet",
                    ),
                    StageNode(
                        stage_id=1,
                        stage_name="join_orders",
                        num_partitions=4,
                        is_shuffle_stage=True,
                        rdd_name=None,
                        description="Join customers with orders and aggregate by region",
                    ),
                ],
                edges=[
                    DAGEdge(
                        from_stage_id=0,
                        to_stage_id=1,
                        shuffle_required=True,
                        reason="join",
                    )
                ],
                root_stage_ids=[0],
                leaf_stage_ids=[1],
                total_stages=2,
            ),
            physical_plan=None,
            logical_plan_hash=LogicalPlanHash(
                plan_hash="dummy",
                plan_text="SELECT region, count(*) FROM customers JOIN orders ...",
                is_sql=True,
            ),
            semantic_hash="dummy-semantic",
            description="Join customers and orders then aggregate by region",
            evidence_sources=[],
        ),
        context=ContextFingerprint(
            spark_config=SparkConfig(
                spark_version="3.4.0",
                scala_version=None,
                java_version=None,
                hadoop_version=None,
                app_name="smoke-test",
                master_url="local[*]",
                config_params={},
                description="Local Spark config for smoke test",
            ),
            executor_config=ExecutorConfig(
                total_executors=2,
                executor_memory_mb=4096,
                executor_cores=2,
                driver_memory_mb=2048,
                driver_cores=2,
                description="2 executors × 4 GB × 2 cores",
            ),
            submit_params=SubmitParameters(
                submit_time=datetime.now(timezone.utc),
                user=None,
                app_id="app-smoke",
                queue=None,
                additional_params={},
            ),
            jvm_settings={},
            optimizations_enabled=[],
            description="Local test context",
            compliance_context=None,
            evidence_sources=[],
        ),
        metrics=MetricsFingerprint(
            execution_summary=ExecutionSummary(
                total_duration_ms=120_000,
                total_tasks=100,
                total_stages=2,
                total_input_bytes=10_000_000,
                total_output_bytes=1_000_000,
                total_shuffle_bytes=5_000_000,
                total_spill_bytes=0,
                failed_task_count=0,
                executor_loss_count=0,
                max_concurrent_tasks=16,
            ),
            stage_metrics=[],
            task_distribution=TaskMetricsDistribution(
                duration_ms=_ps(min_val=10, p25=20, p50=30, p75=40, p99=80,
                                max_val=100, mean=35, stddev=5, count=100, outlier_count=2),
                input_bytes=_ps(min_val=100, p25=200, p50=300, p75=400, p99=800,
                                max_val=1000, mean=350, stddev=50, count=100, outlier_count=2),
                output_bytes=_ps(min_val=50, p25=100, p50=150, p75=200, p99=400,
                                 max_val=500, mean=160, stddev=30, count=100, outlier_count=1),
                shuffle_read_bytes=_ps(min_val=0, p25=0, p50=0, p75=10, p99=100,
                                       max_val=200, mean=5, stddev=20, count=100, outlier_count=1),
                shuffle_write_bytes=_ps(min_val=0, p25=0, p50=0, p75=10, p99=100,
                                        max_val=200, mean=5, stddev=20, count=100, outlier_count=1),
                spill_bytes=_ps(min_val=0, p25=0, p50=0, p75=0, p99=0,
                                max_val=0, mean=0, stddev=0, count=100, outlier_count=0),
            ),
            anomalies=[],
            key_performance_indicators={},
            description="Completed in 120 s with no failures",
            evidence_sources=[],
        ),
        execution_class="cpu_bound",
        analysis_hints=[],
    )


def build_airflow_fingerprint() -> Dict[str, Any]:
    """
    Successful Airflow task fingerprint.
    Uses the shared _AIRFLOW_LOG_LINES captured from a real prices_dag run.
    """
    return {
        "dag_id":         "prices_dag",
        "task_id":        "load_prices",
        "execution_date": "2026-02-25T10:15:00+00:00",
        "try_number":     1,
        "max_retries":    2,
        "log_lines":      _AIRFLOW_LOG_LINES,
    }


def build_data_fingerprint() -> Dict[str, Any]:
    """
    Happy-path data profile: NVDA minute-bar parquet.
    Low null rates, tight schema, baseline present for drift comparison.
    """
    cols = [
        {"name": "symbol", "dtype": "object",  "null_rate": 0.00},
        {"name": "date",   "dtype": "object",  "null_rate": 0.00},
        {"name": "open",   "dtype": "float64", "null_rate": 0.00, "mean": 125.3},
        {"name": "high",   "dtype": "float64", "null_rate": 0.00, "mean": 127.1},
        {"name": "low",    "dtype": "float64", "null_rate": 0.00, "mean": 123.8},
        {"name": "close",  "dtype": "float64", "null_rate": 0.01, "mean": 126.0},
        {"name": "volume", "dtype": "int64",   "null_rate": 0.00, "mean": 4_200_000},
    ]
    baseline_cols = [
        {"name": "symbol", "dtype": "object",  "null_rate": 0.00},
        {"name": "date",   "dtype": "object",  "null_rate": 0.00},
        {"name": "open",   "dtype": "float64", "null_rate": 0.00, "mean": 124.9},
        {"name": "high",   "dtype": "float64", "null_rate": 0.00, "mean": 126.5},
        {"name": "low",    "dtype": "float64", "null_rate": 0.00, "mean": 123.2},
        {"name": "close",  "dtype": "float64", "null_rate": 0.00, "mean": 125.5},
        {"name": "volume", "dtype": "int64",   "null_rate": 0.00, "mean": 4_100_000},
    ]
    return {
        "dataset_name": "prices_daily",
        "row_count":    390,
        "columns":      cols,
        "reference": {
            "dataset_name": "prices_daily_baseline",
            "row_count":    385,
            "columns":      baseline_cols,
        },
    }


def build_change_fingerprint() -> Dict[str, Any]:
    """
    Low-churn git snapshot: single author, small diffs, no hotspot files.
    A reference window is included for churn-delta comparison.
    """
    return {
        "repo_name":   "prices-etl",
        "window_days": 7,
        "commits": [
            {
                "hash":      "abc123",
                "author":    "alice",
                "timestamp": "2026-02-24T09:00:00Z",
                "files": [
                    {"path": "etl/normalize.py", "added": 12, "deleted": 3},
                ],
            },
            {
                "hash":      "def456",
                "author":    "alice",
                "timestamp": "2026-02-23T14:30:00Z",
                "files": [
                    {"path": "etl/load.py", "added": 5, "deleted": 1},
                ],
            },
        ],
        "reference": {
            "window_days": 7,
            "commits": [
                {
                    "hash":      "old001",
                    "author":    "alice",
                    "timestamp": "2026-02-17T10:00:00Z",
                    "files": [
                        {"path": "etl/normalize.py", "added": 8, "deleted": 2},
                    ],
                },
            ],
        },
    }


def build_infra_fingerprint() -> Dict[str, Any]:
    """
    Resource-pressured production cluster snapshot.
    CPU 87.5 % (>85 → HIGH), Memory 91 % (near 92 CRITICAL),
    only 40 % workers free, 310 queued tasks (>200 → HIGH),
    autoscaler scaled *down* while under load.
    """
    return {
        "cluster_id":             "prod-spark-01",
        "environment":            "production",
        "time_window":            "2026-02-25T08:00:00Z / 2026-02-25T09:00:00Z",
        "cpu_utilization":        87.5,   # above HIGH threshold (85 %)
        "memory_utilization":     91.0,   # near CRITICAL threshold (92 %)
        "disk_io_utilization":    62.0,
        "network_io_utilization": 45.0,
        "total_workers":          20,
        "available_workers":       8,    # 40 % free → HIGH
        "queued_tasks":           310,   # > 200 → HIGH
        "autoscale_events": [
            {"direction": "down", "delta": 4, "timestamp": "2026-02-25T08:30:00Z"},
        ],
        "alert_count":  6,
        "error_count": 14,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: write a fingerprint dict to a temp JSON file for orchestrators that
# expect a file path (DataProfilerOrchestrator, ChangeAnalyzerOrchestrator).
# ─────────────────────────────────────────────────────────────────────────────

class _TempJsonFile:
    """Context manager that writes a dict to a NamedTemporaryFile as JSON."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data
        self._path: str = ""

    def __enter__(self) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(self._data, f)
            self._path = f.name
        return self._path

    def __exit__(self, *_: object) -> None:
        try:
            os.unlink(self._path)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. Spark
# ─────────────────────────────────────────────────────────────────────────────

async def test_spark_smoke_happy_path() -> None:
    """
    Happy-path Spark job with no failures.

    Direct: SparkOrchestrator.solve_problem — expects a populated AnalysisResult.
    Orchestrator: not directly applicable (SparkOrchestrator is standalone);
                  KratosOrchestrator routing with execution_fingerprint instead.
    """
    fingerprint = build_spark_execution_fingerprint()
    orchestrator = SparkOrchestrator(
        fingerprint=fingerprint,
        llm_config=LLMConfig(model="gpt-4.1", temperature=0.2, max_tokens=1024),
    )

    result = await orchestrator.solve_problem(
        user_query="What does this job do and what is the overall health?"
    )

    print("\n=== Spark – SparkOrchestrator ===")
    print("problem_type     :", result.problem_type)
    print("health_score     :", result.health_score)
    print("executive_summary:", (result.executive_summary or "")[:120])
    print("findings         :", len(result.findings))

    assert result.problem_type is not None, "problem_type must be set"
    assert result.executive_summary, "executive_summary must not be empty"
    assert len(result.findings) > 0, "expected at least one finding"
    assert result.health_score is not None, "health_score must be set"

    # ── Kratos integration path ───────────────────────────────────────────────
    report = await KratosOrchestrator().run(
        user_query="Diagnose this Spark execution",
        execution_fingerprint=fingerprint,
    )
    ip = report.issue_profile

    print("\n=== Spark – KratosOrchestrator ===")
    print("dominant_problem_type:", ip.dominant_problem_type)
    print("overall_health_score :", ip.overall_health_score)
    print("executive_summary    :", (report.executive_summary or "")[:120])

    assert ip.dominant_problem_type is not None, "dominant_problem_type must be set"
    assert report.executive_summary, "executive_summary must not be empty"
    assert ip.overall_health_score is not None, "overall_health_score must be set"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Airflow
# ─────────────────────────────────────────────────────────────────────────────

async def test_airflow_smoke_happy_path() -> None:
    """
    Successful Airflow task log: task exited with return code 0, marked SUCCESS.

    Direct: AirflowLogAnalyzerAgent.analyze — expects success=True, summary mentions SUCCESS.
    Orchestrator: KratosOrchestrator — expects HEALTHY dominant problem type.
    """
    fp = build_airflow_fingerprint()

    # ── Direct agent ──────────────────────────────────────────────────────────
    agent = AirflowLogAnalyzerAgent()
    resp = await agent.analyze(fingerprint_data=fp)

    print("\n=== Airflow – AirflowLogAnalyzerAgent ===")
    print("success :", resp.success)
    print("summary :", resp.summary)
    print("findings:", len(resp.key_findings))
    for kf in resp.key_findings[:3]:
        print(" -", kf)

    assert resp.success is True, f"Agent reported failure: {resp.summary}"
    assert resp.summary, "summary must not be empty"
    assert (
        "SUCCESS" in resp.summary.upper() or "healthy" in resp.summary.lower()
    ), f"Expected success indicator in summary, got: {resp.summary!r}"

    # ── KratosOrchestrator ────────────────────────────────────────────────────
    report = await KratosOrchestrator().run(
        user_query="Check Airflow task health and behaviour",
        airflow_fingerprint=fp,
    )
    ip = report.issue_profile

    print("\n=== Airflow – KratosOrchestrator ===")
    print("dominant_problem_type:", ip.dominant_problem_type)
    print("overall_health_score :", ip.overall_health_score)
    print("executive_summary    :", (report.executive_summary or "")[:120])

    assert ip.dominant_problem_type.name == "HEALTHY", (
        f"Expected HEALTHY, got {ip.dominant_problem_type}"
    )
    assert ip.overall_health_score >= 0.8, (
        f"Expected health ≥ 0.8, got {ip.overall_health_score}"
    )
    assert report.executive_summary, "executive_summary must not be empty"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Data Profiler
# ─────────────────────────────────────────────────────────────────────────────

async def test_data_profiler_smoke_happy_path() -> None:
    """
    Low null-rate dataset with a near-identical baseline → no significant drift.

    Direct: DataProfilerAgent.analyze (sync) — expects success, non-empty findings.
    Orchestrator: KratosOrchestrator via dataset_path (DataProfilerOrchestrator
                  is currently a stub; asserts focus on structural correctness).
    """
    fp = build_data_fingerprint()

    # ── Direct agent ──────────────────────────────────────────────────────────
    agent = DataProfilerAgent()
    resp = agent.analyze(fingerprint_data=fp)  # sync

    print("\n=== Data Profiler – DataProfilerAgent ===")
    print("success :", resp.success)
    print("summary :", resp.summary)
    print("findings:", len(resp.key_findings))
    for kf in resp.key_findings[:3]:
        print(" -", kf)

    assert resp.success is True, f"Agent reported failure: {resp.summary}"
    assert resp.summary, "summary must not be empty"
    assert len(resp.key_findings) > 0, "expected at least one key finding"

    # ── KratosOrchestrator ────────────────────────────────────────────────────
    # DataProfilerOrchestrator reads from a JSON file path.
    with _TempJsonFile(fp) as tmp_path:
        report = await KratosOrchestrator().run(
            user_query="Assess data quality of the prices_daily dataset",
            dataset_path=tmp_path,
        )

    ip = report.issue_profile

    print("\n=== Data Profiler – KratosOrchestrator ===")
    print("dominant_problem_type:", ip.dominant_problem_type)
    print("overall_health_score :", ip.overall_health_score)
    if ip.data_analysis:
        print("data health_score    :", ip.data_analysis.health_score)
        print("data problem_type    :", ip.data_analysis.problem_type)

    assert ip.dominant_problem_type is not None, "dominant_problem_type must be set"
    assert ip.overall_health_score is not None, "overall_health_score must be set"
    assert report.executive_summary, "executive_summary must not be empty"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Change Analyzer
# ─────────────────────────────────────────────────────────────────────────────

async def test_change_analyzer_smoke_happy_path() -> None:
    """
    Low-churn git activity: single author, small diffs, mild delta vs baseline.

    Direct: ChangeAnalyzerAgent.analyze (sync) — expects success, non-empty findings.
    Orchestrator: KratosOrchestrator via git_log_path.
    """
    fp = build_change_fingerprint()

    # ── Direct agent ──────────────────────────────────────────────────────────
    agent = ChangeAnalyzerAgent()
    resp = agent.analyze(fingerprint_data=fp)  # sync

    print("\n=== Change Analyzer – ChangeAnalyzerAgent ===")
    print("success :", resp.success)
    print("summary :", resp.summary)
    print("findings:", len(resp.key_findings))
    for kf in resp.key_findings[:3]:
        print(" -", kf)

    assert resp.success is True, f"Agent reported failure: {resp.summary}"
    assert resp.summary, "summary must not be empty"
    assert len(resp.key_findings) > 0, "expected at least one key finding"

    # ── KratosOrchestrator ────────────────────────────────────────────────────
    # ChangeAnalyzerOrchestrator reads a JSON git-log file.
    with _TempJsonFile(fp) as tmp_path:
        report = await KratosOrchestrator().run(
            user_query="Did recent git changes introduce a regression?",
            git_log_path=tmp_path,
        )

    ip = report.issue_profile

    print("\n=== Change Analyzer – KratosOrchestrator ===")
    print("dominant_problem_type:", ip.dominant_problem_type)
    print("overall_health_score :", ip.overall_health_score)
    if ip.change_analysis:
        print("change health_score  :", ip.change_analysis.health_score)
        print("change problem_type  :", ip.change_analysis.problem_type)

    assert ip.dominant_problem_type is not None, "dominant_problem_type must be set"
    assert ip.overall_health_score is not None, "overall_health_score must be set"
    assert report.executive_summary, "executive_summary must not be empty"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Infra Analyzer
# ─────────────────────────────────────────────────────────────────────────────

async def test_infra_smoke_happy_path() -> None:
    """
    Resource-pressured cluster: CPU 87.5 %, Memory 91 %, 310 queued tasks.
    This is NOT a clean-health scenario — it exercises the HIGH severity path.

    Direct: InfraAnalyzerAgent.analyze (sync) — expects HIGH/CRITICAL severity.
    Orchestrator: KratosOrchestrator — infra_analysis must be populated, health < 100.
    """
    fp = build_infra_fingerprint()

    # ── Direct agent ──────────────────────────────────────────────────────────
    agent = InfraAnalyzerAgent()
    resp = agent.analyze(fingerprint_data=fp)  # sync

    print("\n=== Infra Analyzer – InfraAnalyzerAgent ===")
    print("success      :", resp.success)
    print("summary      :", resp.summary)
    print("severity     :", (resp.metadata or {}).get("severity", "—"))
    print("health_label :", (resp.metadata or {}).get("health_label", "—"))
    print("findings     :", len(resp.key_findings))
    for kf in resp.key_findings[:3]:
        print(" -", kf)

    assert resp.success is True, f"Agent reported failure: {resp.summary}"
    assert resp.summary, "summary must not be empty"
    assert len(resp.key_findings) > 0, "expected at least one key finding"
    assert resp.metadata is not None, "metadata must be populated"
    assert resp.metadata.get("severity") in {"high", "critical"}, (
        f"Expected HIGH or CRITICAL for a pressured cluster, "
        f"got: {resp.metadata.get('severity')!r}"
    )

    # ── KratosOrchestrator ────────────────────────────────────────────────────
    report = await KratosOrchestrator().run(
        user_query="Why is the cluster performing poorly?",
        trigger="infra_check",
        infra_fingerprint=fp,
    )
    ip = report.issue_profile

    print("\n=== Infra Analyzer – KratosOrchestrator ===")
    print("dominant_problem_type:", ip.dominant_problem_type)
    print("overall_health_score :", ip.overall_health_score)
    print("correlations         :", len(ip.correlations))
    if ip.infra_analysis:
        print("infra health_score   :", ip.infra_analysis.health_score)
        print("infra problem_type   :", ip.infra_analysis.problem_type)

    assert ip.infra_analysis is not None, (
        "infra_analysis must be populated when infra_fingerprint is supplied"
    )
    assert ip.infra_analysis.health_score < 100, (
        f"Pressured cluster must not score 100, got {ip.infra_analysis.health_score}"
    )
    assert report.executive_summary, "executive_summary must not be empty"
    assert ip.dominant_problem_type is not None, "dominant_problem_type must be set"
