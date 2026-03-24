"""
src/observability/metrics.py

All Prometheus metrics for the Kratos platform, organised by the RED method
(Rate, Errors, Duration) and USE method (Utilisation, Saturation, Errors).

All metric names start with ``kratos_``.
Label cardinality rule: investigation_id is NEVER a Prometheus label —
use it only in log fields and event payloads.

Usage::

    from src.observability.metrics import M

    M.investigations_started.labels(scenario_id="deposit_aggregation_failure").inc()
    M.phase_duration.labels(phase="BACKTRACK", scenario_id="...", status="PASS").observe(412)
    M.confidence_score.labels(scenario_id=s_id).set(0.87)
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
)

# Isolated registry so demo + obs APIs can import without polluting the
# default Prometheus global registry used by other processes.
REGISTRY = CollectorRegistry(auto_describe=True)


class KratosMetrics:
    # ── Investigations ──────────────────────────────────────────────────────

    investigations_started = Counter(
        "kratos_investigations_started_total",
        "Total RCA investigations started",
        ["scenario_id"],
        registry=REGISTRY,
    )
    investigations_completed = Counter(
        "kratos_investigations_completed_total",
        "Total RCA investigations completed",
        ["scenario_id", "status"],   # status: CONFIRMED|INCONCLUSIVE|ERROR
        registry=REGISTRY,
    )
    investigations_in_flight = Gauge(
        "kratos_investigations_in_flight",
        "Investigations currently running",
        registry=REGISTRY,
    )

    # ── Phases ──────────────────────────────────────────────────────────────

    phase_duration = Histogram(
        "kratos_phase_duration_ms",
        "Time spent per CauseLink phase in milliseconds",
        ["phase", "scenario_id", "status"],
        buckets=[50, 100, 250, 500, 1000, 2000, 5000, 10000],
        registry=REGISTRY,
    )
    phase_errors = Counter(
        "kratos_phase_errors_total",
        "Phase execution errors",
        ["phase", "scenario_id", "error_type"],
        registry=REGISTRY,
    )

    # ── Agents ──────────────────────────────────────────────────────────────

    agent_invocations = Counter(
        "kratos_agent_invocations_total",
        "Total agent invocations",
        ["agent_name", "phase"],
        registry=REGISTRY,
    )
    agent_duration = Histogram(
        "kratos_agent_duration_ms",
        "Agent execution time in milliseconds",
        ["agent_name"],
        buckets=[10, 25, 50, 100, 250, 500, 1000, 3000],
        registry=REGISTRY,
    )

    # ── Evidence & Hypotheses ────────────────────────────────────────────────

    evidence_collected = Counter(
        "kratos_evidence_collected_total",
        "Evidence objects collected",
        ["scenario_id", "tier"],   # tier: SIGNAL|CRITICAL|NOISE
        registry=REGISTRY,
    )
    evidence_rejected = Counter(
        "kratos_evidence_rejected_total",
        "Evidence objects rejected by agents",
        ["scenario_id", "reason"],
        registry=REGISTRY,
    )
    hypotheses_created = Counter(
        "kratos_hypotheses_created_total",
        "Hypotheses generated",
        ["scenario_id", "pattern_id"],
        registry=REGISTRY,
    )
    hypotheses_promoted = Counter(
        "kratos_hypotheses_promoted_total",
        "Hypotheses promoted to SUPPORTED",
        ["scenario_id", "pattern_id"],
        registry=REGISTRY,
    )
    hypotheses_rejected = Counter(
        "kratos_hypotheses_rejected_total",
        "Hypotheses rejected",
        ["scenario_id", "rejection_reason"],
        registry=REGISTRY,
    )

    # ── Backtracking ─────────────────────────────────────────────────────────

    backtrack_hops = Histogram(
        "kratos_backtrack_hops",
        "Number of ontology hops per investigation",
        ["scenario_id"],
        buckets=[1, 2, 3, 4, 5, 6, 7, 8],
        registry=REGISTRY,
    )
    backtrack_early_stops = Counter(
        "kratos_backtrack_early_stops_total",
        "Investigations that hit early-stop rule",
        ["scenario_id"],
        registry=REGISTRY,
    )
    backtrack_max_hops = Counter(
        "kratos_backtrack_max_hops_reached_total",
        "Investigations that hit 8-hop limit without root cause",
        ["scenario_id"],
        registry=REGISTRY,
    )

    # ── ValidationGate ───────────────────────────────────────────────────────

    validation_gate_results = Counter(
        "kratos_validation_gate_results_total",
        "ValidationGate rule results",
        ["gate_rule", "result"],   # result: PASS|FAIL
        registry=REGISTRY,
    )
    validation_gate_failures = Counter(
        "kratos_validation_gate_failures_total",
        "Total ValidationGate failures (blocked root_cause_final)",
        ["scenario_id", "failed_rules"],
        registry=REGISTRY,
    )

    # ── Confidence Scores ────────────────────────────────────────────────────

    confidence_score = Gauge(
        "kratos_confidence_score",
        "Latest composite confidence score per scenario",
        ["scenario_id"],
        registry=REGISTRY,
    )
    confidence_distribution = Histogram(
        "kratos_confidence_distribution",
        "Distribution of composite confidence scores",
        ["scenario_id"],
        buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        registry=REGISTRY,
    )
    confidence_below_threshold = Counter(
        "kratos_confidence_below_threshold_total",
        "Investigations where confidence < 0.70 (INCONCLUSIVE)",
        ["scenario_id"],
        registry=REGISTRY,
    )

    # ── Controls ─────────────────────────────────────────────────────────────

    control_scan_results = Counter(
        "kratos_control_scan_results_total",
        "Control scan results",
        ["control_id", "status"],   # status: PASS|FAIL|WARN
        registry=REGISTRY,
    )

    # ── API Layer ────────────────────────────────────────────────────────────

    api_request_duration = Histogram(
        "kratos_api_request_duration_ms",
        "API endpoint response time",
        ["method", "endpoint", "status_code"],
        buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2000],
        registry=REGISTRY,
    )
    api_errors = Counter(
        "kratos_api_errors_total",
        "API errors by endpoint",
        ["method", "endpoint", "error_type"],
        registry=REGISTRY,
    )
    sse_connections_active = Gauge(
        "kratos_sse_connections_active",
        "Active SSE stream connections",
        registry=REGISTRY,
    )
    sse_events_emitted = Counter(
        "kratos_sse_events_emitted_total",
        "SSE events pushed to clients",
        ["event_type"],
        registry=REGISTRY,
    )

    # ── Queue / Async Health ──────────────────────────────────────────────────

    queue_depth = Gauge(
        "kratos_investigation_queue_depth",
        "Items waiting in per-investigation asyncio.Queue (labelled by scenario only)",
        ["scenario_id"],
        registry=REGISTRY,
    )
    queue_wait_duration = Histogram(
        "kratos_queue_wait_duration_ms",
        "Time SSE events wait in queue before delivery",
        buckets=[1, 5, 10, 25, 50, 100, 250],
        registry=REGISTRY,
    )

    # ── CSV Data Layer ────────────────────────────────────────────────────────

    csv_records_loaded = Gauge(
        "kratos_csv_records_loaded",
        "Total records loaded from kratos_data CSV",
        registry=REGISTRY,
    )
    smdia_exposure_count = Gauge(
        "kratos_smdia_exposure_count",
        "Accounts with balance > $250,000 in loaded dataset",
        registry=REGISTRY,
    )


# Module-level singleton accessed as ``M.metric_name``
M = KratosMetrics()
