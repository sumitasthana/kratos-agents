      *================================================================*
      * PROGRAM: ORC-ASSIGNMENT
      * PURPOSE: Classify deposit accounts into FDIC Ownership
      *          Rights Categories (ORCs) per 12 CFR Part 330
      *
      * KNOWN ISSUES:
      *   - IRR (Irrevocable Trust) not implemented (CRITICAL)
      *   - JNT does not verify natural_person for co-owners
      *   - JNT does not check signature_card or withdrawal_rights
      *   - BUS does not verify EIN tax_id format
      *   - GOV does not verify collateral or custodian designation
      *   - No tribal government classification
      *   - ANC annuity contract ORC assignment incomplete
      *   - Unresolvable accounts silently default to SGL
      *================================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ORC-ASSIGNMENT.
       AUTHOR. LEGACY-SYSTEMS-TEAM.
       DATE-WRITTEN. 2007-11-20.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CUSTOMER-FILE ASSIGN TO 'CUSTFILE'
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-CUST-STATUS.
           SELECT ACCOUNT-FILE ASSIGN TO 'ACCTFILE'
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-ACCT-STATUS.
           SELECT OUTPUT-FILE ASSIGN TO 'ORCOUT'
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-OUT-STATUS.

       DATA DIVISION.
       FILE SECTION.

       FD CUSTOMER-FILE.
       01 CUST-RECORD.
           COPY CUSTOMER-MASTER.

       FD ACCOUNT-FILE.
       01 ACCT-INPUT.
           COPY ACCOUNT-MASTER.

       FD OUTPUT-FILE.
       01 ORC-OUTPUT-REC.
           05 OUT-ACCT-NUMBER     PIC X(20).
           05 OUT-DEPOSITOR-ID    PIC X(15).
           05 OUT-ORC-TYPE        PIC X(4).
           05 OUT-ASSIGNMENT-RULE PIC X(30).
           05 OUT-CONFIDENCE      PIC X(4).
           05 OUT-PENDING-FLAG    PIC X(1).
           05 OUT-PENDING-CODE    PIC X(3).
           05 OUT-TIMESTAMP       PIC X(26).

       WORKING-STORAGE SECTION.

       01 WS-CUST-STATUS         PIC XX.
       01 WS-ACCT-STATUS         PIC XX.
       01 WS-OUT-STATUS          PIC XX.
       01 WS-EOF-ACCT            PIC X VALUE 'N'.
           88 ACCT-EOF            VALUE 'Y'.
       01 WS-CUST-FOUND          PIC X VALUE 'N'.
           88 CUSTOMER-FOUND      VALUE 'Y'.

       01 WS-ASSIGNED-ORC        PIC X(4).
       01 WS-RULE-DESC           PIC X(30).
       01 WS-PENDING-FLAG        PIC X(1).
       01 WS-PENDING-CODE        PIC X(3).
       01 WS-CONFIDENCE          PIC X(4).

      *--- Customer lookup fields ---
       01 WS-CUST-NATURAL-PERSON PIC X(1).
       01 WS-CUST-NAME           PIC X(50).
       01 WS-CUST-GOVT-ID        PIC X(15).
       01 WS-CUST-DEATH-FLAG     PIC X(1).

      *--- Counters ---
       01 WS-TOTAL-PROCESSED     PIC 9(9) VALUE 0.
       01 WS-ASSIGNED-COUNT      PIC 9(9) VALUE 0.
       01 WS-PENDING-COUNT       PIC 9(9) VALUE 0.
       01 WS-UNRESOLVED-COUNT    PIC 9(9) VALUE 0.

       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2000-PROCESS UNTIL ACCT-EOF
           PERFORM 9000-CLEANUP
           STOP RUN.

       1000-INIT.
           OPEN INPUT CUSTOMER-FILE
           OPEN INPUT ACCOUNT-FILE
           OPEN OUTPUT OUTPUT-FILE
           READ ACCOUNT-FILE
               AT END SET ACCT-EOF TO TRUE
           END-READ.

       2000-PROCESS.
           ADD 1 TO WS-TOTAL-PROCESSED
           MOVE 'N' TO WS-PENDING-FLAG
           MOVE SPACES TO WS-PENDING-CODE
           MOVE 'HIGH' TO WS-CONFIDENCE

      *    Lookup customer record
           PERFORM 3000-LOOKUP-CUSTOMER

           IF NOT CUSTOMER-FOUND
      *        BUG: Missing customer → should route to pending
      *        Instead silently defaults to SGL
               MOVE 'SGL' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.6-DEFAULT' TO WS-RULE-DESC
               MOVE 'LOW' TO WS-CONFIDENCE
               ADD 1 TO WS-UNRESOLVED-COUNT
           ELSE
               PERFORM 4000-CLASSIFY-ACCOUNT
           END-IF

           PERFORM 5000-WRITE-OUTPUT

           READ ACCOUNT-FILE
               AT END SET ACCT-EOF TO TRUE
           END-READ.

       3000-LOOKUP-CUSTOMER.
      *    BUG: Sequential scan — no indexed lookup
      *    Performance issue for large customer files
           MOVE 'N' TO WS-CUST-FOUND
           CLOSE CUSTOMER-FILE
           OPEN INPUT CUSTOMER-FILE
           PERFORM UNTIL CUSTOMER-FOUND OR
                         WS-CUST-STATUS NOT = '00'
               READ CUSTOMER-FILE
                   AT END
                       EXIT PERFORM
                   NOT AT END
                       IF CUST-DEPOSITOR-ID = ACCT-DEPOSITOR-ID
                                              OF ACCT-INPUT
                           SET CUSTOMER-FOUND TO TRUE
                           MOVE CUST-NATURAL-PERSON TO
                               WS-CUST-NATURAL-PERSON
                           MOVE CUST-NAME TO WS-CUST-NAME
                           MOVE CUST-GOVT-ID TO WS-CUST-GOVT-ID
                           MOVE CUST-DEATH-FLAG TO WS-CUST-DEATH-FLAG
                       END-IF
               END-READ
           END-PERFORM.

       4000-CLASSIFY-ACCOUNT.
      *    BUG: Classification order matters — first match wins.
      *    Some accounts could qualify for multiple ORCs but only
      *    the first match is used.

      *    Check for Business/Organization
           IF ACCT-BUS-NAME OF ACCT-INPUT NOT = SPACES
               AND WS-CUST-NATURAL-PERSON = 'N'
      *        BUG: Not checking corporation vs. partnership
      *        BUG: Not verifying EIN format (XX-XXXXXXX)
               MOVE 'BUS' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.11-BUSINESS' TO WS-RULE-DESC
               ADD 1 TO WS-ASSIGNED-COUNT
               EXIT PARAGRAPH
           END-IF

      *    Check for Joint Ownership
           IF ACCT-JNT-COUNT OF ACCT-INPUT > 0
      *        COMPLIANCE GAP: Not checking if ALL co-owners
      *        are natural persons (12 CFR 330.9 requirement)
      *        MISSING: signature_card verification
      *        MISSING: withdrawal_rights verification
               MOVE 'JNT' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.9-JOINT' TO WS-RULE-DESC
               ADD 1 TO WS-ASSIGNED-COUNT
               EXIT PARAGRAPH
           END-IF

      *    Check for Revocable Trust
           IF ACCT-BENE-COUNT OF ACCT-INPUT > 0
               MOVE 'REV' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.10-REV-TRUST' TO WS-RULE-DESC
               ADD 1 TO WS-ASSIGNED-COUNT
               EXIT PARAGRAPH
           END-IF

      *    Check for Government entity
           IF ACCT-GOVT-ENTITY OF ACCT-INPUT NOT = SPACES
               PERFORM 4100-CLASSIFY-GOVT
               ADD 1 TO WS-ASSIGNED-COUNT
               EXIT PARAGRAPH
           END-IF

      *    Check for CRA (IRA/Keogh)
           IF ACCT-TYPE OF ACCT-INPUT = 'IRA'
               OR ACCT-TYPE OF ACCT-INPUT = 'KEOGH'
               OR ACCT-TYPE OF ACCT-INPUT = 'ROTH_IRA'
               MOVE 'CRA' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.14C-RETIREMENT' TO WS-RULE-DESC
               ADD 1 TO WS-ASSIGNED-COUNT
               EXIT PARAGRAPH
           END-IF

      *    Check for EBP
           IF ACCT-TYPE OF ACCT-INPUT = '401K'
               OR ACCT-TYPE OF ACCT-INPUT = 'PENSION'
               MOVE 'EBP' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.14-EBP' TO WS-RULE-DESC
               ADD 1 TO WS-ASSIGNED-COUNT
               EXIT PARAGRAPH
           END-IF

      *    NOTE: IRR (Irrevocable Trust) — NOT IMPLEMENTED
      *    This is a CRITICAL compliance gap per 12 CFR 330.13.
      *    All irrevocable trust accounts will be misclassified.

      *    Default to Single Ownership
           IF WS-CUST-NATURAL-PERSON = 'Y'
               MOVE 'SGL' TO WS-ASSIGNED-ORC
               MOVE '12CFR330.6-SINGLE-DFLT' TO WS-RULE-DESC
               ADD 1 TO WS-ASSIGNED-COUNT
           ELSE
      *        Unresolvable — should be pending but defaults
               MOVE 'SGL' TO WS-ASSIGNED-ORC
               MOVE 'UNRESOLVABLE-SGL-DFLT' TO WS-RULE-DESC
               MOVE 'LOW' TO WS-CONFIDENCE
               ADD 1 TO WS-UNRESOLVED-COUNT
           END-IF.

       4100-CLASSIFY-GOVT.
      *    BUG: Tribal governments not handled
           EVALUATE TRUE
               WHEN ACCT-GOVT-ENTITY OF ACCT-INPUT(1:7) = 'FEDERAL'
                   MOVE 'GOV1' TO WS-ASSIGNED-ORC
                   MOVE '12CFR330.15-FED-GOVT' TO WS-RULE-DESC
               WHEN ACCT-GOVT-ENTITY OF ACCT-INPUT(1:5) = 'STATE'
                   MOVE 'GOV2' TO WS-ASSIGNED-ORC
                   MOVE '12CFR330.15-STATE-GOVT' TO WS-RULE-DESC
               WHEN OTHER
                   MOVE 'GOV3' TO WS-ASSIGNED-ORC
                   MOVE '12CFR330.15-MUNI-GOVT' TO WS-RULE-DESC
           END-EVALUATE.

       5000-WRITE-OUTPUT.
           MOVE ACCT-NUMBER OF ACCT-INPUT TO OUT-ACCT-NUMBER
           MOVE ACCT-DEPOSITOR-ID OF ACCT-INPUT TO OUT-DEPOSITOR-ID
           MOVE WS-ASSIGNED-ORC TO OUT-ORC-TYPE
           MOVE WS-RULE-DESC TO OUT-ASSIGNMENT-RULE
           MOVE WS-CONFIDENCE TO OUT-CONFIDENCE
           MOVE WS-PENDING-FLAG TO OUT-PENDING-FLAG
           MOVE WS-PENDING-CODE TO OUT-PENDING-CODE
      *    BUG: Timestamp not populated
           MOVE SPACES TO OUT-TIMESTAMP
           WRITE ORC-OUTPUT-REC.

       9000-CLEANUP.
           CLOSE CUSTOMER-FILE
           CLOSE ACCOUNT-FILE
           CLOSE OUTPUT-FILE
           DISPLAY 'TOTAL PROCESSED: ' WS-TOTAL-PROCESSED
           DISPLAY 'ASSIGNED: ' WS-ASSIGNED-COUNT
           DISPLAY 'PENDING: ' WS-PENDING-COUNT
           DISPLAY 'UNRESOLVED: ' WS-UNRESOLVED-COUNT.
