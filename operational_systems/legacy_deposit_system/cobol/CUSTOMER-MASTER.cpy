      *================================================================*
      * COPYBOOK: CUSTOMER-MASTER
      * PURPOSE: Customer record layout for FDIC Part 370 processing
      * NOTE: Missing email, phone fields per IT Guide Section 2.3.2
      *       data completeness requirements
      *================================================================*
       01 CUST-MASTER-REC.
           05 CUST-DEPOSITOR-ID    PIC X(15).
           05 CUST-NAME            PIC X(50).
           05 CUST-GOVT-ID         PIC X(15).
           05 CUST-NATURAL-PERSON  PIC X(1).
              88 CUST-IS-PERSON    VALUE 'Y'.
              88 CUST-IS-ENTITY    VALUE 'N'.
           05 CUST-DOB             PIC X(10).
           05 CUST-DEATH-FLAG      PIC X(1).
              88 CUST-DECEASED     VALUE 'Y'.
           05 CUST-DEATH-DATE      PIC X(10).
           05 CUST-ADDR-LINE1      PIC X(50).
           05 CUST-ADDR-CITY       PIC X(30).
           05 CUST-ADDR-STATE      PIC X(2).
           05 CUST-ADDR-ZIP        PIC X(10).
      *    MISSING: CUST-EMAIL per IT Guide 2.3.2
      *    MISSING: CUST-PHONE per IT Guide 2.3.2
      *    MISSING: CUST-TAX-ID-TYPE (SSN vs EIN)
           05 CUST-SOURCE-SYSTEM   PIC X(15).
           05 CUST-LAST-UPDATED    PIC X(26).
           05 FILLER               PIC X(16).
