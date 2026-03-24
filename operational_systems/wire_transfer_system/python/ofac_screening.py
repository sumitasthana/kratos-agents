"""
OFAC / Sanctions Screening Engine
Screens wire transfer parties against SDN (Specially Designated Nationals) list.

KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
  1. Screening runs in BATCH mode only — 6-hour delay for real-time wires
  2. SDN list updated weekly from OFAC website — should be daily/real-time
  3. No fuzzy matching for transliterated names (Arabic, Chinese, Korean)
  4. No entity resolution — same person with different name spellings not linked
  5. Screening results not included in QDF output (compliance gap)
  6. Blocked funds not excluded from FDIC insurance calculation
  7. No secondary screening against EU/UK/OFSI/UN sanctions lists
  8. Threshold of 85% match score — too low, produces false positives
     that clog manual review queue; threshold should be configurable per entity type
"""

import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# BUG: SDN list loaded into memory — fails for large lists (>500K entries)
# BUG: No caching or incremental update — full reload every run
SDN_ENTRIES: list[dict] = []


def load_sdn_list(filepath: str) -> int:
    """Load OFAC SDN list from CSV.

    BUG: Only loads SDN. Missing: Consolidated Sanctions List, Sectoral Sanctions,
         Non-SDN Palestinian Legislative Council, Non-SDN Menu-Based Sanctions.
    BUG: No hash verification of downloaded SDN file.
    """
    global SDN_ENTRIES
    SDN_ENTRIES = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            SDN_ENTRIES.append({
                "entry_id": row.get("entry_id", ""),
                "name": row.get("name", "").upper(),
                "type": row.get("type", ""),       # Individual, Entity, Vessel, Aircraft
                "program": row.get("program", ""),  # SDGT, IRAN, UKRAINE-EO13661, etc.
                "aliases": [a.strip().upper() for a in row.get("aliases", "").split(";") if a.strip()],
                "addresses": row.get("addresses", ""),
                "id_numbers": row.get("id_numbers", ""),
            })
    return len(SDN_ENTRIES)


def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    BUG: Only handles Western name formats.
    BUG: No transliteration support (Arabic ↔ Latin, Cyrillic ↔ Latin).
    BUG: Business entity suffixes (LLC, Inc, Corp, GmbH, SA) not standardized.
    """
    name = name.upper().strip()
    name = re.sub(r"[^A-Z0-9\s]", "", name)  # Remove special chars
    name = re.sub(r"\s+", " ", name)          # Collapse whitespace
    # BUG: Should remove common prefixes (Mr, Mrs, Dr, Sheikh, etc.)
    return name


def calculate_match_score(name1: str, name2: str) -> float:
    """Calculate similarity score between two names.

    BUG: Uses simple character-level Jaccard — not phonetic matching (Soundex/Metaphone).
    BUG: No token-level comparison — word order affects score.
    BUG: Single-word names produce inflated scores.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if n1 == n2:
        return 100.0

    # Character bigrams
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1))

    b1 = bigrams(n1)
    b2 = bigrams(n2)

    if not b1 or not b2:
        return 0.0

    intersection = len(b1 & b2)
    union = len(b1 | b2)
    return round((intersection / union) * 100, 1) if union > 0 else 0.0


def screen_party(name: str, threshold: float = 85.0) -> list[dict]:
    """Screen a single party name against the SDN list.

    BUG: Only checks primary name and aliases, not addresses or ID numbers.
    BUG: No context-aware scoring (country, date of birth matching).
    BUG: Returns all matches above threshold — no deduplication of related entries.
    """
    hits = []
    normalized = normalize_name(name)

    for entry in SDN_ENTRIES:
        # Check primary name
        score = calculate_match_score(normalized, entry["name"])
        if score >= threshold:
            hits.append({
                "entry_id": entry["entry_id"],
                "matched_name": entry["name"],
                "match_type": "PRIMARY",
                "score": score,
                "program": entry["program"],
                "entity_type": entry["type"],
            })
            continue

        # Check aliases
        for alias in entry["aliases"]:
            alias_score = calculate_match_score(normalized, alias)
            if alias_score >= threshold:
                hits.append({
                    "entry_id": entry["entry_id"],
                    "matched_name": alias,
                    "match_type": "ALIAS",
                    "score": alias_score,
                    "program": entry["program"],
                    "entity_type": entry["type"],
                })
                break  # BUG: Only reports first alias match, may miss better matches

    return hits


def screen_wire_transfer(wire: dict, threshold: float = 85.0) -> dict:
    """Screen all parties in a wire transfer.

    BUG: Only screens ordering customer and beneficiary.
    BUG: Intermediary banks not screened (correspondent banking risk).
    BUG: Remittance info free text not screened for sanctioned entity references.
    """
    result = {
        "reference": wire.get("reference", ""),
        "screening_time": datetime.now().isoformat(),
        "overall_status": "CLEARED",
        "hits": [],
    }

    # Screen ordering customer
    ordering_name = wire.get("ordering_customer_name", "")
    if ordering_name:
        hits = screen_party(ordering_name, threshold)
        if hits:
            result["hits"].extend(hits)
            result["overall_status"] = "HELD"

    # Screen beneficiary
    beneficiary_name = wire.get("beneficiary_name", "")
    if beneficiary_name:
        hits = screen_party(beneficiary_name, threshold)
        if hits:
            result["hits"].extend(hits)
            result["overall_status"] = "BLOCKED"  # BUG: BLOCKED overrides HELD regardless of score

    # BUG: Should also screen:
    #   - Intermediary bank (Field 56A) against sanctioned financial institutions
    #   - Beneficiary bank (Field 57A) against sanctioned financial institutions
    #   - Remittance info (Field 70) for references to sanctioned programs/countries
    #   - Ordering institution (Field 52A) against sanctioned financial institutions

    return result


def process_batch(input_dir: str, sdn_file: str, output_dir: str, threshold: float = 85.0):
    """Process a batch of parsed wire transfers through OFAC screening.

    BUG: No parallel processing — takes 3+ hours for large batches.
    BUG: No progress reporting or checkpoint/resume capability.
    BUG: Blocked wires not quarantined — only flagged in output.
    """
    load_sdn_list(sdn_file)
    results = []
    total_screened = 0
    total_hits = 0

    input_path = Path(input_dir)
    for json_file in input_path.glob("*.json"):
        with open(json_file) as f:
            parsed = json.load(f)

        for wire in parsed.get("transfers", []):
            screening = screen_wire_transfer(wire, threshold)
            results.append(screening)
            total_screened += 1
            if screening["overall_status"] != "CLEARED":
                total_hits += 1
                # BUG: Wire amount of blocked/held transactions not excluded
                # from depositor's insurable balance calculation

    # Write results
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    with open(output_path / "screening_results.json", "w") as f:
        json.dump({
            "batch_time": datetime.now().isoformat(),
            "total_screened": total_screened,
            "total_hits": total_hits,
            "results": results,
        }, f, indent=2)

    print(f"Screening complete: {total_screened} wires, {total_hits} hits")
    # BUG: No alert/notification for hits — manual review required
    # BUG: No SLA tracking for review completion


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OFAC Sanctions Screening")
    parser.add_argument("--input", required=True)
    parser.add_argument("--sdn-list", required=True)
    parser.add_argument("--threshold", type=float, default=85.0)
    parser.add_argument("--output", default="./screening_output")
    args = parser.parse_args()

    process_batch(args.input, args.sdn_list, args.output, args.threshold)
