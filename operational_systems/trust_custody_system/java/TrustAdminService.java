/**
 * TrustAdminService.java
 * Core service for trust and custody account administration,
 * beneficiary management, and insurance determination integration.
 *
 * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
 *   1. Beneficiary enumeration incomplete — only queries active primary beneficiaries
 *   2. Grantor-level aggregation NOT performed — same grantor with 3 trusts gets 3x coverage
 *   3. Trust sub-accounts (CDs, savings under trust) not rolled into trust balance
 *   4. Beneficiary change audit: changes logged but not reflected in insurance recalc
 *   5. Deceased grantor trusts not reclassified (REV → IRR transition on death)
 *   6. IRA trusts classified as CUS (custodial) not IRR — wrong coverage rule
 *   7. Charitable remainder trusts treated as REV — should have separate logic
 *   8. Plan participant data cached daily — intraday changes not reflected
 *   9. PII (SSN, DOB) exposed in beneficiary query results without masking
 *  10. No encryption of trust instrument documents at rest
 */

package com.bank.trust.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.util.*;
import java.util.stream.Collectors;

public class TrustAdminService {

    private static final BigDecimal SMDIA = new BigDecimal("250000");
    private static final BigDecimal ZERO = BigDecimal.ZERO;
    // BUG: Old rule — FDIC removed beneficiary cap in 2010
    private static final int MAX_REVOCABLE_BENEFICIARIES = 5;

    private final TrustRepository trustRepo;
    private final BeneficiaryRepository beneRepo;
    private final ParticipantRepository participantRepo;
    private final InsuranceResultRepository insuranceRepo;

    public TrustAdminService(TrustRepository trustRepo,
                             BeneficiaryRepository beneRepo,
                             ParticipantRepository participantRepo,
                             InsuranceResultRepository insuranceRepo) {
        this.trustRepo = trustRepo;
        this.beneRepo = beneRepo;
        this.participantRepo = participantRepo;
        this.insuranceRepo = insuranceRepo;
    }

    /**
     * Calculate insurance coverage for a trust account.
     * BUG: Per-trust calculation — does not aggregate by grantor.
     * BUG: Does not consider trust sub-accounts (CDs, savings under trust umbrella).
     */
    public TrustInsuranceResult calculateInsurance(String trustId) {
        TrustAccount trust = trustRepo.findById(trustId);
        if (trust == null) {
            throw new IllegalArgumentException("Trust not found: " + trustId);
        }

        TrustInsuranceResult result = new TrustInsuranceResult();
        result.setTrustId(trustId);
        result.setTrustType(trust.getType());
        result.setCalculatedAt(LocalDateTime.now());

        BigDecimal balance = trust.getBalance().add(trust.getAccruedInterest());
        result.setTotalBalance(balance);

        switch (trust.getType()) {
            case "REV":
                calculateRevocable(trust, result, balance);
                break;
            case "IRR":
                calculateIrrevocable(trust, result, balance);
                break;
            case "EBP":
                calculateEBP(trust, result, balance);
                break;
            case "CUS":
                calculateCustodial(trust, result, balance);
                break;
            default:
                // BUG: Unknown → SGL default, no error raised
                result.setOrcType("SGL");
                result.setInsuredAmount(balance.min(SMDIA));
                result.setUninsuredAmount(balance.subtract(SMDIA).max(ZERO));
                result.setCalcMethod("UNKNOWN_DEFAULT");
                break;
        }

        insuranceRepo.save(result);
        return result;
    }

    /**
     * Calculate revocable trust coverage per 12 CFR 330.10.
     * BUG: Only counts primary beneficiaries — misses contingent beneficiaries
     *       who become primary upon death of prior beneficiary.
     * BUG: Deceased beneficiaries still counted (not excluded).
     * BUG: Caps at 5 beneficiaries — old rule, removed in 2010.
     * BUG: Allocation percentage ignored — assumes equal split.
     */
    private void calculateRevocable(TrustAccount trust, TrustInsuranceResult result,
                                     BigDecimal balance) {
        result.setOrcType("REV");

        // Get active primary beneficiaries
        // BUG: Should include ALL named beneficiaries, not just PRIMARY
        List<Beneficiary> beneficiaries = beneRepo.findByTrustId(trust.getId())
                .stream()
                .filter(b -> "PRI".equals(b.getType()))
                .filter(b -> "A".equals(b.getStatus()))  // BUG: Deceased not removed from DB
                .collect(Collectors.toList());

        int beneCount = beneficiaries.size();

        // BUG: Cap at 5 — this limit was removed by FDIC in 2010
        if (beneCount > MAX_REVOCABLE_BENEFICIARIES) {
            beneCount = MAX_REVOCABLE_BENEFICIARIES;
        }

        if (beneCount == 0) {
            // No beneficiaries — treated as grantor's personal funds
            beneCount = 1;
        }

        BigDecimal maxCoverage = SMDIA.multiply(BigDecimal.valueOf(beneCount));
        result.setInsuredAmount(balance.min(maxCoverage));
        result.setUninsuredAmount(balance.subtract(maxCoverage).max(ZERO));
        result.setBeneficiaryCount(beneCount);
        result.setCalcMethod("REV_PER_BENE_CAPPED_AT_5");
    }

    /**
     * Calculate irrevocable trust coverage per 12 CFR 330.13.
     * BUG: NOT IMPLEMENTED — falls back to SGL with $250K flat limit.
     * Should calculate per non-contingent interest:
     *   Each beneficiary with a non-contingent interest gets up to $250K
     *   based on their proportional interest in the trust.
     */
    private void calculateIrrevocable(TrustAccount trust, TrustInsuranceResult result,
                                       BigDecimal balance) {
        // TODO: Implement proper 12 CFR 330.13 calculation
        // Current: SGL fallback — massively understates coverage for large IRR trusts
        result.setOrcType("SGL");  // BUG: Should be IRR
        result.setInsuredAmount(balance.min(SMDIA));
        result.setUninsuredAmount(balance.subtract(SMDIA).max(ZERO));
        result.setCalcMethod("IRR_NOT_IMPLEMENTED_SGL_FALLBACK");
        // BUG: No error logging for this critical compliance gap
    }

    /**
     * Calculate EBP coverage per 12 CFR 330.14.
     * BUG: Uses plan-level participant count, not actual individual participant data.
     * BUG: Non-vested participants are included.
     * BUG: Terminated participants not removed from count.
     */
    private void calculateEBP(TrustAccount trust, TrustInsuranceResult result,
                               BigDecimal balance) {
        result.setOrcType("EBP");

        // BUG: Using header count instead of querying actual participant roster
        int participantCount = trust.getParticipantCount();

        // Try to get actual count from participant DB
        // BUG: This code exists but participant data is stale (daily cache)
        try {
            List<PlanParticipant> participants = participantRepo.findByPlanId(trust.getId());
            if (participants != null && !participants.isEmpty()) {
                // BUG: Counts ALL participants, not just those with vested interest
                // BUG: Includes terminated participants who haven't rolled over
                participantCount = participants.size();
            }
        } catch (Exception e) {
            // BUG: Silently falls back to header count on DB error
        }

        if (participantCount <= 0) {
            participantCount = 1;
        }

        BigDecimal maxCoverage = SMDIA.multiply(BigDecimal.valueOf(participantCount));
        result.setInsuredAmount(balance.min(maxCoverage));
        result.setUninsuredAmount(balance.subtract(maxCoverage).max(ZERO));
        result.setParticipantCount(participantCount);
        result.setCalcMethod("EBP_PER_PLAN_HEADER_COUNT");
    }

    /**
     * Calculate custodial account coverage.
     * BUG: All custodial accounts treated as SGL regardless of underlying type.
     * IRA custodial should be IRR, UTMA/UGMA should be SGL in minor's name.
     */
    private void calculateCustodial(TrustAccount trust, TrustInsuranceResult result,
                                     BigDecimal balance) {
        // BUG: Does not determine underlying account type
        result.setOrcType("SGL");
        result.setInsuredAmount(balance.min(SMDIA));
        result.setUninsuredAmount(balance.subtract(SMDIA).max(ZERO));
        result.setCalcMethod("CUSTODIAL_AS_SGL");
    }

    /**
     * Check for deceased grantors whose REV trusts should be reclassified to IRR.
     * BUG: Method exists but is NEVER CALLED in the processing pipeline.
     * Per FDIC rules, a revocable trust becomes irrevocable upon grantor's death.
     */
    public List<String> findDeceasedGrantorTrusts() {
        return trustRepo.findAll().stream()
                .filter(t -> "REV".equals(t.getType()))
                .filter(t -> {
                    // BUG: Customer death status checked against wrong table
                    // Trust grantor may not be in the depositor master
                    return false; // Always returns empty — never detects deceased grantors
                })
                .map(TrustAccount::getId)
                .collect(Collectors.toList());
    }

    /**
     * Generate trust insurance summary for QDF output.
     * BUG: Comma delimiter instead of pipe.
     * BUG: Grantor SSN exposed in plaintext — PII violation.
     * BUG: Sub-account balances not included in trust total.
     */
    public String generateTrustQDF(LocalDate reportDate) {
        StringBuilder qdf = new StringBuilder();
        qdf.append("trust_id,trust_name,trust_type,orc_type,grantor_id,grantor_ssn,")
           .append("total_balance,bene_count,insured_amount,uninsured_amount,calc_method\n");

        List<TrustAccount> trusts = trustRepo.findAllActive();
        for (TrustAccount trust : trusts) {
            TrustInsuranceResult result = calculateInsurance(trust.getId());
            // BUG: Recalculates every time — no caching, performance issue
            qdf.append(String.format("%s,%s,%s,%s,%s,%s,%.2f,%d,%.2f,%.2f,%s\n",
                    trust.getId(),
                    trust.getName(),
                    trust.getType(),
                    result.getOrcType(),
                    trust.getGrantorId(),
                    trust.getGrantorSsn(),    // BUG: SSN exposed
                    result.getTotalBalance(),
                    result.getBeneficiaryCount(),
                    result.getInsuredAmount(),
                    result.getUninsuredAmount(),
                    result.getCalcMethod()));
        }

        return qdf.toString();
    }

    /**
     * Validate beneficiary data completeness.
     * BUG: Only checks for presence of name and SSN — no format validation.
     * BUG: Does not verify beneficiary exists in depositor master.
     * BUG: Does not check for duplicate beneficiaries across trusts.
     */
    public Map<String, List<String>> validateBeneficiaryData() {
        Map<String, List<String>> issues = new LinkedHashMap<>();

        List<TrustAccount> trusts = trustRepo.findAll();
        for (TrustAccount trust : trusts) {
            List<String> trustIssues = new ArrayList<>();
            List<Beneficiary> beneficiaries = beneRepo.findByTrustId(trust.getId());

            if (beneficiaries.isEmpty()) {
                trustIssues.add("No beneficiaries registered");
            }

            for (Beneficiary bene : beneficiaries) {
                if (bene.getName() == null || bene.getName().isBlank()) {
                    trustIssues.add("Beneficiary " + bene.getId() + ": missing name");
                }
                if (bene.getSsn() == null || bene.getSsn().isBlank()) {
                    trustIssues.add("Beneficiary " + bene.getId() + ": missing SSN");
                }
                // BUG: Does not validate:
                //   - SSN format (XXX-XX-XXXX)
                //   - DOB is reasonable
                //   - Allocation percentages sum to 100%
                //   - Natural person flag is set
                //   - Beneficiary is alive
            }

            if (!trustIssues.isEmpty()) {
                issues.put(trust.getId(), trustIssues);
            }
        }

        return issues;
    }
}
