"""
src/demo/loaders/csv_evidence_loader.py

CsvEvidenceLoader — loads the kratos_data CSV into EvidenceObjects.

Design:
  - Raw content is NEVER stored inline.  Rows are written to a temp-style
    content_ref path string and summarised in .summary.
  - Every row with current_balance > 250000 AND orc_code requiring
    aggregation is tagged CRITICAL; all others SIGNAL (mapped to HIGH/MEDIUM).
  - ORC_PARTY_MISMATCH rows (Business_LLC ORC on Individual party) are
    included with a compliance-finding tag.
  - CSV is expected at data/kratos_data_20260316_1339.csv relative to
    the workspace root.

Usage::

    loader = CsvEvidenceLoader()
    objects = loader.load_all()           # all 6006 rows
    objects = loader.load_by_orc("Trust_Irrevocable")
"""

from __future__ import annotations

import csv
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from causelink.evidence.contracts import (
    EvidenceObject,
    EvidenceReliabilityTier,
    EvidenceType,
)

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
_CSV_FILE = _DATA_ROOT / "kratos_data_20260316_1339.csv"
_SMDIA = 250_000.0

# ORC codes that require depositor-level aggregation before applying SMDIA
_AGGREGATION_REQUIRED_ORC = frozenset({
    "Joint_JTWROS",
    "Business_LLC",
    "Business_Corp",
    "Business_Partnership",
    "Trust_Revocable",
    "Trust_Irrevocable",
})

# Known ORC codes that belong on business/entity parties but appear on Individual
_BUSINESS_ORC_CODES = frozenset({
    "Business_LLC",
    "Business_Corp",
    "Business_Partnership",
    "Business_SoleProprietorship",
})


class CsvEvidenceLoader:
    """
    Loads kratos_data CSV rows into EvidenceObjects.

    Each EvidenceObject represents one account row.  Content is referenced
    via a file URI + row offset — never stored inline.
    """

    def __init__(self, csv_path: Optional[Path] = None) -> None:
        self._csv_path = csv_path or _CSV_FILE
        if not self._csv_path.exists():
            raise FileNotFoundError(
                f"kratos_data CSV not found: {self._csv_path}. "
                "Ensure the CSV file is present at data/kratos_data_20260316_1339.csv"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_all(self) -> List[EvidenceObject]:
        """Load all rows from the CSV as EvidenceObjects."""
        return self._load(orc_filter=None)

    def load_by_orc(self, orc_code: str) -> List[EvidenceObject]:
        """Load only rows matching *orc_code*."""
        return self._load(orc_filter=orc_code)

    def load_smdia_exposures(self) -> List[EvidenceObject]:
        """Load rows where current_balance > $250,000 (SMDIA threshold)."""
        return self._load(smdia_only=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(
        self,
        orc_filter: Optional[str] = None,
        smdia_only: bool = False,
    ) -> List[EvidenceObject]:
        objects: List[EvidenceObject] = []
        with open(self._csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row_num, row in enumerate(reader, start=2):  # row 1 = header
                orc = row.get("orc_code", "")
                if orc_filter is not None and orc != orc_filter:
                    continue
                try:
                    balance = float(row.get("current_balance", 0))
                except ValueError:
                    balance = 0.0

                if smdia_only and balance <= _SMDIA:
                    continue

                ev = self._row_to_evidence(row, balance, row_num)
                if ev is not None:
                    objects.append(ev)

        logger.debug(
            "CsvEvidenceLoader: loaded %d EvidenceObjects (orc=%s, smdia_only=%s)",
            len(objects),
            orc_filter,
            smdia_only,
        )
        return objects

    def _row_to_evidence(
        self, row: Dict[str, str], balance: float, row_num: int
    ) -> Optional[EvidenceObject]:
        account_id = row.get("account_id", f"row-{row_num}")
        orc = row.get("orc_code", "UNKNOWN")
        party_type = row.get("party_type", "")
        account_status = row.get("account_status", "")

        if account_status.lower() not in ("active", ""):
            return None  # skip closed/inactive accounts

        # Determine reliability tier
        needs_aggregation = orc in _AGGREGATION_REQUIRED_ORC
        is_smdia_exposed = balance > _SMDIA and needs_aggregation
        reliability = 0.90 if is_smdia_exposed else 0.75
        tier = EvidenceReliabilityTier.HIGH if reliability >= 0.80 else EvidenceReliabilityTier.MEDIUM

        # Compliance tags
        tags: list[str] = ["kratos_data_csv", orc]
        if is_smdia_exposed:
            tags.append("smdia_exposure")
        if orc in _BUSINESS_ORC_CODES and party_type == "Individual":
            tags.append("orc_party_mismatch")

        # Deterministic hash from account_id + balance
        hash_input = f"{account_id}:{balance}:{orc}".encode()
        raw_hash = EvidenceObject.make_hash(hash_input)

        # Safe summary (no PII)
        open_date_str = row.get("account_open_date", "")
        try:
            ts = datetime.fromisoformat(open_date_str)
        except (ValueError, TypeError):
            ts = datetime(2020, 1, 1)

        summary = (
            f"Account {account_id}: orc={orc}, "
            f"balance=${balance:,.2f}, "
            f"smdia_exposed={is_smdia_exposed}, "
            f"party_type={party_type}"
        )
        if "orc_party_mismatch" in tags:
            summary += " [ORC_PARTY_MISMATCH compliance finding]"

        return EvidenceObject(
            type=EvidenceType.QUERY_RESULT,
            source_system="kratos_data_csv",
            content_ref=f"file://data/kratos_data_20260316_1339.csv#row={row_num}",
            summary=summary,
            reliability=reliability,
            reliability_tier=tier,
            raw_hash=raw_hash,
            collected_by="CsvEvidenceLoader",
            time_range_start=ts,
            time_range_end=ts,
            query_executed=f"csv:orc_filter={orc}",
            tags=tuple(tags),
        )
