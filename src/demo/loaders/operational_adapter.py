"""
src/demo/loaders/operational_adapter.py

OperationalAdapter — reference registry mapping known operational_systems
defect IDs to CanonNode IDs in the demo CanonGraphs.

Design:
  - This module is READ-ONLY with respect to operational_systems source files.
    It never modifies COBOL, Java, Python, SQL, or config files.
  - Used by DemoRcaService to attach defect metadata to RootCauseCandidate
    descriptions and recommendations.

Usage::

    adapter = OperationalAdapter()
    defect  = adapter.get_defect("DEF-LDS-001")
    node_id = adapter.node_id_for_defect("DEF-LDS-001")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DefectRecord:
    """Metadata for a known operational_systems defect."""

    defect_id: str
    artifact_path: str
    description: str
    system: str                  # legacy_deposit_system | trust_custody_system | wire_transfer_system
    scenario_id: str
    canon_node_id: str           # CanonNode neo4j_id in the demo graph
    remediation: str


_DEFECT_REGISTRY: List[DefectRecord] = [
    # ── Deposit aggregation failure ────────────────────────────────────────
    DefectRecord(
        defect_id="DEF-LDS-001",
        artifact_path="operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl",
        description="Step 3 AGGRSTEP commented out — depositor-level aggregation disabled",
        system="legacy_deposit_system",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-art-jcl",
        remediation=(
            "Uncomment EXEC PGM=FDIC003 for step AGGRSTEP in DAILY-INSURANCE-JOB.jcl. "
            "Re-run DAILY-INSURANCE-JOB-20260316 after fix to regenerate accurate coverage report."
        ),
    ),
    DefectRecord(
        defect_id="DEF-LDS-002",
        artifact_path="operational_systems/legacy_deposit_system/cobol/ORC-ASSIGNMENT.cob",
        description="IRR ORC code not implemented in COBOL assignment logic",
        system="legacy_deposit_system",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-art-jcl",
        remediation="Implement IRR paragraph in ORC-ASSIGNMENT.cob and deploy to CICSPROD.",
    ),
    DefectRecord(
        defect_id="DEF-LDS-003",
        artifact_path="operational_systems/legacy_deposit_system/java/DepositService.java",
        description="EBP coverage applies flat $250K not per-participant",
        system="legacy_deposit_system",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-stp-agg",
        remediation="Update DepositService.java to apply per-participant EBP limit.",
    ),
    DefectRecord(
        defect_id="DEF-LDS-004",
        artifact_path="operational_systems/legacy_deposit_system/batch/DAILY-INSURANCE-JOB.jcl",
        description="Comma delimiter instead of pipe separator in output file",
        system="legacy_deposit_system",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-art-jcl",
        remediation="Update JCL PARM for REPTSTEP to use pipe (|) delimiter.",
    ),
    DefectRecord(
        defect_id="DEF-LDS-005",
        artifact_path="operational_systems/legacy_deposit_system/java/DepositService.java",
        description="PII (SSN/EIN) written in plaintext to output report",
        system="legacy_deposit_system",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-stp-agg",
        remediation="Mask SSN/EIN fields before writing output in DepositService.java.",
    ),
    # ── Trust IRR misclassification ────────────────────────────────────────
    DefectRecord(
        defect_id="DEF-TCS-001",
        artifact_path="operational_systems/trust_custody_system/cobol/TRUST-INSURANCE-CALC.cob",
        description="IRR falls back to SGL — IRR paragraph not coded in COBOL",
        system="trust_custody_system",
        scenario_id="trust_irr_misclassification",
        canon_node_id="node-tim-art-cob",
        remediation=(
            "Implement PERFORM IRR-CALC paragraph in TRUST-INSURANCE-CALC.cob. "
            "Apply per-beneficiary $250,000 ceiling. Recompile and deploy to CICSPROD."
        ),
    ),
    DefectRecord(
        defect_id="DEF-TCS-002",
        artifact_path="operational_systems/trust_custody_system/config/trust-config.properties",
        description="REV beneficiary cap configured at 5 (regulation allows up to 250)",
        system="trust_custody_system",
        scenario_id="trust_irr_misclassification",
        canon_node_id="node-tim-art-bcj",
        remediation="Update rev.beneficiary.cap=250 in trust-config.properties.",
    ),
    DefectRecord(
        defect_id="DEF-TCS-003",
        artifact_path="operational_systems/trust_custody_system/java/BeneficiaryClassifier.java",
        description="IRR → SGL in switch statement at line 147",
        system="trust_custody_system",
        scenario_id="trust_irr_misclassification",
        canon_node_id="node-tim-art-bcj",
        remediation=(
            "Replace case IRR -> SGL with case IRR -> IRR in BeneficiaryClassifier.java:147. "
            "Add IRRBeneficiaryCalculator implementation."
        ),
    ),
    DefectRecord(
        defect_id="DEF-TCS-004",
        artifact_path="operational_systems/trust_custody_system/config/trust-config.properties",
        description="include_deceased=true causes deceased beneficiaries to count toward coverage",
        system="trust_custody_system",
        scenario_id="trust_irr_misclassification",
        canon_node_id="node-tim-art-bcj",
        remediation="Set include_deceased=false in trust-config.properties.",
    ),
    DefectRecord(
        defect_id="DEF-TCS-005",
        artifact_path="operational_systems/trust_custody_system/config/trust-config.properties",
        description="grantor_level.enabled=false — grantor-level aggregation disabled",
        system="trust_custody_system",
        scenario_id="trust_irr_misclassification",
        canon_node_id="node-tim-art-bcj",
        remediation="Set grantor_level.enabled=true in trust-config.properties.",
    ),
    DefectRecord(
        defect_id="DEF-TCS-006",
        artifact_path="operational_systems/trust_custody_system/sql/sp_calculate_trust_insurance.sql",
        description="Sub-account balances excluded from trust insurance calculation",
        system="trust_custody_system",
        scenario_id="trust_irr_misclassification",
        canon_node_id="node-tim-art-cob",
        remediation="Update sp_calculate_trust_insurance.sql to include sub-account JOIN.",
    ),
    # ── Wire MT202 drop ────────────────────────────────────────────────────
    DefectRecord(
        defect_id="DEF-WTS-001",
        artifact_path="operational_systems/wire_transfer_system/python/swift_parser.py",
        description="parse_message() handles MT103 only — MT202/MT202COV silently dropped",
        system="wire_transfer_system",
        scenario_id="wire_mt202_drop",
        canon_node_id="node-wmd-art-swp",
        remediation=(
            "Add elif message_type == 'MT202' and elif message_type == 'MT202COV' branches "
            "in swift_parser.py:parse_message(). "
            "Add raise ValueError for unknown message types to prevent silent drops."
        ),
    ),
    DefectRecord(
        defect_id="DEF-WTS-002",
        artifact_path="operational_systems/wire_transfer_system/config/wire-config.properties",
        description="OFAC batch mode configured with 6-hour delay",
        system="wire_transfer_system",
        scenario_id="wire_mt202_drop",
        canon_node_id="node-wmd-mod-swp",
        remediation="Reduce ofac.batch.delay to ≤ 2 hours in wire-config.properties.",
    ),
    DefectRecord(
        defect_id="DEF-WTS-007",
        artifact_path="operational_systems/wire_transfer_system/python/reconciliation.py",
        description="Nostro accounts not matched in GL reconciliation",
        system="wire_transfer_system",
        scenario_id="wire_mt202_drop",
        canon_node_id="node-wmd-mod-swp",
        remediation="Update reconciliation.py to JOIN all nostro accounts in nightly recon.",
    ),
    # ── Cross-system defects ───────────────────────────────────────────────
    DefectRecord(
        defect_id="DEF-XSY-001",
        artifact_path="ALL SYSTEMS",
        description="No cross-channel depositor aggregation across deposit/wire/trust systems",
        system="all",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-pip-dij",
        remediation="Implement cross-channel aggregation service that joins party IDs across all three systems.",
    ),
    DefectRecord(
        defect_id="DEF-XSY-002",
        artifact_path="ALL SYSTEMS",
        description="SMDIA hardcoded at $250,000 — no parameterisation",
        system="all",
        scenario_id="deposit_aggregation_failure",
        canon_node_id="node-daf-pip-dij",
        remediation="Move SMDIA constant to a shared configuration property file.",
    ),
]

# Build lookup dict at module load time
_BY_DEFECT_ID: Dict[str, DefectRecord] = {d.defect_id: d for d in _DEFECT_REGISTRY}
_BY_SCENARIO: Dict[str, List[DefectRecord]] = {}
for _d in _DEFECT_REGISTRY:
    _BY_SCENARIO.setdefault(_d.scenario_id, []).append(_d)


class OperationalAdapter:
    """Read-only reference to the known operational_systems defect registry."""

    def get_defect(self, defect_id: str) -> Optional[DefectRecord]:
        """Return the DefectRecord for *defect_id*, or None if unknown."""
        return _BY_DEFECT_ID.get(defect_id)

    def defects_for_scenario(self, scenario_id: str) -> List[DefectRecord]:
        """Return all defects associated with *scenario_id*."""
        return list(_BY_SCENARIO.get(scenario_id, []))

    def node_id_for_defect(self, defect_id: str) -> Optional[str]:
        """Return the CanonNode neo4j_id associated with *defect_id*."""
        rec = _BY_DEFECT_ID.get(defect_id)
        return rec.canon_node_id if rec else None

    def primary_defect_for_scenario(self, scenario_id: str) -> Optional[DefectRecord]:
        """Return the first (primary) defect for a scenario (from the instructions)."""
        primary_ids = {
            "deposit_aggregation_failure": "DEF-LDS-001",
            "trust_irr_misclassification": "DEF-TCS-001",
            "wire_mt202_drop":             "DEF-WTS-001",
        }
        defect_id = primary_ids.get(scenario_id)
        return _BY_DEFECT_ID.get(defect_id) if defect_id else None
