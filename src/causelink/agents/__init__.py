"""
causelink.agents — Phase D: Ontology-bounded CauseLink agent suite.

Pipeline order (each agent mutates InvestigationState in place):

    1. OntologyContextAgent   — loads bounded CanonGraph from Neo4j
    2. EvidenceCollectorAgent — collects EvidenceObjects scoped to CanonGraph
    3. HypothesisGeneratorAgent — pattern-first hypothesis generation
    4. CausalEngineAgent      — builds validated causal DAG
    5. RankerAgent             — scores candidates, sets root_cause_final

Skills layer (Claude Skills architecture — behavioral contracts in Markdown):

    SkillLoader               — reads skills/*/SKILL.md at agent init
    load_skill(name)          — convenience singleton accessor
    master_directive()        — returns CLAUDE.md content

    Registered skills:
      rca-orchestrator        → skills/rca-orchestrator/SKILL.md
      intake-agent            → skills/intake-agent/SKILL.md
      log-analyst             → skills/log-analyst/SKILL.md
      hypothesis-agent        → skills/hypothesis-agent/SKILL.md
      causal-edge-agent       → skills/causal-edge-agent/SKILL.md
      confidence-agent        → skills/confidence-agent/SKILL.md
      remediation-agent       → skills/remediation-agent/SKILL.md
      conversation-interface  → skills/conversation-interface/SKILL.md
"""

from .base import CauseLinkAgent
from .ontology_context import OntologyContextAgent
from .evidence_collector import EvidenceCollectorAgent
from .hypothesis_generator import HypothesisGeneratorAgent
from .causal_engine import CausalEngineAgent
from .ranker import RankerAgent
from .skill_loader import SkillLoader, get_loader, load_skill, master_directive

__all__ = [
    "CauseLinkAgent",
    "OntologyContextAgent",
    "EvidenceCollectorAgent",
    "HypothesisGeneratorAgent",
    "CausalEngineAgent",
    "RankerAgent",
    # Skills layer
    "SkillLoader",
    "get_loader",
    "load_skill",
    "master_directive",
]
