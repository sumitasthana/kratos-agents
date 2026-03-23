#!/bin/bash
# ============================================================================
# ACH BATCH SETTLEMENT PROCESSING
# Processes ACH origination and receiving, settles batches, updates balances
# ============================================================================
# KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
#   1. ACH returns (R01-R29) not properly reversed in insurance calc
#   2. Same-day ACH not reflected in real-time balance snapshots
#   3. No cross-reference between ACH customer IDs and wire customer master
#   4. Government ACH payments (GACH) not flagged for GOV ORC classification
#   5. Prenote transactions create phantom depositor records
# ============================================================================

ACH_HOME="/opt/wire_transfer"
NACHA_DIR="${ACH_HOME}/data/nacha"
SETTLED_DIR="${ACH_HOME}/data/settled"
LOG_FILE="${ACH_HOME}/logs/ach_batch_$(date +%Y%m%d).log"

DB_HOST="prod-wire-db.internal"
DB_USER="wire_admin"
DB_PASS="W1r3Tr@nsf3r!"  # SECURITY: Hardcoded credentials

log() { echo "[$(date '+%H:%M:%S')] $1" >> "$LOG_FILE"; }

# ── Parse NACHA Files ──────────────────────────────────────────────
log "Parsing NACHA batch files..."
for f in "${NACHA_DIR}"/*.ach; do
    python3 "${ACH_HOME}/python/nacha_parser.py" \
        --input "$f" \
        --output "${SETTLED_DIR}/$(basename "$f" .ach).json"
    # BUG: Addenda records (7-records) ignored — contains beneficiary info
    # BUG: File header (1-record) origin DFI not validated
done

# ── Process Returns ────────────────────────────────────────────────
log "Processing ACH returns..."
PGPASSWORD="${DB_PASS}" psql -h "${DB_HOST}" -U "${DB_USER}" -d wire_ledger \
    -c "CALL sp_process_ach_returns();"
# BUG: Returns only update transaction status, not depositor balance snapshot
# BUG: R06 (returned per ODFI request) not distinguishing hold vs final

# ── Settle Credits ─────────────────────────────────────────────────
log "Settling ACH credits to depositor accounts..."
PGPASSWORD="${DB_PASS}" psql -h "${DB_HOST}" -U "${DB_USER}" -d wire_ledger \
    -c "CALL sp_settle_ach_credits();"
# BUG: Government recurring payments (Social Security, VA) not tagged as GOV ORC
# BUG: No duplicate payment detection across consecutive batches

# ── Update Insurance Snapshot ──────────────────────────────────────
log "Updating insurance balance snapshot..."
PGPASSWORD="${DB_PASS}" psql -h "${DB_HOST}" -U "${DB_USER}" -d wire_ledger \
    -c "CALL sp_snapshot_balances_for_insurance();"
# BUG: Snapshot taken at batch time, not end-of-day
# BUG: Same-day ACH credits not included in snapshot
# BUG: Pending debits not deducted from insurable balance

log "ACH batch settlement complete."
