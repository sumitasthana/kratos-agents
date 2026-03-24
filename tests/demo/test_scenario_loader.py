"""
tests/demo/test_scenario_loader.py

Tests for ScenarioLoader and ScenarioRegistry.
No external dependencies — all file I/O is against the real scenarios/ folder.
"""

from __future__ import annotations

import pytest

from demo.loaders.scenario_loader import ScenarioLoader
from demo.scenario_registry import ScenarioRegistry


SCENARIO_IDS = [
    "deposit_aggregation_failure",
    "trust_irr_misclassification",
    "wire_mt202_drop",
]


# ── ScenarioLoader ─────────────────────────────────────────────────────────────


class TestScenarioLoader:

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_load_returns_pack(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert pack.scenario_id == scenario_id

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_incident_has_required_keys(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert "incident_id" in pack.incident
        assert "severity" in pack.incident
        assert "anchor_type" in pack.incident

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_controls_non_empty(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert len(pack.controls) > 0, "each scenario must have at least one control"

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_job_run_has_job_id(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert "job_id" in pack.job_run

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_log_text_non_empty(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert len(pack.log_text) > 20, "log text must contain real content"

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_accounts_non_empty(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert len(pack.accounts) > 0, "each scenario must have sample accounts"

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_incident_id_property(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert pack.incident_id == pack.incident["incident_id"]

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_job_id_property(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        assert pack.job_id == pack.job_run["job_id"]

    @pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
    def test_failed_controls_property(self, scenario_id: str) -> None:
        pack = ScenarioLoader(scenario_id).load()
        failed = pack.failed_controls
        # All failed controls must be from the controls list
        control_ids = {c["control_id"] for c in pack.controls}
        for fc in failed:
            assert fc["control_id"] in control_ids

    def test_unknown_scenario_raises(self) -> None:
        with pytest.raises((FileNotFoundError, ValueError, KeyError)):
            ScenarioLoader("nonexistent_scenario").load()

    def test_deposit_log_contains_signal(self) -> None:
        pack = ScenarioLoader("deposit_aggregation_failure").load()
        assert "AGGRSTEP" in pack.log_text

    def test_trust_log_contains_signal(self) -> None:
        pack = ScenarioLoader("trust_irr_misclassification").load()
        assert "IRR" in pack.log_text

    def test_wire_log_contains_signal(self) -> None:
        pack = ScenarioLoader("wire_mt202_drop").load()
        assert "MT202" in pack.log_text or "silently dropped" in pack.log_text


# ── ScenarioRegistry ───────────────────────────────────────────────────────────


class TestScenarioRegistry:

    def test_registry_loads_all_three(self) -> None:
        reg = ScenarioRegistry()
        ids = reg.scenario_ids()
        for sid in SCENARIO_IDS:
            assert sid in ids, f"Expected '{sid}' in registry"

    def test_has_scenario_true(self) -> None:
        reg = ScenarioRegistry()
        assert reg.has_scenario("deposit_aggregation_failure")

    def test_has_scenario_false(self) -> None:
        reg = ScenarioRegistry()
        assert not reg.has_scenario("ghost_scenario_xyz")

    def test_get_pack_returns_correct_scenario(self) -> None:
        reg = ScenarioRegistry()
        pack = reg.get_pack("wire_mt202_drop")
        assert pack.scenario_id == "wire_mt202_drop"

    def test_get_pack_raises_for_unknown(self) -> None:
        reg = ScenarioRegistry()
        with pytest.raises(KeyError):
            reg.get_pack("ghost_scenario_xyz")

    def test_list_scenarios_returns_summaries(self) -> None:
        reg = ScenarioRegistry()
        summaries = reg.list_scenarios()
        assert len(summaries) >= 3
        for s in summaries:
            assert s.scenario_id in SCENARIO_IDS
