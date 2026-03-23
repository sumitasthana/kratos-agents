"""
src/demo/scenario_registry.py

ScenarioRegistry — auto-discovers all scenario folders under scenarios/.

A scenario folder is valid if it contains at minimum:
  - incident.json
  - job_run.json
  - controls.json

Adding a 4th scenario requires only dropping a new folder here plus entries
in canon_graphs.py and patterns/library.py — no changes to services or API.

Usage::

    registry = ScenarioRegistry()
    summaries = registry.list_scenarios()
    pack      = registry.get_pack("deposit_aggregation_failure")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .loaders.scenario_loader import ScenarioPack, ScenarioLoader

logger = logging.getLogger(__name__)

_SCENARIOS_ROOT = Path(__file__).resolve().parents[2] / "scenarios"

_REQUIRED_FILES = {"incident.json", "job_run.json", "controls.json"}


class ScenarioSummary:
    """Lightweight description of a scenario (no log text loaded)."""

    def __init__(self, pack: ScenarioPack) -> None:
        inc = pack.incident
        job = pack.job_run
        self.scenario_id: str = pack.scenario_id
        self.incident_id: str = pack.incident_id
        self.title: str = inc.get("title", pack.scenario_id)
        self.severity: str = inc.get("severity", "UNKNOWN")
        self.regulation: str = inc.get("regulation", "")
        self.defect_id: str = inc.get("defect_id", "")
        self.control_id: str = inc.get("control_id", "")
        self.job_id: str = pack.job_id
        self.job_status: str = job.get("status", "UNKNOWN")
        self.total_controls: int = len(pack.controls)
        self.failed_controls: int = len(pack.failed_controls)
        self.total_accounts: int = len(pack.accounts)
        self.log_filename: str = pack.log_filename

    def to_dict(self) -> dict:
        return {
            "scenario_id":      self.scenario_id,
            "incident_id":      self.incident_id,
            "title":            self.title,
            "severity":         self.severity,
            "regulation":       self.regulation,
            "defect_id":        self.defect_id,
            "control_id":       self.control_id,
            "job_id":           self.job_id,
            "job_status":       self.job_status,
            "total_controls":   self.total_controls,
            "failed_controls":  self.failed_controls,
            "total_accounts":   self.total_accounts,
            "log_filename":     self.log_filename,
        }


class ScenarioRegistry:
    """
    Auto-discovering registry of demo scenarios.

    On construction, scans *scenarios_root* for valid scenario directories
    and loads each one via ScenarioLoader.  Invalid or partially-built
    directories are skipped with a warning.
    """

    def __init__(self, scenarios_root: Optional[Path] = None) -> None:
        self._root = scenarios_root or _SCENARIOS_ROOT
        self._packs: Dict[str, ScenarioPack] = {}
        self._scan()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_scenarios(self) -> List[ScenarioSummary]:
        """Return summaries for all discovered scenarios (sorted by ID)."""
        return [ScenarioSummary(pack) for pack in sorted(
            self._packs.values(), key=lambda p: p.scenario_id
        )]

    def get_pack(self, scenario_id: str) -> ScenarioPack:
        """Return the full ScenarioPack for *scenario_id*.  Raises KeyError if not found."""
        if scenario_id not in self._packs:
            raise KeyError(
                f"Scenario '{scenario_id}' not found. "
                f"Available: {sorted(self._packs.keys())}"
            )
        return self._packs[scenario_id]

    def has_scenario(self, scenario_id: str) -> bool:
        return scenario_id in self._packs

    def scenario_ids(self) -> List[str]:
        return sorted(self._packs.keys())

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _scan(self) -> None:
        if not self._root.is_dir():
            logger.warning("Scenarios root not found: %s", self._root)
            return

        for candidate in sorted(self._root.iterdir()):
            if not candidate.is_dir():
                continue
            if not self._is_valid_scenario_dir(candidate):
                logger.debug("Skipping non-scenario directory: %s", candidate.name)
                continue
            try:
                loader = ScenarioLoader(candidate.name, scenarios_root=self._root)
                self._packs[candidate.name] = loader.pack
                logger.info("Registered scenario: %s", candidate.name)
            except (FileNotFoundError, ValueError) as exc:
                logger.warning(
                    "Failed to load scenario '%s': %s", candidate.name, exc
                )

        logger.info(
            "ScenarioRegistry: %d scenario(s) loaded from %s",
            len(self._packs),
            self._root,
        )

    def _is_valid_scenario_dir(self, path: Path) -> bool:
        present = {f.name for f in path.iterdir() if f.is_file()}
        return _REQUIRED_FILES.issubset(present)
