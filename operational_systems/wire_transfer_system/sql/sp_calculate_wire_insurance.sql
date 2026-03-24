-- ============================================================================
-- sp_calculate_wire_insurance.sql
-- Calculates FDIC deposit insurance coverage for wire transfer depositors
-- ============================================================================
-- KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
--   1. Per-customer calculation — not aggregated by ORC type across products
--   2. Only considers SETTLED wire transactions — pending excluded
--   3. No cross-system aggregation (wire + deposit + savings balances)
--   4. Government deposits (GOV1/GOV2/GOV3) — collateral not checked
--   5. JNT ORC uses equal split — not actual ownership interest
--   6. IRR (irrevocable trust) falls through to SGL default
--   7. EBP (employee benefit plan) capped at $250K — should be per participant
--   8. REV trust: caps at 5 beneficiaries ($1.25M) — should be unlimited
--   9. ACH credits included but ACH returns not deducted
-- ============================================================================

CREATE OR REPLACE PROCEDURE sp_calculate_wire_insurance(
    p_calc_date DATE DEFAULT CURRENT_DATE
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_smdia          NUMERIC(18,2) := 250000.00;
    v_start_time     TIMESTAMP;
    v_processed      INTEGER := 0;
    v_errors         INTEGER := 0;
BEGIN
    v_start_time := CURRENT_TIMESTAMP;

    -- Log start
    INSERT INTO wire_audit_log (event_type, details)
    VALUES ('INSURANCE_CALC_START', 'Wire insurance calculation started for ' || p_calc_date);

    -- Clear previous results for this date
    DELETE FROM wire_insurance_results WHERE calculation_date = p_calc_date;

    -- Calculate insurance per customer per ORC type
    -- BUG: Should aggregate across ALL deposit channels, not just wires
    INSERT INTO wire_insurance_results (
        customer_id, orc_type, calculation_date,
        total_deposits, insured_amount, uninsured_amount, pending_amount
    )
    SELECT
        c.customer_id,
        c.orc_type,
        p_calc_date,
        -- Total deposits from settled wire transactions
        COALESCE(SUM(
            CASE WHEN t.direction = 'INBOUND' AND t.status = 'SETTLED'
                 THEN COALESCE(t.converted_amount, t.amount)
                 WHEN t.direction = 'OUTBOUND' AND t.status = 'SETTLED'
                 THEN -COALESCE(t.converted_amount, t.amount)
                 ELSE 0
            END
        ), 0) AS total_deposits,
        -- Insured amount by ORC type
        LEAST(
            GREATEST(
                COALESCE(SUM(
                    CASE WHEN t.direction = 'INBOUND' AND t.status = 'SETTLED'
                         THEN COALESCE(t.converted_amount, t.amount)
                         WHEN t.direction = 'OUTBOUND' AND t.status = 'SETTLED'
                         THEN -COALESCE(t.converted_amount, t.amount)
                         ELSE 0
                    END
                ), 0),
                0
            ),
            CASE c.orc_type
                WHEN 'SGL' THEN v_smdia
                WHEN 'JNT' THEN v_smdia * 2          -- BUG: Hardcoded 2 owners
                WHEN 'REV' THEN v_smdia * 5           -- BUG: Capped at 5 beneficiaries
                WHEN 'BUS' THEN v_smdia
                WHEN 'EBP' THEN v_smdia               -- BUG: Flat $250K, not per participant
                WHEN 'CRA' THEN v_smdia
                WHEN 'GOV1' THEN v_smdia               -- BUG: No collateral offset
                WHEN 'GOV2' THEN v_smdia
                WHEN 'GOV3' THEN v_smdia
                WHEN 'IRR' THEN v_smdia                -- BUG: IRR should have per-beneficiary calc
                ELSE v_smdia                           -- BUG: Unknown ORC → SGL default
            END
        ) AS insured_amount,
        -- Uninsured = Total - Insured (floored at 0)
        GREATEST(
            COALESCE(SUM(
                CASE WHEN t.direction = 'INBOUND' AND t.status = 'SETTLED'
                     THEN COALESCE(t.converted_amount, t.amount)
                     WHEN t.direction = 'OUTBOUND' AND t.status = 'SETTLED'
                     THEN -COALESCE(t.converted_amount, t.amount)
                     ELSE 0
                END
            ), 0) -
            LEAST(
                GREATEST(
                    COALESCE(SUM(
                        CASE WHEN t.direction = 'INBOUND' AND t.status = 'SETTLED'
                             THEN COALESCE(t.converted_amount, t.amount)
                             WHEN t.direction = 'OUTBOUND' AND t.status = 'SETTLED'
                             THEN -COALESCE(t.converted_amount, t.amount)
                             ELSE 0
                        END
                    ), 0),
                    0
                ),
                CASE c.orc_type
                    WHEN 'JNT' THEN v_smdia * 2
                    WHEN 'REV' THEN v_smdia * 5
                    ELSE v_smdia
                END
            ),
            0
        ) AS uninsured_amount,
        -- Pending deposits — BUG: Always 0, pending wires not included
        0 AS pending_amount
    FROM wire_customers c
    LEFT JOIN wire_transactions t
        ON c.customer_id = t.ordering_customer_id
        AND t.value_date <= p_calc_date
    WHERE c.is_active = TRUE
    GROUP BY c.customer_id, c.orc_type;

    GET DIAGNOSTICS v_processed = ROW_COUNT;

    -- Log completion
    INSERT INTO wire_audit_log (event_type, details)
    VALUES ('INSURANCE_CALC_COMPLETE',
            format('Processed %s depositors in %s',
                   v_processed,
                   age(CURRENT_TIMESTAMP, v_start_time)));

    -- BUG: No check if processing exceeded 24-hour deadline
    -- BUG: No notification on completion
    -- BUG: No validation that results sum matches ledger total

EXCEPTION WHEN OTHERS THEN
    v_errors := v_errors + 1;
    INSERT INTO wire_audit_log (event_type, details)
    VALUES ('INSURANCE_CALC_ERROR', SQLERRM);
    RAISE;
END;
$$;
