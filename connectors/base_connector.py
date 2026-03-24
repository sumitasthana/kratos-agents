"""
connectors/base_connector.py
Abstract connector interface for all Kratos external data source adapters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import AsyncIterator

from core.models import IncidentContext, LineageGraph, LogChunk


class BaseConnector(ABC):
    """
    Abstract base for all Kratos external data source adapters.

    Connectors bridge raw infrastructure data (Spark event logs, Airflow
    task logs, banking API responses) into typed Kratos models that the
    agent pipeline consumes.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish the connection to the upstream data source."""
        ...

    @abstractmethod
    async def fetch_incident(self, incident_id: str) -> IncidentContext:
        """
        Fetch full incident context for the given incident_id.

        Args:
            incident_id: Unique identifier of the incident to retrieve.

        Returns:
            Populated IncidentContext ready for the RCA pipeline.
        """
        ...

    @abstractmethod
    async def stream_logs(
        self, incident_id: str
    ) -> AsyncIterator[LogChunk]:
        """
        Stream log records for the given incident as an async iterator.

        Args:
            incident_id: Incident to stream logs for.

        Yields:
            LogChunk instances in chronological order.
        """
        ...

    @abstractmethod
    async def fetch_lineage(self, job_id: str) -> LineageGraph:
        """
        Fetch the data-lineage graph for the given pipeline job.

        Args:
            job_id: Pipeline job identifier.

        Returns:
            LineageGraph with nodes and directed edges.
        """
        ...

    async def close(self) -> None:
        """Release resources held by this connector. Override as needed."""

    async def __aenter__(self) -> BaseConnector:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val:  BaseException | None,
        exc_tb:   TracebackType | None,
    ) -> None:
        await self.close()
