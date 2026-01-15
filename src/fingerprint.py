"""
Main Fingerprint Generator Orchestrator

Coordinates extraction of all three fingerprint layers and produces complete ExecutionFingerprint.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.schemas import (
    ExecutionFingerprint,
    FingerprintMetadata,
)
from src.parser import EventLogParser, EventIndex
from src.semantic_generator import SemanticFingerprintGenerator
from src.context_generator import ContextFingerprintGenerator
from src.metrics_generator import MetricsFingerprintGenerator


class ExecutionFingerprintGenerator:
    """
    Orchestrates generation of complete ExecutionFingerprint.
    Combines semantic, context, and metrics layers.
    """

    def __init__(self, event_log_path: str, generator_version: str = "3.0.0"):
        """
        Initialize fingerprint generator.

        Args:
            event_log_path: Path to Spark event log file
            generator_version: Version of this generator
        """
        self.event_log_path = str(event_log_path)
        self.generator_version = generator_version
        self.parser = EventLogParser(self.event_log_path)
        self.events, self.metadata = self.parser.parse()
        self.index = EventIndex(self.events)

    def generate(self) -> ExecutionFingerprint:
        """
        Generate complete execution fingerprint.

        Returns:
            ExecutionFingerprint with all three layers

        Raises:
            ValueError: If event log cannot be parsed or is missing critical events
        """
        # Validate event log
        if not self.events:
            raise ValueError("No events found in event log")

        app_start = self.index.get_by_type("SparkListenerApplicationStart")
        if not app_start:
            raise ValueError("Missing SparkListenerApplicationStart event")

        # Generate each layer
        print("Generating semantic layer...")
        semantic_gen = SemanticFingerprintGenerator(self.event_log_path)
        semantic = semantic_gen.generate()

        print("Generating context layer...")
        context_gen = ContextFingerprintGenerator(self.event_log_path)
        context = context_gen.generate()

        print("Generating metrics layer...")
        metrics_gen = MetricsFingerprintGenerator(self.index)
        metrics = metrics_gen.generate()

        # Create metadata
        event_log_size = Path(self.event_log_path).stat().st_size if Path(self.event_log_path).exists() else 0

        metadata = FingerprintMetadata(
            fingerprint_schema_version="1.0.0",
            generated_at=datetime.now(),
            generator_version=self.generator_version,
            event_log_path=self.event_log_path,
            event_log_size_bytes=event_log_size,
            events_parsed=len(self.events),
            events_total=self.metadata.get("total_events"),
            parsing_issues=[msg for _, msg in self.parser.get_parse_errors()],
        )

        # Determine execution class
        execution_class = self._classify_execution(metrics)

        # Generate analysis hints
        analysis_hints = self._generate_analysis_hints(semantic, context, metrics)

        return ExecutionFingerprint(
            metadata=metadata,
            semantic=semantic,
            context=context,
            metrics=metrics,
            execution_class=execution_class,
            analysis_hints=analysis_hints,
        )

    def _classify_execution(self, metrics: any) -> str:
        """
        Classify execution based on characteristics.

        Returns execution class: cpu_bound, io_bound, memory_bound, network_bound, balanced
        """
        exec_summary = metrics.execution_summary

        if exec_summary.total_tasks == 0:
            return "unknown"

        # Calculate ratios
        total_data = exec_summary.total_input_bytes + exec_summary.total_output_bytes
        shuffle_ratio = (
            exec_summary.total_shuffle_bytes / total_data if total_data > 0 else 0
        )
        spill_ratio = (
            exec_summary.total_spill_bytes / total_data if total_data > 0 else 0
        )

        avg_task_duration = exec_summary.total_duration_ms / max(exec_summary.total_tasks, 1)

        # Classification logic
        if spill_ratio > 0.1:
            return "memory_bound"
        elif shuffle_ratio > 0.5:
            return "network_bound"
        elif total_data > 1024 * 1024 * 1024:  # > 1 GB
            return "io_bound"
        elif exec_summary.failed_task_count > 0:
            return "unstable"
        else:
            return "balanced"

    def _generate_analysis_hints(self, semantic: any, context: any, metrics: any) -> list:
        """Generate hints for LLM analysis focus."""
        hints = []

        # Anomaly hints
        if metrics.anomalies:
            hints.append(f"⚠️ {len(metrics.anomalies)} anomalies detected - investigate impact")

        # High spill
        if metrics.execution_summary.total_spill_bytes > 100 * 1024 * 1024:  # > 100 MB
            hints.append("🔴 High memory spill - consider increasing executor memory or reducing partition size")

        # Failed tasks
        if metrics.execution_summary.failed_task_count > 0:
            failure_rate = (
                metrics.execution_summary.failed_task_count / metrics.execution_summary.total_tasks
            )
            if failure_rate > 0.01:
                hints.append("🔴 Significant task failure rate - check executor logs for errors")

        # High shuffle
        if metrics.execution_summary.total_shuffle_bytes > 5 * 1024 * 1024 * 1024:  # > 5 GB
            hints.append("🟡 Large shuffle volume - consider optimizing join/groupBy logic")

        # Config optimization opportunities
        if not context.optimizations_enabled:
            hints.append("🟢 No optimizations detected - enable AQE for better performance")

        return hints


def generate_fingerprint(
    event_log_path: str,
    output_format: str = "json",
    output_path: Optional[str] = None,
    include_evidence: bool = True,
    detail_level: str = "balanced",
) -> ExecutionFingerprint:
    """
    Convenience function: parse event log and generate fingerprint.

    Args:
        event_log_path: Path to event log file
        output_format: 'json', 'yaml', or 'markdown'
        output_path: Path to save output (optional)
        include_evidence: Include evidence linking in output
        detail_level: 'summary', 'balanced', or 'detailed'

    Returns:
        ExecutionFingerprint object
    """
    from src.formatter import FingerprintFormatter

    # Generate fingerprint
    print(f"Parsing event log: {event_log_path}")
    gen = ExecutionFingerprintGenerator(event_log_path)
    fingerprint = gen.generate()

    # Save output if requested
    if output_path:
        print(f"Saving {output_format} output: {output_path}")
        if output_format == "json":
            FingerprintFormatter.save_json(
                fingerprint,
                output_path,
                include_evidence=include_evidence,
                detail_level=detail_level,
            )
        elif output_format == "yaml":
            FingerprintFormatter.save_yaml(
                fingerprint,
                output_path,
                include_evidence=include_evidence,
                detail_level=detail_level,
            )
        elif output_format == "markdown":
            FingerprintFormatter.save_markdown(
                fingerprint, output_path, include_evidence=include_evidence
            )
        else:
            raise ValueError(f"Unknown format: {output_format}")

    return fingerprint
