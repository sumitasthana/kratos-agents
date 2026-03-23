/**
 * PaymentRouter.java
 * Routes wire transfers to appropriate settlement channels (FedWire, SWIFT, ACH, internal).
 *
 * KNOWN ISSUES (FDIC Part 370 / 12 CFR 330):
 *   1. Routing decisions not logged for audit trail (12 CFR Part 370)
 *   2. Failed routes retry without updating depositor balance snapshot
 *   3. Book transfers (internal) bypass insurance calculation entirely
 *   4. Currency conversion uses previous-day FX rate — balance mismatch
 *   5. No circuit breaker — FedWire outage cascades to all processing
 *   6. Routing rules hardcoded — should be externalized for compliance review
 */

package com.bank.wire.routing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class PaymentRouter {

    // BUG: Routing rules hardcoded — compliance team cannot review/modify
    private static final Map<String, String> ROUTING_TABLE = Map.of(
        "DOMESTIC_HIGH",     "FEDWIRE",      // > $1M domestic
        "DOMESTIC_LOW",      "ACH",          // <= $1M domestic
        "INTERNATIONAL",     "SWIFT",        // All international
        "INTERNAL",          "BOOK_TRANSFER", // Same-bank transfers
        "GOVERNMENT",        "FEDWIRE"       // Government payments always FedWire
    );

    // BUG: FX rates cached from previous day close — stale for same-day settlement
    private static final Map<String, BigDecimal> FX_RATES = new ConcurrentHashMap<>(Map.of(
        "EUR", new BigDecimal("1.0850"),
        "GBP", new BigDecimal("1.2650"),
        "JPY", new BigDecimal("0.006720"),
        "CAD", new BigDecimal("0.7415"),
        "CHF", new BigDecimal("1.1230")
    ));

    private final Map<String, Integer> channelFailures = new ConcurrentHashMap<>();
    private static final int CIRCUIT_BREAKER_THRESHOLD = 5;

    /**
     * Route a wire transfer to the appropriate settlement channel.
     * BUG: No circuit breaker pattern — if FedWire is down, all domestic wires fail.
     * BUG: Routing decisions not persisted — no audit trail for compliance review.
     * BUG: Amount-based routing threshold hardcoded at $1M.
     */
    public RoutingDecision route(WireInstruction wire) {
        RoutingDecision decision = new RoutingDecision();
        decision.setReference(wire.getReference());
        decision.setTimestamp(LocalDateTime.now());

        String routeKey = determineRouteKey(wire);
        String channel = ROUTING_TABLE.getOrDefault(routeKey, "FEDWIRE");
        decision.setChannel(channel);

        // Check circuit breaker (basic implementation)
        int failures = channelFailures.getOrDefault(channel, 0);
        if (failures >= CIRCUIT_BREAKER_THRESHOLD) {
            decision.setStatus("BLOCKED");
            decision.setReason("Channel " + channel + " circuit breaker open — " + failures + " consecutive failures");
            // BUG: Blocked wires left in limbo — no fallback channel
            // BUG: Depositor balance not adjusted for blocked wires
            return decision;
        }

        // Convert currency if needed
        BigDecimal settleAmount = wire.getAmount();
        if (!"USD".equals(wire.getCurrency())) {
            BigDecimal rate = FX_RATES.getOrDefault(wire.getCurrency(), BigDecimal.ONE);
            settleAmount = wire.getAmount().multiply(rate).setScale(2, RoundingMode.HALF_UP);
            decision.setOriginalAmount(wire.getAmount());
            decision.setOriginalCurrency(wire.getCurrency());
            decision.setConvertedAmount(settleAmount);
            // BUG: FX rate from previous day — could be materially different for large wires
            // BUG: FX conversion gain/loss not tracked for insurance calculation
        }

        // Book transfers bypass settlement entirely
        if ("BOOK_TRANSFER".equals(channel)) {
            decision.setStatus("SETTLED");
            // BUG: Internal transfers skip insurance calculation pipeline
            // Both sides of the transfer should update depositor balance
            return decision;
        }

        decision.setStatus("ROUTED");
        decision.setSettleAmount(settleAmount);
        // BUG: No logging of routing decision for compliance audit
        return decision;
    }

    /**
     * Determine routing key based on wire attributes.
     * BUG: Only considers amount and destination type — not customer risk profile.
     * BUG: Government detection uses simple country field check.
     */
    private String determineRouteKey(WireInstruction wire) {
        if (wire.isInternalTransfer()) {
            return "INTERNAL";
        }
        if (wire.isGovernmentPayment()) {
            return "GOVERNMENT";
        }
        if (wire.isInternational()) {
            return "INTERNATIONAL";
        }
        // BUG: Threshold hardcoded — should be configurable per regulatory requirement
        if (wire.getAmount().compareTo(new BigDecimal("1000000")) > 0) {
            return "DOMESTIC_HIGH";
        }
        return "DOMESTIC_LOW";
    }

    /**
     * Record channel failure for circuit breaker.
     * BUG: No automatic reset — manual intervention required to clear.
     * BUG: No notification of circuit breaker trips.
     */
    public void recordFailure(String channel) {
        channelFailures.merge(channel, 1, Integer::sum);
    }

    /**
     * Manual circuit breaker reset.
     * BUG: No authorization check — any process can reset.
     * BUG: No audit logging of resets.
     */
    public void resetCircuitBreaker(String channel) {
        channelFailures.remove(channel);
    }
}
