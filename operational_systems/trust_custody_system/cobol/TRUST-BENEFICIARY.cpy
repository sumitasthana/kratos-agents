      ******************************************************************
      * TRUST-BENEFICIARY.CPY
      * Copybook for Trust Beneficiary Record Layout
      * Used by: TRUST-INSURANCE-CALC.cob, TRUST-VALUATION.cob
      ******************************************************************
      * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
      *   1. BENE-ALLOCATION-PCT not used in coverage calculation
      *   2. No field for contingent vs non-contingent interest
      *   3. BENE-RELATIONSHIP limited to 10 chars — truncates types
      *   4. Missing: charitable beneficiary flag, minor flag
      *   5. No death date field — deceased beneficiaries counted
      *   6. Missing beneficiary-of-beneficiary (successor) tracking
      ******************************************************************

       01  TRUST-BENEFICIARY-REC.
           05  BENE-ID                 PIC X(10).
           05  BENE-TRUST-ID           PIC X(12).
           05  BENE-NAME               PIC X(40).
           05  BENE-SSN                PIC X(11).
           05  BENE-DOB                PIC X(10).
           05  BENE-RELATIONSHIP       PIC X(10).
           05  BENE-TYPE               PIC X(3).
               88  BENE-PRIMARY        VALUE 'PRI'.
               88  BENE-CONTINGENT     VALUE 'CON'.
               88  BENE-REMAINDER      VALUE 'REM'.
           05  BENE-ALLOCATION-PCT     PIC 9(3)V99.
           05  BENE-NATURAL-PERSON     PIC X.
               88  BENE-IS-PERSON      VALUE 'Y'.
               88  BENE-IS-ENTITY      VALUE 'N'.
           05  BENE-STATUS             PIC X(1).
               88  BENE-ACTIVE         VALUE 'A'.
               88  BENE-DECEASED       VALUE 'D'.
               88  BENE-REMOVED        VALUE 'R'.
           05  BENE-EFF-DATE           PIC X(10).
           05  BENE-END-DATE           PIC X(10).
           05  FILLER                  PIC X(20).
