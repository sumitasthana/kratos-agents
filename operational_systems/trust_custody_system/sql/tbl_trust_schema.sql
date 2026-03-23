-- ============================================================================
-- Trust & Custody System Database Schema
-- SQL Server — Trust ledger, beneficiary database, fiduciary records
-- ============================================================================
-- KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
--   1. No UNIQUE on (grantor_id, trust_type) — allows duplicate trust records
--   2. Beneficiary table missing non_contingent_interest flag (12 CFR 330.13)
--   3. No FK between trust sub-accounts and trust master
--   4. Plan participants stored separately — no FK to trust
--   5. Missing deceased_date on beneficiaries and grantors
--   6. No allocation_sum CHECK constraint (should sum to 100%)
--   7. Collateral table for government trusts does not exist
--   8. Audit trail has no tamper-proof mechanism
-- ============================================================================

-- ── Trust Accounts ────────────────────────────────────────────────
CREATE TABLE trust_accounts (
    trust_id            VARCHAR(12)    PRIMARY KEY,
    trust_name          VARCHAR(100)   NOT NULL,
    trust_type          VARCHAR(3)     NOT NULL,  -- REV, IRR, EBP, CUS
    grantor_id          VARCHAR(10),              -- BUG: No FK to depositor master
    grantor_name        VARCHAR(60),
    grantor_ssn         VARCHAR(11),              -- BUG: Plaintext PII, no encryption
    trustee_id          VARCHAR(10),
    trustee_name        VARCHAR(60),
    balance             DECIMAL(15,2)  DEFAULT 0,
    accrued_interest    DECIMAL(11,2)  DEFAULT 0,
    beneficiary_count   INT            DEFAULT 0,  -- BUG: May be stale — not auto-updated
    participant_count   INT            DEFAULT 0,  -- BUG: EBP only, plan-level not individual
    orc_assigned        VARCHAR(5),               -- BUG: Trust-level ORC, not per-beneficiary
    trust_status        CHAR(1)        DEFAULT 'A', -- A=Active, C=Closed, F=Frozen
    open_date           DATE,
    close_date          DATE,
    institution_id      VARCHAR(5)     DEFAULT '99999',
    created_at          DATETIME       DEFAULT GETDATE(),
    updated_at          DATETIME       DEFAULT GETDATE()
    -- BUG: No instrument_date — can't determine trust modification history
    -- BUG: No grantor_deceased flag — REV→IRR transition not tracked
    -- BUG: No cross_reference_id — can't link sub-accounts (CDs under trust)
);

-- BUG: No unique index on (grantor_id, trust_type) — allows duplicates
CREATE INDEX idx_trust_grantor ON trust_accounts(grantor_id);
CREATE INDEX idx_trust_type ON trust_accounts(trust_type);

-- ── Trust Beneficiaries ───────────────────────────────────────────
CREATE TABLE trust_beneficiaries (
    beneficiary_id      VARCHAR(10)    PRIMARY KEY,
    trust_id            VARCHAR(12)    NOT NULL,  -- FK to trust_accounts
    beneficiary_name    VARCHAR(60)    NOT NULL,
    beneficiary_ssn     VARCHAR(11),              -- BUG: Plaintext PII
    date_of_birth       DATE,
    relationship        VARCHAR(20),               -- SPOUSE, CHILD, GRANDCHILD, etc.
    beneficiary_type    CHAR(3)        NOT NULL,   -- PRI (primary), CON (contingent), REM (remainder)
    allocation_pct      DECIMAL(5,2)   DEFAULT 0,  -- BUG: Not enforced to sum to 100%
    natural_person      CHAR(1)        DEFAULT 'Y',
    status              CHAR(1)        DEFAULT 'A', -- A=Active, D=Deceased, R=Removed
    effective_date      DATE,
    end_date            DATE,
    created_at          DATETIME       DEFAULT GETDATE()
    -- BUG: No non_contingent_interest flag — required for IRR (12 CFR 330.13)
    -- BUG: No deceased_date — can't determine when to reclassify
    -- BUG: No SSN format validation — can contain invalid values
    -- BUG: No per_stirpes flag — distribution method unknown
);

CREATE INDEX idx_bene_trust ON trust_beneficiaries(trust_id);
-- BUG: No index on beneficiary_ssn — slow duplicate detection

-- ── Plan Participants (EBP) ───────────────────────────────────────
CREATE TABLE plan_participants (
    participant_id      VARCHAR(15)    PRIMARY KEY,
    plan_trust_id       VARCHAR(12)    NOT NULL,  -- FK to trust_accounts
    participant_name    VARCHAR(60)    NOT NULL,
    participant_ssn     VARCHAR(11),              -- BUG: Plaintext PII
    employer_name       VARCHAR(60),
    plan_type           VARCHAR(20),               -- 401K, PENSION, ESOP, PROFIT_SHARING
    vested_pct          DECIMAL(5,2)   DEFAULT 100.00,
    account_balance     DECIMAL(15,2)  DEFAULT 0,
    enrollment_date     DATE,
    termination_date    DATE,                       -- BUG: Terminated participants not excluded
    status              CHAR(1)        DEFAULT 'A', -- A=Active, T=Terminated, R=Retired
    created_at          DATETIME       DEFAULT GETDATE()
    -- BUG: No vested_amount field — must calculate from pct * balance
    -- BUG: No rollover_date — can't track when participant moved funds
    -- BUG: Multiple plans per employer not linked
);

CREATE INDEX idx_participant_plan ON plan_participants(plan_trust_id);

-- ── Trust Sub-Accounts ────────────────────────────────────────────
-- Tracks CDs, savings, money market accounts held under a trust umbrella
CREATE TABLE trust_sub_accounts (
    sub_account_id      VARCHAR(15)    PRIMARY KEY,
    trust_id            VARCHAR(12),              -- BUG: No FK constraint to trust_accounts
    account_type        VARCHAR(20)    NOT NULL,   -- CD, SAVINGS, MONEY_MARKET, CHECKING
    balance             DECIMAL(15,2)  DEFAULT 0,
    interest_rate       DECIMAL(5,4),
    maturity_date       DATE,
    is_active           BIT            DEFAULT 1,
    created_at          DATETIME       DEFAULT GETDATE()
    -- BUG: Sub-account balances NOT included in trust total for insurance calc
    -- BUG: ORC type inherited from trust — not independently classified
);

-- ── Insurance Results ─────────────────────────────────────────────
CREATE TABLE trust_insurance_results (
    result_id           INT IDENTITY   PRIMARY KEY,
    trust_id            VARCHAR(12)    NOT NULL,
    orc_type            VARCHAR(5)     NOT NULL,
    calculation_date    DATE           NOT NULL,
    total_balance       DECIMAL(15,2)  NOT NULL,
    beneficiary_count   INT            DEFAULT 0,
    participant_count   INT            DEFAULT 0,
    insured_amount      DECIMAL(15,2)  NOT NULL,
    uninsured_amount    DECIMAL(15,2)  NOT NULL,
    pending_amount      DECIMAL(15,2)  DEFAULT 0,
    calc_method         VARCHAR(30),               -- REV_PER_BENE_CAPPED, IRR_NOT_IMPL, etc.
    created_at          DATETIME       DEFAULT GETDATE()
    -- BUG: No grantor_aggregation_id — can't trace multi-trust aggregation
    -- BUG: No sub_account_total — trust_sub_accounts not included
);

-- ── Audit Trail ───────────────────────────────────────────────────
CREATE TABLE trust_audit_log (
    log_id              INT IDENTITY   PRIMARY KEY,
    event_type          VARCHAR(50)    NOT NULL,
    trust_id            VARCHAR(12),
    entity_id           VARCHAR(20),               -- beneficiary_id, participant_id, etc.
    old_value           VARCHAR(500),
    new_value           VARCHAR(500),
    changed_by          VARCHAR(20),
    change_reason       VARCHAR(200),
    created_at          DATETIME       DEFAULT GETDATE()
    -- BUG: No hash chain for tamper detection
    -- BUG: old_value/new_value unstructured — hard to query
    -- BUG: changed_by often NULL in batch processing
);

-- ── Views ─────────────────────────────────────────────────────────

-- Trust Summary View — BUG: Does not include sub-account balances
CREATE VIEW vw_trust_summary AS
SELECT
    t.trust_id,
    t.trust_name,
    t.trust_type,
    t.grantor_id,
    t.grantor_name,
    t.balance + t.accrued_interest AS total_balance,
    (SELECT COUNT(*) FROM trust_beneficiaries b
     WHERE b.trust_id = t.trust_id AND b.status = 'A') AS active_beneficiaries,
    (SELECT COUNT(*) FROM trust_beneficiaries b
     WHERE b.trust_id = t.trust_id AND b.status = 'D') AS deceased_beneficiaries,
    (SELECT COUNT(*) FROM plan_participants p
     WHERE p.plan_trust_id = t.trust_id AND p.status = 'A') AS active_participants,
    (SELECT COALESCE(SUM(s.balance), 0) FROM trust_sub_accounts s
     WHERE s.trust_id = t.trust_id AND s.is_active = 1) AS sub_account_total
FROM trust_accounts t
WHERE t.trust_status = 'A';

-- Grantor Aggregation View — BUG: EXISTS but is NEVER USED in insurance calc
CREATE VIEW vw_grantor_aggregation AS
SELECT
    t.grantor_id,
    t.grantor_name,
    t.grantor_ssn,
    COUNT(DISTINCT t.trust_id) AS trust_count,
    SUM(t.balance + t.accrued_interest) AS total_trust_balance,
    STRING_AGG(t.trust_type, ',') AS trust_types
FROM trust_accounts t
WHERE t.trust_status = 'A' AND t.grantor_id IS NOT NULL
GROUP BY t.grantor_id, t.grantor_name, t.grantor_ssn;
