#!/bin/bash
# ============================================================
# SCRIPT: run_nightly_calc.sh
# PURPOSE: Execute nightly FDIC Part 370 insurance calculation
# SCHEDULE: Runs via cron at 02:30 AM EST
#
# KNOWN ISSUES:
#   - No elapsed time check against 24-hour regulatory deadline
#   - No notification on failure (emails silently fail)
#   - No file integrity verification (checksums)
#   - Data in transit not encrypted between servers
#   - No lock mechanism to prevent concurrent execution
#   - Exit codes not properly propagated
#   - Log rotation not configured — disk fill risk
# ============================================================

set -e  # BUG: set -e will abort on first error but won't notify

CALC_DATE=$(date +%Y-%m-%d)
LOG_DIR="/var/log/fdic_insurance"
OUTPUT_DIR="/data/fdic_output"
DATA_DIR="/data/fdic_staging"
JAVA_HOME="/usr/lib/jvm/java-11"
COBOL_RUNTIME="/opt/microfocus/cobol"

# BUG: No lock file to prevent concurrent execution
# Two instances could corrupt calculation results

echo "[$(date)] Starting nightly insurance calculation for ${CALC_DATE}"
echo "[$(date)] Writing to log: ${LOG_DIR}/calc_${CALC_DATE}.log"

# Step 1: Extract customer data from source systems
echo "[$(date)] Step 1: Extracting customer data..."
# BUG: No encryption for data in transit
# BUG: Credentials hardcoded in connection string
sqlcmd -S db-server-prod -U svc_fdic -P 'Pr0d_P@ssw0rd!' \
    -d DEPOSIT_DB \
    -Q "EXEC dbo.sp_extract_customers @as_of_date='${CALC_DATE}'" \
    -o "${DATA_DIR}/customers_${CALC_DATE}.csv" \
    -s "," -W
# BUG: Using comma separator — FDIC spec requires pipe (|)

if [ $? -ne 0 ]; then
    echo "[$(date)] ERROR: Customer extraction failed"
    # BUG: No email/SMS alert sent on failure
    exit 1
fi

# Step 2: Extract account data
echo "[$(date)] Step 2: Extracting account data..."
sqlcmd -S db-server-prod -U svc_fdic -P 'Pr0d_P@ssw0rd!' \
    -d DEPOSIT_DB \
    -Q "SELECT * FROM dbo.vw_depositor_portfolio WHERE account_status='ACTIVE'" \
    -o "${DATA_DIR}/accounts_${CALC_DATE}.csv" \
    -s "," -W

# Step 3: Run ORC assignment
# BUG: Should call sp_aggregate_deposits BEFORE insurance calc
# but aggregation step is skipped
echo "[$(date)] Step 3: Running ORC assignment..."
${JAVA_HOME}/bin/java -jar /opt/fdic/orc-classifier.jar \
    --input "${DATA_DIR}/accounts_${CALC_DATE}.csv" \
    --customers "${DATA_DIR}/customers_${CALC_DATE}.csv" \
    --output "${DATA_DIR}/orc_assigned_${CALC_DATE}.csv"

# Step 4: Run insurance calculation
# BUG: Runs per-account, not on aggregated depositor totals
echo "[$(date)] Step 4: Running insurance calculation..."
sqlcmd -S db-server-prod -U svc_fdic -P 'Pr0d_P@ssw0rd!' \
    -d DEPOSIT_DB \
    -Q "EXEC dbo.sp_calculate_insurance @calculation_date='${CALC_DATE}'"

# Step 5: Generate output files
echo "[$(date)] Step 5: Generating QDF and ARE files..."
${JAVA_HOME}/bin/java -jar /opt/fdic/output-generator.jar \
    --batch-date "${CALC_DATE}" \
    --output-dir "${OUTPUT_DIR}" \
    --format csv
# BUG: CSV format — should be pipe-delimited per FDIC spec
# BUG: No file header with version, timestamp, record count
# BUG: No checksum/hash generated for output files

# Step 6: Copy to FDIC submission landing zone
echo "[$(date)] Step 6: Copying to landing zone..."
# BUG: No encryption for data in transit
# BUG: No checksum verification after copy
cp "${OUTPUT_DIR}/QDF_${CALC_DATE}.csv" /data/fdic_submission/
cp "${OUTPUT_DIR}/ARE_${CALC_DATE}.csv" /data/fdic_submission/

# BUG: No elapsed time check
# Per 12 CFR 370.3(b), must complete within 24 hours
ELAPSED_HOURS=$(( ($(date +%s) - $(date -d "today 02:30" +%s)) / 3600 ))
echo "[$(date)] Completed. Elapsed: ~${ELAPSED_HOURS} hours"
# BUG: No alert if ELAPSED_HOURS > 20 (approaching 24-hour limit)

echo "[$(date)] Nightly insurance calculation complete."
exit 0
