"""
SWIFT Message Parser — MT103 / MT202 Wire Transfer Messages
Parses incoming SWIFT messages and extracts depositor/beneficiary information.

KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
  1. MT202COV (cover payments) not parsed — beneficiary info lost
  2. Field 50K (Ordering Customer) extracted but not linked to depositor master
  3. Field 59 (Beneficiary) name normalization uses simple split — fails for
     international name formats (Korean, Arabic, etc.)
  4. No validation of BIC codes against SWIFT directory
  5. Intermediary bank (Field 56A) fees not tracked for balance accuracy
  6. Multi-currency wires converted at stale FX rate (previous day close)
"""

import csv
import json
import os
import re
import sys
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class WireTransfer:
    """Represents a parsed wire transfer instruction."""
    reference: str = ""
    message_type: str = ""  # MT103, MT202, MT202COV
    value_date: str = ""
    currency: str = "USD"
    amount: float = 0.0
    ordering_customer_name: str = ""
    ordering_customer_account: str = ""
    ordering_customer_id: str = ""  # BUG: Not linked to depositor master
    beneficiary_name: str = ""
    beneficiary_account: str = ""
    beneficiary_bank_bic: str = ""
    intermediary_bank_bic: str = ""
    sender_bic: str = ""
    receiver_bic: str = ""
    charges: str = "SHA"  # SHA, OUR, BEN
    remittance_info: str = ""
    screening_status: str = "PENDING"  # PENDING, CLEARED, HELD, BLOCKED
    parsed_at: str = ""
    # MISSING: depositor_id linkage, orc_type classification, insurance_relevant flag


@dataclass
class ParseResult:
    """Result of parsing a SWIFT message file."""
    file_name: str = ""
    total_messages: int = 0
    parsed_ok: int = 0
    parse_errors: int = 0
    transfers: list = field(default_factory=list)
    errors: list = field(default_factory=list)


# BUG: Regex patterns only handle standard SWIFT format
# Fails on: extended character sets, multi-line field continuations
MT103_FIELD_PATTERNS = {
    "20":  r":20:(.+)",           # Transaction Reference
    "23B": r":23B:(.+)",          # Bank Operation Code
    "32A": r":32A:(\d{6})([A-Z]{3})([\d,]+)",  # Value Date/Currency/Amount
    "50K": r":50K:/?(.+?)(?=\n:)",  # Ordering Customer
    "59":  r":59:/?(.+?)(?=\n:)",   # Beneficiary
    "56A": r":56A:(.+)",          # Intermediary Bank
    "71A": r":71A:(.+)",          # Charges
    "70":  r":70:(.+)",           # Remittance Info
}


def parse_swift_message(raw_text: str) -> Optional[WireTransfer]:
    """Parse a single SWIFT MT103 message into a WireTransfer object.

    BUG: Only handles MT103. MT202/MT202COV silently dropped.
    BUG: No checksum validation of SWIFT message blocks.
    BUG: Field 77B (Regulatory Reporting) ignored — may contain compliance data.
    """
    wire = WireTransfer()
    wire.parsed_at = datetime.now().isoformat()

    # Determine message type
    if "{2:O103" in raw_text:
        wire.message_type = "MT103"
    elif "{2:O202" in raw_text:
        wire.message_type = "MT202"
        return None  # BUG: MT202 dropped entirely — includes bank-to-bank transfers
    else:
        return None

    # Extract reference
    ref_match = re.search(r":20:(.+)", raw_text)
    if ref_match:
        wire.reference = ref_match.group(1).strip()

    # Extract value date, currency, amount
    val_match = re.search(r":32A:(\d{6})([A-Z]{3})([\d,]+)", raw_text)
    if val_match:
        wire.value_date = val_match.group(1)
        wire.currency = val_match.group(2)
        # BUG: Comma used as decimal separator in SWIFT — incorrect parsing for amounts > 999
        wire.amount = float(val_match.group(3).replace(",", "."))

    # Extract ordering customer
    orc_match = re.search(r":50[AFK]:/?(.+?)(?:\n:[0-9])", raw_text, re.DOTALL)
    if orc_match:
        lines = orc_match.group(1).strip().split("\n")
        wire.ordering_customer_account = lines[0] if lines else ""
        wire.ordering_customer_name = " ".join(lines[1:]).strip() if len(lines) > 1 else ""
        # BUG: No depositor master linkage attempted
        # BUG: Name normalization too simplistic for international names

    # Extract beneficiary
    ben_match = re.search(r":59:/?(.+?)(?:\n:[0-9])", raw_text, re.DOTALL)
    if ben_match:
        lines = ben_match.group(1).strip().split("\n")
        wire.beneficiary_account = lines[0] if lines else ""
        wire.beneficiary_name = " ".join(lines[1:]).strip() if len(lines) > 1 else ""

    # Extract sender/receiver BIC
    sender_match = re.search(r"\{1:F01([A-Z0-9]{8,11})", raw_text)
    if sender_match:
        wire.sender_bic = sender_match.group(1)
    receiver_match = re.search(r"\{2:O103\d{4}(\d{6})([A-Z0-9]{8,11})", raw_text)
    if receiver_match:
        wire.receiver_bic = receiver_match.group(2)

    # Extract charges
    chg_match = re.search(r":71A:(.+)", raw_text)
    if chg_match:
        wire.charges = chg_match.group(1).strip()

    return wire


def parse_swift_file(filepath: str) -> ParseResult:
    """Parse a SWIFT message file containing one or more messages.

    BUG: Assumes messages are delimited by {1: — fails for concatenated files.
    BUG: No encoding detection — assumes UTF-8, but SWIFT uses ASCII subset.
    """
    result = ParseResult(file_name=os.path.basename(filepath))

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        # BUG: Fallback to latin-1 silently — may corrupt special characters
        with open(filepath, "r", encoding="latin-1") as f:
            content = f.read()

    # Split into individual messages
    messages = re.split(r"(?=\{1:F01)", content)
    messages = [m.strip() for m in messages if m.strip()]
    result.total_messages = len(messages)

    for msg in messages:
        try:
            wire = parse_swift_message(msg)
            if wire:
                result.transfers.append(asdict(wire))
                result.parsed_ok += 1
            else:
                result.parse_errors += 1
                result.errors.append(f"Unsupported message type in: {msg[:50]}...")
        except Exception as e:
            result.parse_errors += 1
            result.errors.append(str(e))

    return result


def link_to_depositor_master(wire: WireTransfer, db_conn) -> Optional[str]:
    """Attempt to link wire ordering customer to depositor master.

    BUG: This function exists but is NEVER CALLED in the pipeline.
    BUG: Matching uses exact name match only — no fuzzy/phonetic matching.
    BUG: No handling of business entity name variations (LLC, Inc, Corp).
    """
    cursor = db_conn.cursor()
    cursor.execute(
        "SELECT depositor_id FROM customers WHERE UPPER(full_name) = UPPER(%s)",
        (wire.ordering_customer_name,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Parse SWIFT MT103/MT202 messages")
    parser.add_argument("--input", required=True, help="Input directory")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--format", default="MT103,MT202", help="Message types")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_wires = 0
    total_errors = 0

    for swift_file in input_dir.glob("*.swift"):
        result = parse_swift_file(str(swift_file))
        output_file = output_dir / f"{swift_file.stem}.json"
        with open(output_file, "w") as f:
            json.dump(asdict(result), f, indent=2)
        total_wires += result.parsed_ok
        total_errors += result.parse_errors
        print(f"Parsed {swift_file.name}: {result.parsed_ok} OK, {result.parse_errors} errors")

    print(f"\nTotal: {total_wires} wires parsed, {total_errors} errors")
    # BUG: Exit code 0 even if errors > 0 — downstream steps proceed with bad data
