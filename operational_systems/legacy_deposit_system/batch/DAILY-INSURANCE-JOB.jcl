//INSURJOB JOB (ACCT),'FDIC INSURANCE CALC',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),
//         NOTIFY=&SYSUID
//*================================================================*
//* JOB: DAILY-INSURANCE-JOB
//* PURPOSE: Nightly batch job for FDIC Part 370 deposit
//*          insurance determination processing
//* SCHEDULE: Daily at 02:00 AM EST after close of business
//*
//* KNOWN ISSUES:
//*   - Does not verify close-of-business balance cutoff
//*     per 12 CFR 360.8 before calculation begins
//*   - No elapsed time monitoring against 24-hour deadline
//*   - No automatic notification on failure
//*   - Step 3 (aggregation) is commented out — NOT RUNNING
//*   - Output uses comma delimiter instead of pipe (|)
//*   - No checksum/hash generation for output files
//*   - No encryption for PII in output files
//*================================================================*
//*
//*--- STEP 1: EXTRACT CUSTOMER DATA FROM CORE BANKING ---
//STEP01   EXEC PGM=IKJEFT01,REGION=64M
//SYSTSPRT DD SYSOUT=*
//SYSTSIN  DD *
  DSN SYSTEM(DB2P)
  RUN PROGRAM(DSNTEP2) PLAN(DSNTEP4) -
    LIB('BANK.PROD.RUNLIB.LOAD')
  END
/*
//SYSIN    DD *
  SELECT DEPOSITOR_ID, CUSTOMER_NAME, GOVERNMENT_ID,
         IS_NATURAL_PERSON, DATE_OF_DEATH,
         ADDRESS_LINE1, ADDRESS_CITY, ADDRESS_STATE, ADDRESS_ZIP,
         SOURCE_SYSTEM
  FROM BANK.CUSTOMERS
  WHERE LAST_UPDATED >= CURRENT DATE - 1 DAY
     OR DATE_OF_DEATH IS NOT NULL;
/*
//CUSTOUT  DD DSN=BANK.FDIC.CUSTOMER.EXTRACT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(50,10)),
//            DCB=(RECFM=FB,LRECL=300,BLKSIZE=27000)
//*
//*--- STEP 2: RUN ORC ASSIGNMENT (COBOL PROGRAM) ---
//STEP02   EXEC PGM=ORCASGN,REGION=128M
//STEPLIB  DD DSN=BANK.PROD.LOADLIB,DISP=SHR
//CUSTFILE DD DSN=BANK.FDIC.CUSTOMER.EXTRACT,DISP=SHR
//ACCTFILE DD DSN=BANK.PROD.ACCOUNT.MASTER,DISP=SHR
//ORCOUT   DD DSN=BANK.FDIC.ORC.ASSIGNED,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20)),
//            DCB=(RECFM=FB,LRECL=200,BLKSIZE=27000)
//SYSOUT   DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//*
//*--- STEP 3: AGGREGATE BY DEPOSITOR+ORC ---
//* BUG: THIS STEP IS COMMENTED OUT. The insurance calculation
//* in Step 4 runs per-account instead of on aggregated totals.
//* This violates 12 CFR Part 330 which requires insurance
//* coverage applied to AGGREGATE balance per depositor per ORC.
//*
//*STEP03   EXEC PGM=IKJEFT01,REGION=64M
//*SYSTSPRT DD SYSOUT=*
//*SYSTSIN  DD *
//*  DSN SYSTEM(DB2P)
//*  RUN PROGRAM(DSNTEP2) PLAN(DSNTEP4)
//*  END
//*SYSIN    DD *
//*  EXEC SQL
//*    CALL BANK.SP_AGGREGATE_DEPOSITS(CURRENT DATE)
//*  END EXEC;
//*
//*--- STEP 4: RUN INSURANCE CALCULATION (COBOL PROGRAM) ---
//STEP04   EXEC PGM=DEPINSUR,REGION=256M
//STEPLIB  DD DSN=BANK.PROD.LOADLIB,DISP=SHR
//ACCTFILE DD DSN=BANK.FDIC.ORC.ASSIGNED,DISP=SHR
//RSLTFILE DD DSN=BANK.FDIC.INSURANCE.RESULTS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(200,50)),
//            DCB=(RECFM=FB,LRECL=200,BLKSIZE=27000)
//ERRFILE  DD DSN=BANK.FDIC.CALC.ERRORS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(10,5))
//SYSOUT   DD SYSOUT=*
//*
//*--- STEP 5: GENERATE QDF OUTPUT ---
//* BUG: Uses comma delimiter — FDIC spec requires pipe (|)
//* BUG: No file header with version/timestamp/record count
//* BUG: PII (government_id) not encrypted
//STEP05   EXEC PGM=QDFGEN,REGION=128M
//STEPLIB  DD DSN=BANK.PROD.LOADLIB,DISP=SHR
//RSLTIN   DD DSN=BANK.FDIC.INSURANCE.RESULTS,DISP=SHR
//QDFOUT   DD DSN=BANK.FDIC.QDF.OUTPUT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20))
//SYSOUT   DD SYSOUT=*
//*
//*--- STEP 6: GENERATE ARE OUTPUT ---
//* BUG: Missing several required ARE fields per Appendix A
//STEP06   EXEC PGM=AREGEN,REGION=128M
//STEPLIB  DD DSN=BANK.PROD.LOADLIB,DISP=SHR
//RSLTIN   DD DSN=BANK.FDIC.INSURANCE.RESULTS,DISP=SHR
//AREOUT   DD DSN=BANK.FDIC.ARE.OUTPUT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20))
//SYSOUT   DD SYSOUT=*
//*
//*--- STEP 7: COPY OUTPUT TO LANDING ZONE ---
//* BUG: No checksum/hash verification after copy
//* BUG: No encryption for data in transit
//STEP07   EXEC PGM=IEBGENER
//SYSPRINT DD SYSOUT=*
//SYSIN    DD DUMMY
//SYSUT1   DD DSN=BANK.FDIC.QDF.OUTPUT,DISP=SHR
//SYSUT2   DD DSN=BANK.FDIC.LANDING.QDF,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20))
//
