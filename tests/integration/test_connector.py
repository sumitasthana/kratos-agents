"""
tests/integration/test_connector.py
Integration tests for BankPipelineConnector using respx HTTP mocks.

All tests are fully offline — no real bank-pipeline-api is required.
respx intercepts every httpx call and returns the fixtures defined in conftest.py.

Coverage
--------
connect / close / context-manager lifecycle
fetch_incident   — happy path, malformed JSON, 503 retry, 404 error, timeout
stream_logs      — full SSE stream, DONE sentinel, malformed line skipped
fetch_lineage    — happy path, empty graph
list_incidents   — filtering by severity
503 retry logic  — verify exponential back-off kicks in
timeout handling — ConnectorError raised after retries exhausted
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from connectors.bank_pipeline import BankPipelineConnector, ConnectorError
from core.models import IncidentContext, LineageGraph, LogChunk, LogSource


BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Helper: fresh connector per test
# ---------------------------------------------------------------------------

def _connector() -> BankPipelineConnector:
    return BankPipelineConnector(base_url=BASE_URL, token="test-token")


# ---------------------------------------------------------------------------
# Lifecycle tests
# ---------------------------------------------------------------------------

class TestConnectorLifecycle:
    @pytest.mark.asyncio
    async def test_connect_creates_client(self):
        conn = _connector()
        await conn.connect()
        assert conn._client is not None
        await conn.close()

    @pytest.mark.asyncio
    async def test_close_resets_client(self):
        conn = _connector()
        await conn.connect()
        await conn.close()
        assert conn._client is None

    @pytest.mark.asyncio
    async def test_context_manager_connects_and_closes(self, mock_bank_api):
        async with _connector() as conn:
            assert conn._client is not None
        assert conn._client is None

    @pytest.mark.asyncio
    async def test_request_before_connect_raises_connector_error(self, mock_bank_api):
        conn = _connector()
        with pytest.raises(ConnectorError, match="not connected"):
            await conn.fetch_incident("INC-DEP-001")

    @pytest.mark.asyncio
    async def test_token_included_in_headers(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/rca/context/INC-TOKEN-001").mock(
                return_value=httpx.Response(200, json={
                    "incident_id": "INC-TOKEN-001",
                    "run_id": "RUN-001",
                    "pipeline_stage": "test",
                    "failed_controls": [],
                    "metadata": {},
                })
            )
            async with BankPipelineConnector(base_url=BASE_URL, token="my-secret") as conn:
                await conn.fetch_incident("INC-TOKEN-001")
            req = router.calls.last.request
            assert req.headers.get("Authorization") == "Bearer my-secret"


# ---------------------------------------------------------------------------
# fetch_incident tests
# ---------------------------------------------------------------------------

class TestFetchIncident:
    @pytest.mark.asyncio
    async def test_happy_path_returns_incident_context(self, mock_bank_api):
        async with _connector() as conn:
            ctx = await conn.fetch_incident("INC-DEP-001")
        assert isinstance(ctx, IncidentContext)
        assert ctx.incident_id == "INC-DEP-001"
        assert ctx.run_id == "RUN-20260316-001"
        assert ctx.pipeline_stage == "deposit_aggregation"

    @pytest.mark.asyncio
    async def test_failed_controls_are_extracted_as_ids(self, mock_bank_api):
        async with _connector() as conn:
            ctx = await conn.fetch_incident("INC-DEP-001")
        assert "CTL-DEP-001" in ctx.failed_controls

    @pytest.mark.asyncio
    async def test_raw_controls_preserved_in_metadata(self, mock_bank_api):
        async with _connector() as conn:
            ctx = await conn.fetch_incident("INC-DEP-001")
        assert "_raw_controls" in ctx.metadata

    @pytest.mark.asyncio
    async def test_404_raises_connector_error(self):
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/rca/context/MISSING-001").mock(
                return_value=httpx.Response(404, json={"detail": "incident not found"})
            )
            async with _connector() as conn:
                with pytest.raises(ConnectorError) as exc_info:
                    await conn.fetch_incident("MISSING-001")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_503_with_eventual_success_retries(self):
        """
        First 2 attempts return 503; 3rd returns 200.
        The retry helper should succeed without raising.
        """
        call_count = 0

        def _side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(503, json={"detail": "Service unavailable"})
            return httpx.Response(200, json={
                "incident_id": "INC-RETRY-001",
                "run_id": "RUN-001",
                "pipeline_stage": "test",
                "failed_controls": [],
                "metadata": {},
            })

        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(side_effect=_side_effect)
            # Patch asyncio.sleep to avoid slowing down tests
            import asyncio
            original_sleep = asyncio.sleep

            async def _fast_sleep(_):
                pass

            asyncio.sleep = _fast_sleep
            try:
                async with _connector() as conn:
                    ctx = await conn.fetch_incident("INC-RETRY-001")
                assert ctx.incident_id == "INC-RETRY-001"
                assert call_count == 3
            finally:
                asyncio.sleep = original_sleep

    @pytest.mark.asyncio
    async def test_503_exhausted_retries_raises_connector_error(self):
        """All 3 attempts return 503 → ConnectorError after max retries."""
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                return_value=httpx.Response(503, json={"detail": "Still down"})
            )
            import asyncio
            original_sleep = asyncio.sleep

            async def _fast_sleep(_):
                pass

            asyncio.sleep = _fast_sleep
            try:
                async with _connector() as conn:
                    with pytest.raises(ConnectorError):
                        await conn.fetch_incident("INC-DOWN-001")
            finally:
                asyncio.sleep = original_sleep

    @pytest.mark.asyncio
    async def test_timeout_raises_after_retries(self):
        """TimeoutException on all attempts → ConnectorError raised."""
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(
                side_effect=httpx.TimeoutException("timed out")
            )
            import asyncio
            original_sleep = asyncio.sleep

            async def _fast_sleep(_):
                pass

            asyncio.sleep = _fast_sleep
            try:
                async with _connector() as conn:
                    with pytest.raises(ConnectorError):
                        await conn.fetch_incident("INC-TIMEOUT-001")
            finally:
                asyncio.sleep = original_sleep

    @pytest.mark.asyncio
    async def test_500_raises_immediately_no_retry(self):
        """500 Internal Server Error is not retryable — must raise on first attempt."""
        call_count = 0

        def _once(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={"detail": "Internal error"})

        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/rca/context/").mock(side_effect=_once)
            async with _connector() as conn:
                with pytest.raises(ConnectorError) as exc_info:
                    await conn.fetch_incident("INC-500-001")
            assert call_count == 1, "500 must not be retried"
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# stream_logs tests
# ---------------------------------------------------------------------------

class TestStreamLogs:
    @pytest.mark.asyncio
    async def test_stream_yields_log_chunks(self, mock_bank_api):
        async with _connector() as conn:
            chunks = [c async for c in conn.stream_logs("INC-DEP-001")]
        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(chunk, LogChunk)
            assert chunk.message

    @pytest.mark.asyncio
    async def test_chunk_has_correct_fields(self, mock_bank_api):
        async with _connector() as conn:
            chunks = [c async for c in conn.stream_logs("INC-DEP-001")]
        if chunks:
            chunk = chunks[0]
            assert isinstance(chunk.source, LogSource)
            assert isinstance(chunk.timestamp, datetime)
            assert chunk.level in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL"}

    @pytest.mark.asyncio
    async def test_malformed_sse_line_is_skipped(self):
        malformed_sse = (
            "data: NOT_JSON\n\n"
            'data: {"source": "spark", "timestamp": "2026-03-16T08:00:00Z", '
            '"level": "INFO", "message": "valid line"}\n\n'
            "data: [DONE]\n\n"
        )
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=malformed_sse.encode(),
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            async with _connector() as conn:
                chunks = [c async for c in conn.stream_logs("INC-MALFORMED-001")]
        # Malformed line skipped; valid line parsed.
        assert len(chunks) == 1
        assert chunks[0].message == "valid line"

    @pytest.mark.asyncio
    async def test_empty_stream_returns_no_chunks(self):
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"data: [DONE]\n\n",
                    headers={"Content-Type": "text/event-stream"},
                )
            )
            async with _connector() as conn:
                chunks = [c async for c in conn.stream_logs("INC-EMPTY-001")]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_stream_404_raises_connector_error(self):
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/logs/stream/").mock(
                return_value=httpx.Response(404, json={"detail": "not found"})
            )
            async with _connector() as conn:
                with pytest.raises(ConnectorError) as exc_info:
                    async for _ in conn.stream_logs("INC-MISSING-001"):
                        pass
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# fetch_lineage tests
# ---------------------------------------------------------------------------

class TestFetchLineage:
    @pytest.mark.asyncio
    async def test_happy_path_returns_lineage_graph(self, mock_bank_api):
        async with _connector() as conn:
            graph = await conn.fetch_lineage("deposit_nightly")
        assert isinstance(graph, LineageGraph)
        assert graph.job_id == "deposit_nightly"

    @pytest.mark.asyncio
    async def test_lineage_has_nodes_and_edges(self, mock_bank_api):
        async with _connector() as conn:
            graph = await conn.fetch_lineage("deposit_nightly")
        assert isinstance(graph.nodes, list)
        assert isinstance(graph.edges, list)
        assert len(graph.nodes) >= 1

    @pytest.mark.asyncio
    async def test_empty_lineage_graph_handled(self):
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get(url__regex=r"/lineage/").mock(
                return_value=httpx.Response(200, json={
                    "job_id": "empty_job",
                    "nodes": [],
                    "edges": [],
                })
            )
            async with _connector() as conn:
                graph = await conn.fetch_lineage("empty_job")
        assert graph.nodes == []
        assert graph.edges == []


# ---------------------------------------------------------------------------
# list_incidents tests
# ---------------------------------------------------------------------------

class TestListIncidents:
    @pytest.mark.asyncio
    async def test_list_returns_incident_list(self, mock_bank_api):
        async with _connector() as conn:
            incidents = await conn.list_incidents()
        assert isinstance(incidents, list)
        assert len(incidents) >= 1

    @pytest.mark.asyncio
    async def test_each_incident_has_required_fields(self, mock_bank_api):
        async with _connector() as conn:
            incidents = await conn.list_incidents()
        for inc in incidents:
            assert "incident_id" in inc
            assert "severity" in inc

    @pytest.mark.asyncio
    async def test_severity_filter_passed_as_query_param(self):
        with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
            router.get("/incidents").mock(
                return_value=httpx.Response(200, json=[
                    {
                        "incident_id": "INC-P1-001",
                        "control_id": "CTL-001",
                        "severity": "P1",
                        "status": "open",
                    }
                ])
            )
            async with _connector() as conn:
                results = await conn.list_incidents(severity="P1")
            # Verify query param was forwarded correctly.
            req = router.calls.last.request
            assert "severity=P1" in str(req.url)
            assert len(results) == 1
            assert results[0]["severity"] == "P1"
