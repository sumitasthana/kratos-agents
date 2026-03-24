-- ============================================================================
-- Wire Transfer System Database Schema
-- PostgreSQL 14+ — Transaction ledger, customer master, audit trail
-- ============================================================================
-- KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
--   1. No UNIQUE constraint on customer.govt_id — duplicate depositors possible
--   2. Missing FK from transactions to customers — orphan transactions allowed
--   3. No ownership_category column — prevents proper ORC classification
--   4. Beneficiary info stored as free text — not linkable to depositor master
--   5. No collateral tracking table for government deposits
--   6. Missing index on customer_id + orc_type — aggregation queries slow
--   7. No partitioning — 10+ years of transactions in single table
-- ============================================================================

-- ── Customers ─────────────────────────────────────────────────────
CREATE TABLE wire_customers (
    customer_id         VARCHAR(20)    PRIMARY KEY,
    full_name           VARCHAR(200)   NOT NULL,
    entity_type         VARCHAR(20)    DEFAULT 'INDIVIDUAL',  -- INDIVIDUAL, BUSINESS, GOVERNMENT
    govt_id             VARCHAR(20),          -- SSN or EIN — BUG: no UNIQUE constraint
    govt_id_type        VARCHAR(10),          -- SSN, EIN, ITIN
    date_of_birth       DATE,
    address_line1       VARCHAR(200),
    address_line2       VARCHAR(200),
    city                VARCHAR(100),
    state               VARCHAR(2),
    zip                 VARCHAR(10),
    country             VARCHAR(3)     DEFAULT 'USA',
    phone               VARCHAR(20),         -- BUG: Stored as plaintext
    email               VARCHAR(200),        -- BUG: Stored as plaintext
    orc_type            VARCHAR(5)     DEFAULT 'SGL',     -- BUG: Assigned at customer level, not account level
    risk_rating         VARCHAR(10)    DEFAULT 'STANDARD', -- STANDARD, ENHANCED, PROHIBITED
    is_active           BOOLEAN        DEFAULT TRUE,
    created_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    -- BUG: No natural_person flag — can't distinguish individuals from entities
    -- BUG: No deceased flag — dead depositor accounts still active
    -- BUG: No linked_depositor_id — can't aggregate across wire + deposit channels
);

-- BUG: No index on govt_id — slow deduplication queries
CREATE INDEX idx_wire_customers_name ON wire_customers(full_name);

-- ── Wire Transactions ─────────────────────────────────────────────
CREATE TABLE wire_transactions (
    txn_id              SERIAL         PRIMARY KEY,
    reference           VARCHAR(35)    NOT NULL UNIQUE,  -- SWIFT reference
    message_type        VARCHAR(10)    NOT NULL,         -- MT103, MT202, ACH
    direction           VARCHAR(10)    NOT NULL,         -- INBOUND, OUTBOUND
    ordering_customer_id VARCHAR(20),  -- BUG: No FK constraint to wire_customers
    ordering_name       VARCHAR(200),  -- BUG: Denormalized — may drift from customer master
    beneficiary_name    VARCHAR(200),  -- BUG: Free text — not linked to depositor
    beneficiary_account VARCHAR(50),
    beneficiary_bank    VARCHAR(100),
    amount              NUMERIC(18,2)  NOT NULL,
    currency            VARCHAR(3)     DEFAULT 'USD',
    converted_amount    NUMERIC(18,2), -- USD equivalent — BUG: stale FX rate
    fx_rate             NUMERIC(12,6),
    fees                NUMERIC(10,2)  DEFAULT 0,
    net_amount          NUMERIC(18,2), -- BUG: Calculated field not always populated
    status              VARCHAR(20)    DEFAULT 'PENDING', -- PENDING, SETTLED, RETURNED, BLOCKED, FAILED
    orc_type            VARCHAR(5),    -- BUG: Copied from customer, not transaction-specific
    settlement_channel  VARCHAR(20),   -- FEDWIRE, SWIFT, ACH, BOOK_TRANSFER
    ofac_status         VARCHAR(20)    DEFAULT 'NOT_SCREENED', -- BUG: Default is "not screened"
    value_date          DATE,
    settled_at          TIMESTAMP,
    created_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    -- BUG: No insurance_relevant flag — all txns treated equally
    -- BUG: No pending_deposit_code column — can't classify pending types
    -- BUG: No return_reason_code — ACH returns not categorized
);

CREATE INDEX idx_wire_txn_customer ON wire_transactions(ordering_customer_id);
CREATE INDEX idx_wire_txn_date ON wire_transactions(value_date);
-- BUG: Missing index on (ordering_customer_id, orc_type) for insurance aggregation

-- ── Insurance Results ─────────────────────────────────────────────
CREATE TABLE wire_insurance_results (
    result_id           SERIAL         PRIMARY KEY,
    customer_id         VARCHAR(20)    NOT NULL,
    orc_type            VARCHAR(5)     NOT NULL,
    calculation_date    DATE           NOT NULL,
    total_deposits      NUMERIC(18,2)  NOT NULL,
    insured_amount      NUMERIC(18,2)  NOT NULL,
    uninsured_amount    NUMERIC(18,2)  NOT NULL,
    pending_amount      NUMERIC(18,2)  DEFAULT 0,  -- BUG: Always 0 — pending wires not included
    calculation_method  VARCHAR(20)    DEFAULT 'PER_TRANSACTION',  -- BUG: Should be AGGREGATED
    created_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    -- BUG: No aggregation_group_id — can't trace back to individual transactions
    -- BUG: No cross_channel_flag — wire + deposit balances not combined
);

-- ── Audit Log ─────────────────────────────────────────────────────
CREATE TABLE wire_audit_log (
    log_id              SERIAL         PRIMARY KEY,
    event_type          VARCHAR(50)    NOT NULL,
    reference           VARCHAR(35),
    details             TEXT,
    operator_id         VARCHAR(20),   -- BUG: Often NULL — no mandatory operator tracking
    ip_address          VARCHAR(45),
    created_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    -- BUG: No event_severity column — can't filter critical vs info events
    -- BUG: No retention policy — logs grow unbounded
    -- BUG: No tamper-proof mechanism (hash chain, append-only, etc.)
);

-- ── OFAC Screening Results ────────────────────────────────────────
CREATE TABLE wire_ofac_results (
    screening_id        SERIAL         PRIMARY KEY,
    txn_reference       VARCHAR(35)    NOT NULL,
    screened_name       VARCHAR(200)   NOT NULL,
    party_type          VARCHAR(20),   -- ORDERING, BENEFICIARY
    match_score         NUMERIC(5,1),
    matched_entry_id    VARCHAR(20),
    matched_name        VARCHAR(200),
    match_type          VARCHAR(10),   -- PRIMARY, ALIAS
    list_type           VARCHAR(20)    DEFAULT 'SDN',  -- BUG: Only SDN — no EU/UK/UN lists
    disposition         VARCHAR(20)    DEFAULT 'PENDING', -- PENDING, CLEARED, BLOCKED, ESCALATED
    reviewed_by         VARCHAR(20),
    reviewed_at         TIMESTAMP,
    created_at          TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
    -- BUG: No link to depositor_id — can't assess insurance impact of blocked funds
    -- BUG: blocked amounts not excluded from insurance calculation
);

-- ── Depositor Balance Snapshot ────────────────────────────────────
-- BUG: This view only considers settled wire transactions
-- BUG: Does not include deposit/savings/CD account balances from other systems
-- BUG: Pending wires excluded
CREATE VIEW vw_wire_depositor_balance AS
SELECT
    c.customer_id AS depositor_id,
    c.full_name AS depositor_name,
    c.govt_id,
    c.orc_type,
    COALESCE(SUM(CASE WHEN t.direction = 'INBOUND' AND t.status = 'SETTLED'
                      THEN t.net_amount ELSE 0 END), 0)
    - COALESCE(SUM(CASE WHEN t.direction = 'OUTBOUND' AND t.status = 'SETTLED'
                      THEN t.net_amount ELSE 0 END), 0) AS net_balance,
    COUNT(t.txn_id) AS transaction_count,
    MAX(t.settled_at) AS last_activity
FROM wire_customers c
LEFT JOIN wire_transactions t ON c.customer_id = t.ordering_customer_id
WHERE c.is_active = TRUE
GROUP BY c.customer_id, c.full_name, c.govt_id, c.orc_type;
