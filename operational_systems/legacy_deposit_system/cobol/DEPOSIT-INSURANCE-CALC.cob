      *================================================================*
      * PROGRAM: DEPOSIT-INSURANCE-CALC
      * PURPOSE: Calculate FDIC deposit insurance coverage per
      *          depositor per Ownership Rights Category (ORC)
      * REGULATION: 12 CFR Part 330, FDIC IT Guide v3.0
      *
      * KNOWN ISSUES:
      *   - Does NOT aggregate across multiple accounts per
      *     depositor before applying SMDIA (BUG)
      *   - EBP pass-through coverage not implemented (BUG)
      *   - IRR (Irrevocable Trust) falls through to SGL (BUG)
      *   - No close-of-business balance cutoff (12 CFR 360.8)
      *   - JNT divides equally instead of checking actual interest
      *   - No collateral offset for GOV deposits
      *================================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DEPOSIT-INSURANCE-CALC.
       AUTHOR. LEGACY-SYSTEMS-TEAM.
       DATE-WRITTEN. 2008-03-15.
       DATE-COMPILED.

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNT-FILE ASSIGN TO 'ACCTFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-ACCT-STATUS.
           SELECT RESULT-FILE ASSIGN TO 'RSLTFILE'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-RSLT-STATUS.
           SELECT ERROR-FILE ASSIGN TO 'ERRFILE'
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-ERR-STATUS.

       DATA DIVISION.
       FILE SECTION.

       FD ACCOUNT-FILE.
       01 ACCT-RECORD.
           05 ACCT-NUMBER          PIC X(20).
           05 ACCT-DEPOSITOR-ID    PIC X(15).
           05 ACCT-BALANCE         PIC S9(13)V99.
           05 ACCT-ORC-TYPE        PIC X(4).
           05 ACCT-TYPE            PIC X(10).
           05 ACCT-JNT-COUNT       PIC 9(2).
           05 ACCT-BENE-COUNT      PIC 9(3).
           05 ACCT-DEBT-FLAG       PIC X(1).
           05 ACCT-DEBT-TYPE       PIC X(15).
           05 ACCT-DEATH-DATE      PIC X(10).
           05 FILLER               PIC X(20).

       FD RESULT-FILE.
       01 RSLT-RECORD.
           05 RSLT-ACCT-NUMBER     PIC X(20).
           05 RSLT-DEPOSITOR-ID    PIC X(15).
           05 RSLT-ORC-TYPE        PIC X(4).
           05 RSLT-BALANCE         PIC S9(13)V99.
           05 RSLT-INSURED-AMT     PIC S9(13)V99.
           05 RSLT-UNINSURED-AMT   PIC S9(13)V99.
           05 RSLT-CALC-METHOD     PIC X(20).
           05 RSLT-ERROR-FLAG      PIC X(1).
           05 RSLT-TIMESTAMP       PIC X(26).

       FD ERROR-FILE.
       01 ERR-RECORD              PIC X(200).

       WORKING-STORAGE SECTION.

       01 WS-ACCT-STATUS          PIC XX.
       01 WS-RSLT-STATUS          PIC XX.
       01 WS-ERR-STATUS           PIC XX.
       01 WS-EOF-FLAG             PIC X VALUE 'N'.
           88 END-OF-FILE         VALUE 'Y'.

      *--- Insurance Constants ---
      * BUG: SMDIA is hardcoded. Should be configurable and loaded
      *      from a parameter table for regulatory changes.
       01 WS-SMDIA                PIC S9(13)V99 VALUE 250000.00.
       01 WS-MAX-COVERAGE        PIC S9(13)V99.
       01 WS-INSURED             PIC S9(13)V99.
       01 WS-UNINSURED           PIC S9(13)V99.

      *--- Working fields ---
       01 WS-PER-OWNER-SHARE     PIC S9(13)V99.
       01 WS-JNT-OWNERS          PIC 9(2).
       01 WS-BENE-COUNT          PIC 9(3).
       01 WS-CALC-METHOD         PIC X(20).
       01 WS-ERROR-MSG           PIC X(200).
       01 WS-RECORD-COUNT        PIC 9(9) VALUE 0.
       01 WS-ERROR-COUNT         PIC 9(9) VALUE 0.
       01 WS-CURRENT-TIMESTAMP   PIC X(26).

       PROCEDURE DIVISION.
       0000-MAIN-CONTROL.
           PERFORM 1000-INITIALIZE
           PERFORM 2000-PROCESS-ACCOUNTS UNTIL END-OF-FILE
           PERFORM 9000-FINALIZE
           STOP RUN.

       1000-INITIALIZE.
           OPEN INPUT ACCOUNT-FILE
           OPEN OUTPUT RESULT-FILE
           OPEN OUTPUT ERROR-FILE
           IF WS-ACCT-STATUS NOT = '00'
               DISPLAY 'ERROR OPENING ACCOUNT FILE: ' WS-ACCT-STATUS
               STOP RUN
           END-IF
           READ ACCOUNT-FILE
               AT END SET END-OF-FILE TO TRUE
           END-READ.

       2000-PROCESS-ACCOUNTS.
      *    BUG: Processing account-by-account instead of
      *    aggregating by depositor+ORC first.
      *    Per 12 CFR Part 330, insurance must be calculated
      *    on the AGGREGATE balance per depositor per ORC,
      *    not per individual account.
           EVALUATE ACCT-ORC-TYPE
               WHEN 'SGL'
                   PERFORM 3100-CALC-SGL
               WHEN 'JNT'
                   PERFORM 3200-CALC-JNT
               WHEN 'REV'
                   PERFORM 3300-CALC-REV
               WHEN 'BUS'
                   PERFORM 3400-CALC-BUS
               WHEN 'EBP'
                   PERFORM 3500-CALC-EBP
               WHEN 'CRA'
                   PERFORM 3600-CALC-CRA
               WHEN 'GOV1' 'GOV2' 'GOV3'
                   PERFORM 3700-CALC-GOV
               WHEN 'ANC'
                   PERFORM 3800-CALC-ANC
               WHEN 'IRR'
      *            BUG: IRR not properly handled.
      *            Falls through to default SGL calculation.
      *            12 CFR 330.13 requires per-beneficiary interest.
                   PERFORM 3100-CALC-SGL
                   MOVE 'IRR_FALLBACK_SGL' TO WS-CALC-METHOD
               WHEN OTHER
                   MOVE 'UNKNOWN ORC: ' TO WS-ERROR-MSG
                   STRING WS-ERROR-MSG DELIMITED SIZE
                          ACCT-ORC-TYPE DELIMITED SIZE
                          INTO WS-ERROR-MSG
                   PERFORM 8000-LOG-ERROR
                   PERFORM 3100-CALC-SGL
           END-EVALUATE

           PERFORM 4000-WRITE-RESULT
           ADD 1 TO WS-RECORD-COUNT

           READ ACCOUNT-FILE
               AT END SET END-OF-FILE TO TRUE
           END-READ.

       3100-CALC-SGL.
      *    Single Ownership: 12 CFR 330.6
      *    BUG: Not aggregating across depositor's other SGL accounts
           IF ACCT-BALANCE > WS-SMDIA
               MOVE WS-SMDIA TO WS-INSURED
               COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-SMDIA
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'SGL_STANDARD' TO WS-CALC-METHOD.

       3200-CALC-JNT.
      *    Joint Ownership: 12 CFR 330.9
      *    BUG: Divides balance equally among owners.
      *    Per 12 CFR 330.9, coverage is based on each owner's
      *    ACTUAL interest, not equal division.
      *    BUG: Not checking if all owners are natural persons.
      *    BUG: Not verifying signature card evidence.
           MOVE ACCT-JNT-COUNT TO WS-JNT-OWNERS
           IF WS-JNT-OWNERS < 2
               MOVE 2 TO WS-JNT-OWNERS
           END-IF

           COMPUTE WS-PER-OWNER-SHARE =
               ACCT-BALANCE / WS-JNT-OWNERS

           IF WS-PER-OWNER-SHARE > WS-SMDIA
               COMPUTE WS-INSURED =
                   WS-SMDIA * WS-JNT-OWNERS
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
           END-IF

           IF WS-INSURED > ACCT-BALANCE
               MOVE ACCT-BALANCE TO WS-INSURED
           END-IF
           COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-INSURED
           MOVE 'JNT_EQUAL_SPLIT' TO WS-CALC-METHOD.

       3300-CALC-REV.
      *    Revocable Trust: 12 CFR 330.10
      *    BUG: Does not handle >5 beneficiary aggregate calculation
           MOVE ACCT-BENE-COUNT TO WS-BENE-COUNT
           IF WS-BENE-COUNT = 0
               MOVE 1 TO WS-BENE-COUNT
           END-IF

           IF WS-BENE-COUNT <= 5
               COMPUTE WS-MAX-COVERAGE =
                   WS-SMDIA * WS-BENE-COUNT
           ELSE
      *        BUG: Caps at $1.25M instead of proper aggregate
               COMPUTE WS-MAX-COVERAGE = WS-SMDIA * 5
           END-IF

           IF ACCT-BALANCE > WS-MAX-COVERAGE
               MOVE WS-MAX-COVERAGE TO WS-INSURED
               COMPUTE WS-UNINSURED =
                   ACCT-BALANCE - WS-MAX-COVERAGE
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'REV_BENE_CALC' TO WS-CALC-METHOD.

       3400-CALC-BUS.
      *    Business/Organization: 12 CFR 330.11
           IF ACCT-BALANCE > WS-SMDIA
               MOVE WS-SMDIA TO WS-INSURED
               COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-SMDIA
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'BUS_STANDARD' TO WS-CALC-METHOD.

       3500-CALC-EBP.
      *    Employee Benefit Plan: 12 CFR 330.14
      *    BUG: Should calculate per-participant pass-through
      *    coverage but instead applies single SMDIA to entire
      *    plan balance. This is a CRITICAL violation.
           IF ACCT-BALANCE > WS-SMDIA
               MOVE WS-SMDIA TO WS-INSURED
               COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-SMDIA
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'EBP_NO_PASSTHRU' TO WS-CALC-METHOD.

       3600-CALC-CRA.
      *    Certain Retirement Accounts: 12 CFR 330.14(c)
           IF ACCT-BALANCE > WS-SMDIA
               MOVE WS-SMDIA TO WS-INSURED
               COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-SMDIA
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'CRA_STANDARD' TO WS-CALC-METHOD.

       3700-CALC-GOV.
      *    Government Deposits: 12 CFR 330.15
      *    BUG: Not accounting for collateral pledged against
      *    government deposits. Insured amount should be NET
      *    of collateral.
      *    BUG: Not verifying official custodian designation.
           IF ACCT-BALANCE > WS-SMDIA
               MOVE WS-SMDIA TO WS-INSURED
               COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-SMDIA
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'GOV_NO_COLLATERAL' TO WS-CALC-METHOD.

       3800-CALC-ANC.
      *    Annuity Contract: 12 CFR 330.8
           IF ACCT-BALANCE > WS-SMDIA
               MOVE WS-SMDIA TO WS-INSURED
               COMPUTE WS-UNINSURED = ACCT-BALANCE - WS-SMDIA
           ELSE
               MOVE ACCT-BALANCE TO WS-INSURED
               MOVE 0 TO WS-UNINSURED
           END-IF
           MOVE 'ANC_STANDARD' TO WS-CALC-METHOD.

       4000-WRITE-RESULT.
           MOVE ACCT-NUMBER TO RSLT-ACCT-NUMBER
           MOVE ACCT-DEPOSITOR-ID TO RSLT-DEPOSITOR-ID
           MOVE ACCT-ORC-TYPE TO RSLT-ORC-TYPE
           MOVE ACCT-BALANCE TO RSLT-BALANCE
           MOVE WS-INSURED TO RSLT-INSURED-AMT
           MOVE WS-UNINSURED TO RSLT-UNINSURED-AMT
           MOVE WS-CALC-METHOD TO RSLT-CALC-METHOD
           MOVE 'N' TO RSLT-ERROR-FLAG
      *    BUG: Timestamp not populated
           MOVE SPACES TO RSLT-TIMESTAMP
           WRITE RSLT-RECORD.

       8000-LOG-ERROR.
           ADD 1 TO WS-ERROR-COUNT
           WRITE ERR-RECORD FROM WS-ERROR-MSG.

       9000-FINALIZE.
           CLOSE ACCOUNT-FILE
           CLOSE RESULT-FILE
           CLOSE ERROR-FILE
           DISPLAY 'RECORDS PROCESSED: ' WS-RECORD-COUNT
           DISPLAY 'ERRORS LOGGED: ' WS-ERROR-COUNT.
