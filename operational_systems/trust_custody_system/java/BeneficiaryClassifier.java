/**
 * BeneficiaryClassifier.java
 * Classifies trust beneficiaries for FDIC insurance coverage determination.
 *
 * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
 *   1. Does not distinguish qualifying vs non-qualifying beneficiaries
 *   2. Charitable organizations treated same as natural persons
 *   3. Minor beneficiaries (UTMA/UGMA) not special-cased
 *   4. Successor beneficiaries not tracked
 *   5. Per-stirpes vs per-capita distribution not modeled
 *   6. Living trust grantor-as-beneficiary double-counts coverage
 *   7. No validation of beneficiary relationship (spouse, child, etc.)
 *   8. Cross-trust beneficiary deduplication not performed
 */

package com.bank.trust.classifier;

import java.math.BigDecimal;
import java.util.*;
import java.util.stream.Collectors;

public class BeneficiaryClassifier {

    // FDIC qualifying beneficiary categories
    private static final Set<String> QUALIFYING_RELATIONSHIPS = Set.of(
        "SPOUSE", "CHILD", "GRANDCHILD", "PARENT", "SIBLING"
    );

    // BUG: This set is incomplete — FDIC considers ALL named beneficiaries qualifying
    // The restriction to family members was an interpretation error
    private static final Set<String> ENTITY_TYPES = Set.of(
        "CHARITY", "FOUNDATION", "CHURCH", "UNIVERSITY"
    );

    /**
     * Classify beneficiaries of a trust for insurance coverage.
     * BUG: Only returns PRIMARY type beneficiaries — CONTINGENT beneficiaries
     *       may become qualifying if primary disclaims or predeceases.
     * BUG: Does not check if beneficiary has a non-contingent interest
     *       (required for IRR trusts under 12 CFR 330.13).
     */
    public List<ClassifiedBeneficiary> classifyForTrust(String trustId, String trustType,
                                                         List<Beneficiary> beneficiaries) {
        List<ClassifiedBeneficiary> classified = new ArrayList<>();

        for (Beneficiary bene : beneficiaries) {
            ClassifiedBeneficiary cb = new ClassifiedBeneficiary();
            cb.setBeneficiaryId(bene.getId());
            cb.setTrustId(trustId);
            cb.setName(bene.getName());
            cb.setRelationship(bene.getRelationship());

            // Determine if qualifying for FDIC coverage
            if ("REV".equals(trustType)) {
                // BUG: Only PRIMARY type counted as qualifying
                cb.setQualifying("PRI".equals(bene.getType()) && "A".equals(bene.getStatus()));
                // BUG: Should also be qualifying if named in trust instrument regardless of type
            } else if ("IRR".equals(trustType)) {
                // BUG: IRR requires non-contingent interest — not implemented
                // Just using allocation percentage as proxy
                cb.setQualifying(bene.getAllocationPct().compareTo(BigDecimal.ZERO) > 0);
                cb.setNonContingentInterest(bene.getAllocationPct());
            } else if ("EBP".equals(trustType)) {
                // EBP: All vested participants qualify
                cb.setQualifying(true); // BUG: No vesting check
            } else {
                cb.setQualifying(false);
            }

            // Entity vs natural person check
            // BUG: Charities should not receive separate $250K coverage
            // unless they have a ascertainable interest in the trust
            cb.setNaturalPerson("Y".equals(bene.getNaturalPerson()));

            // BUG: No check of deceased status
            // BUG: No check of age (minor beneficiaries have different rules)

            classified.add(cb);
        }

        return classified;
    }

    /**
     * Count qualifying beneficiaries for coverage calculation.
     * BUG: Simple count — does not consider:
     *   - Same beneficiary across multiple trusts from same grantor
     *   - Entity beneficiaries that don't qualify for separate coverage
     *   - Deceased beneficiaries that haven't been removed
     */
    public int countQualifyingBeneficiaries(List<ClassifiedBeneficiary> classified) {
        return (int) classified.stream()
                .filter(ClassifiedBeneficiary::isQualifying)
                .count();
        // BUG: Should also filter by naturalPerson for certain trust types
    }

    /**
     * Detect cross-trust beneficiary duplicates.
     * BUG: Method exists but is NEVER CALLED in the pipeline.
     * Same beneficiary in multiple trusts from same grantor should share one $250K limit.
     */
    public Map<String, List<String>> detectCrossTrustDuplicates(
            Map<String, List<ClassifiedBeneficiary>> trustBeneficiaries) {
        Map<String, List<String>> duplicates = new HashMap<>();

        // Group by beneficiary SSN across all trusts
        Map<String, List<ClassifiedBeneficiary>> bySsn = trustBeneficiaries.values().stream()
                .flatMap(List::stream)
                .filter(b -> b.getSsn() != null)
                .collect(Collectors.groupingBy(ClassifiedBeneficiary::getSsn));

        for (Map.Entry<String, List<ClassifiedBeneficiary>> entry : bySsn.entrySet()) {
            if (entry.getValue().size() > 1) {
                List<String> trustIds = entry.getValue().stream()
                        .map(ClassifiedBeneficiary::getTrustId)
                        .distinct()
                        .collect(Collectors.toList());
                if (trustIds.size() > 1) {
                    duplicates.put(entry.getKey(), trustIds);
                    // BUG: Detection only — no automatic coverage adjustment
                    // BUG: No alert to compliance team
                }
            }
        }

        return duplicates;
    }
}
