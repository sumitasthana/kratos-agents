"""
Smoke test / demo: run KratosOrchestrator with an infra_fingerprint representing
a resource-pressured cluster alongside a simulated execution failure.

This exercises:
  - RoutingAgent  → emits infra_analyzer task
  - InfraAnalyzerAgent / InfraAnalyzerOrchestrator
  - TriangulationAgent Pattern 4 (log+infra correlation)
  - IssueProfile.infra_analysis field

Run from the repo root:
    cd src && python ../tests/smoke_test_infra.py
"""

import asyncio
import sys
import os

# Allow running from repo root: `python tests/smoke_test_infra.py`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orchestrator import KratosOrchestrator
from schemas import ExecutionFingerprint, ProblemType

# ── Simulated infra snapshot (resource-pressured cluster) ────────────────────
INFRA_FINGERPRINT = {
    "cluster_id":          "prod-spark-01",
    "environment":         "production",
    "time_window":         "2026-02-25T08:00:00Z / 2026-02-25T09:00:00Z",
    # CPU slightly above HIGH threshold (85 %)
    "cpu_utilization":     87.5,
    # Memory just below CRITICAL threshold (92 %)
    "memory_utilization":  91.0,
    "disk_io_utilization": 62.0,
    "network_io_utilization": 45.0,
    # Capacity: only 8/20 workers free  → utilisation 60 % → HIGH
    "total_workers":       20,
    "available_workers":   8,
    # Many tasks queued → HIGH
    "queued_tasks":        310,
    # Autoscaler scaled *down* while under load → suspicious
    "autoscale_events": [
        {"direction": "down", "delta": 4, "timestamp": "2026-02-25T08:30:00Z"},
    ],
    "alert_count":  6,
    "error_count": 14,
}


async def main() -> None:
    kratos = KratosOrchestrator()

    print("=" * 64)
    print("Kratos Infra Smoke Test")
    print("=" * 64)

    report = await kratos.run(
        user_query="Why did the Spark ETL job fail with out-of-memory errors?",
        trigger="failure",
        infra_fingerprint=INFRA_FINGERPRINT,
    )

    ip = report.issue_profile

    # ── Basic report fields ──────────────────────────────────────────────────
    print(f"\ndominant_problem_type : {ip.dominant_problem_type}")
    print(f"overall_health_score  : {ip.overall_health_score}")
    print(f"overall_confidence    : {ip.overall_confidence:.2f}")
    print(f"agents_invoked        : {ip.agents_invoked}")

    # ── Infra analysis ───────────────────────────────────────────────────────
    ia = ip.infra_analysis
    if ia:
        print(f"\n[Infra Analyzer]")
        print(f"  health_score  : {ia.health_score}")
        print(f"  problem_type  : {ia.problem_type}")
        print(f"  findings      : {len(ia.findings)}")
        for f in ia.findings[:3]:
            print(f"    [{f.severity}] {f.description[:72]}")
        md = ia.metadata or {}
        print(f"  severity label: {md.get('severity', '?')}")
        print(f"  health label  : {md.get('health_label', '?')}")
    else:
        print("\n[Infra Analyzer] NOT invoked (check trigger / infra_fingerprint)")

    # ── Cross-agent correlations ─────────────────────────────────────────────
    print(f"\n[Correlations] count={len(ip.correlations)}")
    for c in ip.correlations:
        print(f"  [{c.severity}] conf={c.confidence:.2f}  {c.pattern[:70]}")

    # ── Recommendations ──────────────────────────────────────────────────────
    print(f"\n[Recommendations] count={len(report.recommendations)}")
    for rec in report.recommendations[:3]:
        print(f"  [{rec.priority}] {rec.action[:72]}")

    # ── Assertions (basic smoke checks) ─────────────────────────────────────
    assert ip.infra_analysis is not None, "infra_analysis should be populated"
    assert ip.infra_analysis.health_score < 100, "cluster should not be healthy"
    print("\n✓ All smoke-test assertions passed")


if __name__ == "__main__":
    asyncio.run(main())
