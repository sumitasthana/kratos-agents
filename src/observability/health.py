"""
src/observability/health.py

Deep health check covering all platform APIs, metric collector state,
and investigation queue depths.

Returned shape mirrors the /obs/health endpoint response.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from .logger import get_logger
from .metrics import M, REGISTRY

log = get_logger(__name__)

# Ports used by each platform component
_COMPONENT_URLS = {
    "demo_api":       "http://127.0.0.1:8002/demo/health",
    "causelink_api":  "http://127.0.0.1:8001/health",
    "kratos_data_api": "http://127.0.0.1:8000/health",
}


async def deep_health_check() -> Dict[str, Any]:
    """Run async health checks against all platform components.

    Returns a dict of per-component status dicts plus an overall status.
    Never raises — all errors are captured as ``{"status": "down", "error": ...}``.
    """
    checks: Dict[str, Any] = {}

    try:
        import httpx  # noqa: PLC0415
        for name, url in _COMPONENT_URLS.items():
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(url)
                    latency_ms = round(resp.elapsed.total_seconds() * 1000)
                    checks[name] = {
                        "status":     "ok" if resp.status_code == 200 else "degraded",
                        "latency_ms": latency_ms,
                        "http_status": resp.status_code,
                    }
            except Exception as exc:
                checks[name] = {"status": "down", "error": str(exc)}
    except ImportError:
        for name in _COMPONENT_URLS:
            checks[name] = {"status": "unknown", "error": "httpx not installed"}

    # Metrics subsystem is always local
    try:
        collector_count = len(list(REGISTRY._names_to_collectors.keys()))
        in_flight = M.investigations_in_flight._value.get()
        checks["metrics"] = {
            "status":                 "ok",
            "registry_collectors":    collector_count,
            "investigations_in_flight": int(in_flight),
        }
    except Exception as exc:
        checks["metrics"] = {"status": "degraded", "error": str(exc)}

    overall = (
        "ok"
        if all(v.get("status") == "ok" for v in checks.values())
        else "degraded"
    )

    return {
        "overall":   overall,
        "checks":    checks,
        "timestamp": time.time(),
    }
