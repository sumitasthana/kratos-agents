"""
causelink.agents — Phase D: Ontology-bounded CauseLink agent suite.

Pipeline order (each agent mutates InvestigationState in place):

    1. OntologyContextAgent   — loads bounded CanonGraph from Neo4j
    2. EvidenceCollectorAgent — collects EvidenceObjects scoped to CanonGraph
    3. HypothesisGeneratorAgent — pattern-first hypothesis generation
    4. CausalEngineAgent      — builds validated causal DAG
    5. RankerAgent             — scores candidates, sets root_cause_final
"""

from .base import CauseLinkAgent
from .ontology_context import OntologyContextAgent
from .evidence_collector import EvidenceCollectorAgent
from .hypothesis_generator import HypothesisGeneratorAgent
from .causal_engine import CausalEngineAgent
from .ranker import RankerAgent

__all__ = [
    "CauseLinkAgent",
    "OntologyContextAgent",
    "EvidenceCollectorAgent",
    "HypothesisGeneratorAgent",
    "CausalEngineAgent",
    "RankerAgent",
]
