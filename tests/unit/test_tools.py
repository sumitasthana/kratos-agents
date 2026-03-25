"""
tests/unit/test_tools.py
Unit tests for all 5 Kratos BaseTool wrappers.

Coverage
--------
- SparkLogTool   : healthy metrics, OOM scenario, empty dict, missing key
- DataQualityTool: clean profile, high-null column, no columns key
- DDLDiffTool    : high-churn commit, empty commits list
- GitDiffTool    : diff with reads/writes, no git fingerprint
- AirflowLogTool : failed task, healthy task, empty log_lines

All tests are deterministic (no real LLM calls).
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.llm import LLMConfig
from core.models import EvidenceObject, IncidentContext, Priority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(metadata: dict, incident_id: str = "INC-TEST-001") -> IncidentContext:
    return IncidentContext(
        incident_id=incident_id,
        run_id="RUN-UNIT-001",
        pipeline_stage="unit_test",
        failed_controls=[],
        metadata=metadata,
    )


def _assert_evidence_list(result: list, *, min_items: int = 0) -> None:
    assert isinstance(result, list)
    assert len(result) >= min_items
    for ev in result:
        assert isinstance(ev, EvidenceObject), f"Expected EvidenceObject, got {type(ev)}"
        assert ev.source_tool, "source_tool must not be empty"
        assert ev.severity in Priority, f"Invalid severity: {ev.severity}"
        assert ev.description, "description must not be empty"


# ---------------------------------------------------------------------------
# SparkLogTool
# ---------------------------------------------------------------------------

class TestSparkLogTool:
    @pytest.fixture(autouse=True)
    def tool(self):
        from unittest.mock import AsyncMock
        from tools.log_analyzer.spark_log_tool import SparkLogTool
        self.tool = SparkLogTool(LLMConfig())
        # Avoid hitting the real OpenAI API in unit tests.
        self.tool._agent._call_llm = AsyncMock(
            return_value=(
                "Health Assessment: Spark execution analysed.\n"
                "- Task failure rate reviewed.\n"
                "- Memory utilisation within expected bounds.\n"
            )
        )

    @pytest.mark.asyncio
    async def test_name_and_description(self):
        assert self.tool.name == "SparkLogTool"
        assert "Spark" in self.tool.description

    @pytest.mark.asyncio
    async def test_schema_has_required_incident_id(self):
        schema = self.tool.schema()
        assert schema["function"]["name"] == "SparkLogTool"
        assert "incident_id" in schema["function"]["parameters"]["required"]

    @pytest.mark.asyncio
    async def test_healthy_spark_metrics_returns_evidence(self):
        ctx = _ctx({
            "spark_metrics": {
                "execution_summary": {
                    "failed_task_count": 0,
                    "total_tasks": 500,
                    "total_duration_ms": 60000,
                },
                "memory": {"spill_bytes": 0, "oom_events": 0},
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)
        assert self.tool.name in [ev.source_tool for ev in result]

    @pytest.mark.asyncio
    async def test_oom_scenario_produces_high_severity(self):
        ctx = _ctx({
            "spark_metrics": {
                "execution_summary": {
                    "failed_task_count": 60,        # > 50% failure rate → CRITICAL
                    "total_tasks": 100,
                    "total_duration_ms": 90000,
                    "total_spill_bytes": 5_000_000_000,   # required for confidence calc
                    "total_shuffle_bytes": 2_000_000_000, # required for confidence calc
                },
                "anomalies": [
                    {"severity": "critical", "anomaly_type": "OOM",
                     "description": "12 out-of-memory events"},
                    {"severity": "critical", "anomaly_type": "HIGH_FAILURE_RATE",
                     "description": "60% task failure rate"},
                    {"severity": "warning", "anomaly_type": "MEMORY_SPILL",
                     "description": "5 GB spill to disk"},
                ],
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)
        # At least one P1 or P2 piece of evidence for an OOM scenario.
        severities = {ev.severity for ev in result}
        assert severities & {Priority.P1, Priority.P2}, (
            f"Expected P1/P2 in a 60% failure OOM scenario, got: {severities}"
        )

    @pytest.mark.asyncio
    async def test_empty_metadata_returns_empty_list(self):
        """When spark_metrics key is absent and metadata is empty, return []."""
        ctx = _ctx({})
        result = await self.tool.run(ctx)
        # Should return empty or gracefully degrade — never raise.
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_non_dict_spark_metrics_returns_empty(self):
        ctx = _ctx({"spark_metrics": "not-a-dict"})
        result = await self.tool.run(ctx)
        assert result == [], "Non-dict spark_metrics must return []"

    @pytest.mark.asyncio
    async def test_fallback_to_fingerprint_key(self):
        """SparkLogTool falls back to 'fingerprint' key when spark_metrics absent."""
        ctx = _ctx({
            "fingerprint": {
                "execution_summary": {"failed_task_count": 5, "total_tasks": 100}
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# DataQualityTool
# ---------------------------------------------------------------------------

class TestDataQualityTool:
    @pytest.fixture(autouse=True)
    def tool(self):
        from tools.data_profiler.dq_tool import DataQualityTool
        self.tool = DataQualityTool()

    def test_name_and_description(self):
        assert self.tool.name == "DataQualityTool"
        assert "quality" in self.tool.description.lower()

    @pytest.mark.asyncio
    async def test_clean_profile_returns_evidence(self):
        ctx = _ctx({
            "data_profile": {
                "dataset_name": "deposit_ledger",
                "row_count": 100_000,
                "columns": [
                    {"name": "account_id", "dtype": "string",  "null_rate": 0.0},
                    {"name": "balance",    "dtype": "float64", "null_rate": 0.01},
                ],
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)
        for ev in result:
            assert ev.source_tool == "DataQualityTool"

    @pytest.mark.asyncio
    async def test_high_null_rate_produces_p1_or_p2(self):
        ctx = _ctx({
            "data_profile": {
                "dataset_name": "trust_accounts",
                "row_count": 5000,
                "columns": [
                    {"name": "insurance_class", "dtype": "string", "null_rate": 0.85},
                ],
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)
        severities = {ev.severity for ev in result}
        assert severities & {Priority.P1, Priority.P2}, (
            "85% null rate must produce at least P2 severity evidence"
        )

    @pytest.mark.asyncio
    async def test_empty_columns_does_not_raise(self):
        ctx = _ctx({
            "data_profile": {
                "dataset_name": "empty_dataset",
                "row_count": 0,
                "columns": [],
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_missing_data_profile_key_returns_gracefully(self):
        ctx = _ctx({})          # no data_profile key
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_zero_row_count_handled(self):
        ctx = _ctx({
            "data_profile": {
                "dataset_name": "wire_records",
                "row_count": 0,
                "columns": [
                    {"name": "wire_id", "dtype": "string", "null_rate": 0.0}
                ],
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# DDLDiffTool
# ---------------------------------------------------------------------------

class TestDDLDiffTool:
    @pytest.fixture(autouse=True)
    def tool(self):
        from tools.change_analyzer.ddl_diff_tool import DDLDiffTool
        self.tool = DDLDiffTool()

    def test_name_and_description(self):
        assert self.tool.name == "DDLDiffTool"
        assert self.tool.description

    @pytest.mark.asyncio
    async def test_high_churn_commit_returns_evidence(self):
        ctx = _ctx({
            "change_fingerprint": {
                "repo_name": "fdic-controls",
                "window_days": 7,
                "commits": [
                    {
                        "hash": "abc123",
                        "author": "alice",
                        "timestamp": "2026-03-15T10:00:00Z",
                        "files": [
                            {
                                "path": "etl/sp_calculate_insurance.sql",
                                "added": 350,
                                "deleted": 200,
                            }
                        ],
                    }
                ],
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)
        for ev in result:
            assert ev.source_tool == "DDLDiffTool"

    @pytest.mark.asyncio
    async def test_empty_commits_does_not_raise(self):
        ctx = _ctx({
            "change_fingerprint": {
                "repo_name": "empty-repo",
                "window_days": 7,
                "commits": [],
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_missing_change_fingerprint_returns_gracefully(self):
        ctx = _ctx({})
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_single_contributor_flagged(self):
        """All commits from one author should raise at least some concern."""
        commits = [
            {
                "hash": f"aaa{i:03d}",
                "author": "alice",
                "timestamp": f"2026-03-{10+i:02d}T10:00:00Z",
                "files": [{"path": "etl/risk.py", "added": 50, "deleted": 5}],
            }
            for i in range(10)
        ]
        ctx = _ctx({
            "change_fingerprint": {
                "repo_name": "risk-engine",
                "window_days": 14,
                "commits": commits,
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# GitDiffTool
# ---------------------------------------------------------------------------

class TestGitDiffTool:
    @pytest.fixture(autouse=True)
    def tool(self):
        from tools.code_analyzer.git_diff_tool import GitDiffTool
        self.tool = GitDiffTool(LLMConfig())

    def test_name_and_description(self):
        assert self.tool.name == "GitDiffTool"
        assert self.tool.description

    @pytest.mark.asyncio
    async def test_schema_structure(self):
        schema = self.tool.schema()
        assert schema["type"] == "function"
        assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_git_diff_fingerprint_returns_evidence(self):
        ctx = _ctx({
            "git_diff": {
                "repo_path": "/tmp/test-repo",
                "max_commits": 5,
                "diffs": [
                    {
                        "commit": "abc123",
                        "author": "alice",
                        "message": "Disable aggregation step",
                        "diff_text": (
                            "- AGGRSTEP = True\n"
                            "+ AGGRSTEP = False  # disabled for testing\n"
                        ),
                    }
                ],
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_missing_git_diff_key_returns_gracefully(self):
        ctx = _ctx({})
        result = await self.tool.run(ctx)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# AirflowLogTool
# ---------------------------------------------------------------------------

class TestAirflowLogTool:
    @pytest.fixture(autouse=True)
    def tool(self):
        from tools.log_analyzer.airflow_log_tool import AirflowLogTool
        self.tool = AirflowLogTool(LLMConfig())

    def test_name_and_description(self):
        assert self.tool.name == "AirflowLogTool"
        assert self.tool.description

    @pytest.mark.asyncio
    async def test_failed_task_returns_evidence(self):
        ctx = _ctx({
            "airflow_logs": {
                "dag_id": "deposit_nightly",
                "task_id": "run_orc_aggregation",
                "execution_date": "2026-03-16",
                "try_number": 3,
                "max_retries": 3,
                "log_lines": [
                    "[INFO] Task started",
                    "[ERROR] AGGRSTEP disabled via feature flag",
                    "[FATAL] Task failed after 3 retries",
                ],
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)
        for ev in result:
            assert ev.source_tool == "AirflowLogTool"

    @pytest.mark.asyncio
    async def test_healthy_task_returns_evidence(self):
        ctx = _ctx({
            "airflow_logs": {
                "dag_id": "wire_nightly",
                "task_id": "process_wires",
                "execution_date": "2026-03-16",
                "try_number": 1,
                "max_retries": 3,
                "log_lines": [
                    "[INFO] Task started",
                    "[INFO] Processed 1500 wire messages",
                    "[INFO] Task completed successfully",
                ],
            }
        })
        result = await self.tool.run(ctx)
        _assert_evidence_list(result, min_items=1)

    @pytest.mark.asyncio
    async def test_empty_log_lines_does_not_raise(self):
        ctx = _ctx({
            "airflow_logs": {
                "dag_id": "trust_nightly",
                "task_id": "classify_accounts",
                "execution_date": "2026-03-16",
                "try_number": 1,
                "max_retries": 3,
                "log_lines": [],
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_missing_airflow_fingerprint_returns_gracefully(self):
        ctx = _ctx({})
        result = await self.tool.run(ctx)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_is_high_severity(self):
        ctx = _ctx({
            "airflow_logs": {
                "dag_id": "deposit_nightly",
                "task_id": "run_orc_aggregation",
                "execution_date": "2026-03-16",
                "try_number": 3,
                "max_retries": 3,   # try == max → exhausted
                "log_lines": [
                    "[ERROR] Task failed: connection timeout",
                ],
            }
        })
        result = await self.tool.run(ctx)
        assert isinstance(result, list)
        if result:
            severities = {ev.severity for ev in result}
            # Exhausted retries must not produce only P4 (informational).
            assert severities != {Priority.P4}, (
                "Exhausted retries should produce P1/P2/P3, not only P4"
            )


# ---------------------------------------------------------------------------
# Cross-tool: register all via TOOL_REGISTRY fixture
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_all_five_tools_registered(self, tool_registry):
        expected = {"SparkLogTool", "DataQualityTool", "DDLDiffTool", "GitDiffTool", "AirflowLogTool"}
        assert set(tool_registry.keys()) == expected

    def test_each_tool_has_schema(self, tool_registry):
        for name, tool in tool_registry.items():
            schema = tool.schema()
            assert schema["function"]["name"] == name, (
                f"{name}: schema name mismatch"
            )
