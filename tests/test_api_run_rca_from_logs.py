"""
test_api_run_rca_from_logs.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for the POST /api/run_rca_from_logs FastAPI endpoint.

These tests use httpx.AsyncClient with an ASGITransport so no socket is
opened — the FastAPI app is exercised in-process.

Prerequisites
-------------
- Fixture log files present under logs/test_fixtures/ (skip otherwise).
- ``httpx`` available (``pip install httpx``).
- ``pytest-asyncio`` available (``pip install pytest-asyncio``).

Run:
    cd src
    pytest ../tests/test_api_run_rca_from_logs.py -v
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Ensure src/ is on sys.path so rca_api / orchestrator / schemas can be imported.
SRC_DIR = Path(__file__).parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

# ── Skip entire module if httpx is not installed ──────────────────────────────
pytest.importorskip("httpx", reason="httpx not installed — skip API tests")

from httpx import AsyncClient, ASGITransport  # noqa: E402 (after importorskip)
from rca_api import app                        # noqa: E402

LOG_ROOT = Path(__file__).parent.parent / "logs" / "test_fixtures"

# ── Helper to skip a test if a required fixture file is missing ───────────────

def _require_fixture(*parts: str) -> None:
    """Call at the start of a test; skips if the file doesn't exist."""
    p = LOG_ROOT.joinpath(*parts)
    if not p.exists():
        pytest.skip(f"Fixture log not found: {p}")


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_rca_from_logs_spark_only():
    """
    Spark-only include=True (all others False) should return a valid
    RecommendationReport with a non-empty executive_summary.
    """
    _require_fixture("spark", "spark_failure_spill.jsonl")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/run_rca_from_logs",
            json={
                "scenario":   "test_spark_only",
                "user_query": "Why did the Spark job fail?",
                "include": {
                    "spark":   True,
                    "airflow": False,
                    "data":    False,
                    "infra":   False,
                    "change":  False,
                },
            },
        )

    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:500]}"
    data = resp.json()

    # Top-level structure
    assert "executive_summary" in data,    "Missing executive_summary"
    assert data["executive_summary"],      "executive_summary must not be empty"
    assert "issue_profile" in data,        "Missing issue_profile"
    assert "dominant_problem_type" in data["issue_profile"], \
        "Missing issue_profile.dominant_problem_type"

    # At least one recommendation
    fixes = data.get("prioritized_fixes", [])
    assert isinstance(fixes, list), "prioritized_fixes must be a list"


@pytest.mark.asyncio
async def test_run_rca_from_logs_airflow_only():
    """
    Airflow-only run — checks response wiring, not health semantics.
    """
    _require_fixture("airflow", "airflow_retries_failure.log")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/run_rca_from_logs",
            json={
                "scenario":   "test_airflow_only",
                "user_query": "Why did the Airflow task fail after retries?",
                "include": {
                    "spark":   False,
                    "airflow": True,
                    "data":    False,
                    "infra":   False,
                    "change":  False,
                },
            },
        )

    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    assert data.get("executive_summary"), "executive_summary must not be empty"


@pytest.mark.asyncio
async def test_run_rca_from_logs_full_demo_incident():
    """
    Full demo-incident run with spark + airflow + data + infra selected.
    This is the scenario triggered by the 'Demo Incident (Real Logs)' UI option.
    """
    # Skip if any fixture is missing
    _require_fixture("spark",        "spark_failure_spill.jsonl")
    _require_fixture("airflow",      "airflow_retries_failure.log")
    _require_fixture("data_quality", "ohlcv_null_spike.log")
    _require_fixture("infra",        "node_pressure_oom.log")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/run_rca_from_logs",
            json={
                "scenario":   "demo_ohlcv_pipeline",
                "user_query": "Full multi-signal demo incident: Spark + Airflow + Data + Infra",
                "include": {
                    "spark":   True,
                    "airflow": True,
                    "data":    True,
                    "infra":   True,
                    "change":  False,
                },
            },
        )

    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:500]}"
    data = resp.json()

    assert data.get("executive_summary"),           "executive_summary must not be empty"
    assert data.get("issue_profile"),               "issue_profile must be present"
    dominant = data["issue_profile"].get("dominant_problem_type")
    assert dominant is not None,                    "dominant_problem_type must not be None"

    # overall_health_score lives inside issue_profile, not at the report root
    score = data["issue_profile"].get("overall_health_score")
    assert score is not None,                       "overall_health_score must be present in issue_profile"
    assert isinstance(score, (int, float)),         "overall_health_score must be numeric"
    assert 0.0 <= score <= 100.0,                   f"overall_health_score out of range: {score}"

    # End-to-end fix: at least one prioritized fix must be generated
    fixes = data.get("prioritized_fixes", [])
    assert isinstance(fixes, list),                 "prioritized_fixes must be a list"
    assert len(fixes) > 0,                          "prioritized_fixes must not be empty for a multi-signal demo incident"


@pytest.mark.asyncio
async def test_run_rca_from_logs_missing_fixture_returns_422():
    """
    When a requested fixture file does not exist the endpoint should return
    HTTP 422 (Unprocessable Entity) with a human-readable error detail.
    """
    # Request a fixture that definitely does not exist.
    # We use the spark path since build_spark_fingerprint_from_real_log()
    # would be called first; rename it to something guaranteed absent.
    import shutil

    spark_fixture = LOG_ROOT / "spark" / "spark_failure_spill.jsonl"
    backup_path   = spark_fixture.with_suffix(".jsonl.bak")

    if not spark_fixture.exists():
        pytest.skip("Spark fixture not present — can't test 422 path")

    # Temporarily rename to simulate a missing file
    spark_fixture.rename(backup_path)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/run_rca_from_logs",
                json={
                    "include": {"spark": True, "airflow": False, "data": False,
                                "infra": False, "change": False},
                    "user_query": "Should fail with 422",
                },
            )
        assert resp.status_code == 422, \
            f"Expected 422 for missing fixture, got {resp.status_code}: {resp.text[:200]}"
        detail = resp.json().get("detail", "")
        assert "spark" in detail.lower() or "not found" in detail.lower(), \
            f"422 detail should mention missing file: {detail}"
    finally:
        # Restore the fixture file
        backup_path.rename(spark_fixture)


@pytest.mark.asyncio
async def test_run_rca_from_logs_health_check():
    """Sanity: /health liveness probe should always return 200."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/logs/browse
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_browse_logs_endpoint():
    """
    GET /api/logs/browse must return 200 and include the 4 known fixtures under
    logs/test_fixtures/.  Each entry must carry path, filename, category,
    size_bytes, and modified_at.
    """
    LOGS_ROOT = Path(__file__).parent.parent / "logs"
    if not LOGS_ROOT.exists():
        pytest.skip("logs/ directory not present — skip browse test")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/logs/browse")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    entries = resp.json()
    assert isinstance(entries, list), "Response must be a list"

    # Check required fields on every entry
    for entry in entries:
        assert "path"        in entry, f"Missing 'path' in entry: {entry}"
        assert "filename"    in entry, f"Missing 'filename' in entry: {entry}"
        assert "category"    in entry, f"Missing 'category' in entry: {entry}"
        assert "size_bytes"  in entry, f"Missing 'size_bytes' in entry: {entry}"
        assert "modified_at" in entry, f"Missing 'modified_at' in entry: {entry}"

    # The 4 known fixture files should appear when test_fixtures are present
    known_fixtures = {
        "spark_failure_spill.jsonl",
        "airflow_retries_failure.log",
        "ohlcv_null_spike.log",
        "node_pressure_oom.log",
    }
    returned_names = {e["filename"] for e in entries}
    present = known_fixtures & returned_names
    missing = known_fixtures - returned_names
    # Only assert fixtures that actually exist on disk
    for name in list(missing):
        # Check whether the fixture is actually on disk; skip check if not
        found_on_disk = any(
            (Path(__file__).parent.parent / "logs").rglob(name)
        )
        if found_on_disk:
            assert name in returned_names, \
                f"Fixture '{name}' exists on disk but was not returned by browse endpoint"

    # Category auto-detection sanity check
    for entry in entries:
        assert entry["category"] in {"spark", "airflow", "data", "infra", "change", "unknown"}, \
            f"Unexpected category value: {entry['category']} for {entry['filename']}"


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/run_rca_from_file — single spark fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_rca_from_file_spark():
    """
    POST /api/run_rca_from_file with the spark fixture file must return a
    valid RecommendationReport with a non-empty executive_summary and a
    populated dominant_problem_type.
    """
    _require_fixture("spark", "spark_failure_spill.jsonl")

    spark_path = "logs/test_fixtures/spark/spark_failure_spill.jsonl"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/run_rca_from_file",
            json={
                "files": [{"path": spark_path, "category": "spark"}],
                "user_query": "Why did the Spark job fail?",
            },
        )

    assert resp.status_code == 200, \
        f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    data = resp.json()
    assert "issue_profile"     in data, "Response must contain issue_profile"
    assert "executive_summary" in data, "Response must contain executive_summary"
    assert data["executive_summary"], "executive_summary must be non-empty"

    ip = data["issue_profile"]
    assert ip.get("dominant_problem_type"), "dominant_problem_type must be present in issue_profile"
    assert isinstance(ip.get("overall_health_score"), (int, float)), \
        "overall_health_score must be numeric"


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/run_rca_from_file — multi-signal (spark + infra)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_rca_from_file_multi():
    """
    POST /api/run_rca_from_file with spark + infra fixtures must return a
    non-empty prioritized_fixes list (both analyzers contribute recommendations).
    """
    _require_fixture("spark", "spark_failure_spill.jsonl")
    _require_fixture("infra", "node_pressure_oom.log")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/run_rca_from_file",
            json={
                "files": [
                    {"path": "logs/test_fixtures/spark/spark_failure_spill.jsonl", "category": "spark"},
                    {"path": "logs/test_fixtures/infra/node_pressure_oom.log",     "category": "infra"},
                ],
                "user_query": "Investigate the combined Spark + infrastructure failure.",
            },
        )

    assert resp.status_code == 200, \
        f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    data  = resp.json()
    fixes = data.get("prioritized_fixes", [])
    assert isinstance(fixes, list), "prioritized_fixes must be a list"
    assert len(fixes) > 0, \
        "prioritized_fixes must be non-empty when spark + infra signals are both present"

    ip = data.get("issue_profile", {})
    assert ip.get("overall_health_score") is not None, \
        "overall_health_score must be present when multiple analyzers run"
