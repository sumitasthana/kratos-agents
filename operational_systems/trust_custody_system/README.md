# Trust & Custody Account Management System

Fiduciary trust and custody account platform managing revocable/irrevocable trusts,
employee benefit plans, custodial accounts, and government deposit safekeeping.

## Technology Stack
- **COBOL/CICS** — Core trust accounting engine (mainframe), beneficiary registry
- **Java/Spring** — Trust administration API, plan participant management
- **SQL Server** — Trust ledger, beneficiary database, fiduciary records
- **JCL** — Daily trust valuation batch, beneficiary payout processing
- **Shell Scripts** — Trust-to-deposit reconciliation, regulatory extract
- **XML/Properties** — Trust rules, beneficiary allocation, coverage tables

## FDIC Part 370 Compliance Status: **HIGH RISK — UNTESTED**

This system has SIGNIFICANT compliance gaps in beneficiary tracking, pass-through
coverage calculation, and trust-type classification. It is the most complex system
for FDIC insurance determination due to multi-layered ownership structures.

## Architecture

```
[Trust Instruments DB] → [Beneficiary Registry] → [Trust COBOL Engine]
                                                          ↓
                                              [Plan Participant Loader]
                                                          ↓
                                              [Insurance Calc (Multi-Layer)]
                                                          ↓
                                              [QDF/ARE with Trust Overlay]
```

## Compliance Scenario
This system represents a **HIGH RISK** profile with:
- Revocable trust beneficiaries not properly enumerated (affects 12 CFR 330.10)
- Irrevocable trust not implemented at all (12 CFR 330.13 gap)
- EBP participant count hardcoded to plan level, not individual (12 CFR 330.14)
- Trust-owned CDs treated as single ownership (should inherit trust ORC)
- Government trust accounts missing collateral documentation
- No beneficiary change audit trail — stale data in coverage calc
- Deceased beneficiary accounts not flagged or excluded
