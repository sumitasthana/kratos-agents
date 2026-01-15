"""
Spark Event Log Parser

Reads JSON event logs from Spark History Server and extracts structured event streams.
Preserves causality and timing for LLM analysis.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple


class SparkEvent:
    """Wrapper around a Spark event with metadata."""

    def __init__(self, event_dict: Dict[str, Any], event_index: int, file_path: str):
        self.event_dict = event_dict
        self.event_index = event_index  # Position in log file
        self.file_path = file_path
        self.event_type = event_dict.get("Event", "Unknown")
        self.timestamp = event_dict.get("Timestamp")

    def __getitem__(self, key: str) -> Any:
        """Delegate item access to underlying dict."""
        return self.event_dict.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from event dict."""
        return self.event_dict.get(key, default)

    def __repr__(self) -> str:
        return f"SparkEvent(type={self.event_type}, index={self.event_index}, ts={self.timestamp})"


class EventLogParser:
    """
    Parses Spark JSON event logs and provides structured stream access.
    """

    def __init__(self, log_path: str):
        """
        Initialize parser for a Spark event log.

        Args:
            log_path: Path to event log file (typically from Spark History Server)
        """
        self.log_path = Path(log_path)
        self.events: List[SparkEvent] = []
        self.metadata: Dict[str, Any] = {}
        self._parse_errors: List[Tuple[int, str]] = []

    def parse(self) -> Tuple[List[SparkEvent], Dict[str, Any]]:
        """
        Parse event log and return all events.

        Returns:
            Tuple of (events list, metadata dict)
        """
        if not self.log_path.exists():
            raise FileNotFoundError(f"Event log not found: {self.log_path}")

        event_index = 0
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event_dict = json.loads(line)
                        event = SparkEvent(event_dict, event_index, str(self.log_path))
                        self.events.append(event)

                        # Extract metadata from first event (ApplicationStart)
                        if event.event_type == "SparkListenerApplicationStart" and not self.metadata:
                            self._extract_app_metadata(event)

                        event_index += 1

                    except json.JSONDecodeError as e:
                        self._parse_errors.append((line_num, f"JSON parse error: {str(e)}"))

        except Exception as e:
            self._parse_errors.append((0, f"File read error: {str(e)}"))

        self.metadata["total_events"] = len(self.events)
        self.metadata["parse_errors"] = len(self._parse_errors)

        return self.events, self.metadata

    def _extract_app_metadata(self, app_start_event: SparkEvent) -> None:
        """Extract application metadata from SparkListenerApplicationStart event."""
        self.metadata = {
            "app_id": app_start_event.get("App ID", "unknown"),
            "app_name": app_start_event.get("App Name", "unknown"),
            "timestamp": app_start_event.get("Timestamp"),
            "user": app_start_event.get("User", "unknown"),
            "spark_version": app_start_event.get("Spark Version", "unknown"),
        }

    def get_events_by_type(self, event_type: str) -> List[SparkEvent]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]

    def get_stage_events(self) -> List[SparkEvent]:
        """Get all stage-related events (submitted, completed, failed)."""
        return [
            e
            for e in self.events
            if e.event_type in ("SparkListenerStageSubmitted", "SparkListenerStageCompleted")
        ]

    def get_task_events(self) -> List[SparkEvent]:
        """Get all task-related events."""
        return [
            e
            for e in self.events
            if e.event_type
            in (
                "SparkListenerTaskStart",
                "SparkListenerTaskEnd",
                "SparkListenerTaskExecutorMetrics",
            )
        ]

    def get_sql_events(self) -> List[SparkEvent]:
        """Get all SQL execution events."""
        return [
            e
            for e in self.events
            if e.event_type in ("SparkListenerSQLExecutionStart", "SparkListenerSQLExecutionEnd")
        ]

    def get_error_events(self) -> List[SparkEvent]:
        """Get all executor/task failure events."""
        return [
            e
            for e in self.events
            if e.event_type
            in (
                "SparkListenerTaskEnd",
                "SparkListenerExecutorMetricsUpdate",
                "SparkListenerBlockManagerExceptionEvent",
            )
        ]

    def stream_events(self) -> Generator[SparkEvent, None, None]:
        """Stream events in order for incremental processing."""
        for event in self.events:
            yield event

    def get_parse_errors(self) -> List[Tuple[int, str]]:
        """Get list of parsing errors encountered."""
        return self._parse_errors


class EventIndex:
    """
    Indexed view of event log for fast lookups by event type and stage/task ID.
    Enables efficient extraction of specific execution paths.
    """

    def __init__(self, events: List[SparkEvent]):
        self.events = events
        self._build_indices()

    def _build_indices(self) -> None:
        """Build lookup indices."""
        self.by_type: Dict[str, List[SparkEvent]] = {}
        self.by_stage_id: Dict[int, List[SparkEvent]] = {}
        self.by_task_id: Dict[int, List[SparkEvent]] = {}
        self.by_executor_id: Dict[str, List[SparkEvent]] = {}

        for event in self.events:
            # Index by type
            event_type = event.event_type
            if event_type not in self.by_type:
                self.by_type[event_type] = []
            self.by_type[event_type].append(event)

            # Index by stage ID
            stage_id = event.get("Stage ID") or event.get("stageId")
            if stage_id is not None:
                if stage_id not in self.by_stage_id:
                    self.by_stage_id[stage_id] = []
                self.by_stage_id[stage_id].append(event)

            # Index by task ID
            task_id = event.get("Task ID") or event.get("taskId")
            if task_id is not None:
                if task_id not in self.by_task_id:
                    self.by_task_id[task_id] = []
                self.by_task_id[task_id].append(event)

            # Index by executor ID
            executor_id = event.get("Executor ID") or event.get("executorId")
            if executor_id is not None:
                if executor_id not in self.by_executor_id:
                    self.by_executor_id[executor_id] = []
                self.by_executor_id[executor_id].append(event)

    def events_for_stage(self, stage_id: int) -> List[SparkEvent]:
        """Get all events for a specific stage."""
        return self.by_stage_id.get(stage_id, [])

    def events_for_task(self, task_id: int) -> List[SparkEvent]:
        """Get all events for a specific task."""
        return self.by_task_id.get(task_id, [])

    def events_for_executor(self, executor_id: str) -> List[SparkEvent]:
        """Get all events for a specific executor."""
        return self.by_executor_id.get(executor_id, [])

    def get_by_type(self, event_type: str) -> List[SparkEvent]:
        """Get all events of a type."""
        return self.by_type.get(event_type, [])


# ============================================================================
# Specialized event extraction helpers
# ============================================================================


def extract_application_info(events: List[SparkEvent]) -> Dict[str, Any]:
    """Extract application information from SparkListenerApplicationStart."""
    for event in events:
        if event.event_type == "SparkListenerApplicationStart":
            return {
                "app_id": event.get("App ID"),
                "app_name": event.get("App Name"),
                "timestamp": event.get("Timestamp"),
                "user": event.get("User"),
                "spark_version": event.get("Spark Version"),
            }
    return {}


def extract_environment_info(events: List[SparkEvent]) -> Dict[str, Any]:
    """Extract environment and configuration from SparkListenerEnvironmentUpdate."""
    for event in events:
        if event.event_type == "SparkListenerEnvironmentUpdate":
            return event.get("environmentDetails", {})
    return {}


def extract_stage_info(events: List[SparkEvent], stage_id: int) -> Dict[str, Any]:
    """Extract all info for a specific stage."""
    stage_submitted = None
    stage_completed = None

    for event in events:
        if event.event_type == "SparkListenerStageSubmitted":
            if event.get("Stage Info", {}).get("Stage ID") == stage_id:
                stage_submitted = event.get("Stage Info", {})
        elif event.event_type == "SparkListenerStageCompleted":
            if event.get("Stage Info", {}).get("Stage ID") == stage_id:
                stage_completed = event.get("Stage Info", {})

    return {
        "submitted": stage_submitted,
        "completed": stage_completed,
    }


def extract_task_metrics(events: List[SparkEvent], task_id: int) -> Dict[str, Any]:
    """Extract all metrics for a specific task."""
    metrics = {}

    for event in events:
        if event.event_type == "SparkListenerTaskEnd":
            if event.get("Task ID") == task_id:
                metrics["task_info"] = event.get("Task Info", {})
                metrics["task_metrics"] = event.get("Task Metrics", {})
                metrics["task_type"] = event.get("Task Type")
                metrics["reason"] = event.get("Task End Reason", {})

    return metrics
