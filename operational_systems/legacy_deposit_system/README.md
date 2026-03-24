# Legacy Deposit Insurance Determination System
## Enterprise Banking Compliance Platform

This is a legacy enterprise deposit insurance determination system
representative of systems found in large US banking institutions.
The system combines mainframe COBOL programs, SQL stored procedures,
Java middleware, batch JCL jobs, and shell scripts — a typical
multi-generation technology stack accumulated over 20+ years.

### Technology Stack
- **COBOL** — Core insurance calculation and ORC assignment (mainframe heritage)
- **SQL Server** — Stored procedures for aggregation and reporting
- **Java/Spring** — Middleware REST API and batch processing
- **JCL** — Mainframe batch job scheduling
- **Shell Scripts** — ETL data extraction and nightly processing
- **Config Files** — Properties, XML, CSV rule mappings

### Compliance Status: UNTESTED
This system has NOT been validated against current FDIC Part 370 requirements.
Known gaps may exist in ORC handling, insurance calculation, output file
generation, and certification readiness.

### System Architecture
```
[Core Banking DB] → [ETL Scripts] → [COBOL Batch] → [SQL Aggregation]
                                          ↓
                                   [Java Middleware]
                                          ↓
                              [QDF/ARE Output Generation]
```
