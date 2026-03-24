-- ============================================================
-- TABLE SCHEMA: FDIC Part 370 Deposit Insurance System
-- PURPOSE: Core database tables for insurance determination
--
-- KNOWN ISSUES:
--   - customers table missing email, phone fields
--   - accounts table missing ownership_category field
--   - accounts table missing collateral_pledge_ref for GOV
--   - accounts table missing ebp_participant_count
--   - No beneficiary table with government_id
--   - No data lineage/audit trail table
--   - Missing indices for performance
-- ============================================================

-- Customer master table
CREATE TABLE dbo.customers (
    depositor_id        VARCHAR(15) PRIMARY KEY,
    customer_name       VARCHAR(100) NOT NULL,
    government_id       VARCHAR(15),        -- SSN or EIN
    -- BUG: No UNIQUE constraint on government_id
    -- Allows duplicate persons across depositor_ids
    is_natural_person   CHAR(1) DEFAULT 'Y',
    date_of_birth       DATE,
    date_of_death       DATE,               -- NULL if alive
    address_line1       VARCHAR(100),
    address_city        VARCHAR(50),
    address_state       CHAR(2),
    address_zip         VARCHAR(10),
    -- MISSING: email per IT Guide 2.3.2
    -- MISSING: phone per IT Guide 2.3.2
    -- MISSING: tax_id_type (SSN vs EIN distinction)
    source_system       VARCHAR(20) DEFAULT 'CORE_BANKING',
    last_updated        DATETIME DEFAULT GETDATE(),
    created_at          DATETIME DEFAULT GETDATE()
);

-- Account master table
CREATE TABLE dbo.accounts (
    account_number      VARCHAR(20) PRIMARY KEY,
    depositor_id        VARCHAR(15) NOT NULL,
    -- BUG: No FOREIGN KEY to customers table
    -- Allows orphan accounts referencing non-existent customers
    balance             DECIMAL(15,2) NOT NULL DEFAULT 0,
    orc_type            VARCHAR(4),
    account_type        VARCHAR(20) NOT NULL,
    account_status      VARCHAR(10) DEFAULT 'ACTIVE',
    open_date           DATE,
    close_date          DATE,
    source_system       VARCHAR(20) DEFAULT 'CORE_BANKING',
    joint_owner_count   INT DEFAULT 0,
    beneficiary_count   INT DEFAULT 0,
    business_name       VARCHAR(100),
    government_entity   VARCHAR(100),
    tax_id              VARCHAR(15),
    -- MISSING: ownership_category per Part 370 Appendix A
    -- MISSING: collateral_pledge_ref for GOV accounts
    -- MISSING: ebp_participant_count for EBP accounts
    -- MISSING: right_and_capacity per IT Guide
    last_updated        DATETIME DEFAULT GETDATE()
);

-- Insurance calculation results
CREATE TABLE dbo.insurance_results (
    result_id           INT IDENTITY(1,1) PRIMARY KEY,
    batch_id            VARCHAR(50) NOT NULL,
    account_number      VARCHAR(20) NOT NULL,
    depositor_id        VARCHAR(15) NOT NULL,
    orc_type            VARCHAR(4),
    balance             DECIMAL(15,2),
    insured_amount      DECIMAL(15,2),
    uninsured_amount    DECIMAL(15,2),
    calc_method         VARCHAR(30),
    calc_timestamp      DATETIME DEFAULT GETDATE(),
    error_flag          CHAR(1) DEFAULT 'N',
    -- MISSING: pending_reason_code
    -- MISSING: aggregation_group_id for cross-account aggregation
    INDEX ix_batch_id (batch_id),
    INDEX ix_depositor (depositor_id)
);

-- Audit log
CREATE TABLE dbo.calculation_audit_log (
    log_id              INT IDENTITY(1,1) PRIMARY KEY,
    batch_id            VARCHAR(50),
    calc_date           DATE,
    records_processed   INT,
    error_count         INT,
    smdia_value         DECIMAL(15,2),
    created_at          DATETIME DEFAULT GETDATE()
    -- MISSING: completed_within_24hrs flag per 12 CFR 370.3(b)
    -- MISSING: operator_id for accountability
);

-- Pending deposits (incomplete)
-- BUG: Only 5 reason codes. IT Guide Section 2.4 requires 10.
CREATE TABLE dbo.pending_deposits (
    pending_id          INT IDENTITY(1,1) PRIMARY KEY,
    account_number      VARCHAR(20),
    depositor_id        VARCHAR(15),
    balance             DECIMAL(15,2),
    reason_code         VARCHAR(3),
    reason_description  VARCHAR(200),
    entered_date        DATETIME DEFAULT GETDATE(),
    -- BUG: No auto_resolve_deadline. No 6-month review cycle.
    resolved_date       DATETIME,
    resolved_by         VARCHAR(50),
    status              VARCHAR(10) DEFAULT 'PENDING'
);

-- Joint owners (separate table for JNT accounts)
CREATE TABLE dbo.joint_owners (
    owner_id            INT IDENTITY(1,1) PRIMARY KEY,
    account_number      VARCHAR(20) NOT NULL,
    co_owner_name       VARCHAR(100),
    co_owner_govt_id    VARCHAR(15),
    -- BUG: No is_natural_person flag
    -- Per 12 CFR 330.9, all JNT co-owners must be natural persons
    -- BUG: No withdrawal_rights or signature_card evidence
    ownership_percentage DECIMAL(5,2)
    -- BUG: Percentage not used in insurance calculation
    -- Calculation uses equal division instead
);

-- Trust beneficiaries
CREATE TABLE dbo.trust_beneficiaries (
    beneficiary_id      INT IDENTITY(1,1) PRIMARY KEY,
    account_number      VARCHAR(20) NOT NULL,
    grantor_depositor_id VARCHAR(15),
    beneficiary_name    VARCHAR(100),
    -- MISSING: beneficiary_govt_id for identification
    -- MISSING: allocation_percentage for >5 beneficiary calc
    relationship        VARCHAR(30)
);
