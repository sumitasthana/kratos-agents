# Moved from: src\agents\airflow_log_analyzer.py
# Import updates applied by migrate step.
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentResponse, AgentType, FingerprintDomain


class AirflowLogAnalyzerAgent(BaseAgent):
    """
    Pipeline observability RCA for Airflow task logs.

    Scope (MVP):
      - Analyze a single Airflow task's log lines.
      - Extract lifecycle (start/end/duration, state, retries).
      - Extract data semantics (what the task did, which datasets/paths).
      - Assess task health (healthy / warning / critical).
      - Emit key findings and remediation hints.

    Later:
      - Extend to DAG-level aggregation and infra correlation.
    """

    @property
    def agent_type(self) -> AgentType:
        # You may want to add a dedicated enum later, e.g. PIPELINE_LOG_ANALYZER.
        return AgentType.LOG_ANALYZER

    @property
    def fingerprint_domain(self) -> FingerprintDomain:
        # For now, treat as GENERIC pipeline logs, not Spark-specific.
        return FingerprintDomain.GENERIC

    @property
    def agent_name(self) -> str:
        return "Airflow Log Analyzer"

    @property
    def description(self) -> str:
        return "Analyzes Airflow task logs for pipeline health and data ingestion behaviour."

    @property
    def system_prompt(self) -> str:
        # Not used in MVP (rule-based); keep placeholder for future LLM enhancement.
        return "Airflow log analysis prompt (unused in rule-based mode)."

    # ------------------------------------------------------------------ #
    # Public analyse method
    # ------------------------------------------------------------------ #

    async def analyze(
        self,
        fingerprint_data: Dict[str, Any],
        context: Optional[Any] = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Analyze an Airflow log snippet.

        Expected fingerprint_data format (MVP):
          {
            "dag_id": "prices_dag",
            "task_id": "load_prices",
            "execution_date": "2026-02-25T10:15:00+00:00",
            "try_number": 1,
            "max_retries": 2,
            "log_lines": [ "...", "...", ... ],  # raw log lines as strings
          }
        """
        dag_id = fingerprint_data.get("dag_id", "UNKNOWN_DAG")
        task_id = fingerprint_data.get("task_id", "UNKNOWN_TASK")
        execution_date = fingerprint_data.get("execution_date")
        try_number = fingerprint_data.get("try_number")
        max_retries = fingerprint_data.get("max_retries")
        log_lines = fingerprint_data.get("log_lines", []) or []

        if not log_lines:
            return self._create_error_response("No Airflow log lines provided")

        # Parse log for metrics
        parsed = self._parse_airflow_log(log_lines, execution_date)

        # Derive health classification
        health, severity = self._classify_health(parsed)

        # Build summary
        summary = self._build_summary(
            dag_id=dag_id,
            task_id=task_id,
            execution_date=execution_date,
            health=health,
            parsed=parsed,
        )

        # Build key findings
        key_findings = self._build_key_findings(
            dag_id=dag_id,
            task_id=task_id,
            parsed=parsed,
            health=health,
            severity=severity,
        )

        # Explanation (MVP: simple markdown)
        explanation = self._build_explanation(
            dag_id=dag_id,
            task_id=task_id,
            execution_date=execution_date,
            parsed=parsed,
            health=health,
            severity=severity,
        )

        metadata = {
            "dag_id": dag_id,
            "task_id": task_id,
            "execution_date": execution_date,
            "health": health,
            "severity": severity,
            "parsed": parsed,
        }

        return AgentResponse(
            agent_type=self.agent_type,
            agent_name=self.agent_name,
            # `success` reflects task health, not just whether the agent ran.
            # True  = task was Healthy or Warning (completed, possibly with caveats).
            # False = task was Critical (failed state, exhausted retries, etc.).
            success=health != "Critical",
            summary=summary,
            explanation=explanation,
            key_findings=key_findings,
            confidence=1.0,  # rule-based
            metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    def _parse_airflow_log(
        self,
        lines: List[str],
        execution_date: Optional[str],
    ) -> Dict[str, Any]:
        """
        Extracts structured info from Airflow task logs.

        Improvements vs previous version:
          - Robust timestamp parsing (keeps timezone, no manual slicing).
          - Duration computed from earliest log timestamp to last task line if needed.
          - Captures scheduled vs actual start latency when execution_date is provided.

        Returns a dict like:
          {
            "start_time": datetime | None,
            "end_time": datetime | None,
            "duration_sec": float | None,
            "host": str | None,
            "state": "success" | "failed" | "other",
            "attempt": int | None,
            "max_attempts": int | None,
            "downstream_scheduled": int,
            "api_calls": [ { "url": ..., "symbol": ..., "date": ... }, ... ],
            "s3_writes": [ { "path": ..., "rows": ... }, ... ],
            "messages": [ ... ],
            "latency_sec": float | None,  # actual start - scheduled execution_date
        }
        """
        # Example timestamp token in log:
        # [2026-02-25, 10:15:00 +0000]
        ts_pattern = re.compile(
            r"^\[(?P<date>\d{4}-\d{2}-\d{2}),\s*(?P<time>\d{2}:\d{2}:\d{2})\s*(?P<tz>[+\-]\d{4})\]"
        )

        start_time: Optional[datetime] = None
        end_time: Optional[datetime] = None
        earliest_ts: Optional[datetime] = None
        latest_ts: Optional[datetime] = None

        host: Optional[str] = None
        state: str = "unknown"
        attempt: Optional[int] = None
        max_attempts: Optional[int] = None
        downstream_scheduled = 0

        api_calls: List[Dict[str, Any]] = []
        s3_writes: List[Dict[str, Any]] = []
        messages: List[str] = []

        for line in lines:
            stripped = line.strip()

            # Parse timestamp robustly
            ts: Optional[datetime] = None
            m = ts_pattern.match(stripped)
            if m:
                # Build an ISO-like string: "2026-02-25 10:15:00+0000"
                iso_like = (
                    f"{m.group('date')} {m.group('time')}{m.group('tz')}"
                )
                try:
                    ts = datetime.strptime(iso_like, "%Y-%m-%d %H:%M:%S%z")
                except Exception:
                    ts = None

            if ts:
                if earliest_ts is None or ts < earliest_ts:
                    earliest_ts = ts
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

            # Attempt info
            if "Starting attempt" in stripped:
                m2 = re.search(r"Starting attempt (\d+) of (\d+)", stripped)
                if m2:
                    attempt = int(m2.group(1))
                    max_attempts = int(m2.group(2))

            # Host info
            if "Running <TaskInstance:" in stripped and "on host" in stripped:
                parts = stripped.split("on host", 1)
                if len(parts) == 2:
                    host = parts[1].strip()
                if ts and start_time is None:
                    start_time = ts

            # State transitions
            if "Marking task as SUCCESS" in stripped:
                state = "success"
                if ts:
                    end_time = ts
            elif "Marking task as FAILED" in stripped:
                state = "failed"
                if ts:
                    end_time = ts

            # Downstream scheduling
            if "downstream tasks scheduled" in stripped:
                m3 = re.search(r"(\d+) downstream tasks scheduled", stripped)
                if m3:
                    downstream_scheduled = int(m3.group(1))

            # API calls
            if "Requesting data from" in stripped and "api.example.com/prices" in stripped:
                m4 = re.search(
                    r"prices\?symbol=(?P<symbol>[^&]+)&date=(?P<date>[\d-]+)",
                    stripped,
                )
                api_calls.append(
                    {
                        "url": self._extract_url(stripped),
                        "symbol": m4.group("symbol") if m4 else None,
                        "date": m4.group("date") if m4 else None,
                    }
                )

            # S3 writes
            if "Writing data to s3://" in stripped:
                path = stripped.split("Writing data to", 1)[1].strip()
                s3_writes.append({"path": path, "rows": None})
            if "Successfully wrote" in stripped and "rows" in stripped:
                m5 = re.search(r"Successfully wrote (\d+) rows", stripped)
                rows = int(m5.group(1)) if m5 else None
                if s3_writes:
                    s3_writes[-1]["rows"] = rows

            # Important info messages for context
            if "Downloading prices" in stripped or "Normalizing schema" in stripped:
                messages.append(stripped)

        # Fallbacks for start/end time:
        # - start_time: prefer first "Running <TaskInstance>" ts; else earliest log ts
        # - end_time: prefer SUCCESS/FAILED ts; else latest log ts
        if start_time is None:
            start_time = earliest_ts
        if end_time is None:
            end_time = latest_ts

        duration_sec: Optional[float] = None
        if start_time and end_time:
            duration_sec = (end_time - start_time).total_seconds()

        # Compute latency from scheduled execution_date to actual start, if possible
        latency_sec: Optional[float] = None
        if execution_date and start_time:
            try:
                # Airflow usually uses ISO-like execution_date with timezone
                sched_dt = datetime.fromisoformat(execution_date)
                if sched_dt.tzinfo is None and start_time.tzinfo is not None:
                    # Assume scheduled is in same tz as log
                    sched_dt = sched_dt.replace(tzinfo=start_time.tzinfo)
                latency_sec = (start_time - sched_dt).total_seconds()
            except Exception:
                latency_sec = None

        return {
            "start_time": start_time,
            "end_time": end_time,
            "duration_sec": duration_sec,
            "host": host,
            "state": state,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "downstream_scheduled": downstream_scheduled,
            "api_calls": api_calls,
            "s3_writes": s3_writes,
            "messages": messages,
            "latency_sec": latency_sec,
        }

    @staticmethod
    def _extract_url(line: str) -> Optional[str]:
        m = re.search(r"(https?://\S+)", line)
        return m.group(1) if m else None

    # ------------------------------------------------------------------ #
    # Health classification
    # ------------------------------------------------------------------ #

    def _classify_health(self, parsed: Dict[str, Any]) -> tuple[str, str]:
        """
        Returns (health_label, severity).

        health_label: "Healthy" | "Warning" | "Critical".
        severity: "low" | "medium" | "high".
        """
        state = parsed.get("state", "unknown")
        attempt = parsed.get("attempt") or 1
        max_attempts = parsed.get("max_attempts") or 1
        duration = parsed.get("duration_sec")
        latency = parsed.get("latency_sec")

        if state == "failed":
            return "Critical", "high"

        # Succeeded but used multiple attempts
        if state == "success" and attempt > 1:
            return "Warning", "medium"

        # Long duration
        if state == "success" and duration is not None and duration > 600:
            return "Warning", "medium"

        # High start latency vs scheduled time (e.g., > 300s)
        if state == "success" and latency is not None and latency > 300:
            return "Warning", "medium"

        if state == "success":
            return "Healthy", "low"

        return "Warning", "medium"

    # ------------------------------------------------------------------ #
    # Output builders
    # ------------------------------------------------------------------ #

    def _build_summary(
        self,
        dag_id: str,
        task_id: str,
        execution_date: Optional[str],
        health: str,
        parsed: Dict[str, Any],
    ) -> str:
        state = parsed.get("state", "unknown")
        duration = parsed.get("duration_sec")
        duration_str = f"{duration:.1f}s" if duration is not None else "unknown duration"
        latency = parsed.get("latency_sec")
        latency_str = (
            f", start_latency={latency:.1f}s" if latency is not None else ""
        )
        return (
            f"{health} Airflow task: {dag_id}.{task_id} "
            f"({state}) in {duration_str}{latency_str} for execution_date={execution_date}"
        )

    def _build_key_findings(
        self,
        dag_id: str,
        task_id: str,
        parsed: Dict[str, Any],
        health: str,
        severity: str,
    ) -> List[str]:
        kfs: List[str] = []

        state = parsed.get("state", "unknown")
        duration = parsed.get("duration_sec")
        attempt = parsed.get("attempt") or 1
        max_attempts = parsed.get("max_attempts") or 1
        s3_writes = parsed.get("s3_writes", [])
        api_calls = parsed.get("api_calls", [])
        latency = parsed.get("latency_sec")

        if duration is not None:
            kfs.append(
                f"Task {dag_id}.{task_id} completed with state={state}, "
                f"attempt={attempt}/{max_attempts}, duration={duration:.1f}s"
            )
        else:
            kfs.append(
                f"Task {dag_id}.{task_id} completed with state={state}, "
                f"attempt={attempt}/{max_attempts}, duration=unknown"
            )

        if latency is not None:
            kfs.append(
                f"Task start latency vs scheduled execution_date: {latency:.1f}s"
            )

        for api in api_calls:
            kfs.append(
                f"External API call: {api.get('url')} "
                f"(symbol={api.get('symbol')}, date={api.get('date')})"
            )

        for s3 in s3_writes:
            kfs.append(
                f"Data written to {s3.get('path')} "
                f"rows={s3.get('rows')}"
            )

        if health == "Critical":
            kfs.append("Task is in a critical state; investigate failures and retries.")
        elif health == "Warning":
            kfs.append(
                "Task shows warning signals; monitor retries, duration, and latency; adjust thresholds or capacity."
            )

        return kfs

    def _build_explanation(
        self,
        dag_id: str,
        task_id: str,
        execution_date: Optional[str],
        parsed: Dict[str, Any],
        health: str,
        severity: str,
    ) -> str:
        lines: List[str] = []

        lines.append("## Task\n")
        lines.append(f"- DAG: `{dag_id}`")
        lines.append(f"- Task: `{task_id}`")
        if execution_date:
            lines.append(f"- Execution date: `{execution_date}`")

        lines.append(f"- Host: `{parsed.get('host')}`")
        lines.append(f"- State: `{parsed.get('state')}`")
        lines.append(
            f"- Attempt: `{parsed.get('attempt')}` of `{parsed.get('max_attempts')}`"
        )

        duration = parsed.get("duration_sec")
        if duration is not None:
            lines.append(f"- Duration: `{duration:.1f}s`")

        latency = parsed.get("latency_sec")
        if latency is not None:
            lines.append(f"- Start latency vs scheduled: `{latency:.1f}s`")

        lines.append("")
        lines.append("## Work done\n")

        for msg in parsed.get("messages", []):
            lines.append(f"- {msg}")

        for api in parsed.get("api_calls", []):
            lines.append(
                f"- Called external API `{api.get('url')}` "
                f"(symbol={api.get('symbol')}, date={api.get('date')})"
            )

        for s3 in parsed.get("s3_writes", []):
            lines.append(
                f"- Wrote data to `{s3.get('path')}` "
                f"with `{s3.get('rows')}` rows"
            )

        lines.append("")
        lines.append("## Health assessment\n")
        lines.append(f"- Overall health: **{health}** (severity: {severity})")

        if health == "Healthy":
            lines.append(
                "- The task completed successfully on the first attempt with normal duration and acceptable latency."
            )
        elif health == "Warning":
            lines.append(
                "- The task completed but shows potential issues (retries, long duration, or high start latency)."
            )
        else:
            lines.append(
                "- The task failed or encountered severe issues; investigate logs, upstream dependencies, and capacity."
            )

        return "\n".join(lines)
