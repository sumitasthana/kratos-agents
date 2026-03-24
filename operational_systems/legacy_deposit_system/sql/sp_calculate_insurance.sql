-- ============================================================
-- STORED PROCEDURE: sp_calculate_insurance
-- PURPOSE: Calculate FDIC deposit insurance per depositor/ORC
-- REGULATION: 12 CFR Part 330, 12 CFR Part 370
--
-- KNOWN ISSUES:
--   - Does NOT aggregate across accounts before applying SMDIA
--     (processes per-account, not per-depositor-per-ORC)
--   - EBP pass-through not calculated (uses flat $250K)
--   - No deceased depositor 6-month grace period
--   - IRR (Irrevocable Trust) falls through to SGL logic
--   - No close-of-business balance cutoff (12 CFR 360.8)
--   - Hardcoded SMDIA value instead of parameter table
-- ============================================================

CREATE OR ALTER PROCEDURE dbo.sp_calculate_insurance
    @calculation_date DATE = NULL,
    @batch_id VARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- BUG: Hardcoded SMDIA. Should come from config table
    -- to handle regulatory changes without code deployment
    DECLARE @SMDIA DECIMAL(15,2) = 250000.00;
    DECLARE @calc_date DATE = ISNULL(@calculation_date, GETDATE());
    DECLARE @batch VARCHAR(50) = ISNULL(@batch_id, NEWID());
    DECLARE @error_count INT = 0;
    DECLARE @processed INT = 0;

    -- Clear previous results for this batch
    DELETE FROM dbo.insurance_results WHERE batch_id = @batch;

    -- ============================================================
    -- BUG: This calculates insurance PER ACCOUNT, not per
    -- depositor aggregate. Per 12 CFR Part 330, insurance coverage
    -- must be applied to the AGGREGATE balance across all accounts
    -- owned by the same depositor under the same ORC category.
    --
    -- Example: If depositor has two SGL checking accounts of
    -- $200,000 each, total SGL exposure is $400,000, insured
    -- should be $250,000. But this proc would show each account
    -- as fully insured ($200K + $200K = $400K insured), which
    -- overstates coverage by $150,000.
    -- ============================================================

    INSERT INTO dbo.insurance_results (
        batch_id, account_number, depositor_id, orc_type,
        balance, insured_amount, uninsured_amount,
        calc_method, calc_timestamp, error_flag
    )
    SELECT
        @batch,
        a.account_number,
        a.depositor_id,
        a.orc_type,
        a.balance,

        -- Insurance calculation (per-account, NOT aggregated)
        CASE
            -- Single Ownership: 12 CFR 330.6
            WHEN a.orc_type = 'SGL' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            -- Joint: 12 CFR 330.9
            -- BUG: Equal division instead of actual interest
            WHEN a.orc_type = 'JNT' THEN
                CASE WHEN (a.balance / NULLIF(a.joint_owner_count, 0)) > @SMDIA
                     THEN @SMDIA * ISNULL(NULLIF(a.joint_owner_count, 0), 2)
                     ELSE a.balance END

            -- Revocable Trust: 12 CFR 330.10
            WHEN a.orc_type = 'REV' THEN
                CASE WHEN a.beneficiary_count <= 5
                     THEN CASE WHEN a.balance > (@SMDIA * a.beneficiary_count)
                               THEN @SMDIA * a.beneficiary_count
                               ELSE a.balance END
                     -- BUG: Cap at $1.25M for >5 beneficiaries
                     ELSE CASE WHEN a.balance > (@SMDIA * 5)
                               THEN @SMDIA * 5
                               ELSE a.balance END
                END

            -- Business: 12 CFR 330.11
            WHEN a.orc_type = 'BUS' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            -- EBP: 12 CFR 330.14
            -- BUG: Should be per-participant pass-through
            WHEN a.orc_type = 'EBP' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            -- CRA: 12 CFR 330.14(c)
            WHEN a.orc_type = 'CRA' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            -- Government: 12 CFR 330.15
            -- BUG: No collateral offset
            WHEN a.orc_type IN ('GOV1', 'GOV2', 'GOV3') THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            -- IRR: 12 CFR 330.13
            -- BUG: Falls through to SGL calculation
            WHEN a.orc_type = 'IRR' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            -- ANC: 12 CFR 330.8
            WHEN a.orc_type = 'ANC' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA
                     ELSE a.balance END

            ELSE 0  -- Unknown ORC
        END AS insured_amount,

        -- Uninsured = balance - insured
        a.balance - CASE
            WHEN a.orc_type = 'SGL' THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA ELSE a.balance END
            WHEN a.orc_type = 'JNT' THEN
                CASE WHEN (a.balance / NULLIF(a.joint_owner_count, 0)) > @SMDIA
                     THEN @SMDIA * ISNULL(NULLIF(a.joint_owner_count, 0), 2)
                     ELSE a.balance END
            WHEN a.orc_type IN ('BUS','CRA','IRR','ANC','EBP') THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA ELSE a.balance END
            WHEN a.orc_type IN ('GOV1','GOV2','GOV3') THEN
                CASE WHEN a.balance > @SMDIA THEN @SMDIA ELSE a.balance END
            WHEN a.orc_type = 'REV' THEN
                CASE WHEN a.beneficiary_count <= 5
                     THEN CASE WHEN a.balance > (@SMDIA * a.beneficiary_count)
                               THEN @SMDIA * a.beneficiary_count
                               ELSE a.balance END
                     ELSE CASE WHEN a.balance > (@SMDIA * 5)
                               THEN @SMDIA * 5
                               ELSE a.balance END
                END
            ELSE a.balance
        END AS uninsured_amount,

        CASE a.orc_type
            WHEN 'SGL' THEN 'SGL_PER_ACCT'
            WHEN 'JNT' THEN 'JNT_EQUAL_SPLIT'
            WHEN 'REV' THEN 'REV_PER_BENE'
            WHEN 'BUS' THEN 'BUS_STANDARD'
            WHEN 'EBP' THEN 'EBP_NO_PASSTHRU'
            WHEN 'CRA' THEN 'CRA_STANDARD'
            WHEN 'IRR' THEN 'IRR_FALLBACK_SGL'
            ELSE 'UNKNOWN_ORC'
        END AS calc_method,

        @calc_date,
        CASE WHEN a.orc_type = 'IRR' THEN 'Y'
             WHEN a.orc_type IS NULL THEN 'Y'
             ELSE 'N'
        END AS error_flag

    FROM dbo.accounts a
    WHERE a.account_status = 'ACTIVE'
      AND a.balance > 0;

    SET @processed = @@ROWCOUNT;

    -- Log batch summary
    INSERT INTO dbo.calculation_audit_log (
        batch_id, calc_date, records_processed, error_count,
        smdia_value, created_at
    )
    VALUES (
        @batch, @calc_date, @processed,
        (SELECT COUNT(*) FROM dbo.insurance_results
         WHERE batch_id = @batch AND error_flag = 'Y'),
        @SMDIA, GETDATE()
    );

    -- Return summary
    SELECT
        @batch AS batch_id,
        @processed AS records_processed,
        SUM(balance) AS total_deposits,
        SUM(insured_amount) AS total_insured,
        SUM(uninsured_amount) AS total_uninsured,
        SUM(CASE WHEN error_flag = 'Y' THEN 1 ELSE 0 END) AS errors
    FROM dbo.insurance_results
    WHERE batch_id = @batch;
END;
GO
