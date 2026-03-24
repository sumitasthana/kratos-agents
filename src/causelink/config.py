"""
causelink/config.py

Centralised configuration for the CauseLink RCA engine.

All settings are read from environment variables at import time.
Sensitive values (passwords, tokens) are NEVER logged or exposed in repr().

Usage:
    from causelink.config import settings

    uri = settings.neo4j_uri
    if settings.mock_mode:
        adapter = MockAdapter()

Environment variables (see .env.example for documentation):
    NEO4J_URI                  bolt://localhost:7687
    NEO4J_USER                 neo4j
    NEO4J_PASSWORD             <required in production; empty = mock mode>
    CAUSELINK_MOCK_MODE        false
    CAUSELINK_LOG_LEVEL        INFO
    CAUSELINK_LOG_FORMAT       json
    CAUSELINK_MAX_HOPS         3
    CAUSELINK_CONFIDENCE_THRESHOLD  0.80
    CAUSELINK_API_HOST         0.0.0.0
    CAUSELINK_API_PORT         8001
    CAUSELINK_REQUEST_TIMEOUT  30
    CAUSELINK_NEO4J_TIMEOUT    10
    CAUSELINK_MAX_GRAPH_NODES  500
    CAUSELINK_AUDIT_REDACT_PII true
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel for missing required values
# ---------------------------------------------------------------------------
_UNSET = object()


def _env(key: str, default=_UNSET, cast=str):
    """Read an environment variable, cast it, and raise clearly if missing."""
    raw = os.environ.get(key)
    if raw is None:
        if default is _UNSET:
            raise EnvironmentError(
                f"Required environment variable '{key}' is not set. "
                f"Copy .env.example to .env and populate it."
            )
        return default
    if cast is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    try:
        return cast(raw.strip())
    except (ValueError, TypeError) as exc:
        raise EnvironmentError(
            f"Environment variable '{key}' has invalid value {raw!r}: {exc}"
        ) from exc


class CauseLinkSettings:
    """
    Immutable configuration snapshot for the CauseLink engine.

    Constructed once at startup; re-read by calling settings.reload().
    Sensitive fields are excluded from __repr__ and logging.
    """

    # -- Neo4j connection ----------------------------------------------------
    neo4j_uri: str
    neo4j_user: str
    _neo4j_password: str  # never exposed in repr

    # -- Operational flags ---------------------------------------------------
    mock_mode: bool
    log_level: str
    log_format: Literal["json", "text"]

    # -- Investigation parameters -------------------------------------------
    max_hops: int
    confidence_threshold: float
    max_graph_nodes: int
    audit_redact_pii: bool

    # -- API / network -------------------------------------------------------
    api_host: str
    api_port: int
    request_timeout: int   # seconds — for evidence connectors
    neo4j_timeout: int     # seconds — for Neo4j queries

    def __init__(self) -> None:
        self.neo4j_uri = _env("NEO4J_URI", default="bolt://localhost:7687")
        self.neo4j_user = _env("NEO4J_USER", default="neo4j")
        self._neo4j_password = _env("NEO4J_PASSWORD", default="")

        self.mock_mode = _env("CAUSELINK_MOCK_MODE", default=False, cast=bool)
        self.log_level = _env("CAUSELINK_LOG_LEVEL", default="INFO").upper()
        _log_format = _env("CAUSELINK_LOG_FORMAT", default="json").lower()
        if _log_format not in ("json", "text"):
            raise EnvironmentError(
                f"CAUSELINK_LOG_FORMAT must be 'json' or 'text', got {_log_format!r}"
            )
        self.log_format = _log_format  # type: ignore[assignment]

        self.max_hops = _env("CAUSELINK_MAX_HOPS", default=3, cast=int)
        if not 1 <= self.max_hops <= 6:
            raise EnvironmentError(
                f"CAUSELINK_MAX_HOPS must be 1-6, got {self.max_hops}"
            )

        self.confidence_threshold = _env(
            "CAUSELINK_CONFIDENCE_THRESHOLD", default=0.80, cast=float
        )
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise EnvironmentError(
                f"CAUSELINK_CONFIDENCE_THRESHOLD must be 0.0-1.0, "
                f"got {self.confidence_threshold}"
            )

        self.max_graph_nodes = _env("CAUSELINK_MAX_GRAPH_NODES", default=500, cast=int)
        self.audit_redact_pii = _env("CAUSELINK_AUDIT_REDACT_PII", default=True, cast=bool)

        self.api_host = _env("CAUSELINK_API_HOST", default="0.0.0.0")
        self.api_port = _env("CAUSELINK_API_PORT", default=8001, cast=int)
        self.request_timeout = _env("CAUSELINK_REQUEST_TIMEOUT", default=30, cast=int)
        self.neo4j_timeout = _env("CAUSELINK_NEO4J_TIMEOUT", default=10, cast=int)

        # Emit startup information (safe fields only)
        if not self.mock_mode and not self._neo4j_password:
            logger.warning(
                "NEO4J_PASSWORD is not set and CAUSELINK_MOCK_MODE=false. "
                "Neo4j connections will fail. Set CAUSELINK_MOCK_MODE=true "
                "for local/demo usage without a live Neo4j instance."
            )

    @property
    def neo4j_password(self) -> str:
        """Return Neo4j password. Never log this value."""
        return self._neo4j_password

    def __repr__(self) -> str:
        return (
            f"CauseLinkSettings("
            f"neo4j_uri={self.neo4j_uri!r}, "
            f"neo4j_user={self.neo4j_user!r}, "
            f"neo4j_password=<redacted>, "
            f"mock_mode={self.mock_mode}, "
            f"log_level={self.log_level!r}, "
            f"log_format={self.log_format!r}, "
            f"max_hops={self.max_hops}, "
            f"confidence_threshold={self.confidence_threshold}, "
            f"api_port={self.api_port}"
            f")"
        )

    def startup_summary(self) -> dict:
        """Return a loggable dict of safe (non-sensitive) settings."""
        return {
            "neo4j_uri": self.neo4j_uri,
            "neo4j_user": self.neo4j_user,
            "mock_mode": self.mock_mode,
            "log_level": self.log_level,
            "log_format": self.log_format,
            "max_hops": self.max_hops,
            "confidence_threshold": self.confidence_threshold,
            "max_graph_nodes": self.max_graph_nodes,
            "audit_redact_pii": self.audit_redact_pii,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "request_timeout": self.request_timeout,
            "neo4j_timeout": self.neo4j_timeout,
        }


@lru_cache(maxsize=1)
def _load_settings() -> CauseLinkSettings:
    return CauseLinkSettings()


def get_settings() -> CauseLinkSettings:
    """Return the singleton settings instance (cached after first call)."""
    return _load_settings()


# Module-level convenience alias used throughout the codebase.
# Import as:  from causelink.config import settings
settings = get_settings()
