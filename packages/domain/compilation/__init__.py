"""Pure semantic compilation contracts and validation functions."""

from packages.domain.compilation.assembly import assemble_canonical_candidates
from packages.domain.compilation.compiler import compile
from packages.domain.compilation.confidence_aggregation import (
    FactConfidenceAggregationResult,
    aggregate_fact_confidences,
)
from packages.domain.compilation.conflict_detection import (
    ConflictDetectionResult,
    detect_conflicts,
    detect_identity_conflicts,
    detect_property_conflicts,
    detect_relationship_conflicts,
)
from packages.domain.compilation.contracts import (
    CanonicalSnapshot,
    CompilationInput,
    CompilationResult,
    FactConfidence,
    TypedPropertyFact,
)
from packages.domain.compilation.entity_resolution import (
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
    resolve_entity_identities,
)
from packages.domain.compilation.evidence_association import (
    EvidenceAssociationResult,
    associate_property_evidence,
    associate_relationship_evidence,
    is_evidence_current_for_input,
)
from packages.domain.compilation.normalization import (
    NormalizationResult,
    NormalizationStatus,
    NormalizedAttributeClaim,
    normalize_proposal_claims,
)
from packages.domain.compilation.relationship_resolution import (
    RelationshipCompilationResult,
    RelationshipEvidenceSource,
    compile_relationship_candidates,
)
from packages.domain.compilation.review import (
    CorrectionCandidate,
    ReviewDecisionResult,
    apply_review_decision,
)
from packages.domain.compilation.schema_validation import validate_proposal_batch
from packages.domain.compilation.typed_properties import (
    TypedProperties,
    TypedPropertyCandidate,
    TypedPropertyCompilationResult,
    compile_typed_property_candidates,
)

__all__ = [
    "CanonicalSnapshot",
    "CompilationInput",
    "CompilationResult",
    "ConflictDetectionResult",
    "CorrectionCandidate",
    "EntityResolution",
    "EntityResolutionResult",
    "EntityResolutionStatus",
    "EvidenceAssociationResult",
    "FactConfidence",
    "FactConfidenceAggregationResult",
    "NormalizationResult",
    "NormalizationStatus",
    "NormalizedAttributeClaim",
    "RelationshipCompilationResult",
    "RelationshipEvidenceSource",
    "ReviewDecisionResult",
    "TypedProperties",
    "TypedPropertyFact",
    "TypedPropertyCandidate",
    "TypedPropertyCompilationResult",
    "aggregate_fact_confidences",
    "apply_review_decision",
    "assemble_canonical_candidates",
    "associate_property_evidence",
    "associate_relationship_evidence",
    "compile",
    "compile_relationship_candidates",
    "detect_conflicts",
    "detect_identity_conflicts",
    "detect_property_conflicts",
    "detect_relationship_conflicts",
    "compile_typed_property_candidates",
    "is_evidence_current_for_input",
    "normalize_proposal_claims",
    "resolve_entity_identities",
    "validate_proposal_batch",
]
