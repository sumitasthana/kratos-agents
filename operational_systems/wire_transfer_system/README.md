# Wire Transfer & Payment Processing System

Enterprise wire transfer and payment processing platform handling domestic/international
payments, ACH batch processing, and real-time gross settlement (RTGS) transactions.

## Technology Stack
- **Python 3.8** — ETL pipelines, payment routing engine, OFAC screening
- **Java/Spring Boot** — REST API gateway, transaction orchestration
- **PostgreSQL** — Transaction ledger, customer master, audit trail
- **Shell Scripts** — Nightly batch reconciliation, SWIFT message processing
- **CSV/XML Config** — Routing rules, fee schedules, compliance thresholds

## FDIC Part 370 Compliance Status: **PARTIALLY TESTED**

Known coverage gaps exist in beneficiary identification for wire transfers,
depositor aggregation across payment channels, and 24-hour processing SLA compliance.

## Architecture

```
[SWIFT/FedWire] → [Message Parser] → [OFAC Screen] → [Routing Engine]
                                           ↓
                              [Transaction Ledger (PostgreSQL)]
                                           ↓
                              [Settlement Engine] → [GL Posting]
                                           ↓
                              [QDF/ARE Output Generation]
```

## Compliance Scenario
This system represents a **MODERATE RISK** profile with:
- Partial OFAC integration (batch-only, no real-time screening)
- Missing beneficiary tracking for international wires
- Incomplete pending deposit classification
- No encrypted PII in output files
- ACH returns not properly reflected in insurance calculations
