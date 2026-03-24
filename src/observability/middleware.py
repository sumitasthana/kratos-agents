"""
src/observability/middleware.py

FastAPI middleware for automatic request tracing and RED metrics.

Usage::

    from src.observability.middleware import KratosObservabilityMiddleware

    app.add_middleware(KratosObservabilityMiddleware)
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .tracer import get_tracer, SpanAttr
from .metrics import M
from .logger import get_logger

log = get_logger(__name__)

_SKIP_PATHS = frozenset({"/obs/metrics", "/obs/logs/stream", "/obs/health"})


class KratosObservabilityMiddleware(BaseHTTPMiddleware):
    """Wraps every request in an OTel span and records RED metrics.

    Skipped for the Prometheus scrape endpoint and SSE log stream to
    avoid self-referential noise.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        if path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        span_name = f"HTTP {method} {path}"

        with get_tracer().start_as_current_span(span_name) as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.route", path)

            try:
                response = await call_next(request)
                elapsed_ms = (time.perf_counter() - start) * 1000
                status_code = str(response.status_code)

                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute(SpanAttr.PHASE_DURATION_MS, round(elapsed_ms))

                M.api_request_duration.labels(
                    method=method,
                    endpoint=path,
                    status_code=status_code,
                ).observe(elapsed_ms)

                return response

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                M.api_errors.labels(
                    method=method,
                    endpoint=path,
                    error_type=type(exc).__name__,
                ).inc()
                span.record_exception(exc)
                raise
