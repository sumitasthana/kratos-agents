"""
src/demo/__init__.py

Demo layer for the Kratos Intelligence Platform.

Provides 3 pre-built RCA scenarios (deposit_aggregation_failure,
trust_irr_misclassification, wire_mt202_drop) that run fully in-memory
without Neo4j or OpenAI dependencies.

Public API::

    from src.demo import ScenarioRegistry
    registry = ScenarioRegistry()
    scenarios = registry.list_scenarios()
"""
