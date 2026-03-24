#!/bin/bash
# ============================================================================
# TRUST RECONCILIATION & BENEFICIARY SYNC
# Reconciles trust ledger with GL, syncs beneficiary registry changes
# ============================================================================
# KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
#   1. Beneficiary changes detected but not applied to insurance recalc
#   2. Sub-account balances not reconciled against trust master
#   3. Terminated plan participants not removed from participant roster
#   4. Deceased beneficiary detection relies on external death file (monthly)
#   5. Grantor death notification not automated — manual process only
#   6. No audit trail for reconciliation adjustments
# ============================================================================

TRUST_HOME="/opt/trust_custody"
LOG_DIR="${TRUST_HOME}/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/trust_recon_${TIMESTAMP}.log"

# BUG: Hardcoded database credentials
DB_HOST="prod-trust-db.internal"
DB_USER="trust_admin"
DB_PASS="Tru$tM@ster2024!"   # SECURITY: Plaintext password

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# ── Step 1: Reconcile Trust Balances ───────────────────────────────
log "STEP 1: Reconciling trust balances against GL..."
sqlcmd -S "${DB_HOST}" -U "${DB_USER}" -P "${DB_PASS}" -d trust_db \
    -Q "EXEC sp_reconcile_trust_balances;"
# BUG: No tolerance parameter — exact match required, causes false breaks
# BUG: Sub-accounts not included in reconciliation

# ── Step 2: Sync Beneficiary Changes ──────────────────────────────
log "STEP 2: Syncing beneficiary registry changes..."
sqlcmd -S "${DB_HOST}" -U "${DB_USER}" -P "${DB_PASS}" -d trust_db \
    -Q "EXEC sp_sync_beneficiary_changes;"
# BUG: Changes detected and logged but existing insurance results NOT recalculated
# BUG: New beneficiaries added during the day missed until tomorrow's batch

# ── Step 3: Process Death Notifications ────────────────────────────
log "STEP 3: Processing death notification file..."
DEATH_FILE="${TRUST_HOME}/data/incoming/death_notifications.csv"
if [ -f "$DEATH_FILE" ]; then
    sqlcmd -S "${DB_HOST}" -U "${DB_USER}" -P "${DB_PASS}" -d trust_db \
        -Q "BULK INSERT death_staging FROM '${DEATH_FILE}' WITH (FIELDTERMINATOR=',', FIRSTROW=2);
            EXEC sp_process_death_notifications;"
    # BUG: Death file only received monthly from SSA
    # BUG: REV trusts of deceased grantors not reclassified to IRR
    # BUG: Deceased beneficiaries not excluded from count until next day
    mv "$DEATH_FILE" "${TRUST_HOME}/data/archive/death_${TIMESTAMP}.csv"
else
    log "WARNING: No death notification file found"
fi

# ── Step 4: Update EBP Participant Counts ──────────────────────────
log "STEP 4: Updating EBP plan participant counts..."
sqlcmd -S "${DB_HOST}" -U "${DB_USER}" -P "${DB_PASS}" -d trust_db \
    -Q "UPDATE trust_accounts SET participant_count = (
            SELECT COUNT(*) FROM plan_participants p
            WHERE p.plan_trust_id = trust_accounts.trust_id
            -- BUG: Counts ALL participants including TERMINATED and non-vested
        )
        WHERE trust_type = 'EBP' AND trust_status = 'A';"
# BUG: participant_count updated from stale roster
# BUG: No reconciliation against plan sponsor records

# ── Step 5: Roll Up Sub-Account Balances ───────────────────────────
log "STEP 5: Rolling up sub-account balances..."
# BUG: This step updates trust.balance but the insurance calc
# uses the ORIGINAL balance from the morning extract — timing gap
sqlcmd -S "${DB_HOST}" -U "${DB_USER}" -P "${DB_PASS}" -d trust_db \
    -Q "UPDATE trust_accounts SET balance = balance + (
            SELECT COALESCE(SUM(s.balance), 0)
            FROM trust_sub_accounts s
            WHERE s.trust_id = trust_accounts.trust_id AND s.is_active = 1
        )
        WHERE trust_status = 'A';"
# BUG: This DOUBLE COUNTS sub-account balances if run more than once
# BUG: No idempotency check — catastrophic if batch reruns

log "Trust reconciliation complete."
# BUG: No 24-hour deadline check
# BUG: No completion notification
