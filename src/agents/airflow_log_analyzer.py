import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResponse, AgentType, FingerprintDomain


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
        dag_id         = fingerprint_data.get("dag_id", "UNKNOWN_DAG")
        task_id        = fingerprint_data.get("task_id", "UNKNOWN_TASK")
        execution_date = fingerprint_data.get("execution_date")
        try_number     = fingerprint_data.get("try_number")
        max_retries    = fingerprint_data.get("max_retries")
        log_lines      = fingerprint_data.get("log_lines", []) or []

        if not log_lines:
            return self._create_error_response("No Airflow log lines provided")

        # Parse log for metrics
        parsed = self._parse_airflow_log(log_lines)

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
            success=True,
            summary=summary,
            explanation=explanation,
            key_findings=key_findings,
            confidence=1.0,  # rule-based
            metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    def _parse_airflow_log(self, lines: List[str]) -> Dict[str, Any]:
        """
        Extracts structured info from Airflow task logs.

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
            "messages": [ ... ],  # selected important info-level messages
        }
        """
        ts_pattern = re.compile(r"^\[(?P<ts>[^]]+)\]")
        start_time: Optional[datetime] = None
        end_time: Optional[datetime]   = None
        host: Optional[str]            = None
        state: str                     = "unknown"
        attempt: Optional[int]         = None
        max_attempts: Optional[int]    = None
        downstream_scheduled = 0

        api_calls: List[Dict[str, Any]] = []
        s3_writes: List[Dict[str, Any]] = []
        messages: List[str]             = []

        for line in lines:
            stripped = line.strip()

            # Parse timestamp (for start/end)
            m = ts_pattern.match(stripped)
            ts: Optional[datetime] = None
            if m:
                ts_text = m.group("ts").split(" ", 1)[0]  # "2026-02-25,"
                # Trim trailing comma and timezone part
                ts_clean = ts_text.replace(",", "")
                try:
                    ts = datetime.fromisoformat(ts_clean)
                except Exception:
                    ts = None

            # Attempt info
            if "Starting attempt" in stripped:
                # e.g. "Starting attempt 1 of 2"
                m2 = re.search(r"Starting attempt (\d+) of (\d+)", stripped)
                if m2:
                    attempt      = int(m2.group(1))
                    max_attempts = int(m2.group(2))

            # Host info
            if "Running <TaskInstance:" in stripped and "on host" in stripped:
                # e.g. "Running <TaskInstance: ...> on host airflow-worker-0"
                parts = stripped.split("on host", 1)
                if len(parts) == 2:
                    host = parts[1].strip()

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

            # API calls (your example pattern)
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
                # e.g. "Writing data to s3://quant-data/prices/nvda/2026-02-24.parquet"
                path = stripped.split("Writing data to", 1)[1].strip()
                s3_writes.append({"path": path, "rows": None})
            if "Successfully wrote" in stripped and "rows" in stripped:
                m5 = re.search(r"Successfully wrote (\d+) rows", stripped)
                rows = int(m5.group(1)) if m5 else None
                # Attach to last s3_writes entry if available
                if s3_writes:
                    s3_writes[-1]["rows"] = rows

            # Important info messages for context
            if "Downloading prices" in stripped or "Normalizing schema" in stripped:
                messages.append(stripped)

            # Start time (first time we see the task instance running)
            if (
                "Running <TaskInstance" in stripped
                and "on host" in stripped
                and ts
                and start_time is None
            ):
                start_time = ts

        duration_sec: Optional[float] = None
        if start_time and end_time:
            duration_sec = (end_time - start_time).total_seconds()

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
        }

    @staticmethod
    def _extract_url(line: str) -> Optional[str]:
        # Very simple URL extraction for the example
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
        state      = parsed.get("state", "unknown")
        attempt    = parsed.get("attempt") or 1
        max_attempts = parsed.get("max_attempts") or 1
        duration  = parsed.get("duration_sec")

        if state == "failed":
            return "Critical", "high"

        # If succeeded but used multiple attempts
        if state == "success" and attempt > 1:
            return "Warning", "medium"

        # Long-ish duration could be a warning (rule of thumb, tweak later)
        if state == "success" and duration is not None and duration > 600:
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
        state    = parsed.get("state", "unknown")
        duration = parsed.get("duration_sec")
        duration_str = f"{duration:.1f}s" if duration is not None else "unknown duration"
        return (
            f"{health} Airflow task: {dag_id}.{task_id} "
            f"({state}) in {duration_str} for execution_date={execution_date}"
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

        state      = parsed.get("state", "unknown")
        duration   = parsed.get("duration_sec")
        attempt    = parsed.get("attempt") or 1
        max_attempts = parsed.get("max_attempts") or 1
        s3_writes  = parsed.get("s3_writes", [])
        api_calls  = parsed.get("api_calls", [])

        kfs.append(
            f"Task {dag_id}.{task_id} completed with state={state}, "
            f"attempt={attempt}/{max_attempts}, "
            f"duration={duration:.1f}s" if duration is not None else "duration=unknown"
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
            kfs.append("Task shows warning signals; monitor retries/duration and adjust thresholds.")

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

        lines.append(f"## Task\n")
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
            lines.append("- The task completed successfully on the first attempt with normal duration.")
        elif health == "Warning":
            lines.append("- The task completed but shows potential issues (retries or long duration).")
        else:
            lines.append("- The task failed or encountered severe issues; investigate logs and upstream dependencies.")

        return "\n".join(lines)
