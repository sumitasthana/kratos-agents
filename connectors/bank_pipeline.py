"""
connectors/bank_pipeline.py
My_Bank connector for the Kratos RCA platform.

Bridges the bank-pipeline-api (FastAPI + PostgreSQL) into the typed
Kratos model layer consumed by the agent pipeline.

Endpoints consumed:
  POST /pipeline/run          – trigger nightly batch
  GET  /incidents             – list incidents
  GET  /rca/context/{id}      – full RCA context bundle
  GET  /logs/stream/{id}      – SSE log stream
  GET  /lineage/{job_id}      – upstream/downstream lineage graph
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import TracebackType
from typing import AsyncIterator, Optional

import httpx

from connectors.base_connector import BaseConnector
from core.models import (
    IncidentContext,
    LineageEdge,
    LineageGraph,
    LineageNode,
    LogChunk,
    LogSource,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ConnectorError(Exception):
    """Raised when the bank-pipeline-api returns an unexpected HTTP status."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------

_RETRYABLE_STATUSES = {502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0   # seconds; doubles each attempt (1 → 2 → 4)


async def _with_retry(coro_fn, *args, **kwargs):
    """Execute an async callable with exponential back-off on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await coro_fn(*args, **kwargs)
        except httpx.TimeoutException as exc:
            last_exc = exc
            wait = _BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "BankPipelineConnector: timeout (attempt %d/%d), retrying in %.1fs",
                attempt + 1, _MAX_RETRIES, wait,
            )
            await asyncio.sleep(wait)
        except ConnectorError as exc:
            if exc.status_code in _RETRYABLE_STATUSES:
                last_exc = exc
                wait = _BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "BankPipelineConnector: HTTP %s (attempt %d/%d), retrying in %.1fs",
                    exc.status_code, attempt + 1, _MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
            else:
                raise

    raise ConnectorError(
        f"BankPipelineConnector: request failed after {_MAX_RETRIES} retries"
    ) from last_exc


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class BankPipelineConnector(BaseConnector):
    """
    Async connector to the My_Bank pipeline API.

    Usage (context manager — preferred)::

        async with BankPipelineConnector() as conn:
            ctx = await conn.fetch_incident("INC-4491")
            async for chunk in conn.stream_logs("INC-4491"):
                print(chunk.message)

    Usage (manual lifecycle)::

        conn = BankPipelineConnector(base_url="http://my-bank-api:8000", token="s3cret")
        await conn.connect()
        try:
            graph = await conn.fetch_lineage("nightly_batch")
        finally:
            await conn.close()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        token: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the underlying httpx.AsyncClient."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=httpx.Timeout(30.0),
        )
        logger.debug("BankPipelineConnector: connected to %s", self._base_url)

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("BankPipelineConnector: connection closed")

    async def __aenter__(self) -> "BankPipelineConnector":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val:  BaseException | None,
        exc_tb:   TracebackType | None,
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError(
                "BankPipelineConnector is not connected. "
                "Call connect() or use it as an async context manager."
            )
        return self._client

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise ConnectorError for non-2xx responses, including API detail text."""
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise ConnectorError(
                f"HTTP {response.status_code} from {response.url}: {detail}",
                status_code=response.status_code,
            )

    # ------------------------------------------------------------------
    # BaseConnector implementation
    # ------------------------------------------------------------------

    async def fetch_incident(self, incident_id: str) -> IncidentContext:
        """
        Fetch the full RCA context bundle for *incident_id*.

        Calls GET /rca/context/{id} and maps the response to IncidentContext.
        Translates My_Bank structured evidence into the metadata keys that
        Kratos tools expect (data_profile, airflow_logs, git_artifacts, etc.).
        """
        async def _fetch():
            resp = await self._http.get(f"/rca/context/{incident_id}")
            self._raise_for_status(resp)
            return resp.json()

        data: dict = await _with_retry(_fetch)

        # ── Extract top-level sections (guard against explicit nulls) ────
        incident   = data.get("incident") or {}
        control    = data.get("control") or {}
        chain      = data.get("control_chain") or {}
        entities   = data.get("implicated_entities") or {}
        evidence   = data.get("evidence") or []
        traversal  = data.get("ontology_traversal") or {}
        history    = data.get("control_history") or []

        source_system = incident.get("source_system", "unknown")
        stage         = incident.get("stage", "unknown")
        control_id    = incident.get("control_id", "")
        created_at    = incident.get("created_at", "")

        # Script & code-event nodes from the control chain
        # Use `or {}` to guard against explicit JSON nulls
        script_node   = chain.get("script") or {}
        script_props  = script_node.get("properties") or {}
        code_event    = entities.get("code_event") or {}
        event_props   = code_event.get("properties") or {}

        # ── Build tool-compatible metadata ──────────────────────────────

        # 1. data_profile — from evidence violation summaries
        columns = []
        total_records = 0
        for field in control.get("applicable_fields", []):
            columns.append({"name": field, "dtype": "string", "null_rate": 0.0})
        for ev in evidence:
            cj = ev.get("content_json", {})
            violations = cj.get("violation_summary", [])
            if isinstance(violations, list):
                total_records += len(violations)

        data_profile = {
            "dataset_name": f"{source_system}.{stage}",
            "row_count": max(total_records, 1),
            "columns": columns or [{"name": "unknown", "dtype": "string", "null_rate": 0.0}],
        }

        # 2. airflow_logs — from evidence and stage info
        log_lines = []
        for ev in evidence:
            cj = ev.get("content_json", {})
            rule = cj.get("rule", "")
            if rule:
                log_lines.append(f"[CONTROL] {rule}")
            violations = cj.get("violation_summary", [])
            if isinstance(violations, list):
                for v in violations[:5]:
                    log_lines.append(f"[VIOLATION] {json.dumps(v)}")

        airflow_logs = {
            "dag_id": f"{source_system}_pipeline",
            "task_id": stage,
            "execution_date": created_at,
            "log_lines": log_lines or [f"[INFO] Control {control_id} evaluated"],
        }

        # 3. git_artifacts — from script node and code event
        git_files = []
        if script_props.get("path"):
            diff_lines = []
            if script_props.get("known_issue"):
                diff_lines.append(f"--- Known Issue ---")
                diff_lines.append(f"+ {script_props['known_issue']}")
            if event_props.get("change"):
                diff_lines.append(f"--- Last Change ---")
                diff_lines.append(f"+ {event_props['change']}")

            git_files.append({
                "file_path": script_props["path"],
                "commits": [{
                    "commit_hash": code_event.get("node_id", "HEAD"),
                    "author": event_props.get("author", "ops-automation"),
                    "date": event_props.get("date", created_at),
                    "message": event_props.get("change", f"Change to {script_props['path']}"),
                    "diff": "\n".join(diff_lines) if diff_lines else f"# {script_node.get('label', 'unknown')}",
                }],
            })

        git_artifacts = {"files": git_files} if git_files else {}

        # 4. change_fingerprint — from code event
        change_commits = []
        if code_event:
            change_commits.append({
                "hash": code_event.get("node_id", "unknown"),
                "author": event_props.get("author", "unknown"),
                "timestamp": event_props.get("date", created_at),
                "files": [{
                    "path": script_props.get("path", "unknown"),
                    "added": 5,
                    "deleted": 0,
                }],
            })

        change_fingerprint = {
            "repo_name": source_system,
            "commits": change_commits,
        }

        # ── Build ontology snapshot ─────────────────────────────────────
        ontology_snapshot = {
            "control_chain": chain,
            "implicated_entities": entities,
            "ontology_traversal": traversal,
        }

        # ── Assemble IncidentContext ────────────────────────────────────
        metadata = {
            "data_profile": data_profile,
            "airflow_logs": airflow_logs,
            "git_artifacts": git_artifacts,
            "change_fingerprint": change_fingerprint,
            # Preserve full My_Bank context for chat and audit
            "rca_context": data,
            "control": control,
            "control_chain": chain,
            "implicated_entities": entities,
            "evidence": evidence,
            "control_history": history,
        }

        return IncidentContext(
            incident_id=incident.get("incident_id", incident_id),
            run_id=incident.get("run_id", ""),
            pipeline_stage=stage,
            failed_controls=[control_id] if control_id else [],
            ontology_snapshot=ontology_snapshot,
            metadata=metadata,
        )

    async def persist_rca(self, summary: dict) -> None:
        """Submit RCA results back to My_Bank via POST /rca/results/{id}."""
        incident_id = summary.get("incident_id", "")
        if not incident_id:
            logger.warning("persist_rca: no incident_id in summary — skipping")
            return

        # Extract root cause entity from evidence if available
        root_cause_entity_id = ""
        root_cause_entity_type = "Script"
        rca_context = summary.get("_rca_context", {})
        chain = rca_context.get("control_chain", {})
        script = chain.get("script", {})
        if script.get("node_id"):
            root_cause_entity_id = script["node_id"]

        payload = {
            "root_cause": summary.get("final_root_cause", "Unknown"),
            "root_cause_entity_type": root_cause_entity_type,
            "root_cause_entity_id": root_cause_entity_id,
            "confidence_score": summary.get("confidence_score", 0.50),
            "recommendation": "",
            "evidence_summary": summary.get("final_root_cause", ""),
            "supporting_entities": [],
            "traversal_path": [],
            "reasoning_summary": summary.get("final_root_cause", ""),
            "submitted_by": "kratos-rca-agent",
        }

        try:
            resp = await self._http.post(f"/rca/results/{incident_id}", json=payload)
            if resp.is_error:
                logger.warning("persist_rca: HTTP %s — %s", resp.status_code, resp.text[:200])
            else:
                logger.info("persist_rca: submitted RCA result for %s", incident_id)
        except Exception as exc:
            logger.warning("persist_rca: failed to submit — %s", exc)

    async def stream_logs(self, incident_id: str) -> AsyncIterator[LogChunk]:
        """
        Stream SSE log chunks from GET /logs/stream/{id}.

        Yields LogChunk instances in arrival order. Each SSE event ``data``
        field must be a JSON object with at minimum:
        ``source``, ``timestamp``, ``level``, ``message``.
        """
        url = f"/logs/stream/{incident_id}"
        sse_headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

        async with self._http.stream("GET", url, headers=sse_headers) as response:
            if response.is_error:
                await response.aread()
            self._raise_for_status(response)

            async for line in response.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if not payload or payload == "[DONE]":
                    break

                try:
                    event: dict = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning(
                        "BankPipelineConnector: skipping malformed SSE line: %r", payload
                    )
                    continue

                try:
                    source_raw = event.get("source", "system").lower()
                    source = (
                        LogSource(source_raw)
                        if source_raw in LogSource._value2member_map_
                        else LogSource.SYSTEM
                    )

                    ts_raw = event.get("timestamp")
                    if isinstance(ts_raw, str):
                        ts = datetime.fromisoformat(ts_raw)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    else:
                        ts = datetime.now(timezone.utc)

                    yield LogChunk(
                        source=source,
                        timestamp=ts,
                        level=event.get("level", "INFO").upper(),
                        message=event.get("message", ""),
                        metadata={
                            k: v for k, v in event.items()
                            if k not in ("source", "timestamp", "level", "message")
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "BankPipelineConnector: could not parse log event: %s — %r", exc, event
                    )

    async def fetch_lineage(self, job_id: str) -> LineageGraph:
        """
        Fetch the upstream/downstream lineage graph for *job_id*.

        Calls GET /lineage/{job_id} and maps response to LineageGraph.
        """
        async def _fetch():
            resp = await self._http.get(f"/lineage/{job_id}")
            self._raise_for_status(resp)
            return resp.json()

        data: dict = await _with_retry(_fetch)

        nodes = [
            LineageNode(
                id=n["id"],
                type=n.get("type", "unknown"),
                name=n.get("name", n["id"]),
            )
            for n in data.get("nodes", [])
        ]
        edges = [
            LineageEdge(
                source=e["source"],
                target=e["target"],
                relation=e.get("relation", "UNKNOWN"),
            )
            for e in data.get("edges", [])
        ]

        return LineageGraph(job_id=job_id, nodes=nodes, edges=edges)

    # ------------------------------------------------------------------
    # Additional helpers
    # ------------------------------------------------------------------

    async def trigger_pipeline(self, scenario: str) -> str:
        """
        Trigger a nightly batch run via POST /pipeline/run.

        Args:
            scenario: Scenario name, e.g. ``"deposit_aggregation_failure"``.

        Returns:
            The ``run_id`` string assigned by the API.

        Raises:
            ConnectorError: If the API returns a non-2xx response or no run_id.
        """
        async def _post():
            resp = await self._http.post("/pipeline/run", json={"scenario": scenario})
            self._raise_for_status(resp)
            return resp.json()

        data: dict = await _with_retry(_post)
        run_id: str = data.get("run_id", "")
        if not run_id:
            raise ConnectorError("trigger_pipeline: API response missing run_id")
        logger.info(
            "BankPipelineConnector: triggered pipeline scenario=%r → run_id=%s",
            scenario, run_id,
        )
        return run_id

    async def list_incidents(
        self,
        run_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[dict]:
        """
        List incidents via GET /incidents with optional filters.

        Args:
            run_id:   Filter results to a specific pipeline run.
            severity: Filter by severity string, e.g. ``"P1"``.

        Returns:
            Raw list of incident dicts as returned by the API.
        """
        params: dict[str, str] = {}
        if run_id:
            params["run_id"] = run_id
        if severity:
            params["severity"] = severity

        async def _fetch():
            resp = await self._http.get("/incidents", params=params)
            self._raise_for_status(resp)
            return resp.json()

        return await _with_retry(_fetch)

