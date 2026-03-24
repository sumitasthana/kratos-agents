"""
causelink/agents/base.py

CauseLinkAgent — abstract base class for all pipeline agents.

All Phase D agents:
  - receive InvestigationState
  - append-only mutate it (never truncate/replace existing lists)
  - append an AuditTraceEntry for every meaningful action
  - return the mutated state
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from causelink.state.investigation import AuditTraceEntry, InvestigationState

logger = logging.getLogger(__name__)


class CauseLinkAgent(ABC):
    """Base class for all CauseLink pipeline agents."""

    # Subclasses MUST override this with a stable one-word string.
    AGENT_TYPE: str = "base"

    @abstractmethod
    def run(self, state: InvestigationState) -> InvestigationState:
        """
        Execute this agent's pipeline step.

        Receives the full InvestigationState and returns it after appending
        only this agent's contributions.  Must not replace or truncate
        any existing list in the state.
        """
        ...

    # ── Helpers available to all subclasses ──────────────────────────────────

    def _audit(
        self,
        state: InvestigationState,
        action: str,
        inputs_summary: Optional[Dict[str, Any]] = None,
        outputs_summary: Optional[Dict[str, Any]] = None,
        ontology_paths_accessed: Optional[List[str]] = None,
        evidence_ids_accessed: Optional[List[str]] = None,
        decision: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Append a standardised audit trace entry."""
        state.append_audit(
            AuditTraceEntry(
                agent_type=self.AGENT_TYPE,
                action=action,
                inputs_summary=inputs_summary or {},
                outputs_summary=outputs_summary or {},
                ontology_paths_accessed=ontology_paths_accessed or [],
                evidence_ids_accessed=evidence_ids_accessed or [],
                decision=decision,
                notes=notes,
            )
        )

    def _log(self, msg: str, *args: Any) -> None:
        logger.info(f"[{self.AGENT_TYPE.upper()}] {msg}", *args)

    def _warn(self, msg: str, *args: Any) -> None:
        logger.warning(f"[{self.AGENT_TYPE.upper()}] {msg}", *args)
