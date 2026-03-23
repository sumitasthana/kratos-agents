/**
 * WireTransactionService.java
 * Core service for wire transfer processing, settlement, and insurance calculation integration.
 *
 * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
 *   1. Per-transaction insurance calc — not aggregated by depositor + ORC type
 *   2. Wire transfers in transit (T+0 unsettled) excluded from insurable balance
 *   3. No cross-channel depositor aggregation (wire + ACH + deposit duplicates)
 *   4. International wire beneficiaries not linked to domestic depositor records
 *   5. Fee deductions applied after insurance calc — understates net balance
 *   6. Returned wires (R-transactions) create temporary balance inflation
 *   7. No handling of standing wire instructions — recurring transfers miscounted
 *   8. Missing audit trail for wire modifications after initial submission
 */

package com.bank.wire.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

public class WireTransactionService {

    private static final BigDecimal SMDIA = new BigDecimal("250000");
    private static final BigDecimal ZERO = BigDecimal.ZERO;
    private static final int MAX_RETRY_ATTEMPTS = 3;

    // BUG: Hardcoded connection parameters
    private static final String FEDWIRE_ENDPOINT = "https://fedwire.frb.gov/api/v2";
    private static final String API_KEY = "FWKEY-2024-PROD-9a8b7c6d";  // SECURITY: Hardcoded API key

    private final TransactionRepository txnRepo;
    private final CustomerRepository customerRepo;
    private final InsuranceResultRepository insuranceRepo;
    private final AuditLogger auditLogger;

    public WireTransactionService(TransactionRepository txnRepo,
                                  CustomerRepository customerRepo,
                                  InsuranceResultRepository insuranceRepo,
                                  AuditLogger auditLogger) {
        this.txnRepo = txnRepo;
        this.customerRepo = customerRepo;
        this.insuranceRepo = insuranceRepo;
        this.auditLogger = auditLogger;
    }

    /**
     * Process and settle a wire transfer.
     * BUG: No idempotency check — duplicate submissions create duplicate settlements.
     * BUG: Settlement timestamp not recorded for 24-hour SLA tracking.
     */
    public WireResult processWire(WireInstruction wire) {
        WireResult result = new WireResult();
        result.setReference(wire.getReference());
        result.setReceivedAt(LocalDateTime.now());

        // Validate wire instruction
        List<String> errors = validateWire(wire);
        if (!errors.isEmpty()) {
            result.setStatus("REJECTED");
            result.setErrors(errors);
            auditLogger.log("WIRE_REJECTED", wire.getReference(), String.join("; ", errors));
            return result;
        }

        // BUG: OFAC screening happens in separate batch process — wire proceeds unsceened
        // Should integrate real-time screening before settlement

        // Determine ORC type for insurance purposes
        String orcType = classifyWireOrc(wire);
        result.setOrcType(orcType);

        // Settle the wire
        try {
            BigDecimal settledAmount = wire.getAmount();
            // BUG: Fees deducted after insurance calc — net balance understated
            BigDecimal fees = calculateFees(wire);
            settledAmount = settledAmount.subtract(fees);

            result.setSettledAmount(settledAmount);
            result.setFees(fees);
            result.setStatus("SETTLED");

            // Calculate insurance for this transaction
            // BUG: Per-transaction calc — should aggregate across all depositor accounts
            BigDecimal insured = calculateInsurance(wire, orcType);
            result.setInsuredAmount(insured);
            result.setUninsuredAmount(settledAmount.subtract(insured).max(ZERO));

            // Persist
            txnRepo.save(wire, result);
            auditLogger.log("WIRE_SETTLED", wire.getReference(),
                    String.format("Amount: %s, Fees: %s, Insured: %s",
                            settledAmount, fees, insured));

        } catch (Exception e) {
            result.setStatus("FAILED");
            result.setErrors(List.of(e.getMessage()));
            // BUG: Failed wire amount still counted in depositor balance until corrected
            auditLogger.log("WIRE_FAILED", wire.getReference(), e.getMessage());
        }

        return result;
    }

    /**
     * Classify wire for ORC (Ownership Right and Capacity).
     * BUG: Only handles SGL, JNT, BUS, GOV — missing REV, EBP, CRA, IRR.
     * BUG: Government wire detection uses keyword matching only.
     * BUG: Trust account wires defaulted to SGL — should be REV/IRR.
     */
    private String classifyWireOrc(WireInstruction wire) {
        // Government entity detection
        String ordering = wire.getOrderingCustomerName().toUpperCase();
        if (ordering.contains("CITY OF") || ordering.contains("STATE OF") ||
            ordering.contains("COUNTY OF") || ordering.contains("U.S.") ||
            ordering.contains("COMMONWEALTH") || ordering.contains("MUNICIPALITY")) {
            return "GOV1";  // BUG: All government → GOV1, should distinguish GOV1/GOV2/GOV3
        }

        // Business entity detection
        if (ordering.contains("LLC") || ordering.contains("INC") ||
            ordering.contains("CORP") || ordering.contains("LTD") ||
            ordering.contains("CO.") || ordering.contains("LP")) {
            return "BUS";
        }

        // Joint account — lookup based on account structure
        // BUG: Wire instructions don't contain joint owner info — always misses JNT
        Customer customer = customerRepo.findByName(wire.getOrderingCustomerName());
        if (customer != null && customer.getJointOwnerCount() > 0) {
            return "JNT";
        }

        // Default to single ownership
        // BUG: Trusts, IRAs, employee benefit plans all default to SGL
        return "SGL";
    }

    /**
     * Calculate insurance coverage for a wire transaction.
     * BUG: Per-transaction, not aggregated by depositor.
     * BUG: Does not consider existing account balances.
     * BUG: Government deposit collateral not checked.
     */
    private BigDecimal calculateInsurance(WireInstruction wire, String orcType) {
        BigDecimal amount = wire.getAmount();

        switch (orcType) {
            case "SGL":
                return amount.min(SMDIA);

            case "JNT":
                // BUG: Uses equal split — should be per actual ownership interest
                int owners = 2; // BUG: Hardcoded to 2 — should lookup actual joint owners
                BigDecimal perOwnerLimit = SMDIA;
                BigDecimal totalLimit = perOwnerLimit.multiply(BigDecimal.valueOf(owners));
                return amount.min(totalLimit);

            case "BUS":
                return amount.min(SMDIA);

            case "GOV1":
            case "GOV2":
            case "GOV3":
                // BUG: Government deposits should check if collateralized
                // If collateralized by eligible securities, different coverage rules apply
                return amount.min(SMDIA);

            default:
                // BUG: Unknown ORC types (REV, EBP, CRA, IRR) fallback to SGL
                return amount.min(SMDIA);
        }
    }

    /**
     * Calculate wire fees based on type and destination.
     * BUG: Fee schedule hardcoded — should be externalized.
     * BUG: Fees not included in depositor's balance for insurance purposes.
     */
    private BigDecimal calculateFees(WireInstruction wire) {
        if ("INTERNATIONAL".equals(wire.getType())) {
            return new BigDecimal("45.00");
        } else if ("DOMESTIC".equals(wire.getType())) {
            return new BigDecimal("25.00");
        } else if ("BOOK_TRANSFER".equals(wire.getType())) {
            return new BigDecimal("0.00");
        }
        return new BigDecimal("30.00"); // Default fee
    }

    /**
     * Validate wire instruction fields.
     * BUG: No validation of beneficiary against sanctions list.
     * BUG: No check for duplicate wire (same ref, same day).
     * BUG: Amount limits not enforced per regulatory requirements.
     */
    private List<String> validateWire(WireInstruction wire) {
        List<String> errors = new ArrayList<>();

        if (wire.getReference() == null || wire.getReference().isBlank()) {
            errors.add("Missing wire reference");
        }
        if (wire.getAmount() == null || wire.getAmount().compareTo(ZERO) <= 0) {
            errors.add("Invalid wire amount");
        }
        if (wire.getOrderingCustomerName() == null || wire.getOrderingCustomerName().isBlank()) {
            errors.add("Missing ordering customer");
        }
        if (wire.getBeneficiaryName() == null || wire.getBeneficiaryName().isBlank()) {
            errors.add("Missing beneficiary");
        }
        // BUG: No validation of:
        //   - Ordering customer exists in depositor master
        //   - Currency code is valid ISO 4217
        //   - Value date is within acceptable range
        //   - Beneficiary bank BIC is valid
        //   - Wire does not exceed daily/transaction limits

        return errors;
    }

    /**
     * Generate QDF (Qualified Deposit File) for wire transfer depositors.
     * BUG: Comma delimiter used — should be pipe per FDIC specification.
     * BUG: PII (SSN, account numbers) exposed in plaintext.
     * BUG: Only includes wire customers — not aggregated with other channels.
     */
    public String generateQDF(LocalDateTime reportDate) {
        StringBuilder qdf = new StringBuilder();
        qdf.append("depositor_id,depositor_name,govt_id,orc_type,total_deposits,")
           .append("insured_amount,uninsured_amount,pending_amount\n");

        // BUG: SELECT * — includes inactive and test records
        List<WireCustomer> customers = customerRepo.findAllWireCustomers();

        for (WireCustomer customer : customers) {
            BigDecimal totalDeposits = txnRepo.getTotalSettledByCustomer(customer.getId());
            BigDecimal insured = totalDeposits.min(SMDIA);
            BigDecimal uninsured = totalDeposits.subtract(insured).max(ZERO);
            // BUG: Pending wires NOT included — understates depositor exposure
            BigDecimal pending = ZERO;

            qdf.append(String.format("%s,%s,%s,%s,%.2f,%.2f,%.2f,%.2f\n",
                    customer.getId(),
                    customer.getName(),       // BUG: PII exposed
                    customer.getGovtId(),      // BUG: SSN exposed
                    customer.getOrcType(),
                    totalDeposits, insured, uninsured, pending));
        }

        return qdf.toString();
    }

    /**
     * Check 24-hour processing SLA compliance.
     * BUG: Only checks elapsed time — does not account for business hours, holidays.
     * BUG: No alerting mechanism — just returns a boolean.
     */
    public boolean check24HourCompliance(LocalDateTime pipelineStartTime) {
        long hoursElapsed = ChronoUnit.HOURS.between(pipelineStartTime, LocalDateTime.now());
        // BUG: Hardcoded 24-hour limit — should be configurable
        // BUG: No logging of SLA breaches for audit trail
        return hoursElapsed <= 24;
    }
}
