"""
Output Formatter

Renders ExecutionFingerprint as JSON/YAML for LLM consumption.
Supports tiered detail levels and cross-references.
"""

import json
from typing import Any
from datetime import datetime

try:
    import yaml
except ImportError:
    yaml = None

from src.schemas import ExecutionFingerprint


class FingerprintFormatter:
    """
    Formats ExecutionFingerprint for LLM analysis.
    Supports JSON, YAML, and markdown outputs with configurable detail levels.
    """

    @staticmethod
    def to_json(
        fingerprint: ExecutionFingerprint,
        include_evidence: bool = True,
        detail_level: str = "balanced",
        pretty: bool = True,
    ) -> str:
        """
        Export fingerprint as JSON string.

        Args:
            fingerprint: ExecutionFingerprint object
            include_evidence: Include evidence linking
            detail_level: 'summary', 'balanced', or 'detailed'
            pretty: Pretty-print JSON

        Returns:
            JSON string
        """
        data = fingerprint.dict_for_llm(
            include_evidence=include_evidence,
            detail_level=detail_level,
        )

        # Convert datetime objects to ISO format
        data = FingerprintFormatter._serialize_dates(data)

        if pretty:
            return json.dumps(data, indent=2, default=str)
        return json.dumps(data, default=str)

    @staticmethod
    def to_yaml(
        fingerprint: ExecutionFingerprint,
        include_evidence: bool = True,
        detail_level: str = "balanced",
    ) -> str:
        """
        Export fingerprint as YAML string.

        Args:
            fingerprint: ExecutionFingerprint object
            include_evidence: Include evidence linking
            detail_level: 'summary', 'balanced', or 'detailed'

        Returns:
            YAML string
        """
        if yaml is None:
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")

        data = fingerprint.dict_for_llm(
            include_evidence=include_evidence,
            detail_level=detail_level,
        )

        data = FingerprintFormatter._serialize_dates(data)

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    @staticmethod
    def to_markdown(
        fingerprint: ExecutionFingerprint,
        include_evidence: bool = True,
    ) -> str:
        """
        Export fingerprint as markdown for LLM analysis.

        Args:
            fingerprint: ExecutionFingerprint object
            include_evidence: Include evidence linking

        Returns:
            Markdown string
        """
        lines = []

        # Header
        lines.append("# Spark Execution Fingerprint\n")

        # Metadata section
        lines.append("## Metadata\n")
        lines.append(f"- **Generated**: {fingerprint.metadata.generated_at}")
        lines.append(f"- **Application**: {fingerprint.metadata.event_log_path}")
        lines.append(f"- **Schema Version**: {fingerprint.metadata.fingerprint_schema_version}")
        lines.append(f"- **Events Parsed**: {fingerprint.metadata.events_parsed}/{fingerprint.metadata.events_total or '?'}")
        if fingerprint.metadata.parsing_issues:
            lines.append(f"- **Issues**: {', '.join(fingerprint.metadata.parsing_issues)}")
        lines.append("")

        # Analysis hints (if any)
        if fingerprint.analysis_hints:
            lines.append("## Analysis Hints (LLM Focus)\n")
            for hint in fingerprint.analysis_hints:
                lines.append(f"- {hint}")
            lines.append("")

        # Execution class
        lines.append(f"## Execution Classification: `{fingerprint.execution_class}`\n")

        # Semantic section
        lines.append("## Semantic Fingerprint (What computation)\n")
        lines.append(f"**Semantic Hash**: `{fingerprint.semantic.semantic_hash[:16]}...`\n")
        lines.append(f"**Description**: {fingerprint.semantic.description}\n")

        lines.append("### DAG Structure")
        lines.append(f"- **Stages**: {fingerprint.semantic.dag.total_stages}")
        lines.append(f"- **Root Stages**: {fingerprint.semantic.dag.root_stage_ids}")
        lines.append(f"- **Leaf Stages**: {fingerprint.semantic.dag.leaf_stage_ids}")
        lines.append("")

        lines.append("#### Stages")
        for stage in fingerprint.semantic.dag.stages[:10]:  # Top 10
            shuffle_marker = " (shuffle)" if stage.is_shuffle_stage else ""
            lines.append(f"- Stage {stage.stage_id}: {stage.description}{shuffle_marker}")
        if len(fingerprint.semantic.dag.stages) > 10:
            lines.append(f"- ... and {len(fingerprint.semantic.dag.stages) - 10} more stages")
        lines.append("")

        lines.append("#### Dependencies")
        for edge in fingerprint.semantic.dag.edges[:10]:
            lines.append(f"- Stage {edge.from_stage_id} -> Stage {edge.to_stage_id}: {edge.reason}")
        if len(fingerprint.semantic.dag.edges) > 10:
            lines.append(f"- ... and {len(fingerprint.semantic.dag.edges) - 10} more edges")
        lines.append("")

        # Context section
        lines.append("## Context Fingerprint (Where & how)\n")
        lines.append(f"**Description**: {fingerprint.context.description}\n")

        spark_cfg = fingerprint.context.spark_config
        lines.append("### Spark Configuration")
        lines.append(f"- **Version**: {spark_cfg.spark_version}")
        lines.append(f"- **Application**: {spark_cfg.app_name}")
        lines.append(f"- **Master**: {spark_cfg.master_url}")
        lines.append("")

        exec_cfg = fingerprint.context.executor_config
        lines.append("### Resource Allocation")
        lines.append(f"- **Executors**: {exec_cfg.total_executors}")
        lines.append(f"- **Memory/Executor**: {exec_cfg.executor_memory_mb} MB")
        lines.append(f"- **Cores/Executor**: {exec_cfg.executor_cores}")
        lines.append(f"- **Driver Memory**: {exec_cfg.driver_memory_mb} MB")
        lines.append("")

        if fingerprint.context.optimizations_enabled:
            lines.append("### Optimizations Enabled")
            for opt in fingerprint.context.optimizations_enabled:
                lines.append(f"- {opt}")
            lines.append("")

        # Metrics section
        lines.append("## Metrics & Performance\n")
        lines.append(f"**Description**: {fingerprint.metrics.description}\n")

        exec_summary = fingerprint.metrics.execution_summary
        lines.append("### Execution Summary")
        lines.append(f"- **Duration**: {exec_summary.total_duration_ms / 1000:.1f} seconds")
        lines.append(f"- **Tasks**: {exec_summary.total_tasks} (failed: {exec_summary.failed_task_count})")
        lines.append(f"- **Stages**: {exec_summary.total_stages}")
        lines.append(f"- **Input Data**: {exec_summary.total_input_bytes / (1024**2):.1f} MB")
        lines.append(f"- **Shuffle**: {exec_summary.total_shuffle_bytes / (1024**2):.1f} MB")
        lines.append(f"- **Spill**: {exec_summary.total_spill_bytes / (1024**2):.1f} MB")
        lines.append(f"- **Max Concurrent Tasks**: {exec_summary.max_concurrent_tasks}")
        lines.append("")

        # Task distribution
        lines.append("### Task Duration Distribution")
        task_dur = fingerprint.metrics.task_distribution.duration_ms
        lines.append(f"- **Min**: {task_dur.min_val:.0f} ms")
        lines.append(f"- **P25**: {task_dur.p25:.0f} ms")
        lines.append(f"- **Median**: {task_dur.p50:.0f} ms")
        lines.append(f"- **P75**: {task_dur.p75:.0f} ms")
        lines.append(f"- **P99**: {task_dur.p99:.0f} ms")
        lines.append(f"- **Max**: {task_dur.max_val:.0f} ms")
        lines.append(f"- **Outliers**: {task_dur.outlier_count}/{task_dur.count} tasks")
        lines.append("")

        # Anomalies
        if fingerprint.metrics.anomalies:
            lines.append("### Detected Anomalies\n")
            for anomaly in fingerprint.metrics.anomalies:
                severity_tag = "[CRITICAL]" if anomaly.severity == "critical" else "[HIGH]" if anomaly.severity == "high" else "[MEDIUM]"
                lines.append(f"{severity_tag} **{anomaly.anomaly_type}** ({anomaly.severity})")
                lines.append(f"   {anomaly.description}")
                if anomaly.affected_stages:
                    lines.append(f"   Stages: {anomaly.affected_stages}")
                lines.append("")

        # KPIs
        if fingerprint.metrics.key_performance_indicators:
            lines.append("### Key Performance Indicators")
            for kpi_name, kpi_value in fingerprint.metrics.key_performance_indicators.items():
                if isinstance(kpi_value, float):
                    lines.append(f"- **{kpi_name}**: {kpi_value:.2f}")
                else:
                    lines.append(f"- **{kpi_name}**: {kpi_value}")
            lines.append("")

        # Stage breakdown (summary)
        lines.append("### Stage Metrics (Top 5)\n")
        for stage_metric in fingerprint.metrics.stage_metrics[:5]:
            lines.append(f"#### Stage {stage_metric.stage_id}")
            lines.append(f"- Tasks: {stage_metric.num_tasks} (failed: {stage_metric.num_failed_tasks})")
            lines.append(f"- Duration: {stage_metric.task_duration_ms.p50:.0f} ms (median)")
            lines.append(f"- Input: {stage_metric.input_bytes / (1024**2):.1f} MB")
            lines.append(f"- Shuffle: {(stage_metric.shuffle_read_bytes + stage_metric.shuffle_write_bytes) / (1024**2):.1f} MB")
            lines.append("")

        # Evidence (if included)
        if include_evidence:
            lines.append("## Evidence Sources\n")
            lines.append("### Semantic")
            for ev in fingerprint.semantic.evidence_sources[:5]:
                lines.append(f"- {ev}")
            lines.append("\n### Context")
            for ev in fingerprint.context.evidence_sources[:5]:
                lines.append(f"- {ev}")
            lines.append("\n### Metrics")
            for ev in fingerprint.metrics.evidence_sources[:5]:
                lines.append(f"- {ev}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def save_json(
        fingerprint: ExecutionFingerprint,
        file_path: str,
        include_evidence: bool = True,
        detail_level: str = "balanced",
    ) -> None:
        """Save fingerprint as JSON file."""
        content = FingerprintFormatter.to_json(
            fingerprint,
            include_evidence=include_evidence,
            detail_level=detail_level,
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def save_yaml(
        fingerprint: ExecutionFingerprint,
        file_path: str,
        include_evidence: bool = True,
        detail_level: str = "balanced",
    ) -> None:
        """Save fingerprint as YAML file."""
        content = FingerprintFormatter.to_yaml(
            fingerprint,
            include_evidence=include_evidence,
            detail_level=detail_level,
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def save_markdown(
        fingerprint: ExecutionFingerprint,
        file_path: str,
        include_evidence: bool = True,
    ) -> None:
        """Save fingerprint as markdown file."""
        content = FingerprintFormatter.to_markdown(fingerprint, include_evidence=include_evidence)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _serialize_dates(obj: Any) -> Any:
        """Recursively convert datetime objects to ISO format strings."""
        if isinstance(obj, dict):
            return {k: FingerprintFormatter._serialize_dates(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [FingerprintFormatter._serialize_dates(item) for item in obj]
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj
