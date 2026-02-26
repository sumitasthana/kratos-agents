"""
rca_api.py — Kratos RCA HTTP service.

Exposes a single endpoint:

    POST /api/run_rca

that accepts an optional-field JSON payload, delegates to
KratosOrchestrator.run(), and returns the full RecommendationReport
serialised via Pydantic's model_dump().

Run directly:
    cd src
    python rca_api.py

Or via uvicorn:
    uvicorn rca_api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json as _json
import logging
import os
import tempfile as _tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from orchestrator import KratosOrchestrator
from schemas import ExecutionFingerprint, RecommendationReport

# Absolute path to the repo-level logs/ directory.
# Works whether rca_api.py is run from src/ or the repo root.
_LOGS_ROOT: Path = Path(__file__).parent.parent / "logs"

_LOG_EXTENSIONS = {".log", ".jsonl", ".json", ".txt", ".csv"}


def _detect_category(filename: str) -> str:
    """
    Infer a log category from the filename using simple keyword matching.

    Rules (first match wins):
        spark                             → "spark"
        airflow                           → "airflow"
        dq | null | quality | profil      → "data"
        infra | node                      → "infra"
        git | change                      → "change"
        anything else                     → "unknown"
    """
    name = filename.lower()
    if "spark" in name:
        return "spark"
    if "airflow" in name:
        return "airflow"
    if any(k in name for k in ("dq", "null", "quality", "profil")):
        return "data"
    if any(k in name for k in ("infra", "node")):
        return "infra"
    if any(k in name for k in ("git", "change")):
        return "change"
    return "unknown"

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Kratos RCA API",
    description=(
        "Root-cause analysis service for Spark / Airflow / data / git / infra workloads. "
        "Delegates to KratosOrchestrator and returns a structured RecommendationReport."
    ),
    version="1.0.0",
)

# Allow the React dev server (port 5173 / 3000) and the dashboard Express
# server (port 3001) to call this API without CORS errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request schema
# ─────────────────────────────────────────────────────────────────────────────

class RCARequest(BaseModel):
    """
    Body for POST /api/run_rca.

    All fields except user_query are optional; omit any that are not
    relevant to the failure being investigated.

    execution_fingerprint:
        Full Spark ExecutionFingerprint object as a nested dict.
        Parsed into schemas.ExecutionFingerprint before being forwarded.

    airflow_fingerprint / infra_fingerprint:
        Passed through as plain dicts to the relevant orchestrators.

    dataset_path / git_log_path:
        Filesystem paths to JSON files consumed by DataProfilerOrchestrator
        and ChangeAnalyzerOrchestrator respectively.
    """

    user_query:            str                      = Field(
        ...,
        description="Natural-language description of the failure or question.",
        examples=["Why did my Spark ETL job fail with OOM errors?"],
    )
    trigger:               str                      = Field(
        default="manual",
        description="What initiated this analysis: 'manual' | 'failure' | 'infra_check' | …",
    )
    job_id:                Optional[str]            = Field(
        None,
        description="Optional stable job identifier for correlation across runs.",
    )

    # ── Spark ────────────────────────────────────────────────────────────────
    execution_fingerprint: Optional[Dict[str, Any]] = Field(
        None,
        description="Spark ExecutionFingerprint as a dict (see schemas.ExecutionFingerprint).",
    )
    spark_log_path:        Optional[str]            = Field(
        None,
        description="Path to a raw Spark event-log file (alternative to execution_fingerprint).",
    )

    # ── Airflow ──────────────────────────────────────────────────────────────
    airflow_fingerprint:   Optional[Dict[str, Any]] = Field(
        None,
        description="Airflow task fingerprint dict (dag_id, task_id, log_lines, …).",
    )

    # ── Data ─────────────────────────────────────────────────────────────────
    dataset_path:          Optional[str]            = Field(
        None,
        description="Path to a dataset JSON fingerprint consumed by DataProfilerOrchestrator.",
    )

    # ── Git / Change ─────────────────────────────────────────────────────────
    git_log_path:          Optional[str]            = Field(
        None,
        description="Path to a git-log JSON fingerprint consumed by ChangeAnalyzerOrchestrator.",
    )
    repo_path:             Optional[str]            = Field(
        None,
        description="Path to a local git repository (used by git-log extractor).",
    )

    # ── Infra ─────────────────────────────────────────────────────────────────
    infra_fingerprint:     Optional[Dict[str, Any]] = Field(
        None,
        description="Cluster observability snapshot dict (cpu_utilization, queued_tasks, …).",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/run_rca",
    response_model=None,          # we serialise manually so datetime fields round-trip cleanly
    summary="Run root-cause analysis",
    response_description="Full RecommendationReport as JSON",
)
async def run_rca(body: RCARequest) -> Dict[str, Any]:
    """
    Trigger a full Kratos RCA pipeline run.

    The handler:
    1. Validates and deserialises the request body.
    2. Converts `execution_fingerprint` (dict) → `schemas.ExecutionFingerprint`
       if present, raising HTTP 422 on validation failure.
    3. Calls `KratosOrchestrator().run(...)` with only the arguments that
       are present in the payload.
    4. Serialises the resulting `RecommendationReport` via `.model_dump()`
       and returns it as a JSON object.
    """

    # ── 1. Parse execution_fingerprint ───────────────────────────────────────
    parsed_execution_fingerprint: Optional[ExecutionFingerprint] = None
    if body.execution_fingerprint is not None:
        try:
            parsed_execution_fingerprint = ExecutionFingerprint.model_validate(
                body.execution_fingerprint
            )
        except Exception as exc:
            logger.warning("execution_fingerprint validation failed: %s", exc)
            raise HTTPException(
                status_code=422,
                detail=f"Invalid execution_fingerprint: {exc}",
            ) from exc

    # ── 2. Build kwargs — only forward fields that were supplied ─────────────
    kwargs: Dict[str, Any] = {
        "user_query": body.user_query,
        "trigger":    body.trigger,
    }

    if body.job_id is not None:
        kwargs["job_id"] = body.job_id
    if parsed_execution_fingerprint is not None:
        kwargs["execution_fingerprint"] = parsed_execution_fingerprint
    if body.spark_log_path is not None:
        kwargs["spark_log_path"] = body.spark_log_path
    if body.airflow_fingerprint is not None:
        kwargs["airflow_fingerprint"] = body.airflow_fingerprint
    if body.dataset_path is not None:
        kwargs["dataset_path"] = body.dataset_path
    if body.git_log_path is not None:
        kwargs["git_log_path"] = body.git_log_path
    if body.repo_path is not None:
        kwargs["repo_path"] = body.repo_path
    if body.infra_fingerprint is not None:
        kwargs["infra_fingerprint"] = body.infra_fingerprint

    # ── 3. Run the pipeline ───────────────────────────────────────────────────
    try:
        orchestrator = KratosOrchestrator()
        report: RecommendationReport = await orchestrator.run(**kwargs)
    except Exception as exc:
        logger.exception("KratosOrchestrator.run raised an exception")
        raise HTTPException(
            status_code=500,
            detail=f"RCA pipeline failed: {exc}",
        ) from exc

    # ── 4. Serialise and return ───────────────────────────────────────────────
    # mode="json" coerces datetime → ISO string and Enum → .value so the
    # response is always a plain JSON-serialisable dict.
    return report.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────────────────────
# Health check (useful for container liveness probes and dashboard status)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", summary="Liveness probe")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "kratos-rca-api"}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/run_rca_from_logs — analyse real fixture log files
# ─────────────────────────────────────────────────────────────────────────────

class IncludeSelection(BaseModel):
    """Which signal sources to include in the demo RCA run."""

    spark:  bool = Field(True,  description="Include Spark execution fingerprint from fixture logs")
    airflow: bool = Field(True, description="Include Airflow task fingerprint from fixture logs")
    data:   bool = Field(True,  description="Include data-quality fingerprint from fixture logs")
    infra:  bool = Field(True,  description="Include infra / cluster fingerprint from fixture logs")
    change: bool = Field(False, description="Include git change analysis (slow; needs repo on disk)")


class RunFromLogsRequest(BaseModel):
    """Body for POST /api/run_rca_from_logs."""

    scenario: str = Field(
        default="demo_ohlcv_pipeline",
        description="Named fixture scenario identifier (informational only for now).",
    )
    include: IncludeSelection = Field(
        default_factory=IncludeSelection,
        description="Toggles for which signal sources to include.",
    )
    user_query: str = Field(
        default="Investigate the selected pipeline incident using real log fixtures",
        description="Natural-language question forwarded to the orchestrator.",
    )


@app.post(
    "/api/run_rca_from_logs",
    response_model=None,
    summary="Run RCA using curated log fixtures",
    response_description="Full RecommendationReport as JSON",
)
async def run_rca_from_logs(body: RunFromLogsRequest) -> Dict[str, Any]:
    """
    Convenience endpoint that reads real-style log files from
    ``logs/test_fixtures/``, builds fingerprints, and runs the full
    multi-agent pipeline.

    Callers can toggle individual signal sources via the ``include`` field.
    When ``include.data`` is True the data-quality fingerprint dict is
    serialised to a temporary JSON file whose path is forwarded as
    ``dataset_path`` (DataProfilerOrchestrator reads from disk).

    Raises HTTP 422 if the requested fixture files are not present on disk.
    Raises HTTP 500 on pipeline execution errors.
    """
    import sys
    import os

    # Ensure src/ is importable (no-op when running via uvicorn from src/)
    src_dir = os.path.dirname(__file__)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from demo_fixtures import (  # noqa: PLC0415 (deferred import is intentional)
        build_airflow_fingerprint_from_real_log,
        build_dq_fingerprint_from_real_log,
        build_infra_fingerprint_from_real_log,
        build_spark_fingerprint_from_real_log,
        temp_json_file,
    )

    kwargs: Dict[str, Any] = {
        "user_query": body.user_query,
        "trigger":    "demo",
        "job_id":     f"demo-{body.scenario}",
    }

    # ── Build fingerprints for the selected signals ───────────────────────────
    try:
        if body.include.spark:
            kwargs["execution_fingerprint"] = build_spark_fingerprint_from_real_log()

        if body.include.airflow:
            kwargs["airflow_fingerprint"] = build_airflow_fingerprint_from_real_log()

        if body.include.infra:
            kwargs["infra_fingerprint"] = build_infra_fingerprint_from_real_log()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # ── Data-quality: write dict → temp file for DataProfilerOrchestrator ────
    dq_tmp_ctx = None
    if body.include.data:
        try:
            dq_fp = build_dq_fingerprint_from_real_log()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # Open a temp-file context; we manage entry/exit manually so we can
        # pass the path into the async orchestrator call, then clean up after.
        import json as _json
        import tempfile as _tempfile

        _fp = _tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        _json.dump(dq_fp, _fp)
        _fp.flush()
        _fp.close()
        kwargs["dataset_path"] = _fp.name

    # ── Run the pipeline ──────────────────────────────────────────────────────
    try:
        orchestrator = KratosOrchestrator()
        report: RecommendationReport = await orchestrator.run(**kwargs)
    except Exception as exc:
        logger.exception("KratosOrchestrator.run raised an exception (run_rca_from_logs)")
        raise HTTPException(status_code=500, detail=f"RCA pipeline failed: {exc}") from exc
    finally:
        # Clean up the temp dataset file regardless of success / failure.
        if body.include.data and "dataset_path" in kwargs:
            try:
                import os as _os
                _os.unlink(kwargs["dataset_path"])
            except OSError:
                pass

    return report.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/logs/browse — list all eligible files under logs/
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
    "/api/logs/browse",
    response_model=None,
    summary="Browse log files",
    response_description="List of log file entries with category, size, and modified time",
)
async def browse_logs() -> List[Dict[str, Any]]:
    """
    Walk the ``logs/`` directory tree and return every eligible file as a
    JSON entry.

    Each entry contains:
    - ``path``        – repo-relative path using forward slashes
    - ``filename``    – bare filename
    - ``category``    – auto-detected category (spark/airflow/data/infra/change/unknown)
    - ``size_bytes``  – file size in bytes
    - ``modified_at`` – ISO-8601 last-modified timestamp

    Only files with extensions ``.log``, ``.jsonl``, ``.json``, ``.txt``,
    ``.csv`` are included. Results are sorted by sub-directory, then
    alphabetically by filename.

    Returns HTTP 400 if the ``logs/`` directory does not exist.
    """
    if not _LOGS_ROOT.exists():
        raise HTTPException(
            status_code=400,
            detail=f"logs/ directory not found at {_LOGS_ROOT}. "
                   "Create the directory or populate it with log files.",
        )

    entries: List[Dict[str, Any]] = []

    for dirpath, _dirnames, filenames in os.walk(_LOGS_ROOT):
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in _LOG_EXTENSIONS:
                continue
            try:
                stat = fpath.stat()
            except OSError:
                continue
            # Build a forward-slash repo-relative path for portability
            try:
                rel = fpath.relative_to(_LOGS_ROOT.parent)
            except ValueError:
                rel = fpath
            entries.append({
                "path":        rel.as_posix(),
                "filename":    fname,
                "category":    _detect_category(fname),
                "size_bytes":  stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            })

    # Sort by sub-directory (parent) then filename
    entries.sort(key=lambda e: (e["path"].rsplit("/", 1)[0], e["filename"]))
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/run_rca_from_file — run RCA on user-selected log files
# ─────────────────────────────────────────────────────────────────────────────

class SelectedFile(BaseModel):
    """A single selected log file with its assigned category."""

    path: str = Field(
        ...,
        description="Repo-relative forward-slash path returned by GET /api/logs/browse, "
                    "e.g. 'logs/test_fixtures/spark/spark_failure_spill.jsonl'.",
    )
    category: str = Field(
        ...,
        description="One of: spark | airflow | data | infra | change | unknown",
    )


class LogFileRCARequest(BaseModel):
    """Body for POST /api/run_rca_from_file."""

    files: List[SelectedFile] = Field(
        ...,
        description="One or more log files to include in this RCA run.",
    )
    user_query: str = Field(
        default="Investigate the selected log files for root causes.",
        description="Natural-language question forwarded to the orchestrator.",
    )


@app.post(
    "/api/run_rca_from_file",
    response_model=None,
    summary="Run RCA on selected log files",
    response_description="Full RecommendationReport as JSON",
)
async def run_rca_from_file(body: LogFileRCARequest) -> Dict[str, Any]:
    """
    Read the caller-selected log files, build the appropriate fingerprints,
    and run the full Kratos multi-agent pipeline.

    Each file in ``body.files`` is routed to the fingerprint builder matching
    its ``category``:

    - ``spark``   → ``build_spark_fingerprint_from_file`` → ExecutionFingerprint
    - ``airflow`` → ``build_airflow_fingerprint_from_file`` → airflow_fingerprint dict
    - ``data``    → ``build_dq_fingerprint_from_file`` → temp JSON → dataset_path
    - ``infra``   → ``build_infra_fingerprint_from_file`` → infra_fingerprint dict
    - ``change``  → path forwarded directly as git_log_path
    - ``unknown`` → treated as ``spark`` (best-effort)

    When a category appears multiple times, the **last** file wins (single
    fingerprint per signal type).

    Raises HTTP 422 on file-read errors, HTTP 500 on pipeline failures.
    """
    import sys

    src_dir = os.path.dirname(__file__)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from demo_fixtures import (  # noqa: PLC0415
        build_airflow_fingerprint_from_file,
        build_dq_fingerprint_from_file,
        build_infra_fingerprint_from_file,
        build_spark_fingerprint_from_file,
    )

    # Resolve repo root once — all client paths are relative to repo root
    repo_root = _LOGS_ROOT.parent

    spark_fp:    Optional[ExecutionFingerprint] = None
    airflow_fp:  Optional[Dict[str, Any]]       = None
    infra_fp:    Optional[Dict[str, Any]]       = None
    change_path: Optional[str]                  = None
    dq_fp:       Optional[Dict[str, Any]]       = None

    for entry in body.files:
        # Resolve to absolute path; guard against path traversal
        abs_path = (repo_root / entry.path).resolve()
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Path escapes repository root: {entry.path}",
            )
        if not abs_path.exists():
            raise HTTPException(
                status_code=422,
                detail=f"File not found: {entry.path}",
            )

        cat = entry.category.lower()
        try:
            if cat in ("spark", "unknown"):
                spark_fp = build_spark_fingerprint_from_file(str(abs_path))
            elif cat == "airflow":
                airflow_fp = build_airflow_fingerprint_from_file(str(abs_path))
            elif cat == "data":
                dq_fp = build_dq_fingerprint_from_file(str(abs_path))
            elif cat == "infra":
                infra_fp = build_infra_fingerprint_from_file(str(abs_path))
            elif cat == "change":
                change_path = str(abs_path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not any([spark_fp, airflow_fp, infra_fp, change_path, dq_fp]):
        raise HTTPException(
            status_code=422,
            detail="No files could be parsed. Select at least one supported log file.",
        )

    kwargs: Dict[str, Any] = {
        "user_query": body.user_query,
        "trigger":    "file_browse",
        "job_id":     f"file-rca-{len(body.files)}files",
    }
    if spark_fp   is not None: kwargs["execution_fingerprint"] = spark_fp
    if airflow_fp is not None: kwargs["airflow_fingerprint"]   = airflow_fp
    if infra_fp   is not None: kwargs["infra_fingerprint"]     = infra_fp
    if change_path is not None: kwargs["git_log_path"]         = change_path

    # Data-quality fingerprint: write to temp file, pass path to orchestrator
    dq_tmp_path: Optional[str] = None
    if dq_fp is not None:
        _fp = _tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        _json.dump(dq_fp, _fp)
        _fp.flush()
        _fp.close()
        dq_tmp_path            = _fp.name
        kwargs["dataset_path"] = dq_tmp_path

    try:
        orchestrator = KratosOrchestrator()
        report: RecommendationReport = await orchestrator.run(**kwargs)
    except Exception as exc:
        logger.exception("KratosOrchestrator.run raised an exception (run_rca_from_file)")
        raise HTTPException(status_code=500, detail=f"RCA pipeline failed: {exc}") from exc
    finally:
        if dq_tmp_path is not None:
            try:
                os.unlink(dq_tmp_path)
            except OSError:
                pass

    return report.model_dump(mode="json")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
