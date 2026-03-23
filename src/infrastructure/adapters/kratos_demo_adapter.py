"""
src/infrastructure/adapters/kratos_demo_adapter.py

KratosDemoAdapter — concrete InfrastructureAdapter for the 3-scenario demo.

Reads from:
  - scenarios/{scenario_id}/  (incident.json, controls.json, job_run.json, logs/)
  - data/kratos_data_20260316_1339.csv  (filtered by scenario)
  - operational_systems/  (for artifact code snippets — read-only)

Auto-registers on import.  Include this module in demo_api.py startup
or demo_rca_service.py to make "kratos_demo" available from get_adapter().
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.infrastructure.base_adapter import InfrastructureAdapter, register_adapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants (resolved at import time — fail fast if repo not found)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCENARIOS_DIR = _REPO_ROOT / "scenarios"
_CSV_PATH = _REPO_ROOT / "data" / "kratos_data_20260316_1339.csv"
_OP_ROOT = _REPO_ROOT / "operational_systems"

# ORC codes that are relevant per scenario
_ORC_FILTERS: dict[str, Any] = {
    "deposit_aggregation_failure": lambda r: (
        r.get("orc_code", "") in ("Joint_JTWROS", "Joint_TenancyInCommon", "Single")
        and _safe_float(r.get("current_balance", "0")) > 200_000
    ),
    "trust_irr_misclassification": lambda r: (
        r.get("orc_code", "") == "Trust_Irrevocable"
    ),
    "wire_mt202_drop": lambda r: (
        r.get("orc_code", "") in (
            "Business_Corporation", "Business_LLC", "Business_Partnership"
        )
        and _safe_float(r.get("current_balance", "0")) > 500_000
    ),
}


def _safe_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class KratosDemoAdapter(InfrastructureAdapter):
    """
    Demo adapter reading from local disk.
    Supports all 3 built-in demo scenarios.
    """

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    def adapter_id(self) -> str:
        return "kratos_demo"

    @property
    def display_name(self) -> str:
        return "Kratos Demo (3 scenarios · 6,006 accounts)"

    @property
    def environment(self) -> str:
        return "demo"

    # ── Scenario discovery ────────────────────────────────────────────────

    async def list_scenarios(self) -> list[dict]:
        result = []
        if not _SCENARIOS_DIR.exists():
            return result
        for d in sorted(_SCENARIOS_DIR.iterdir()):
            if not d.is_dir():
                continue
            incident_path = d / "incident.json"
            if not incident_path.exists():
                continue
            try:
                incident = json.loads(incident_path.read_text(encoding="utf-8"))
                result.append({
                    "scenario_id": d.name,
                    "title":       incident.get("title", d.name),
                    "system":      incident.get("system", ""),
                    "severity":    incident.get("severity", "CRITICAL"),
                })
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("KratosDemoAdapter: could not load %s: %s", incident_path, exc)
        return result

    async def load_scenario_pack(self, scenario_id: str) -> "Any":
        """
        Returns a minimal dict-based pack.
        Full ScenarioPack loading is handled by ScenarioRegistry/ScenarioLoader
        in the existing demo infrastructure.  This method is for adapters that
        want to bypass the registry (e.g. a production adapter using a live DB).
        """
        d = _SCENARIOS_DIR / scenario_id
        if not d.exists():
            raise KeyError(f"Scenario '{scenario_id}' not found at {d}")

        incident = json.loads((d / "incident.json").read_text(encoding="utf-8"))
        controls = json.loads((d / "controls.json").read_text(encoding="utf-8"))
        job_run  = json.loads((d / "job_run.json").read_text(encoding="utf-8"))

        return {
            "incident": incident,
            "controls": controls,
            "job_run":  job_run,
        }

    # ── Ontology ─────────────────────────────────────────────────────────

    async def get_canon_graph(self, scenario_id: str) -> "Any":
        from src.demo.ontology.canon_graphs import CANON_GRAPHS
        if scenario_id not in CANON_GRAPHS:
            raise KeyError(f"No CanonGraph defined for scenario '{scenario_id}'")
        return CANON_GRAPHS[scenario_id]

    # ── Evidence ──────────────────────────────────────────────────────────

    async def fetch_logs(self, scenario_id: str, job_id: str) -> list[dict]:
        log_dir = _SCENARIOS_DIR / scenario_id / "logs"
        if not log_dir.exists():
            return []
        lines: list[dict] = []
        for f in sorted(log_dir.glob("*.log")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    lines.append({"raw": line, "source_file": f.name})
        return lines

    async def fetch_account_records(
        self, scenario_id: str, filters: dict
    ) -> list[dict]:
        if not _CSV_PATH.exists():
            logger.warning("KratosDemoAdapter: CSV not found at %s", _CSV_PATH)
            return []

        filter_fn = _ORC_FILTERS.get(scenario_id, lambda _r: True)
        rows: list[dict] = []
        try:
            with open(_CSV_PATH, encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if filter_fn(row):
                        rows.append(dict(row))
                        if len(rows) >= 20:
                            break
        except OSError as exc:
            logger.warning("KratosDemoAdapter: error reading CSV: %s", exc)
        return rows

    async def fetch_job_run(self, scenario_id: str, job_id: str) -> dict:
        path = _SCENARIOS_DIR / scenario_id / "job_run.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    # ── Code artifact resolution ──────────────────────────────────────────

    async def resolve_artifact(
        self, artifact_path: str, line_ref: str | None = None
    ) -> dict:
        full = _OP_ROOT / artifact_path
        snippet = ""
        if full.exists():
            try:
                lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
                snippet = "\n".join(lines[:60])
            except OSError:
                pass
        return {
            "path":               artifact_path,
            "content_snippet":    snippet,
            "language":           full.suffix.lstrip(".") or "unknown",
            "defect_annotation":  line_ref,
        }

    # ── LLM provider ─────────────────────────────────────────────────────

    def get_llm_config(self) -> dict:
        return {
            "provider":    "anthropic",
            "model":       "claude-sonnet-4-6",
            "max_tokens":  1024,
            "streaming":   True,
            "temperature": 0,
        }


# Auto-register on import
register_adapter(KratosDemoAdapter())
