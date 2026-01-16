"""
Metrics Layer Generator

Collects task/stage metrics, computes statistics, detects anomalies.
"""

import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from src.schemas import (
    AnomalyEvent,
    ExecutionSummary,
    MetricsFingerprint,
    PercentileStats,
    StageMetrics,
    TaskMetricsDistribution,
)
from src.parser import EventIndex


class MetricsFingerprintGenerator:
    """
    Generates metrics fingerprint (performance characteristics, statistics, anomalies).
    Used for regression detection and similarity comparison.
    """

    def __init__(self, events_index: EventIndex):
        self.index = events_index
        self.events = events_index.events

    def generate(self) -> MetricsFingerprint:
        """
        Generate complete metrics fingerprint from event log.

        Returns:
            MetricsFingerprint with execution summary, stage metrics, and anomalies
        """
        logger.info("[METRICS] Collecting task-level metrics from TaskEnd events...")
        # Collect task metrics
        task_metrics = self._collect_task_metrics()
        logger.info(f"[METRICS] Collected metrics for {len(task_metrics)} tasks")

        logger.info("[METRICS] Computing execution summary...")
        # Compute execution summary
        exec_summary = self._compute_execution_summary(task_metrics)
        logger.info(f"[METRICS] Duration: {exec_summary.total_duration_ms}ms, Failed: {exec_summary.failed_task_count}, Spill: {exec_summary.total_spill_bytes:,} bytes")

        logger.info("[METRICS] Computing per-stage metrics...")
        # Compute per-stage metrics
        stage_metrics = self._compute_stage_metrics(task_metrics)
        logger.info(f"[METRICS] Computed metrics for {len(stage_metrics)} stages")

        logger.info("[METRICS] Computing task distribution statistics...")
        # Compute task distribution
        task_dist = self._compute_task_distribution(task_metrics)

        logger.info("[METRICS] Running anomaly detection...")
        # Detect anomalies
        anomalies = self._detect_anomalies(task_metrics, stage_metrics)
        if anomalies:
            logger.warning(f"[METRICS] Detected {len(anomalies)} anomalies:")
            for anomaly in anomalies:
                logger.warning(f"[METRICS]   - [{anomaly.severity.upper()}] {anomaly.anomaly_type}: {anomaly.description[:60]}")
        else:
            logger.info("[METRICS] No anomalies detected")

        logger.info("[METRICS] Computing KPIs...")
        # Compute KPIs
        kpis = self._compute_kpis(exec_summary, task_metrics)
        for kpi_name, kpi_value in kpis.items():
            logger.info(f"[METRICS]   - {kpi_name}: {kpi_value:.2f}")

        # Generate description
        description = self._generate_description(exec_summary, anomalies)

        # Collect evidence
        evidence = self._collect_evidence()

        return MetricsFingerprint(
            execution_summary=exec_summary,
            stage_metrics=stage_metrics,
            task_distribution=task_dist,
            anomalies=anomalies,
            key_performance_indicators=kpis,
            description=description,
            evidence_sources=evidence,
        )

    def _collect_task_metrics(self) -> Dict[int, Dict[str, Any]]:
        """
        Collect metrics for each task from TaskEnd events.

        Returns:
            Dict mapping task_id -> {stage_id, duration_ms, input_bytes, output_bytes, ...}
        """
        task_metrics = {}

        for event in self.index.get_by_type("SparkListenerTaskEnd"):
            task_info = event.get("Task Info", {})
            task_metrics_obj = event.get("Task Metrics", {})
            # Task ID can be at top level or nested in Task Info
            task_id = event.get("Task ID") or (task_info.get("Task ID") if task_info else None)
            stage_id = event.get("Stage ID")

            if task_id is not None:
                duration_ms = task_info.get("Duration", 0) if task_info else 0
                launch_time = task_info.get("Launch Time", 0) if task_info else 0
                finish_time = task_info.get("Finish Time", 0) if task_info else 0

                # Recompute duration if available
                if launch_time and finish_time:
                    duration_ms = finish_time - launch_time

                task_metrics[task_id] = {
                    "stage_id": stage_id,
                    "duration_ms": duration_ms,
                    "input_bytes": task_metrics_obj.get("Input Bytes Read", 0) if task_metrics_obj else 0,
                    "output_bytes": task_metrics_obj.get("Output Bytes", 0) if task_metrics_obj else 0,
                    "shuffle_read_bytes": task_metrics_obj.get("Shuffle Read Bytes", 0) if task_metrics_obj else 0,
                    "shuffle_write_bytes": task_metrics_obj.get("Shuffle Write Bytes", 0) if task_metrics_obj else 0,
                    "spill_bytes": (
                        task_metrics_obj.get("Disk Bytes Spilled", 0)
                        + task_metrics_obj.get("Memory Bytes Spilled", 0)
                        if task_metrics_obj
                        else 0
                    ),
                    "status": task_info.get("Status", "UNKNOWN") if task_info else "UNKNOWN",
                    "failed": task_info.get("Failed", False) if task_info else False,
                }

        return task_metrics

    def _compute_execution_summary(self, task_metrics: Dict[int, Dict[str, Any]]) -> ExecutionSummary:
        """Compute high-level execution summary."""
        if not task_metrics:
            return ExecutionSummary(
                total_duration_ms=0,
                total_tasks=0,
                total_stages=0,
                total_input_bytes=0,
                total_output_bytes=0,
                total_shuffle_bytes=0,
                total_spill_bytes=0,
                failed_task_count=0,
                executor_loss_count=0,
                max_concurrent_tasks=0,
            )

        # Total duration: max finish time - min launch time
        app_start = self.index.get_by_type("SparkListenerApplicationStart")
        app_end = self.index.get_by_type("SparkListenerApplicationEnd")

        total_duration_ms = 0
        if app_start and app_end:
            start_time = app_start[0].get("Timestamp", 0)
            end_time = app_end[0].get("Timestamp", 0)
            total_duration_ms = int(end_time - start_time)

        # Task counts
        total_tasks = len(task_metrics)
        failed_tasks = sum(1 for m in task_metrics.values() if m.get("failed", False))

        # Bytes
        total_input = sum(m.get("input_bytes", 0) for m in task_metrics.values())
        total_output = sum(m.get("output_bytes", 0) for m in task_metrics.values())
        total_shuffle_read = sum(m.get("shuffle_read_bytes", 0) for m in task_metrics.values())
        total_shuffle_write = sum(m.get("shuffle_write_bytes", 0) for m in task_metrics.values())
        total_shuffle = total_shuffle_read + total_shuffle_write
        total_spill = sum(m.get("spill_bytes", 0) for m in task_metrics.values())

        # Stage count
        stage_ids = set(m.get("stage_id") for m in task_metrics.values() if m.get("stage_id") is not None)
        total_stages = len(stage_ids)

        # Executor losses
        executor_losses = len(self.index.get_by_type("SparkListenerExecutorMetricsUpdate"))

        # Max concurrent tasks (approximate from stage info)
        max_concurrent = max(
            (stage_info.get("Number of Tasks", 0) for stage_info in
             [e.get("Stage Info", {}) for e in self.index.get_by_type("SparkListenerStageSubmitted")]),
            default=1
        )

        return ExecutionSummary(
            total_duration_ms=total_duration_ms,
            total_tasks=total_tasks,
            total_stages=total_stages,
            total_input_bytes=total_input,
            total_output_bytes=total_output,
            total_shuffle_bytes=total_shuffle,
            total_spill_bytes=total_spill,
            failed_task_count=failed_tasks,
            executor_loss_count=executor_losses,
            max_concurrent_tasks=max_concurrent,
        )

    def _compute_stage_metrics(self, task_metrics: Dict[int, Dict[str, Any]]) -> List[StageMetrics]:
        """Compute aggregated metrics for each stage."""
        stage_tasks: Dict[int, List[Dict[str, Any]]] = {}

        # Group tasks by stage
        for task_id, metrics in task_metrics.items():
            stage_id = metrics.get("stage_id")
            if stage_id is not None:
                if stage_id not in stage_tasks:
                    stage_tasks[stage_id] = []
                stage_tasks[stage_id].append(metrics)

        stage_metrics_list = []

        for stage_id, tasks in sorted(stage_tasks.items()):
            if not tasks:
                continue

            num_tasks = len(tasks)
            failed = sum(1 for t in tasks if t.get("failed", False))

            # Task duration distribution for this stage
            durations = [t.get("duration_ms", 0) for t in tasks]
            task_duration_stats = self._compute_percentiles(durations)

            # Bytes
            input_bytes = sum(t.get("input_bytes", 0) for t in tasks)
            output_bytes = sum(t.get("output_bytes", 0) for t in tasks)
            shuffle_read = sum(t.get("shuffle_read_bytes", 0) for t in tasks)
            shuffle_write = sum(t.get("shuffle_write_bytes", 0) for t in tasks)
            spill = sum(t.get("spill_bytes", 0) for t in tasks)

            # Partition count (from stage info if available)
            partition_count = num_tasks  # Conservative estimate

            stage_metrics_list.append(
                StageMetrics(
                    stage_id=stage_id,
                    num_tasks=num_tasks,
                    num_failed_tasks=failed,
                    task_duration_ms=task_duration_stats,
                    input_bytes=input_bytes,
                    output_bytes=output_bytes,
                    shuffle_read_bytes=shuffle_read,
                    shuffle_write_bytes=shuffle_write,
                    spill_bytes=spill,
                    partition_count=partition_count,
                )
            )

        return stage_metrics_list

    def _compute_task_distribution(self, task_metrics: Dict[int, Dict[str, Any]]) -> TaskMetricsDistribution:
        """Compute distribution of task metrics across all tasks."""
        durations = [m.get("duration_ms", 0) for m in task_metrics.values()]
        input_bytes_list = [m.get("input_bytes", 0) for m in task_metrics.values()]
        output_bytes_list = [m.get("output_bytes", 0) for m in task_metrics.values()]
        shuffle_read_list = [m.get("shuffle_read_bytes", 0) for m in task_metrics.values()]
        shuffle_write_list = [m.get("shuffle_write_bytes", 0) for m in task_metrics.values()]
        spill_list = [m.get("spill_bytes", 0) for m in task_metrics.values()]

        return TaskMetricsDistribution(
            duration_ms=self._compute_percentiles(durations),
            input_bytes=self._compute_percentiles(input_bytes_list),
            output_bytes=self._compute_percentiles(output_bytes_list),
            shuffle_read_bytes=self._compute_percentiles(shuffle_read_list),
            shuffle_write_bytes=self._compute_percentiles(shuffle_write_list),
            spill_bytes=self._compute_percentiles(spill_list),
        )

    def _compute_percentiles(self, values: List[float]) -> PercentileStats:
        """Compute percentile statistics for a list of values."""
        if not values:
            return PercentileStats(
                min_val=0, p25=0, p50=0, p75=0, p99=0, max_val=0, mean=0, stddev=0, count=0, outlier_count=0
            )

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            index = int((p / 100.0) * (n - 1))
            return sorted_vals[min(index, n - 1)]

        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n if n > 1 else 0
        stddev = variance ** 0.5

        # Count outliers (beyond ±2σ)
        outlier_count = sum(1 for x in values if abs(x - mean) > 2 * stddev)

        return PercentileStats(
            min_val=float(sorted_vals[0]),
            p25=percentile(25),
            p50=percentile(50),
            p75=percentile(75),
            p99=percentile(99),
            max_val=float(sorted_vals[-1]),
            mean=mean,
            stddev=stddev,
            count=n,
            outlier_count=outlier_count,
        )

    def _detect_anomalies(
        self, task_metrics: Dict[int, Dict[str, Any]], stage_metrics: List[StageMetrics]
    ) -> List[AnomalyEvent]:
        """Detect performance anomalies for LLM focus."""
        anomalies = []

        # Check for task failures
        failed_tasks = [tid for tid, m in task_metrics.items() if m.get("failed", False)]
        if failed_tasks:
            anomalies.append(
                AnomalyEvent(
                    anomaly_type="task_failures",
                    severity="high" if len(failed_tasks) > 5 else "medium",
                    description=f"{len(failed_tasks)} task(s) failed",
                    affected_tasks=failed_tasks[:10],
                    evidence={"failure_count": len(failed_tasks)},
                )
            )

        # Check for skewed stages (high variance in task duration)
        for stage_metric in stage_metrics:
            duration_dist = stage_metric.task_duration_ms
            if duration_dist.max_val > 0:
                skew_ratio = duration_dist.max_val / max(duration_dist.p50, 1)
                if skew_ratio > 10:
                    anomalies.append(
                        AnomalyEvent(
                            anomaly_type="skewed_stage",
                            severity="medium" if skew_ratio > 50 else "low",
                            description=f"Stage {stage_metric.stage_id} has high task skew: max {duration_dist.max_val:.0f}ms vs median {duration_dist.p50:.0f}ms",
                            affected_stages=[stage_metric.stage_id],
                            metric_name="task_duration_ms",
                            metric_value=skew_ratio,
                        )
                    )

        # Check for high spill
        total_spill = sum(s.spill_bytes for s in stage_metrics)
        if total_spill > 1024 * 1024 * 100:  # > 100 MB
            anomalies.append(
                AnomalyEvent(
                    anomaly_type="high_spill",
                    severity="medium",
                    description=f"Total spill: {total_spill / (1024*1024):.1f} MB - memory pressure detected",
                    metric_name="spill_bytes",
                    metric_value=total_spill,
                    evidence={"total_spill_mb": total_spill / (1024 * 1024)},
                )
            )

        # Check for high shuffle
        total_shuffle = sum(s.shuffle_read_bytes + s.shuffle_write_bytes for s in stage_metrics)
        if total_shuffle > 1024 * 1024 * 1024:  # > 1 GB
            anomalies.append(
                AnomalyEvent(
                    anomaly_type="high_shuffle",
                    severity="low",
                    description=f"Total shuffle: {total_shuffle / (1024**3):.1f} GB",
                    metric_name="shuffle_bytes",
                    metric_value=total_shuffle,
                )
            )

        return anomalies

    def _compute_kpis(self, exec_summary: ExecutionSummary, task_metrics: Dict[int, Dict[str, Any]]) -> Dict[str, float]:
        """Compute key performance indicators."""
        kpis = {}

        if exec_summary.total_duration_ms > 0:
            throughput = exec_summary.total_input_bytes / (exec_summary.total_duration_ms / 1000.0)
            kpis["throughput_bytes_per_sec"] = throughput

        if exec_summary.total_tasks > 0:
            kpis["avg_task_duration_ms"] = (
                sum(m.get("duration_ms", 0) for m in task_metrics.values()) / exec_summary.total_tasks
            )

            failure_rate = exec_summary.failed_task_count / exec_summary.total_tasks
            kpis["task_failure_rate"] = failure_rate

        if exec_summary.total_shuffle_bytes > 0:
            shuffle_to_input = exec_summary.total_shuffle_bytes / max(exec_summary.total_input_bytes, 1)
            kpis["shuffle_to_input_ratio"] = shuffle_to_input

        return kpis

    def _generate_description(self, exec_summary: ExecutionSummary, anomalies: List[AnomalyEvent]) -> str:
        """Generate natural language description of metrics."""
        parts = []

        duration_sec = exec_summary.total_duration_ms / 1000.0
        parts.append(f"Completed in {duration_sec:.1f} seconds")

        shuffle_gb = exec_summary.total_shuffle_bytes / (1024 ** 3)
        if shuffle_gb > 0:
            parts.append(f"Shuffle: {shuffle_gb:.1f} GB")

        if exec_summary.failed_task_count > 0:
            parts.append(f"{exec_summary.failed_task_count} failed tasks")

        if anomalies:
            parts.append(f"{len(anomalies)} anomalies detected")

        return "; ".join(parts)

    def _collect_evidence(self) -> List[str]:
        """Collect event IDs supporting metrics."""
        evidence = []

        task_end_count = len(self.index.get_by_type("SparkListenerTaskEnd"))
        if task_end_count:
            evidence.append(f"TaskEnd({task_end_count} events)")

        stage_completed = len(self.index.get_by_type("SparkListenerStageCompleted"))
        if stage_completed:
            evidence.append(f"StageCompleted({stage_completed} events)")

        executor_loss = len(self.index.get_by_type("SparkListenerExecutorMetricsUpdate"))
        if executor_loss:
            evidence.append(f"ExecutorMetrics({executor_loss} events)")

        return evidence
