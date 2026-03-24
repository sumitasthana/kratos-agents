"""
src/observability/exporters.py

Convenience setup function that wires OTLP exporter + Prometheus HTTP
exporter from environment variables.  Called once at application startup.

Environment variables::

    OTLP_ENDPOINT        gRPC endpoint for OTel collector (default: disabled)
    KRATOS_ENV           deployment.environment resource attribute (default: demo)
    OTEL_CONSOLE_EXPORT  set to "1" to print spans to stdout (default: off)
    PROMETHEUS_PORT      port for standalone Prometheus HTTP server (default: disabled)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def setup_exporters() -> None:
    """Initialise OTel tracer and optionally start a Prometheus HTTP server.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    from .tracer import init_tracer, _provider  # noqa: PLC0415

    if _provider is None:
        init_tracer()
        logger.info("observability: OTel tracer initialised")
    else:
        logger.debug("observability: OTel tracer already initialised, skipping")

    prometheus_port = os.getenv("PROMETHEUS_PORT", "")
    if prometheus_port:
        try:
            from prometheus_client import start_http_server  # noqa: PLC0415
            from .metrics import REGISTRY  # noqa: PLC0415
            port = int(prometheus_port)
            start_http_server(port, registry=REGISTRY)
            logger.info("observability: Prometheus HTTP server started on port %d", port)
        except Exception as exc:
            logger.warning(
                "observability: failed to start Prometheus HTTP server: %s", exc
            )
