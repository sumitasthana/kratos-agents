-- ============================================================================
-- sp_calculate_trust_insurance.sql
-- Calculates FDIC insurance coverage for trust and custody accounts
-- ============================================================================
-- KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
--   1. REV trusts: beneficiary cap at 5 — FDIC removed this in 2010
--   2. IRR trusts: NOT IMPLEMENTED — defaults to SGL ($250K flat)
--   3. EBP: uses plan-level participant count, not individual pass-through
--   4. Custodial accounts: all treated as SGL regardless of type
--   5. No grantor-level aggregation across multiple trusts
--   6. Sub-account balances (CDs under trust) not included
--   7. Deceased beneficiaries still counted in coverage
--   8. No cross-channel aggregation (trust + deposit system balances)
-- ============================================================================

CREATE OR ALTER PROCEDURE sp_calculate_trust_insurance
    @calc_date DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @calc_date IS NULL
        SET @calc_date = CAST(GETDATE() AS DATE);

    DECLARE @smdia DECIMAL(15,2) = 250000.00;
    DECLARE @start_time DATETIME = GETDATE();
    DECLARE @processed INT = 0;
    DECLARE @errors INT = 0;

    -- Log start
    INSERT INTO trust_audit_log (event_type, details)
    VALUES ('INSURANCE_CALC_START', 'Trust insurance calculation started for ' + CAST(@calc_date AS VARCHAR));

    -- Clear previous results
    DELETE FROM trust_insurance_results WHERE calculation_date = @calc_date;

    -- ══════════════════════════════════════════════════════════════
    -- REVOCABLE TRUSTS (REV) — 12 CFR 330.10
    -- ══════════════════════════════════════════════════════════════
    INSERT INTO trust_insurance_results (
        trust_id, orc_type, calculation_date,
        total_balance, beneficiary_count, insured_amount, uninsured_amount, calc_method
    )
    SELECT
        t.trust_id,
        'REV',
        @calc_date,
        t.balance + t.accrued_interest,
        -- BUG: Only counts PRIMARY + ACTIVE beneficiaries
        -- BUG: Should count ALL named beneficiaries regardless of type
        CASE
            WHEN bene_count > 5 THEN 5  -- BUG: Cap at 5 — removed by FDIC in 2010
            WHEN bene_count = 0 THEN 1  -- No beneficiaries → treat as grantor's own
            ELSE bene_count
        END,
        -- Insured = MIN(balance, bene_count * SMDIA)
        CASE
            WHEN (t.balance + t.accrued_interest) <=
                 CASE WHEN bene_count > 5 THEN 5 WHEN bene_count = 0 THEN 1 ELSE bene_count END * @smdia
            THEN (t.balance + t.accrued_interest)
            ELSE CASE WHEN bene_count > 5 THEN 5 WHEN bene_count = 0 THEN 1 ELSE bene_count END * @smdia
        END,
        -- Uninsured = MAX(0, balance - insured)
        CASE
            WHEN (t.balance + t.accrued_interest) >
                 CASE WHEN bene_count > 5 THEN 5 WHEN bene_count = 0 THEN 1 ELSE bene_count END * @smdia
            THEN (t.balance + t.accrued_interest) -
                 CASE WHEN bene_count > 5 THEN 5 WHEN bene_count = 0 THEN 1 ELSE bene_count END * @smdia
            ELSE 0
        END,
        'REV_PER_BENE_CAPPED_AT_5'
    FROM trust_accounts t
    CROSS APPLY (
        SELECT COUNT(*) AS bene_count
        FROM trust_beneficiaries b
        WHERE b.trust_id = t.trust_id
          AND b.beneficiary_type = 'PRI'  -- BUG: Only primary
          AND b.status = 'A'              -- BUG: Doesn't exclude deceased-but-active
    ) bc
    WHERE t.trust_type = 'REV' AND t.trust_status = 'A';

    SET @processed = @processed + @@ROWCOUNT;

    -- ══════════════════════════════════════════════════════════════
    -- IRREVOCABLE TRUSTS (IRR) — 12 CFR 330.13
    -- BUG: NOT PROPERLY IMPLEMENTED — uses SGL fallback
    -- ══════════════════════════════════════════════════════════════
    INSERT INTO trust_insurance_results (
        trust_id, orc_type, calculation_date,
        total_balance, beneficiary_count, insured_amount, uninsured_amount, calc_method
    )
    SELECT
        t.trust_id,
        'SGL',  -- BUG: Should be 'IRR'
        @calc_date,
        t.balance + t.accrued_interest,
        0,
        -- BUG: Flat $250K — should be per non-contingent beneficiary interest
        CASE
            WHEN (t.balance + t.accrued_interest) <= @smdia
            THEN (t.balance + t.accrued_interest)
            ELSE @smdia
        END,
        CASE
            WHEN (t.balance + t.accrued_interest) > @smdia
            THEN (t.balance + t.accrued_interest) - @smdia
            ELSE 0
        END,
        'IRR_NOT_IMPLEMENTED_SGL_FALLBACK'
    FROM trust_accounts t
    WHERE t.trust_type = 'IRR' AND t.trust_status = 'A';

    SET @processed = @processed + @@ROWCOUNT;

    -- ══════════════════════════════════════════════════════════════
    -- EMPLOYEE BENEFIT PLANS (EBP) — 12 CFR 330.14
    -- ══════════════════════════════════════════════════════════════
    INSERT INTO trust_insurance_results (
        trust_id, orc_type, calculation_date,
        total_balance, participant_count, insured_amount, uninsured_amount, calc_method
    )
    SELECT
        t.trust_id,
        'EBP',
        @calc_date,
        t.balance + t.accrued_interest,
        -- BUG: Uses plan-level count, includes terminated and non-vested
        COALESCE(pc.active_participants, t.participant_count),
        CASE
            WHEN (t.balance + t.accrued_interest) <=
                 COALESCE(pc.active_participants, t.participant_count) * @smdia
            THEN (t.balance + t.accrued_interest)
            ELSE COALESCE(pc.active_participants, t.participant_count) * @smdia
        END,
        CASE
            WHEN (t.balance + t.accrued_interest) >
                 COALESCE(pc.active_participants, t.participant_count) * @smdia
            THEN (t.balance + t.accrued_interest) -
                 COALESCE(pc.active_participants, t.participant_count) * @smdia
            ELSE 0
        END,
        'EBP_PER_PLAN_HEADER'
    FROM trust_accounts t
    OUTER APPLY (
        -- BUG: Counts ALL participants including terminated
        SELECT COUNT(*) AS active_participants
        FROM plan_participants p
        WHERE p.plan_trust_id = t.trust_id
        -- AND p.status = 'A'  -- BUG: This filter is commented out!
    ) pc
    WHERE t.trust_type = 'EBP' AND t.trust_status = 'A';

    SET @processed = @processed + @@ROWCOUNT;

    -- ══════════════════════════════════════════════════════════════
    -- CUSTODIAL ACCOUNTS (CUS)
    -- BUG: All treated as SGL — should determine underlying type
    -- ══════════════════════════════════════════════════════════════
    INSERT INTO trust_insurance_results (
        trust_id, orc_type, calculation_date,
        total_balance, insured_amount, uninsured_amount, calc_method
    )
    SELECT
        t.trust_id,
        'SGL',  -- BUG: Should be based on custodial account type
        @calc_date,
        t.balance + t.accrued_interest,
        CASE
            WHEN (t.balance + t.accrued_interest) <= @smdia
            THEN (t.balance + t.accrued_interest)
            ELSE @smdia
        END,
        CASE
            WHEN (t.balance + t.accrued_interest) > @smdia
            THEN (t.balance + t.accrued_interest) - @smdia
            ELSE 0
        END,
        'CUSTODIAL_AS_SGL'
    FROM trust_accounts t
    WHERE t.trust_type = 'CUS' AND t.trust_status = 'A';

    SET @processed = @processed + @@ROWCOUNT;

    -- Log completion
    INSERT INTO trust_audit_log (event_type, details)
    VALUES ('INSURANCE_CALC_COMPLETE',
            'Processed ' + CAST(@processed AS VARCHAR) + ' trusts in ' +
            CAST(DATEDIFF(SECOND, @start_time, GETDATE()) AS VARCHAR) + ' seconds');

    -- BUG: No 24-hour deadline check
    -- BUG: No grantor-level aggregation post-processing
    -- BUG: No sub-account roll-up
    -- BUG: No alert on completion

    SELECT @processed AS trusts_processed, @errors AS errors;
END;
