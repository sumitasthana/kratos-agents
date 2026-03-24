       IDENTIFICATION DIVISION.
       PROGRAM-ID. TRUST-INSURANCE-CALC.
      ******************************************************************
      * TRUST DEPOSIT INSURANCE CALCULATOR
      * Calculates FDIC insurance coverage for trust and custody accounts
      * with complex ownership structures and beneficiary overlays.
      ******************************************************************
      * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
      *   1. REV trust: only counts PRIMARY beneficiaries — CONTINGENT
      *      and REMAINDER beneficiaries ignored (12 CFR 330.10 gap)
      *   2. IRR trust: NOT IMPLEMENTED — falls through to SGL default
      *      violating 12 CFR 330.13 per-non-contingent-interest rule
      *   3. EBP: uses TRUST-PARTICIP-COUNT which is plan-level count,
      *      not actual number of participants with vested interest
      *      (violates 12 CFR 330.14 pass-through coverage)
      *   4. Per-trust calculation — NOT aggregated by grantor across
      *      multiple trusts (same grantor, same beneficiaries = 1 limit)
      *   5. Deceased beneficiaries still counted — inflates coverage
      *   6. CUSTODIAL accounts default to SGL — should use underlying
      *      ownership type (e.g., IRA custodial = IRR)
      *   7. Beneficiary allocation percentage not used — equal split
      *   8. No handling of charitable remainder trusts
      *   9. Trust sub-accounts (CDs, savings) not rolled up to trust
      *  10. Missing audit trail — no record of calculation methodology
      ******************************************************************

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRUST-FILE    ASSIGN TO TRUSTIN
                                ORGANIZATION IS SEQUENTIAL
                                ACCESS MODE IS SEQUENTIAL
                                FILE STATUS IS WS-TRUST-FS.
           SELECT BENE-FILE     ASSIGN TO BENEIN
                                ORGANIZATION IS SEQUENTIAL
                                ACCESS MODE IS SEQUENTIAL
                                FILE STATUS IS WS-BENE-FS.
           SELECT RESULT-FILE   ASSIGN TO RESULTOUT
                                ORGANIZATION IS SEQUENTIAL
                                ACCESS MODE IS SEQUENTIAL
                                FILE STATUS IS WS-RESULT-FS.
           SELECT ERROR-FILE    ASSIGN TO ERROROUT
                                ORGANIZATION IS SEQUENTIAL
                                ACCESS MODE IS SEQUENTIAL
                                FILE STATUS IS WS-ERROR-FS.

       DATA DIVISION.
       FILE SECTION.
       FD  TRUST-FILE.
       COPY TRUST-ACCOUNT-MASTER.

       FD  BENE-FILE.
       COPY TRUST-BENEFICIARY.

       FD  RESULT-FILE.
       01  RESULT-REC.
           05  RES-TRUST-ID         PIC X(12).
           05  RES-TRUST-NAME       PIC X(60).
           05  RES-TRUST-TYPE       PIC X(3).
           05  RES-ORC-TYPE         PIC X(5).
           05  RES-GRANTOR-ID       PIC X(10).
           05  RES-TOTAL-BALANCE    PIC S9(13)V99.
           05  RES-BENE-COUNT       PIC 9(3).
           05  RES-INSURED-AMT      PIC S9(13)V99.
           05  RES-UNINSURED-AMT    PIC S9(13)V99.
           05  RES-PENDING-AMT      PIC S9(13)V99.
           05  RES-CALC-METHOD      PIC X(20).
           05  RES-STATUS           PIC X(10).

       FD  ERROR-FILE.
       01  ERROR-REC               PIC X(200).

       WORKING-STORAGE SECTION.
       01  WS-TRUST-FS             PIC XX.
       01  WS-BENE-FS              PIC XX.
       01  WS-RESULT-FS            PIC XX.
       01  WS-ERROR-FS             PIC XX.
       01  WS-EOF-TRUST            PIC X VALUE 'N'.
       01  WS-EOF-BENE             PIC X VALUE 'N'.

       01  WS-SMDIA                PIC 9(9)V99 VALUE 250000.00.
       01  WS-TOTAL-INSURED        PIC S9(13)V99 VALUE ZEROS.
       01  WS-TOTAL-UNINSURED      PIC S9(13)V99 VALUE ZEROS.
       01  WS-CALC-BALANCE         PIC S9(13)V99 VALUE ZEROS.
       01  WS-PER-BENE-LIMIT       PIC S9(13)V99 VALUE ZEROS.
       01  WS-ACTIVE-BENE          PIC 9(3) VALUE ZEROS.
       01  WS-TRUST-COUNT          PIC 9(5) VALUE ZEROS.
       01  WS-ERROR-COUNT          PIC 9(5) VALUE ZEROS.
       01  WS-CURRENT-DATE         PIC X(10).

      * BUG: No working storage for grantor-level aggregation
      * BUG: No tracking of previously processed trusts for same grantor

       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INITIALIZE
           PERFORM 2000-PROCESS-TRUSTS UNTIL WS-EOF-TRUST = 'Y'
           PERFORM 9000-FINALIZE
           STOP RUN.

       1000-INITIALIZE.
           OPEN INPUT  TRUST-FILE
                INPUT  BENE-FILE
                OUTPUT RESULT-FILE
                OUTPUT ERROR-FILE.
           MOVE FUNCTION CURRENT-DATE(1:10) TO WS-CURRENT-DATE.
           READ TRUST-FILE
               AT END MOVE 'Y' TO WS-EOF-TRUST
           END-READ.

       2000-PROCESS-TRUSTS.
      * Process each trust account
           ADD 1 TO WS-TRUST-COUNT

      * Determine ORC type and calculate coverage
           EVALUATE TRUE
               WHEN TRUST-REVOCABLE
                   PERFORM 3100-CALC-REVOCABLE
               WHEN TRUST-IRREVOCABLE
                   PERFORM 3200-CALC-IRREVOCABLE
               WHEN TRUST-EBP
                   PERFORM 3300-CALC-EBP
               WHEN TRUST-CUSTODIAL
                   PERFORM 3400-CALC-CUSTODIAL
               WHEN OTHER
      * BUG: Unrecognized trust types default to SGL
      * Should raise error for manual review
                   PERFORM 3900-CALC-DEFAULT
           END-EVALUATE

           READ TRUST-FILE
               AT END MOVE 'Y' TO WS-EOF-TRUST
           END-READ.

       3100-CALC-REVOCABLE.
      * Revocable Trust — 12 CFR 330.10
      * Coverage = $250,000 per qualifying beneficiary
      * BUG #1: Only counts beneficiaries with BENE-TYPE = 'PRI'
      *         Should also count named contingent beneficiaries
      * BUG #2: Deceased beneficiaries (BENE-STATUS = 'D') still counted
      * BUG #3: Does not check if beneficiary is a natural person
      * BUG #4: BENE-ALLOCATION-PCT ignored — assumes equal split
      * BUG #5: No grantor-level aggregation across multiple REV trusts

           MOVE ZEROS TO WS-ACTIVE-BENE
           COMPUTE WS-CALC-BALANCE =
               TRUST-BALANCE + TRUST-ACCRUED-INT

      * Count active primary beneficiaries from BENE-FILE
      * BUG: Sequential scan — extremely slow for large beneficiary files
           PERFORM VARYING WS-ACTIVE-BENE
               FROM 1 BY 0
               UNTIL WS-EOF-BENE = 'Y'
               READ BENE-FILE
                   AT END MOVE 'Y' TO WS-EOF-BENE
               END-READ
               IF BENE-TRUST-ID = TRUST-ID
                   AND BENE-PRIMARY
                   AND BENE-ACTIVE
                   ADD 1 TO WS-ACTIVE-BENE
               END-IF
           END-PERFORM

      * If no beneficiaries found, use header count
      * BUG: Header count may be stale — not synced with beneficiary file
           IF WS-ACTIVE-BENE = 0
               MOVE TRUST-BENE-COUNT TO WS-ACTIVE-BENE
           END-IF

      * BUG: Cap beneficiaries at 5 — FDIC rules do NOT cap
      * This was an OLD rule (pre-2010) that has been removed
           IF WS-ACTIVE-BENE > 5
               MOVE 5 TO WS-ACTIVE-BENE
           END-IF

      * Calculate per-beneficiary limit
           COMPUTE WS-PER-BENE-LIMIT =
               WS-SMDIA * WS-ACTIVE-BENE

           IF WS-CALC-BALANCE <= WS-PER-BENE-LIMIT
               MOVE WS-CALC-BALANCE TO WS-TOTAL-INSURED
               MOVE ZEROS TO WS-TOTAL-UNINSURED
           ELSE
               MOVE WS-PER-BENE-LIMIT TO WS-TOTAL-INSURED
               COMPUTE WS-TOTAL-UNINSURED =
                   WS-CALC-BALANCE - WS-PER-BENE-LIMIT
           END-IF

           MOVE 'REV'               TO RES-ORC-TYPE
           MOVE 'PER_BENE_CAPPED'   TO RES-CALC-METHOD
           PERFORM 8000-WRITE-RESULT.

       3200-CALC-IRREVOCABLE.
      * Irrevocable Trust — 12 CFR 330.13
      * Coverage based on each beneficiary's non-contingent interest
      * BUG: THIS ENTIRE SECTION IS NOT IMPLEMENTED
      * All IRR trusts fall through to SGL default ($250K flat)

           COMPUTE WS-CALC-BALANCE =
               TRUST-BALANCE + TRUST-ACCRUED-INT

      * TODO: Implement per-non-contingent-interest calculation
      * Should determine each beneficiary's proportional interest
      * and apply $250K limit per interest

      * FALLBACK: Apply SGL limit
           IF WS-CALC-BALANCE <= WS-SMDIA
               MOVE WS-CALC-BALANCE TO WS-TOTAL-INSURED
               MOVE ZEROS TO WS-TOTAL-UNINSURED
           ELSE
               MOVE WS-SMDIA TO WS-TOTAL-INSURED
               COMPUTE WS-TOTAL-UNINSURED =
                   WS-CALC-BALANCE - WS-SMDIA
           END-IF

           STRING 'IRR trust ' TRUST-ID
                  ' defaulted to SGL — not implemented'
               DELIMITED SIZE INTO ERROR-REC
           WRITE ERROR-REC
           ADD 1 TO WS-ERROR-COUNT

           MOVE 'SGL'               TO RES-ORC-TYPE
           MOVE 'SGL_DEFAULT_BUG'   TO RES-CALC-METHOD
           PERFORM 8000-WRITE-RESULT.

       3300-CALC-EBP.
      * Employee Benefit Plan — 12 CFR 330.14
      * Coverage = $250,000 per plan participant with vested interest
      * BUG #1: Uses TRUST-PARTICIP-COUNT from header — not actual
      *         participant roster with vested interests
      * BUG #2: Non-vested participants counted — inflates coverage
      * BUG #3: Terminated participants still counted
      * BUG #4: Plan-level calc, not per-participant pass-through
      * BUG #5: Multiple plans by same employer not linked

           COMPUTE WS-CALC-BALANCE =
               TRUST-BALANCE + TRUST-ACCRUED-INT

      * BUG: Using plan-level count instead of individual participant data
           IF TRUST-PARTICIP-COUNT > 0
               COMPUTE WS-PER-BENE-LIMIT =
                   WS-SMDIA * TRUST-PARTICIP-COUNT
           ELSE
      * BUG: If no count, defaults to flat $250K
               MOVE WS-SMDIA TO WS-PER-BENE-LIMIT
           END-IF

           IF WS-CALC-BALANCE <= WS-PER-BENE-LIMIT
               MOVE WS-CALC-BALANCE TO WS-TOTAL-INSURED
               MOVE ZEROS TO WS-TOTAL-UNINSURED
           ELSE
               MOVE WS-PER-BENE-LIMIT TO WS-TOTAL-INSURED
               COMPUTE WS-TOTAL-UNINSURED =
                   WS-CALC-BALANCE - WS-PER-BENE-LIMIT
           END-IF

           MOVE 'EBP'               TO RES-ORC-TYPE
           MOVE 'PER_PLAN_FLAT'     TO RES-CALC-METHOD
           PERFORM 8000-WRITE-RESULT.

       3400-CALC-CUSTODIAL.
      * Custodial Accounts (UTMA/UGMA, IRA Custodial)
      * BUG: All custodial accounts treated as SGL
      * Should determine underlying ownership type:
      *   - IRA custodial → same as IRR  (12 CFR 330.13)
      *   - UTMA/UGMA → SGL in minor's name
      *   - 529 Plan custodial → SGL per beneficiary

           COMPUTE WS-CALC-BALANCE =
               TRUST-BALANCE + TRUST-ACCRUED-INT

           IF WS-CALC-BALANCE <= WS-SMDIA
               MOVE WS-CALC-BALANCE TO WS-TOTAL-INSURED
               MOVE ZEROS TO WS-TOTAL-UNINSURED
           ELSE
               MOVE WS-SMDIA TO WS-TOTAL-INSURED
               COMPUTE WS-TOTAL-UNINSURED =
                   WS-CALC-BALANCE - WS-SMDIA
           END-IF

           MOVE 'SGL'               TO RES-ORC-TYPE
           MOVE 'CUSTODIAL_AS_SGL'  TO RES-CALC-METHOD
           PERFORM 8000-WRITE-RESULT.

       3900-CALC-DEFAULT.
      * Default fallback — SGL treatment
      * BUG: No error logging for unknown trust types
           COMPUTE WS-CALC-BALANCE =
               TRUST-BALANCE + TRUST-ACCRUED-INT

           IF WS-CALC-BALANCE <= WS-SMDIA
               MOVE WS-CALC-BALANCE TO WS-TOTAL-INSURED
               MOVE ZEROS TO WS-TOTAL-UNINSURED
           ELSE
               MOVE WS-SMDIA TO WS-TOTAL-INSURED
               COMPUTE WS-TOTAL-UNINSURED =
                   WS-CALC-BALANCE - WS-SMDIA
           END-IF

           MOVE 'SGL'               TO RES-ORC-TYPE
           MOVE 'UNKNOWN_DEFAULT'   TO RES-CALC-METHOD
           PERFORM 8000-WRITE-RESULT.

       8000-WRITE-RESULT.
           MOVE TRUST-ID            TO RES-TRUST-ID
           MOVE TRUST-NAME          TO RES-TRUST-NAME
           MOVE TRUST-TYPE          TO RES-TRUST-TYPE
           MOVE TRUST-GRANTOR-ID    TO RES-GRANTOR-ID
           MOVE WS-CALC-BALANCE     TO RES-TOTAL-BALANCE
           MOVE WS-ACTIVE-BENE      TO RES-BENE-COUNT
           MOVE WS-TOTAL-INSURED    TO RES-INSURED-AMT
           MOVE WS-TOTAL-UNINSURED  TO RES-UNINSURED-AMT
           MOVE ZEROS               TO RES-PENDING-AMT
           MOVE 'CALCULATED'        TO RES-STATUS
           WRITE RESULT-REC.

       9000-FINALIZE.
           DISPLAY 'Trust Insurance Calc Complete'
           DISPLAY '  Trusts processed: ' WS-TRUST-COUNT
           DISPLAY '  Errors:           ' WS-ERROR-COUNT
           CLOSE TRUST-FILE BENE-FILE RESULT-FILE ERROR-FILE.
      * BUG: No summary statistics for audit
      * BUG: No 24-hour deadline check
      * BUG: No notification on completion/failure
