"""causelink/rca/scenario_config.py

Backend configuration for the 5 control scenarios available in the RCA workspace.
Each scenario defines investigation context, expected controls, allowed analyzers,
anchor preference, and UI display metadata.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ScenarioUiMetadata(BaseModel):
    color_key: str = "blue"
    priority: int = 1
    short_label: str = ""


class ScenarioConfig(BaseModel):
    scenario_id: str
    title: str
    subtitle: str
    expected_controls: List[str] = Field(default_factory=list)
    expected_problem_types: List[str] = Field(default_factory=list)
    allowed_analyzers: List[str] = Field(default_factory=list)
    anchor_preference: str = "Job"  # "Job" | "Pipeline" | "Incident" | "Violation"
    ui_metadata: ScenarioUiMetadata = Field(default_factory=ScenarioUiMetadata)
    dashboard_card_defaults: Dict[str, Any] = Field(default_factory=dict)


SCENARIO_REGISTRY: Dict[str, ScenarioConfig] = {
    "gl_reconciliation": ScenarioConfig(
        scenario_id="gl_reconciliation",
        title="GL Reconciliation",
        subtitle="General ledger balance discrepancy investigation",
        expected_controls=["CTRL-FIN-001", "CTRL-FIN-003"],
        expected_problem_types=["execution_failure", "compliance_gap"],
        allowed_analyzers=["InfraAnalyzer", "DataProfiler", "CodeAnalyzer"],
        anchor_preference="Job",
        ui_metadata=ScenarioUiMetadata(color_key="blue", priority=1, short_label="GL Recon"),
        dashboard_card_defaults={"show_lineage": True, "show_compliance": True},
    ),
    "joint_qualification": ScenarioConfig(
        scenario_id="joint_qualification",
        title="Joint Qualification",
        subtitle="Multi-party data qualification and control attestation",
        expected_controls=["CTRL-QUAL-002", "CTRL-QUAL-005"],
        expected_problem_types=["compliance_gap", "lineage"],
        allowed_analyzers=["DataProfiler", "CodeAnalyzer", "ChangeAnalyzer"],
        anchor_preference="Job",
        ui_metadata=ScenarioUiMetadata(color_key="violet", priority=2, short_label="Joint Qual"),
        dashboard_card_defaults={"show_lineage": True, "show_compliance": True},
    ),
    "signature_card_validation": ScenarioConfig(
        scenario_id="signature_card_validation",
        title="Signature Card Validation",
        subtitle="Signature and authorization control validation",
        expected_controls=["CTRL-AUTH-010", "CTRL-AUTH-011"],
        expected_problem_types=["compliance_gap"],
        allowed_analyzers=["CodeAnalyzer"],
        anchor_preference="Incident",
        ui_metadata=ScenarioUiMetadata(color_key="red", priority=3, short_label="Sig Card"),
        dashboard_card_defaults={"show_lineage": False, "show_compliance": True},
    ),
    "schema_drift": ScenarioConfig(
        scenario_id="schema_drift",
        title="Schema Drift / Lineage Break",
        subtitle="Upstream schema change causing downstream pipeline failure",
        expected_controls=["CTRL-DATA-007"],
        expected_problem_types=["lineage", "regression_risk"],
        allowed_analyzers=["DataProfiler", "ChangeAnalyzer", "CodeAnalyzer"],
        anchor_preference="Pipeline",
        ui_metadata=ScenarioUiMetadata(color_key="amber", priority=4, short_label="Schema Drift"),
        dashboard_card_defaults={"show_lineage": True, "show_compliance": False},
    ),
    "rule_enforcement": ScenarioConfig(
        scenario_id="rule_enforcement",
        title="Rule Enforcement / Transformation Control",
        subtitle="Control rule violation in transformation or execution layer",
        expected_controls=["CTRL-RULE-020", "CTRL-RULE-021"],
        expected_problem_types=["compliance_gap", "execution_failure"],
        allowed_analyzers=["CodeAnalyzer", "DataProfiler"],
        anchor_preference="Pipeline",
        ui_metadata=ScenarioUiMetadata(color_key="teal", priority=5, short_label="Rule Enforce"),
        dashboard_card_defaults={"show_lineage": True, "show_compliance": True},
    ),
}

SCENARIOS: List[ScenarioConfig] = sorted(
    SCENARIO_REGISTRY.values(), key=lambda s: s.ui_metadata.priority
)


def get_scenario(scenario_id: str) -> ScenarioConfig:
    if scenario_id not in SCENARIO_REGISTRY:
        raise KeyError(
            f"Unknown scenario_id: {scenario_id!r}. "
            f"Valid values: {sorted(SCENARIO_REGISTRY)}"
        )
    return SCENARIO_REGISTRY[scenario_id]
