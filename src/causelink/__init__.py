"""
causelink — Neo4j ontology-native, evidence-only RCA engine for Kratos.

Phase A  Ontology Adapter + CanonGraph       (causelink.ontology)
Phase B  Investigation State Contract         (causelink.state)
Phase C  Evidence Object + Service stubs      (causelink.evidence)
Phase D  Agent Suite                          (causelink.agents)
Phase E  Hypothesis Pattern Library           (causelink.patterns)
Phase F  Causal Engine + Scoring              (causelink.agents.causal_engine / ranker)
Phase G  Platform Packaging + FastAPI         (causelink_api.py)
"""

from causelink.ontology import (
    NODE_LABELS,
    RELATIONSHIP_TYPES,
    ANCHOR_LABELS,
    OntologySchemaSnapshot,
    CanonNode,
    CanonEdge,
    OntologyPath,
    CanonGraph,
    Neo4jOntologyAdapter,
    OntologyAdapterError,
    OntologyGap,
)
from causelink.state import (
    HypothesisStatus,
    CausalEdgeStatus,
    InvestigationStatus,
    InvestigationAnchor,
    InvestigationInput,
    Hypothesis,
    CausalEdge,
    RootCauseCandidate,
    MissingEvidence,
    AuditTraceEntry,
    InvestigationState,
)
from causelink.evidence import (
    EvidenceType,
    EvidenceReliabilityTier,
    EvidenceObject,
    EvidenceSearchParams,
    EvidenceService,
    NullEvidenceService,
)
from causelink.validation import ValidationGate, ValidationResult
from causelink.agents import (
    CauseLinkAgent,
    OntologyContextAgent,
    EvidenceCollectorAgent,
    HypothesisGeneratorAgent,
    CausalEngineAgent,
    RankerAgent,
)
from causelink.patterns import (
    HypothesisPattern,
    HypothesisPatternLibrary,
    PatternMatchResult,
    BUILT_IN_PATTERNS,
)

__all__ = [
    # Ontology
    "NODE_LABELS",
    "RELATIONSHIP_TYPES",
    "ANCHOR_LABELS",
    "OntologySchemaSnapshot",
    "CanonNode",
    "CanonEdge",
    "OntologyPath",
    "CanonGraph",
    "Neo4jOntologyAdapter",
    "OntologyAdapterError",
    "OntologyGap",
    # State
    "HypothesisStatus",
    "CausalEdgeStatus",
    "InvestigationStatus",
    "InvestigationAnchor",
    "InvestigationInput",
    "Hypothesis",
    "CausalEdge",
    "RootCauseCandidate",
    "MissingEvidence",
    "AuditTraceEntry",
    "InvestigationState",
    # Evidence
    "EvidenceType",
    "EvidenceReliabilityTier",
    "EvidenceObject",
    "EvidenceSearchParams",
    "EvidenceService",
    "NullEvidenceService",
    # Validation
    "ValidationGate",
    "ValidationResult",
    # Agents (Phase D–F)
    "CauseLinkAgent",
    "OntologyContextAgent",
    "EvidenceCollectorAgent",
    "HypothesisGeneratorAgent",
    "CausalEngineAgent",
    "RankerAgent",
    # Patterns (Phase E)
    "HypothesisPattern",
    "HypothesisPatternLibrary",
    "PatternMatchResult",
    "BUILT_IN_PATTERNS",
]
