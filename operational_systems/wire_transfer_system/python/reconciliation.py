"""
Payment Reconciliation Engine
Reconciles wire transfer ledger against general ledger and nostro accounts.

KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
  1. Two-way reconciliation only (ledger vs GL) — missing nostro account match
  2. Tolerance of $0.01 too loose — regulatory reporting requires exact match
  3. Foreign currency wire revaluation not included in reconciliation
  4. Pending wires (T+0 unsettled) excluded from depositor balance snapshot
  5. ACH return reversals appear as separate entries — not netted
  6. No reconciliation of fee income against fee schedule
  7. Break items not escalated within 24-hour window
"""

import csv
import json
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ReconciliationBreak:
    """A reconciliation discrepancy."""
    break_id: str = ""
    break_type: str = ""        # MISSING_IN_GL, MISSING_IN_LEDGER, AMOUNT_MISMATCH, DATE_MISMATCH
    reference: str = ""
    ledger_amount: float = 0.0
    gl_amount: float = 0.0
    difference: float = 0.0
    currency: str = "USD"
    detected_at: str = ""
    resolved: bool = False
    resolution_notes: str = ""
    # BUG: No field for depositor_id — breaks can't be traced to insurance impact
    # BUG: No severity classification — all breaks treated equally


@dataclass
class ReconciliationReport:
    """Daily reconciliation report."""
    report_date: str = ""
    ledger_total: float = 0.0
    gl_total: float = 0.0
    net_difference: float = 0.0
    total_transactions: int = 0
    matched: int = 0
    breaks: list = field(default_factory=list)
    # BUG: No nostro_total field — third leg of reconciliation missing
    # BUG: No pending_wire_total — unsettled amounts not tracked


def load_ledger_entries(db_name: str) -> list[dict]:
    """Load wire transfer ledger entries for reconciliation.

    BUG: Loads all entries for current date — no handling of late-posting wires.
    BUG: Multi-currency entries not converted to USD for comparison.
    """
    # Simulated database query — in production, connected to PostgreSQL
    # BUG: No connection pooling, no timeout, no retry logic
    sample_entries = [
        {"ref": "WT20260301001", "amount": 1500000.00, "currency": "USD", "status": "SETTLED", "customer_id": "WC-001"},
        {"ref": "WT20260301002", "amount": 250000.00, "currency": "USD", "status": "SETTLED", "customer_id": "WC-002"},
        {"ref": "WT20260301003", "amount": 5000000.00, "currency": "EUR", "status": "PENDING", "customer_id": "WC-003"},
        {"ref": "WT20260301004", "amount": 75000.00, "currency": "USD", "status": "SETTLED", "customer_id": "WC-004"},
        {"ref": "WT20260301005", "amount": 3200000.00, "currency": "USD", "status": "SETTLED", "customer_id": "WC-005"},
        {"ref": "WT20260301006", "amount": 180000.00, "currency": "USD", "status": "RETURNED", "customer_id": "WC-002"},
    ]
    return sample_entries


def reconcile(ledger_entries: list[dict], gl_filepath: str, tolerance: float = 0.01) -> ReconciliationReport:
    """Perform two-way reconciliation.

    BUG: Only two-way (ledger vs GL). Missing nostro account reconciliation.
    BUG: RETURNED transactions not properly netted against original credits.
    BUG: PENDING transactions excluded — creates balance discrepancy for insurance calc.
    BUG: FX-denominated wires not converted for comparison.
    """
    report = ReconciliationReport(
        report_date=datetime.now().strftime("%Y-%m-%d"),
        total_transactions=len(ledger_entries),
    )

    # Load GL extract
    gl_entries = {}
    try:
        with open(gl_filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gl_entries[row["reference"]] = float(row.get("amount", 0))
    except FileNotFoundError:
        # BUG: Silent failure — proceeds with empty GL, all entries become breaks
        print(f"WARNING: GL extract not found: {gl_filepath}")
        gl_entries = {}

    # Match ledger to GL
    for entry in ledger_entries:
        ref = entry["ref"]
        ledger_amt = entry["amount"]
        report.ledger_total += ledger_amt

        if ref in gl_entries:
            gl_amt = gl_entries[ref]
            report.gl_total += gl_amt
            diff = abs(ledger_amt - gl_amt)

            if diff <= tolerance:
                report.matched += 1
            else:
                report.breaks.append(ReconciliationBreak(
                    break_id=f"BRK-{ref}",
                    break_type="AMOUNT_MISMATCH",
                    reference=ref,
                    ledger_amount=ledger_amt,
                    gl_amount=gl_amt,
                    difference=diff,
                    detected_at=datetime.now().isoformat(),
                ).__dict__)
        else:
            report.breaks.append(ReconciliationBreak(
                break_id=f"BRK-{ref}",
                break_type="MISSING_IN_GL",
                reference=ref,
                ledger_amount=ledger_amt,
                gl_amount=0,
                difference=ledger_amt,
                detected_at=datetime.now().isoformat(),
            ).__dict__)

    # Check for GL entries not in ledger
    for ref, gl_amt in gl_entries.items():
        ledger_refs = {e["ref"] for e in ledger_entries}
        if ref not in ledger_refs:
            report.gl_total += gl_amt
            report.breaks.append(ReconciliationBreak(
                break_id=f"BRK-{ref}",
                break_type="MISSING_IN_LEDGER",
                reference=ref,
                ledger_amount=0,
                gl_amount=gl_amt,
                difference=gl_amt,
                detected_at=datetime.now().isoformat(),
            ).__dict__)

    report.net_difference = abs(report.ledger_total - report.gl_total)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-db", required=True)
    parser.add_argument("--gl-extract", required=True)
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()

    entries = load_ledger_entries(args.ledger_db)
    report = reconcile(entries, args.gl_extract, args.tolerance)

    print(f"Reconciliation: {report.matched}/{report.total_transactions} matched, "
          f"{len(report.breaks)} breaks, net diff: ${report.net_difference:,.2f}")
    # BUG: No alert if net_difference > materiality threshold
    # BUG: No output of depositor-level impact of breaks
