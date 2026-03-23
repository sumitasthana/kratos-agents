-- ============================================================
-- STORED PROCEDURE: sp_aggregate_deposits
-- PURPOSE: Aggregate deposits by depositor + ORC for insurance
-- REGULATION: 12 CFR Part 330/370 — insurance must be on aggregate
--
-- NOTE: This procedure exists but is NOT called by the main
-- insurance calculation (sp_calculate_insurance), which processes
-- per-account. This is a CRITICAL gap — the aggregation should
-- run BEFORE insurance calculation per regulatory requirements.
--
-- KNOWN ISSUES:
--   - Not integrated into main calculation pipeline
--   - Does not handle cross-system depositor matching
--   - Deceased depositor accounts not flagged
--   - No duplicate government_id detection
-- ============================================================

CREATE OR ALTER PROCEDURE dbo.sp_aggregate_deposits
    @as_of_date DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ref_date DATE = ISNULL(@as_of_date, GETDATE());

    -- Aggregate by depositor + ORC type
    -- BUG: This procedure exists but is never called by
    -- sp_calculate_insurance. The insurance calc runs per-account
    -- instead of using these aggregated totals.
    SELECT
        a.depositor_id,
        c.customer_name,
        c.government_id,
        a.orc_type,
        COUNT(a.account_number) AS account_count,
        SUM(a.balance) AS aggregate_balance,
        MIN(a.balance) AS min_account_balance,
        MAX(a.balance) AS max_account_balance
    INTO #depositor_aggregates
    FROM dbo.accounts a
    INNER JOIN dbo.customers c ON a.depositor_id = c.depositor_id
    WHERE a.account_status = 'ACTIVE'
      AND a.balance >= 0
    GROUP BY a.depositor_id, c.customer_name, c.government_id, a.orc_type;

    -- BUG: No check for duplicate government_ids across depositors
    -- Two different depositor_ids could map to the same person

    -- BUG: No detection of deceased depositors requiring
    -- 6-month review per 12 CFR 330.3(j)

    -- BUG: No cross-system matching (core banking + trust system
    -- + IRA system may have same person as different depositor_ids)

    -- Return aggregated results
    SELECT * FROM #depositor_aggregates
    ORDER BY aggregate_balance DESC;

    DROP TABLE #depositor_aggregates;
END;
GO


-- ============================================================
-- VIEW: vw_depositor_portfolio
-- PURPOSE: Consolidated depositor portfolio view
-- BUG: Does not join to beneficiary data for trust accounts
-- BUG: No collateral information for government accounts
-- ============================================================

CREATE OR ALTER VIEW dbo.vw_depositor_portfolio AS
SELECT
    c.depositor_id,
    c.customer_name,
    c.government_id,
    c.is_natural_person,
    c.date_of_death,
    a.account_number,
    a.account_type,
    a.balance,
    a.orc_type,
    a.joint_owner_count,
    a.beneficiary_count,
    a.business_name,
    a.government_entity,
    a.account_status,
    a.source_system,
    -- BUG: Missing beneficiary details for trust accounts
    -- BUG: Missing collateral pledges for government accounts
    -- BUG: Missing EBP participant count
    -- BUG: Missing right_and_capacity per IT Guide
    CASE WHEN c.date_of_death IS NOT NULL
         THEN 'DECEASED'
         ELSE 'ACTIVE'
    END AS depositor_status
FROM dbo.customers c
LEFT JOIN dbo.accounts a ON c.depositor_id = a.depositor_id;
GO
