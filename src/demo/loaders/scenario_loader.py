"""
src/demo/loaders/scenario_loader.py

ScenarioLoader — loads a complete scenario pack from disk.

All JSON files inside a scenario folder are small and are loaded
synchronously with json.load().  Logs are read as plain text.

Usage::

    loader = ScenarioLoader("deposit_aggregation_failure")
    pack   = loader.pack          # ScenarioPack dataclass
    log    = loader.log_text      # raw log file content
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Root of the scenarios/ folder — resolved relative to this file's location.
_SCENARIOS_ROOT = Path(__file__).resolve().parents[3] / "scenarios"


@dataclass
class ScenarioPack:
    """All metadata for a single demo scenario."""

    scenario_id: str
    incident: Dict[str, Any]
    controls: List[Dict[str, Any]]
    job_run: Dict[str, Any]
    accounts: List[Dict[str, Any]]
    log_text: str
    log_filename: str
    scenario_dir: Path

    # Convenience accessors
    @property
    def incident_id(self) -> str:
        return self.incident["incident_id"]

    @property
    def anchor_id(self) -> str:
        return self.incident.get("anchor_id", self.incident_id)

    @property
    def job_id(self) -> str:
        return self.job_run["job_id"]

    @property
    def failed_controls(self) -> List[Dict[str, Any]]:
        return [c for c in self.controls if c.get("status") == "FAILED"]


class ScenarioLoader:
    """
    Loads and validates the full file pack for *scenario_id*.

    Raises FileNotFoundError when the scenario folder or any required
    file is missing; raises ValueError when mandatory JSON keys are absent.
    """

    _REQUIRED_INCIDENT_KEYS = {"incident_id", "severity", "anchor_type", "anchor_id"}
    _REQUIRED_JOB_KEYS = {"job_id", "status", "started_at"}

    def __init__(self, scenario_id: str, scenarios_root: Optional[Path] = None) -> None:
        self.scenario_id = scenario_id
        root = scenarios_root or _SCENARIOS_ROOT
        self.scenario_dir = root / scenario_id

        if not self.scenario_dir.is_dir():
            raise FileNotFoundError(
                f"Scenario directory not found: {self.scenario_dir}"
            )

        self._pack: Optional[ScenarioPack] = None

    @property
    def pack(self) -> ScenarioPack:
        if self._pack is None:
            self._pack = self._load()
        return self._pack

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_json(self, relative_path: str) -> Any:
        full = self.scenario_dir / relative_path
        if not full.exists():
            raise FileNotFoundError(
                f"Required scenario file not found: {full}"
            )
        with open(full, encoding="utf-8") as fh:
            return json.load(fh)

    def _load_log(self) -> tuple[str, str]:
        log_dir = self.scenario_dir / "logs"
        if not log_dir.is_dir():
            raise FileNotFoundError(
                f"logs/ directory not found in scenario: {self.scenario_dir}"
            )
        log_files = list(log_dir.glob("*.log"))
        if not log_files:
            raise FileNotFoundError(
                f"No .log files found in {log_dir}"
            )
        log_file = sorted(log_files)[0]
        with open(log_file, encoding="utf-8") as fh:
            return fh.read(), log_file.name

    def _validate_incident(self, data: Dict[str, Any]) -> None:
        missing = self._REQUIRED_INCIDENT_KEYS - data.keys()
        if missing:
            raise ValueError(
                f"incident.json missing required keys {missing} "
                f"for scenario '{self.scenario_id}'"
            )

    def _validate_job_run(self, data: Dict[str, Any]) -> None:
        missing = self._REQUIRED_JOB_KEYS - data.keys()
        if missing:
            raise ValueError(
                f"job_run.json missing required keys {missing} "
                f"for scenario '{self.scenario_id}'"
            )

    def _load(self) -> ScenarioPack:
        logger.info("Loading scenario pack: %s", self.scenario_id)

        incident = self._load_json("incident.json")
        self._validate_incident(incident)

        controls = self._load_json("controls.json")
        if not isinstance(controls, list):
            raise ValueError(
                f"controls.json must be a JSON array for scenario '{self.scenario_id}'"
            )

        job_run = self._load_json("job_run.json")
        self._validate_job_run(job_run)

        accounts_path = self.scenario_dir / "sample_data" / "accounts.json"
        if accounts_path.exists():
            with open(accounts_path, encoding="utf-8") as fh:
                accounts = json.load(fh)
        else:
            accounts = []
            logger.warning(
                "sample_data/accounts.json not found for scenario '%s'",
                self.scenario_id,
            )

        log_text, log_filename = self._load_log()

        pack = ScenarioPack(
            scenario_id=self.scenario_id,
            incident=incident,
            controls=controls,
            job_run=job_run,
            accounts=accounts,
            log_text=log_text,
            log_filename=log_filename,
            scenario_dir=self.scenario_dir,
        )
        logger.info(
            "Loaded scenario '%s': incident=%s, controls=%d, accounts=%d",
            self.scenario_id,
            pack.incident_id,
            len(controls),
            len(accounts),
        )
        return pack
