package com.bank.deposit.service;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * DepositService — Core deposit insurance processing middleware.
 * 
 * This Java service acts as the middleware layer between the legacy
 * mainframe COBOL programs and the modern REST API layer.
 * 
 * REGULATION: 12 CFR Part 370, 12 CFR Part 330
 * 
 * KNOWN COMPLIANCE ISSUES:
 *   - Does NOT aggregate deposits by depositor+ORC before calculating
 *   - EBP pass-through coverage not implemented
 *   - IRR (Irrevocable Trust) handled as SGL fallback
 *   - No close-of-business balance cutoff per 12 CFR 360.8
 *   - Deceased depositor 6-month grace period not implemented
 *   - Data from multiple source systems not de-duplicated
 *   - No file integrity verification (checksums/hashing)
 *   - QDF uses comma delimiter instead of pipe (|) per FDIC spec
 *   - Government deposits missing collateral offset
 */
public class DepositService {

    // BUG: Hardcoded SMDIA. Should be loaded from configuration
    // to handle regulatory changes without code redeployment.
    private static final BigDecimal SMDIA = new BigDecimal("250000.00");

    // BUG: Hardcoded maximum processing hours. Per 12 CFR 370.3(b),
    // institution must complete calculation within 24 hours of failure.
    private static final int MAX_PROCESSING_HOURS = 24;

    private final AccountRepository accountRepository;
    private final CustomerRepository customerRepository;
    private final InsuranceResultRepository resultRepository;

    public DepositService(
            AccountRepository accountRepository,
            CustomerRepository customerRepository,
            InsuranceResultRepository resultRepository) {
        this.accountRepository = accountRepository;
        this.customerRepository = customerRepository;
        this.resultRepository = resultRepository;
    }

    /**
     * Run the full deposit insurance calculation pipeline.
     * 
     * BUG: Processes accounts individually instead of aggregating
     * by depositor+ORC first. Violates 12 CFR Part 330 which
     * requires insurance on aggregate balances.
     * 
     * BUG: No elapsed time tracking against the 24-hour
     * regulatory deadline per 12 CFR 370.3(b).
     */
    public CalculationResult runInsuranceCalculation(LocalDate asOfDate) {
        String batchId = UUID.randomUUID().toString();
        LocalDateTime startTime = LocalDateTime.now();
        int processed = 0;
        int errors = 0;
        BigDecimal totalInsured = BigDecimal.ZERO;
        BigDecimal totalUninsured = BigDecimal.ZERO;

        List<Account> activeAccounts = accountRepository
                .findByStatusAndBalanceGreaterThan("ACTIVE", BigDecimal.ZERO);

        // BUG: Processing per-account, not per-depositor aggregate
        for (Account account : activeAccounts) {
            try {
                InsuranceResult result = calculateForAccount(account, batchId);
                resultRepository.save(result);
                totalInsured = totalInsured.add(result.getInsuredAmount());
                totalUninsured = totalUninsured.add(result.getUninsuredAmount());
                processed++;
            } catch (Exception e) {
                // BUG: Swallowing exceptions. Should halt or log critical
                // compliance errors, not silently continue.
                errors++;
            }
        }

        // BUG: No check if processing exceeded 24 hours
        LocalDateTime endTime = LocalDateTime.now();

        return new CalculationResult(
                batchId, asOfDate, processed, errors,
                totalInsured, totalUninsured, startTime, endTime);
    }

    /**
     * Calculate insurance for a single account.
     * 
     * BUG: This method operates on individual accounts.
     * It should aggregate all accounts for the same depositor
     * under the same ORC before applying the SMDIA limit.
     */
    private InsuranceResult calculateForAccount(Account account, String batchId) {
        BigDecimal insured;
        BigDecimal uninsured;
        String calcMethod;

        switch (account.getOrcType()) {
            case "SGL":
                // 12 CFR 330.6 — Single Ownership
                // BUG: Not aggregating across depositor's other SGL accounts
                insured = account.getBalance().min(SMDIA);
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = "SGL_PER_ACCT";
                break;

            case "JNT":
                // 12 CFR 330.9 — Joint Ownership
                // BUG: Equal division instead of actual ownership interest
                // BUG: Not checking if all owners are natural persons
                int owners = Math.max(account.getJointOwnerCount(), 2);
                BigDecimal perOwner = account.getBalance()
                        .divide(BigDecimal.valueOf(owners), 2, BigDecimal.ROUND_HALF_UP);
                BigDecimal perOwnerInsured = perOwner.min(SMDIA);
                insured = perOwnerInsured.multiply(BigDecimal.valueOf(owners));
                if (insured.compareTo(account.getBalance()) > 0) {
                    insured = account.getBalance();
                }
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = "JNT_EQUAL_SPLIT";
                break;

            case "REV":
                // 12 CFR 330.10 — Revocable Trust
                // BUG: >5 beneficiary aggregate calculation not implemented
                int beneficiaries = Math.max(account.getBeneficiaryCount(), 1);
                BigDecimal maxCoverage;
                if (beneficiaries <= 5) {
                    maxCoverage = SMDIA.multiply(BigDecimal.valueOf(beneficiaries));
                } else {
                    // BUG: Caps at $1.25M instead of proper aggregate
                    maxCoverage = SMDIA.multiply(BigDecimal.valueOf(5));
                }
                insured = account.getBalance().min(maxCoverage);
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = "REV_PER_BENE";
                break;

            case "EBP":
                // 12 CFR 330.14 — Employee Benefit Plan
                // BUG: Should calculate per-participant pass-through
                // Instead applies single SMDIA to entire plan
                insured = account.getBalance().min(SMDIA);
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = "EBP_NO_PASSTHRU";
                break;

            case "IRR":
                // 12 CFR 330.13 — Irrevocable Trust
                // BUG: Falls through to SGL logic. Should calculate
                // per-beneficiary interest allocation.
                insured = account.getBalance().min(SMDIA);
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = "IRR_FALLBACK_SGL";
                break;

            case "GOV1":
            case "GOV2":
            case "GOV3":
                // 12 CFR 330.15 — Government Deposits
                // BUG: Not accounting for collateral offset
                insured = account.getBalance().min(SMDIA);
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = "GOV_NO_COLLATERAL";
                break;

            default:
                // BUS, CRA, ANC — standard $250K limit
                insured = account.getBalance().min(SMDIA);
                uninsured = account.getBalance().subtract(insured).max(BigDecimal.ZERO);
                calcMethod = account.getOrcType() + "_STANDARD";
                break;
        }

        return new InsuranceResult(
                batchId, account.getAccountNumber(), account.getDepositorId(),
                account.getOrcType(), account.getBalance(),
                insured, uninsured, calcMethod);
    }

    /**
     * Generate QDF (Qualified Depositor File) output.
     * 
     * BUG: Uses comma delimiter instead of pipe (|) per FDIC spec.
     * BUG: No file header with version, timestamp, record count.
     * BUG: PII (government_id) not encrypted in output.
     * BUG: No file integrity checksum generated.
     */
    public String generateQDF(String batchId, String outputDir) {
        List<InsuranceResult> results = resultRepository.findByBatchId(batchId);
        // BUG: Comma delimiter — FDIC spec requires pipe (|)
        String delimiter = ",";
        String filename = outputDir + "/QDF_" + LocalDate.now() + ".csv";

        StringBuilder sb = new StringBuilder();
        // BUG: No file header metadata row
        sb.append("depositor_id").append(delimiter)
          .append("government_id").append(delimiter)  // BUG: PII exposed
          .append("orc_type").append(delimiter)
          .append("balance").append(delimiter)
          .append("insured").append(delimiter)
          .append("uninsured").append(delimiter)
          .append("calc_method").append("\n");

        for (InsuranceResult r : results) {
            Customer cust = customerRepository.findById(r.getDepositorId());
            sb.append(r.getDepositorId()).append(delimiter)
              .append(cust != null ? cust.getGovernmentId() : "").append(delimiter)
              .append(r.getOrcType()).append(delimiter)
              .append(r.getBalance()).append(delimiter)
              .append(r.getInsuredAmount()).append(delimiter)
              .append(r.getUninsuredAmount()).append(delimiter)
              .append(r.getCalcMethod()).append("\n");
        }

        // Write file (simplified — production uses FileWriter)
        return filename;
    }

    /**
     * Check data completeness per IT Guide Section 2.3.2.
     * 
     * BUG: Only checks basic field presence, not format validation.
     * BUG: Doesn't check ORC-specific required fields.
     * BUG: Doesn't detect duplicate government_ids.
     * BUG: Doesn't flag deceased depositors for review.
     */
    public Map<String, Object> checkDataCompleteness() {
        Map<String, Object> report = new HashMap<>();
        List<String> issues = new ArrayList<>();

        List<Customer> allCustomers = customerRepository.findAll();
        List<Account> allAccounts = accountRepository.findAll();

        int missingGovtId = 0;
        int missingName = 0;
        for (Customer c : allCustomers) {
            if (c.getGovernmentId() == null || c.getGovernmentId().trim().isEmpty()) {
                missingGovtId++;
                issues.add("CRITICAL: Missing government_id for " + c.getDepositorId());
            }
            if (c.getName() == null || c.getName().trim().isEmpty()) {
                missingName++;
                issues.add("HIGH: Missing name for " + c.getDepositorId());
            }
            // BUG: Not checking email, phone, DOB, address completeness
        }

        // BUG: Not checking for orphan accounts (account refs missing customer)
        // BUG: Not checking for orphan customers (no accounts)
        // BUG: Not checking ORC-specific required fields

        int totalChecks = allCustomers.size() * 3 + allAccounts.size() * 3;
        int issueCount = issues.size();
        double completeness = totalChecks > 0
                ? ((double)(totalChecks - issueCount) / totalChecks) * 100.0
                : 0.0;

        report.put("total_customers", allCustomers.size());
        report.put("total_accounts", allAccounts.size());
        report.put("completeness_pct", completeness);
        report.put("issues", issues);

        return report;
    }
}
