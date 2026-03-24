"""
src/infrastructure

Pluggable infrastructure adapter layer.

Drop in a new adapter to support a different bank, legacy system,
or data source without touching any core agent code.

Usage::

    from src.infrastructure.base_adapter import get_adapter, register_adapter, list_adapters

    # KratosDemoAdapter is auto-registered on import of demo_api or demo_rca_service
    adapter = get_adapter("kratos_demo")
    scenarios = await adapter.list_scenarios()
"""

from src.infrastructure.base_adapter import (  # noqa: F401
    InfrastructureAdapter,
    register_adapter,
    get_adapter,
    list_adapters,
)
