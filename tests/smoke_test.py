import asyncio
from datetime import datetime, timezone

import pytest

from agents.base import LLMConfig
from orchestrator import SparkOrchestrator
from schemas import (
    ExecutionFingerprint,
    FingerprintMetadata,
    SemanticFingerprint,
    ExecutionDAG,
    StageNode,
    DAGEdge,
    LogicalPlanHash,
    ContextFingerprint,
    SparkConfig,
    ExecutorConfig,
    SubmitParameters,
    MetricsFingerprint,
    ExecutionSummary,
    TaskMetricsDistribution,
    PercentileStats,
)


def build_fingerprint() -> ExecutionFingerprint:
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
                        description=(
                            "Join customers with orders and aggregate by region"
                        ),
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
            description=(
                "Join customers and orders then aggregate by region"
            ),
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
                duration_ms=PercentileStats(
                    min_val=10,
                    p25=20,
                    p50=30,
                    p75=40,
                    p99=80,
                    max_val=100,
                    mean=35,
                    stddev=5,
                    count=100,
                    outlier_count=2,
                ),
                input_bytes=PercentileStats(
                    min_val=100,
                    p25=200,
                    p50=300,
                    p75=400,
                    p99=800,
                    max_val=1000,
                    mean=350,
                    stddev=50,
                    count=100,
                    outlier_count=2,
                ),
                output_bytes=PercentileStats(
                    min_val=50,
                    p25=100,
                    p50=150,
                    p75=200,
                    p99=400,
                    max_val=500,
                    mean=160,
                    stddev=30,
                    count=100,
                    outlier_count=1,
                ),
                shuffle_read_bytes=PercentileStats(
                    min_val=0,
                    p25=0,
                    p50=0,
                    p75=10,
                    p99=100,
                    max_val=200,
                    mean=5,
                    stddev=20,
                    count=100,
                    outlier_count=1,
                ),
                shuffle_write_bytes=PercentileStats(
                    min_val=0,
                    p25=0,
                    p50=0,
                    p75=10,
                    p99=100,
                    max_val=200,
                    mean=5,
                    stddev=20,
                    count=100,
                    outlier_count=1,
                ),
                spill_bytes=PercentileStats(
                    min_val=0,
                    p25=0,
                    p50=0,
                    p75=0,
                    p99=0,
                    max_val=0,
                    mean=0,
                    stddev=0,
                    count=100,
                    outlier_count=0,
                ),
            ),
            anomalies=[],
            key_performance_indicators={},
            description="Completed in 120s with no failures",
            evidence_sources=[],
        ),
        execution_class="cpu_bound",
        analysis_hints=[],
    )


@pytest.mark.asyncio
async def test_spark_smoke_happy_path() -> None:
    fingerprint = build_fingerprint()

    llm_config = LLMConfig(
        model="gpt-4.1",
        temperature=0.2,
        max_tokens=1024,
    )

    orchestrator = SparkOrchestrator(
        fingerprint=fingerprint,
        llm_config=llm_config,
    )

    result = await orchestrator.solve_problem(
        user_query="What does this job do and analyze this?"
    )

    # Basic sanity checks rather than just printing
    assert result.problem_type is not None
    assert result.executive_summary
    assert len(result.findings) > 0
if __name__ == "__main__":
    asyncio.run(test_spark_smoke_happy_path())
