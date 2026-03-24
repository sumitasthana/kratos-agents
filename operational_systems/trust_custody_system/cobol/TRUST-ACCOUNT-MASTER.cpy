      ******************************************************************
      * TRUST-ACCOUNT-MASTER.CPY
      * Copybook for Trust Account Master Record Layout
      * Used by: TRUST-INSURANCE-CALC.cob, TRUST-VALUATION.cob
      ******************************************************************
      * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
      *   1. TRUST-TYPE only supports REV/IRR/EBP — missing CRA, GOV
      *   2. No field for trust instrument date or amendment tracking
      *   3. TRUST-GRANTOR-ID not linked to depositor master
      *   4. Missing fiduciary capacity indicator
      *   5. No sub-account tracking for trust-owned CDs/savings
      *   6. TRUST-BALANCE stores current market value, not deposit value
      ******************************************************************

       01  TRUST-ACCOUNT-REC.
           05  TRUST-ID                PIC X(12).
           05  TRUST-NAME              PIC X(60).
           05  TRUST-TYPE              PIC X(3).
               88  TRUST-REVOCABLE     VALUE 'REV'.
               88  TRUST-IRREVOCABLE   VALUE 'IRR'.
               88  TRUST-EBP           VALUE 'EBP'.
               88  TRUST-CUSTODIAL     VALUE 'CUS'.
           05  TRUST-GRANTOR-ID        PIC X(10).
           05  TRUST-GRANTOR-NAME      PIC X(40).
           05  TRUST-GRANTOR-SSN       PIC X(11).
           05  TRUST-TRUSTEE-ID        PIC X(10).
           05  TRUST-TRUSTEE-NAME      PIC X(40).
           05  TRUST-BALANCE           PIC S9(13)V99
                                       USAGE COMP-3.
           05  TRUST-ACCRUED-INT       PIC S9(9)V99
                                       USAGE COMP-3.
           05  TRUST-BENE-COUNT        PIC 9(3).
           05  TRUST-PARTICIP-COUNT    PIC 9(5).
           05  TRUST-STATUS            PIC X(1).
               88  TRUST-ACTIVE        VALUE 'A'.
               88  TRUST-CLOSED        VALUE 'C'.
               88  TRUST-FROZEN        VALUE 'F'.
           05  TRUST-OPEN-DATE         PIC X(10).
           05  TRUST-INSTITUTION-ID    PIC X(5).
           05  TRUST-ORC-ASSIGNED      PIC X(5).
           05  FILLER                  PIC X(30).
