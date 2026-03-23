"""
src/demo/services/control_scanner.py

ControlScanner — scans a scenario's controls.json and returns
a structured ControlScanResult without starting a full RCA.

Usage::

    scanner = ControlScanner(registry)
    result  = scanner.scan("deposit_aggregation_failure")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from ..scenario_registry import ScenarioRegistry

logger = logging.getLogger(__name__)


@dataclass
class ControlFinding:
    """A single control assessment result."""

    control_id: str
    name: str
    regulation: str
    status: str                  # PASSED | FAILED | WARNING
    severity: str               # CRITICAL | HIGH | MEDIUM | LOW
    defect_id: Optional[str]
    artifact: Optional[str]
    failure_reason: Optional[str]
    last_tested: Optional[str]


@dataclass
class ControlScanResult:
    """Aggregated control scan results for a scenario."""

    scenario_id: str
    incident_id: str
    scanned_at: datetime
    total_controls: int
    passed: int
    failed: int
    warnings: int
    critical_failures: int
    findings: List[ControlFinding] = field(default_factory=list)

    @property
    def has_critical_failure(self) -> bool:
        return self.critical_failures > 0

    def to_dict(self) -> dict:
        return {
            "scenario_id":       self.scenario_id,
            "incident_id":       self.incident_id,
            "scanned_at":        self.scanned_at.isoformat(),
            "total_controls":    self.total_controls,
            "passed":            self.passed,
            "failed":            self.failed,
            "warnings":          self.warnings,
            "critical_failures": self.critical_failures,
            "has_critical_failure": self.has_critical_failure,
            "findings": [
                {
                    "control_id":     f.control_id,
                    "name":           f.name,
                    "regulation":     f.regulation,
                    "status":         f.status,
                    "severity":       f.severity,
                    "defect_id":      f.defect_id,
                    "artifact":       f.artifact,
                    "failure_reason": f.failure_reason,
                    "last_tested":    f.last_tested,
                }
                for f in self.findings
            ],
        }


class ControlScanner:
    """
    Scans a scenario's controls.json and produces a ControlScanResult.

    Does not start an RCA investigation — intended for the
    GET /demo/controls/{scenario_id} endpoint.
    """

    def __init__(self, registry: ScenarioRegistry) -> None:
        self._registry = registry

    def scan(self, scenario_id: str) -> ControlScanResult:
        """
        Scan controls for *scenario_id* and return aggregated findings.

        Raises KeyError if the scenario is not registered.
        """
        pack = self._registry.get_pack(scenario_id)
        controls = pack.controls
        incident_id = pack.incident_id

        findings: List[ControlFinding] = []
        passed = failed = warnings = critical = 0

        for ctrl in controls:
            status = ctrl.get("status", "UNKNOWN").upper()
            severity = ctrl.get("severity", "MEDIUM").upper()

            finding = ControlFinding(
                control_id=ctrl.get("control_id", ""),
                name=ctrl.get("name", ""),
                regulation=ctrl.get("regulation", ""),
                status=status,
                severity=severity,
                defect_id=ctrl.get("defect_id"),
                artifact=ctrl.get("artifact"),
                failure_reason=ctrl.get("failure_reason"),
                last_tested=ctrl.get("last_tested"),
            )
            findings.append(finding)

            if status == "PASSED":
                passed += 1
            elif status == "FAILED":
                failed += 1
                if severity == "CRITICAL":
                    critical += 1
            elif status == "WARNING":
                warnings += 1

        result = ControlScanResult(
            scenario_id=scenario_id,
            incident_id=incident_id,
            scanned_at=datetime.utcnow(),
            total_controls=len(controls),
            passed=passed,
            failed=failed,
            warnings=warnings,
            critical_failures=critical,
            findings=findings,
        )
        logger.info(
            "ControlScanner: scenario=%s total=%d failed=%d critical=%d",
            scenario_id,
            result.total_controls,
            result.failed,
            result.critical_failures,
        )
        return result
