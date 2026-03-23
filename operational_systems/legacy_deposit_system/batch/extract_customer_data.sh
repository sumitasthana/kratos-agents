#!/bin/bash
# ============================================================
# SCRIPT: extract_customer_data.sh
# PURPOSE: ETL extraction from multiple source banking systems
# REGULATION: IT Guide Section 2.3.2 — Data completeness
#
# KNOWN ISSUES:
#   - No data validation after extraction
#   - No cross-system deduplication (govt_id matching)
#   - Missing source: Loan system (needed for offset calcs)
#   - Missing source: Trust system beneficiary details
#   - Government deposit source manually entered, not automated
#   - No data completeness percentage calculation
#   - Credentials hardcoded
# ============================================================

ETL_DATE=$(date +%Y-%m-%d)
STAGING_DIR="/data/fdic_staging"
LOG_FILE="/var/log/fdic_etl/extract_${ETL_DATE}.log"

echo "[$(date)] Starting ETL extraction for ${ETL_DATE}" >> ${LOG_FILE}

# Source 1: Core Banking Platform
echo "[$(date)] Extracting from Core Banking..." >> ${LOG_FILE}
# BUG: Hardcoded credentials in script
sqlcmd -S core-banking-prod:1433 -U svc_etl -P 'ETL_Pr0d_2024!' \
    -d CORE_DEPOSITS \
    -i /opt/fdic/sql/extract_core_customers.sql \
    -o "${STAGING_DIR}/core_customers_${ETL_DATE}.csv" \
    -s "|" -W 2>> ${LOG_FILE}

sqlcmd -S core-banking-prod:1433 -U svc_etl -P 'ETL_Pr0d_2024!' \
    -d CORE_DEPOSITS \
    -i /opt/fdic/sql/extract_core_accounts.sql \
    -o "${STAGING_DIR}/core_accounts_${ETL_DATE}.csv" \
    -s "|" -W 2>> ${LOG_FILE}

# Source 2: Trust Administration System
echo "[$(date)] Extracting from Trust System..." >> ${LOG_FILE}
sqlcmd -S trust-prod:1433 -U svc_etl -P 'Trust_ETL_2024!' \
    -d TRUST_DB \
    -i /opt/fdic/sql/extract_trust_accounts.sql \
    -o "${STAGING_DIR}/trust_accounts_${ETL_DATE}.csv" \
    -s "|" -W 2>> ${LOG_FILE}
# BUG: Not extracting beneficiary details from trust system
# This data is needed for REV (12 CFR 330.10) calculations

# Source 3: IRA/Retirement System
echo "[$(date)] Extracting from IRA System..." >> ${LOG_FILE}
sqlcmd -S ira-prod:1433 -U svc_etl -P 'IRA_ETL_2024!' \
    -d RETIREMENT_DB \
    -i /opt/fdic/sql/extract_ira_accounts.sql \
    -o "${STAGING_DIR}/ira_accounts_${ETL_DATE}.csv" \
    -s "|" -W 2>> ${LOG_FILE}

# Source 4: Government Deposits
# BUG: Government deposits are NOT extracted from any system.
# They are manually entered into spreadsheets and uploaded.
# This violates IT Guide Section 2.3.2 for automated sourcing.
echo "[$(date)] WARNING: Government deposits sourced from manual spreadsheet" >> ${LOG_FILE}
cp /data/manual_entry/govt_deposits_latest.csv \
   "${STAGING_DIR}/govt_deposits_${ETL_DATE}.csv" 2>> ${LOG_FILE}

# MISSING Source 5: Loan System
# BUG: No extraction from loan system. Loan data is needed
# to calculate offset rights per 12 CFR 330.5 which allows
# the institution to offset deposits against obligations owed.

# Merge extracted files into unified staging tables
echo "[$(date)] Loading into staging tables..." >> ${LOG_FILE}
sqlcmd -S db-server-prod -U svc_etl -P 'ETL_Pr0d_2024!' \
    -d DEPOSIT_DB \
    -Q "EXEC dbo.sp_load_staging @etl_date='${ETL_DATE}'"

# BUG: No cross-system deduplication
# Same person may have different depositor_ids across
# core banking, trust, and IRA systems.
# Per IT Guide, institution must maintain a single
# depositor record per unique government_id.

# BUG: No data completeness check after extraction
# IT Guide Section 2.3.3 requires completeness reporting

echo "[$(date)] ETL extraction complete" >> ${LOG_FILE}
