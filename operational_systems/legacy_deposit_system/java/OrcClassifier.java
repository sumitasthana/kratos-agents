package com.bank.deposit.orc;

import java.util.*;

/**
 * OrcClassifier — Ownership Rights Category classification engine.
 * 
 * Classifies deposit accounts into FDIC Ownership Rights Categories
 * per 12 CFR Part 330 for insurance determination.
 * 
 * KNOWN COMPLIANCE ISSUES:
 *   - IRR (Irrevocable Trust) ORC not implemented (CRITICAL)
 *   - JNT does not verify natural_person for all co-owners
 *   - JNT does not check signature_card or withdrawal_rights
 *   - BUS does not verify EIN tax_id format (XX-XXXXXXX)
 *   - GOV does not verify collateral or custodian designation
 *   - Tribal governments not classified
 *   - First-match classification (order-dependent)
 *   - Unresolvable accounts silently default to SGL
 */
public class OrcClassifier {

    private static final Set<String> SUPPORTED_ORCS = Set.of(
        "SGL", "JNT", "REV", "BUS", "EBP", "CRA",
        "GOV1", "GOV2", "GOV3", "ANC"
        // BUG: "IRR" missing — 12 CFR 330.13 Irrevocable Trust
    );

    private static final Set<String> RETIREMENT_TYPES = Set.of(
        "IRA", "KEOGH", "ROTH_IRA", "SEP_IRA", "SIMPLE_IRA"
    );

    private static final Set<String> EBP_TYPES = Set.of(
        "401K", "PENSION", "PROFIT_SHARING"
    );

    private final List<Map<String, Object>> auditLog = new ArrayList<>();
    private int unassignedCount = 0;

    /**
     * Classify a single account into an ORC type.
     * 
     * @param account The deposit account to classify
     * @param customer The account's primary depositor
     * @return The assigned ORC type string
     * 
     * BUG: First-match classification — order matters.
     * BUG: No IRR (Irrevocable Trust) handling.
     * BUG: Silently defaults to SGL for unresolvable.
     */
    public String classify(Account account, Customer customer) {
        // Check Business/Organization
        if (account.getBusinessName() != null
                && !account.getBusinessName().trim().isEmpty()
                && !customer.isNaturalPerson()) {
            // BUG: Not checking corporation vs partnership (12 CFR 330.11)
            // BUG: Not verifying EIN format (XX-XXXXXXX)
            logAssignment(account, "BUS", "12CFR330.11 Business entity");
            return "BUS";
        }

        // Check Joint Ownership
        if (account.getJointOwnerCount() > 0) {
            // COMPLIANCE GAP: Not checking natural_person for co-owners
            // Per 12 CFR 330.9, ALL co-owners must be natural persons
            // MISSING: signature_card verification
            // MISSING: withdrawal_rights verification
            logAssignment(account, "JNT", "12CFR330.9 Joint ownership");
            return "JNT";
        }

        // Check Revocable Trust
        if (account.getBeneficiaryCount() > 0) {
            logAssignment(account, "REV", "12CFR330.10 Revocable trust");
            return "REV";
        }

        // Check Government entity
        if (account.getGovernmentEntity() != null
                && !account.getGovernmentEntity().trim().isEmpty()) {
            String govOrc = classifyGovernment(account.getGovernmentEntity());
            // BUG: No collateral verification for government deposits
            // Per 12 CFR 330.15, government deposits require collateral
            logAssignment(account, govOrc, "12CFR330.15 Government");
            return govOrc;
        }

        // Check CRA (IRA/Keogh)
        if (RETIREMENT_TYPES.contains(account.getAccountType().toUpperCase())) {
            logAssignment(account, "CRA", "12CFR330.14c Retirement");
            return "CRA";
        }

        // Check EBP
        if (EBP_TYPES.contains(account.getAccountType().toUpperCase())) {
            // BUG: Per-participant calculation not implemented
            logAssignment(account, "EBP", "12CFR330.14 Employee Benefit Plan");
            return "EBP";
        }

        // NOTE: IRR (Irrevocable Trust) NOT IMPLEMENTED
        // CRITICAL compliance gap — 12 CFR 330.13

        // Default to Single Ownership
        if (customer.isNaturalPerson()) {
            logAssignment(account, "SGL", "12CFR330.6 Default single");
            return "SGL";
        }

        // Unresolvable — defaults to SGL instead of routing to pending
        unassignedCount++;
        logAssignment(account, "SGL", "UNRESOLVABLE — defaulted to SGL");
        return "SGL";
    }

    private String classifyGovernment(String entity) {
        String lower = entity.toLowerCase();
        if (lower.contains("federal") || lower.contains("united states")) {
            return "GOV1";
        } else if (lower.contains("state")) {
            return "GOV2";
        }
        // BUG: Tribal governments not classified
        return "GOV3";  // Default to municipal
    }

    private void logAssignment(Account account, String orc, String rule) {
        Map<String, Object> entry = new HashMap<>();
        entry.put("account", account.getAccountNumber());
        entry.put("orc", orc);
        entry.put("rule", rule);
        entry.put("timestamp", new java.util.Date().toString());
        auditLog.add(entry);
    }

    public int getUnassignedCount() { return unassignedCount; }
    public List<Map<String, Object>> getAuditLog() { return auditLog; }
}
