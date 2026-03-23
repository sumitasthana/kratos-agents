//TRUSTJOB  JOB (TRUST,'DAILY-TRUST'),CLASS=A,MSGCLASS=X,
//          MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*******************************************************************
//* DAILY TRUST INSURANCE CALCULATION JOB
//* Processes trust accounts, beneficiary overlays, and generates
//* FDIC insurance determination output for trust & custody accounts.
//*******************************************************************
//* KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
//*   1. Step AGGTRUST (grantor aggregation) is COMMENTED OUT
//*      — trusts from same grantor calculated independently
//*   2. Beneficiary file loaded from daily extract — may be stale
//*   3. EBP participant count from plan header, not roster
//*   4. IRR trust calculation step exists but uses SGL fallback
//*   5. Sub-account balances not included in trust totals
//*   6. No 24-hour processing deadline tracking
//*   7. Output uses comma delimiter (should be pipe)
//*   8. No checksum generation for output files
//*   9. Deceased beneficiary cleanup never runs
//*******************************************************************
//*
//* STEP 1: EXTRACT TRUST ACCOUNTS FROM MAINFRAME
//*
//EXTRACT  EXEC PGM=IKJEFT01,REGION=4M
//SYSTSPRT DD SYSOUT=*
//SYSTSIN  DD *
  DSN SYSTEM(TRUSTDB)
  RUN PROGRAM(DSNREXX) PLAN(DSNTIAUL) -
      LIB('TRUST.PROCLIB')
  SELECT TRUST_ID, TRUST_NAME, TRUST_TYPE, GRANTOR_ID,
         GRANTOR_NAME, BALANCE, ACCRUED_INTEREST,
         BENEFICIARY_COUNT, PARTICIPANT_COUNT, TRUST_STATUS
  FROM TRUST_ACCOUNTS
  WHERE TRUST_STATUS = 'A'
  END
/*
//TRUSTOUT DD DSN=TRUST.DAILY.EXTRACT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=300,BLKSIZE=0)
//*
//* STEP 2: EXTRACT BENEFICIARY REGISTRY
//*
//BENEEXT  EXEC PGM=IKJEFT01,REGION=4M
//SYSTSPRT DD SYSOUT=*
//SYSTSIN  DD *
  DSN SYSTEM(TRUSTDB)
  RUN PROGRAM(DSNREXX) PLAN(DSNTIAUL) -
      LIB('TRUST.PROCLIB')
  SELECT BENEFICIARY_ID, TRUST_ID, BENEFICIARY_NAME,
         BENEFICIARY_SSN, BENEFICIARY_TYPE, ALLOCATION_PCT,
         NATURAL_PERSON, STATUS
  FROM TRUST_BENEFICIARIES
  WHERE STATUS IN ('A', 'D')
  END
/*
//* BUG: Includes DECEASED ('D') beneficiaries — they should be excluded
//* BUG: Does not include CONTINGENT type for IRR trust calculations
//BENEOUT  DD DSN=TRUST.DAILY.BENEFICIARIES,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(5,2),RLSE),
//            DCB=(RECFM=FB,LRECL=200,BLKSIZE=0)
//*
//* STEP 3: RUN TRUST INSURANCE CALCULATION (COBOL)
//*
//CALCTRUST EXEC PGM=TRUSTCALC,REGION=8M
//STEPLIB  DD DSN=TRUST.LOADLIB,DISP=SHR
//TRUSTIN  DD DSN=TRUST.DAILY.EXTRACT,DISP=SHR
//BENEIN   DD DSN=TRUST.DAILY.BENEFICIARIES,DISP=SHR
//RESULTOUT DD DSN=TRUST.DAILY.RESULTS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=250,BLKSIZE=0)
//ERROROUT DD DSN=TRUST.DAILY.ERRORS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(1,1),RLSE)
//SYSOUT   DD SYSOUT=*
//*
//* STEP 4: GRANTOR AGGREGATION
//* BUG: THIS STEP IS COMMENTED OUT — NEVER EXECUTES
//* Same grantor with multiple trusts gets separate $250K per trust
//*
//*AGGTRUST EXEC PGM=IKJEFT01,REGION=4M
//*SYSTSPRT DD SYSOUT=*
//*SYSTSIN  DD *
//* DSN SYSTEM(TRUSTDB)
//* RUN PROGRAM(DSNREXX) PLAN(DSNTIAUL) -
//*     LIB('TRUST.PROCLIB')
//* CALL SP_AGGREGATE_TRUST_BY_GRANTOR
//* END
//*
//* STEP 5: GENERATE QDF OUTPUT
//*
//GENQDF   EXEC PGM=JAVA,REGION=256M,
//         PARM='com.bank.trust.TrustQdfGenerator'
//STEPLIB  DD DSN=TRUST.JAVA.LOADLIB,DISP=SHR
//STDIN    DD DSN=TRUST.DAILY.RESULTS,DISP=SHR
//STDOUT   DD DSN=TRUST.OUTPUT.QDF,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(5,2),RLSE)
//SYSOUT   DD SYSOUT=*
//* BUG: Output file uses comma delimiter — should be pipe
//* BUG: Grantor SSN exposed in plaintext — PII not encrypted
//* BUG: No checksum generated for file integrity
//*
//* STEP 6: GENERATE ARE OUTPUT
//*
//GENRE    EXEC PGM=JAVA,REGION=256M,
//         PARM='com.bank.trust.TrustAreGenerator'
//STEPLIB  DD DSN=TRUST.JAVA.LOADLIB,DISP=SHR
//STDIN    DD DSN=TRUST.DAILY.RESULTS,DISP=SHR
//STDOUT   DD DSN=TRUST.OUTPUT.ARE,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(5,2),RLSE)
//SYSOUT   DD SYSOUT=*
//*
//* STEP 7: COPY TO SUBMISSION LANDING ZONE
//*
//COPYSUB  EXEC PGM=IEBGENER
//SYSIN    DD DUMMY
//SYSPRINT DD SYSOUT=*
//SYSUT1   DD DSN=TRUST.OUTPUT.QDF,DISP=SHR
//SYSUT2   DD DSN=FDIC.SUBMIT.TRUST.QDF,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(5,2),RLSE)
//* BUG: Only copies QDF — ARE file not copied to landing zone
//* BUG: No encryption applied before transfer
//* BUG: No notification sent on job completion/failure
//* BUG: No elapsed time check against 24-hour deadline
