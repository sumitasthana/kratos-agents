      *================================================================*
      * COPYBOOK: ACCOUNT-MASTER
      * PURPOSE: Account record layout for FDIC Part 370 processing
      * KNOWN ISSUES:
      *   - Missing ownership_category field per Part 370 Appendix A
      *   - Missing collateral_pledge_ref for GOV accounts
      *   - Missing beneficiary_govt_id for trust beneficiaries
      *   - No participant_count for EBP accounts
      *================================================================*
       01 ACCT-MASTER-REC.
           05 ACCT-NUMBER          PIC X(20).
           05 ACCT-DEPOSITOR-ID    PIC X(15).
           05 ACCT-BALANCE         PIC S9(13)V99.
           05 ACCT-ORC-TYPE        PIC X(4).
           05 ACCT-TYPE            PIC X(10).
           05 ACCT-STATUS          PIC X(8).
              88 ACCT-ACTIVE       VALUE 'ACTIVE'.
              88 ACCT-CLOSED       VALUE 'CLOSED'.
              88 ACCT-DORMANT      VALUE 'DORMANT'.
           05 ACCT-OPEN-DATE       PIC X(10).
           05 ACCT-SOURCE-SYSTEM   PIC X(15).
           05 ACCT-JNT-COUNT       PIC 9(2).
           05 ACCT-BENE-COUNT      PIC 9(3).
           05 ACCT-BUS-NAME        PIC X(50).
           05 ACCT-GOVT-ENTITY     PIC X(50).
           05 ACCT-TAX-ID          PIC X(15).
      *    MISSING: ACCT-OWNERSHIP-CAT per Part 370 Appendix A
      *    MISSING: ACCT-COLLATERAL-REF for GOV accounts
      *    MISSING: ACCT-EBP-PARTICIPANTS for EBP accounts
      *    MISSING: ACCT-RIGHT-AND-CAPACITY per IT Guide
           05 FILLER               PIC X(6).
