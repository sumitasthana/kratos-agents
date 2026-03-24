"""
tests/demo/test_demo_api.py

HTTP-level tests for the Demo API (src/demo_api.py).

Uses FastAPI's TestClient (synchronous httpx-based transport) — no running
server needed.  The TestClient fires the startup event automatically, which
initialises ScenarioRegistry, ControlScanner, and DemoRcaService singletons.

SSE streaming is exercised via a lightweight coroutine helper rather than a
live EventSource, because TestClient cannot consume true server-sent events.
The streaming endpoint is tested at the response header and first-chunk levels.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

# The app is in src/demo_api.py — sys.path already contains the project root
# because pytest is run from the repo root.
from demo_api import app  # type: ignore[import]

# ---------------------------------------------------------------------------
# Single shared client — the startup event is fired once.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


# ---------------------------------------------------------------------------
# /demo/health
# ---------------------------------------------------------------------------

class TestHealth:

    def test_health_ok(self, client: TestClient) -> None:
        r = client.get("/demo/health")
        assert r.status_code == 200

    def test_health_status_ok(self, client: TestClient) -> None:
        data = client.get("/demo/health").json()
        assert data["status"] == "ok"

    def test_health_scenario_count(self, client: TestClient) -> None:
        data = client.get("/demo/health").json()
        assert data["scenario_count"] == 3

    def test_health_scenarios_list(self, client: TestClient) -> None:
        data = client.get("/demo/health").json()
        expected = {
            "deposit_aggregation_failure",
            "trust_irr_misclassification",
            "wire_mt202_drop",
        }
        assert set(data["scenarios"]) == expected


# ---------------------------------------------------------------------------
# GET /demo/scenarios
# ---------------------------------------------------------------------------

class TestListScenarios:

    def test_list_scenarios_200(self, client: TestClient) -> None:
        r = client.get("/demo/scenarios")
        assert r.status_code == 200

    def test_list_scenarios_total_3(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios").json()
        assert data["total"] == 3

    def test_list_scenarios_items_length(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios").json()
        assert len(data["items"]) == 3

    def test_list_scenarios_has_scenario_ids(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios").json()
        ids = {item["scenario_id"] for item in data["items"]}
        expected = {
            "deposit_aggregation_failure",
            "trust_irr_misclassification",
            "wire_mt202_drop",
        }
        assert ids == expected

    def test_list_scenarios_items_have_title(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios").json()
        for item in data["items"]:
            assert "title" in item and item["title"]


# ---------------------------------------------------------------------------
# GET /demo/scenarios/{scenario_id}
# ---------------------------------------------------------------------------

class TestGetScenario:

    @pytest.mark.parametrize("scenario_id", [
        "deposit_aggregation_failure",
        "trust_irr_misclassification",
        "wire_mt202_drop",
    ])
    def test_valid_scenario_200(self, client: TestClient, scenario_id: str) -> None:
        r = client.get(f"/demo/scenarios/{scenario_id}")
        assert r.status_code == 200

    def test_scenario_has_incident(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios/deposit_aggregation_failure").json()
        assert "incident" in data
        assert "incident_id" in data["incident"]

    def test_scenario_has_controls(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios/deposit_aggregation_failure").json()
        assert "controls" in data
        assert isinstance(data["controls"], list)
        assert len(data["controls"]) > 0

    def test_scenario_has_accounts(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios/wire_mt202_drop").json()
        assert "accounts" in data
        assert isinstance(data["accounts"], list)

    def test_scenario_has_log_filename(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios/trust_irr_misclassification").json()
        assert "log_filename" in data
        assert data["log_filename"]

    def test_unknown_scenario_404(self, client: TestClient) -> None:
        r = client.get("/demo/scenarios/ghost_scenario_404")
        assert r.status_code == 404

    def test_unknown_scenario_error_code(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios/ghost_scenario_404").json()
        assert data["error"] == "SCENARIO_NOT_FOUND"

    def test_unknown_scenario_has_available_list(self, client: TestClient) -> None:
        data = client.get("/demo/scenarios/ghost_scenario_404").json()
        assert "available" in data.get("detail", {})


# ---------------------------------------------------------------------------
# GET /demo/controls/{scenario_id}
# ---------------------------------------------------------------------------

class TestControlScan:

    @pytest.mark.parametrize("scenario_id", [
        "deposit_aggregation_failure",
        "trust_irr_misclassification",
        "wire_mt202_drop",
    ])
    def test_control_scan_200(self, client: TestClient, scenario_id: str) -> None:
        r = client.get(f"/demo/controls/{scenario_id}")
        assert r.status_code == 200

    def test_control_scan_has_findings(self, client: TestClient) -> None:
        data = client.get("/demo/controls/deposit_aggregation_failure").json()
        assert "findings" in data
        assert isinstance(data["findings"], list)

    def test_control_scan_has_total_controls(self, client: TestClient) -> None:
        data = client.get("/demo/controls/wire_mt202_drop").json()
        assert "total_controls" in data
        assert data["total_controls"] >= 1

    def test_control_scan_unknown_scenario_404(self, client: TestClient) -> None:
        r = client.get("/demo/controls/ghost_404")
        assert r.status_code == 404

    def test_control_scan_unknown_error_code(self, client: TestClient) -> None:
        data = client.get("/demo/controls/ghost_404").json()
        assert data["error"] == "SCENARIO_NOT_FOUND"


# ---------------------------------------------------------------------------
# POST /demo/investigations
# ---------------------------------------------------------------------------

class TestStartInvestigation:

    def _post(self, client: TestClient, body: Dict[str, Any]) -> Any:
        return client.post("/demo/investigations", json=body)

    def test_start_investigation_201(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": "deposit_aggregation_failure"})
        assert r.status_code == 201

    def test_response_has_investigation_id(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": "deposit_aggregation_failure"})
        data = r.json()
        assert "investigation_id" in data
        assert data["investigation_id"]

    def test_response_status_started(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": "trust_irr_misclassification"})
        data = r.json()
        assert data["status"] == "STARTED"

    def test_response_echoes_scenario_id(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": "wire_mt202_drop"})
        data = r.json()
        assert data["scenario_id"] == "wire_mt202_drop"

    def test_explicit_job_id_accepted(self, client: TestClient) -> None:
        r = self._post(
            client,
            {"scenario_id": "deposit_aggregation_failure", "job_id": "DAILY-INSURANCE-JOB-20260316"},
        )
        assert r.status_code == 201
        assert r.json()["job_id"] == "DAILY-INSURANCE-JOB-20260316"

    def test_missing_scenario_id_400(self, client: TestClient) -> None:
        r = self._post(client, {"job_id": "SOME-JOB"})
        assert r.status_code == 400

    def test_missing_scenario_id_error_code(self, client: TestClient) -> None:
        r = self._post(client, {"job_id": "SOME-JOB"})
        assert r.json()["error"] == "MISSING_SCENARIO_ID"

    def test_empty_scenario_id_400(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": ""})
        assert r.status_code == 400

    def test_unknown_scenario_id_404(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": "scenario_does_not_exist"})
        assert r.status_code == 404

    def test_unknown_scenario_id_error_code(self, client: TestClient) -> None:
        r = self._post(client, {"scenario_id": "scenario_does_not_exist"})
        assert r.json()["error"] == "SCENARIO_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /demo/investigations/{id}  and  GET …/trace  and  GET …/graph
# ---------------------------------------------------------------------------

class TestGetInvestigation:

    @pytest.fixture(scope="class")
    def inv_id(self, client: TestClient) -> str:
        r = client.post(
            "/demo/investigations",
            json={"scenario_id": "deposit_aggregation_failure"},
        )
        assert r.status_code == 201
        return r.json()["investigation_id"]

    def test_get_investigation_200(self, client: TestClient, inv_id: str) -> None:
        r = client.get(f"/demo/investigations/{inv_id}")
        assert r.status_code == 200

    def test_get_investigation_has_status(self, client: TestClient, inv_id: str) -> None:
        data = client.get(f"/demo/investigations/{inv_id}").json()
        assert "status" in data

    def test_get_investigation_unknown_404(self, client: TestClient) -> None:
        r = client.get("/demo/investigations/inv-does-not-exist-xyz")
        assert r.status_code == 404

    def test_get_investigation_unknown_error_code(self, client: TestClient) -> None:
        data = client.get("/demo/investigations/inv-does-not-exist-xyz").json()
        assert data["error"] == "INVESTIGATION_NOT_FOUND"

    def test_trace_endpoint_200(self, client: TestClient, inv_id: str) -> None:
        r = client.get(f"/demo/investigations/{inv_id}/trace")
        assert r.status_code == 200

    def test_trace_returns_items_and_total(self, client: TestClient, inv_id: str) -> None:
        data = client.get(f"/demo/investigations/{inv_id}/trace").json()
        assert "items" in data
        assert "total" in data

    def test_trace_unknown_404(self, client: TestClient) -> None:
        r = client.get("/demo/investigations/unknown-xyz/trace")
        assert r.status_code == 404

    def test_graph_endpoint_200(self, client: TestClient, inv_id: str) -> None:
        r = client.get(f"/demo/investigations/{inv_id}/graph")
        assert r.status_code == 200

    def test_graph_has_nodes(self, client: TestClient, inv_id: str) -> None:
        data = client.get(f"/demo/investigations/{inv_id}/graph").json()
        assert "nodes" in data

    def test_graph_has_edges(self, client: TestClient, inv_id: str) -> None:
        data = client.get(f"/demo/investigations/{inv_id}/graph").json()
        assert "edges" in data

    def test_graph_unknown_404(self, client: TestClient) -> None:
        r = client.get("/demo/investigations/unknown-xyz/graph")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /demo/stream/{investigation_id} — header-level check only
# ---------------------------------------------------------------------------

class TestStreamEndpoint:

    def test_stream_content_type(self, client: TestClient) -> None:
        # First create an investigation to stream
        r = client.post(
            "/demo/investigations",
            json={"scenario_id": "wire_mt202_drop"},
        )
        assert r.status_code == 201
        inv_id = r.json()["investigation_id"]

        # Stream endpoint should return text/event-stream
        with client.stream("GET", f"/demo/stream/{inv_id}") as resp:
            assert resp.status_code == 200
            ct = resp.headers.get("content-type", "")
            assert "text/event-stream" in ct

    def test_stream_yields_data_events(self, client: TestClient) -> None:
        r = client.post(
            "/demo/investigations",
            json={"scenario_id": "trust_irr_misclassification"},
        )
        inv_id = r.json()["investigation_id"]

        lines_seen: list[str] = []
        with client.stream("GET", f"/demo/stream/{inv_id}") as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    lines_seen.append(line)
                if len(lines_seen) >= 1:
                    break

        assert len(lines_seen) >= 1
        payload = json.loads(lines_seen[0].removeprefix("data:").strip())
        assert "phase" in payload

    def test_stream_unknown_investigation_404(self, client: TestClient) -> None:
        r = client.get("/demo/stream/unknown-inv-xyz")
        assert r.status_code == 404
