"""
src/infrastructure/base_adapter.py

InfrastructureAdapter — abstract contract that any pluggable environment
must implement.  The core RCA pipeline only talks to this interface.

Never import from a concrete adapter inside agent code.  Always inject the
adapter as a parameter or use get_adapter(adapter_id).

Extending the platform with a new environment (bank, staging cluster, etc.)
requires ONLY:
  1. Creating a new file in src/infrastructure/adapters/
  2. Subclassing InfrastructureAdapter
  3. Calling register_adapter(YourAdapter()) at the bottom of the file
  4. Importing the file somewhere before startup (demo_api.py startup hook works)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.demo.loaders.scenario_loader import ScenarioPack
    from src.causelink.ontology.models import CanonGraph


class InfrastructureAdapter(ABC):
    """
    Contract that any pluggable environment must implement.
    The core RCA pipeline only talks to this interface.
    Never import from concrete adapters inside agent code.
    """

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier: 'kratos_demo', 'bank_xyz_prod', 'test_mock'"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human label shown in the UI environment selector."""

    @property
    @abstractmethod
    def environment(self) -> str:
        """'demo' | 'staging' | 'production' | 'test'"""

    # ── Scenario discovery ────────────────────────────────────────────────

    @abstractmethod
    async def list_scenarios(self) -> list[dict]:
        """Return available scenario metadata for the scenario selector."""

    @abstractmethod
    async def load_scenario_pack(self, scenario_id: str) -> "ScenarioPack":
        """Load all artifacts for a scenario: incident, controls, job_run, logs."""

    # ── Ontology ─────────────────────────────────────────────────────────

    @abstractmethod
    async def get_canon_graph(self, scenario_id: str) -> "CanonGraph":
        """
        Return the CanonGraph for this scenario.
        Demo: returns in-memory hardcoded graph.
        Production: queries Neo4j for the anchor node's subgraph.
        """

    # ── Evidence ──────────────────────────────────────────────────────────

    @abstractmethod
    async def fetch_logs(
        self, scenario_id: str, job_id: str
    ) -> list[dict]:
        """
        Return raw log lines for the job.
        Demo: reads from scenarios/*/logs/*.log
        Production: queries Splunk / CloudWatch / Datadog Logs API
        """

    @abstractmethod
    async def fetch_account_records(
        self, scenario_id: str, filters: dict
    ) -> list[dict]:
        """
        Return account records relevant to the scenario.
        Demo: reads from kratos_data CSV filtered by orc_code / balance
        Production: queries the live PostgreSQL kratos-data database
        """

    @abstractmethod
    async def fetch_job_run(
        self, scenario_id: str, job_id: str
    ) -> dict:
        """
        Return job execution metadata.
        Demo: reads job_run.json
        Production: queries job scheduler API (Airflow / Control-M / JCL spool)
        """

    # ── Code artifact resolution ──────────────────────────────────────────

    @abstractmethod
    async def resolve_artifact(
        self, artifact_path: str, line_ref: str | None = None
    ) -> dict:
        """
        Resolve a code artifact reference to its content.
        Demo: reads from operational_systems/ directory
        Production: calls GitHub API / BitBucket / internal SCM
        Returns: { path, content_snippet, language, defect_annotation }
        """

    # ── LLM provider ─────────────────────────────────────────────────────

    @abstractmethod
    def get_llm_config(self) -> dict:
        """
        Return LLM configuration for this environment.
        {
          "provider": "anthropic",
          "model": "claude-sonnet-4-6",
          "max_tokens": 1024,
          "streaming": True,
          "temperature": 0,
        }
        Demo may set max_tokens lower for faster streaming.
        Production may route to a different model or provider.
        """


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, InfrastructureAdapter] = {}


def register_adapter(adapter: InfrastructureAdapter) -> None:
    """Register an adapter so it can be retrieved by adapter_id."""
    _REGISTRY[adapter.adapter_id] = adapter


def get_adapter(adapter_id: str) -> InfrastructureAdapter:
    """
    Return the registered adapter for adapter_id.

    Raises:
        KeyError: if no adapter has been registered with that id.
    """
    if adapter_id not in _REGISTRY:
        raise KeyError(
            f"No adapter registered for '{adapter_id}'. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[adapter_id]


def list_adapters() -> list[dict]:
    """Return metadata for all registered adapters (for the /demo/adapters endpoint)."""
    return [
        {
            "adapter_id": a.adapter_id,
            "display_name": a.display_name,
            "environment": a.environment,
        }
        for a in _REGISTRY.values()
    ]
