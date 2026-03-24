"""causelink/rca/session.py

JobInvestigationSession — shared session state for chat and dashboard.
SessionStore — in-memory registry keyed by session_id and job_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobInvestigationSession(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_id: str
    job_id: str
    anchor_type: str
    anchor_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"  # "active" | "completed" | "error"
    investigation_id: Optional[str] = None
    dashboard_url: str = ""
    latest_summary: Optional[Dict[str, Any]] = None
    latest_incident_card: Optional[Dict[str, Any]] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class SessionStore:
    """In-memory session registry.

    Not thread-safe for concurrent writes. Replace with a distributed cache
    (Redis, Postgres) for multi-process or high-concurrency deployments.
    """

    def __init__(self) -> None:
        self._by_id: Dict[str, JobInvestigationSession] = {}
        self._by_job: Dict[str, str] = {}  # job_id -> session_id

    def create(
        self,
        scenario_id: str,
        job_id: str,
        anchor_type: str,
        anchor_id: str,
    ) -> JobInvestigationSession:
        session = JobInvestigationSession(
            scenario_id=scenario_id,
            job_id=job_id,
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            dashboard_url=f"#jobs/{job_id}/dashboard",
        )
        self._by_id[session.session_id] = session
        self._by_job[job_id] = session.session_id
        return session

    def get(self, session_id: str) -> Optional[JobInvestigationSession]:
        return self._by_id.get(session_id)

    def get_by_job(self, job_id: str) -> Optional[JobInvestigationSession]:
        sid = self._by_job.get(job_id)
        if sid:
            return self._by_id.get(sid)
        return None

    def update(self, session: JobInvestigationSession) -> None:
        session.updated_at = datetime.utcnow()
        self._by_id[session.session_id] = session
        self._by_job[session.job_id] = session.session_id

    def all_sessions(self) -> List[JobInvestigationSession]:
        return list(self._by_id.values())

    def clear(self) -> None:
        """Remove all sessions. Useful for test isolation."""
        self._by_id.clear()
        self._by_job.clear()


# Module-level singleton shared by all API routes
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
