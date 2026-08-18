"""Persistence-free orchestration for Phase 5 semantic compilation."""

from packages.domain.compilation.assembly import assemble_canonical_candidates
from packages.domain.compilation.confidence_aggregation import aggregate_fact_confidences
from packages.domain.compilation.conflict_detection import detect_conflicts
from packages.domain.compilation.contracts import (
    CanonicalSnapshot,
    CompilationInput,
    CompilationResult,
)
from packages.domain.compilation.entity_resolution import resolve_entity_identities
from packages.domain.compilation.evidence_association import (
    associate_property_evidence,
    associate_relationship_evidence,
)
from packages.domain.compilation.normalization import normalize_proposal_claims
from packages.domain.compilation.relationship_resolution import (
    compile_relationship_candidates,
)
from packages.domain.compilation.schema_validation import validate_proposal_batch
from packages.domain.compilation.typed_properties import (
    compile_typed_property_candidates,
)
from packages.domain.proposals import ExtractionResult


def compile(
    extraction_result: ExtractionResult,
    canonical_snapshot: CanonicalSnapshot,
) -> CompilationResult:
    """Compile one extraction batch into immutable canonical model candidates."""

    compilation_input = CompilationInput(
        extraction_result=extraction_result,
        canonical_snapshot=canonical_snapshot,
    )

    batch_findings = validate_proposal_batch(compilation_input)
    normalization_result = normalize_proposal_claims(
        compilation_input,
        batch_findings=batch_findings,
    )
    property_result = compile_typed_property_candidates(normalization_result)
    resolution_result = resolve_entity_identities(compilation_input, property_result)

    property_evidence_result = associate_property_evidence(
        compilation_input,
        normalization_result,
        resolution_result,
    )
    property_confidence_result = aggregate_fact_confidences(
        compilation_input,
        property_evidence_result,
    )

    relationship_result = compile_relationship_candidates(
        compilation_input,
        resolution_result,
    )
    relationship_evidence_result = associate_relationship_evidence(
        compilation_input,
        relationship_result,
    )
    relationship_confidence_result = aggregate_fact_confidences(
        compilation_input,
        relationship_evidence_result,
    )

    conflict_result = detect_conflicts(
        compilation_input,
        normalization_result,
        resolution_result,
    )
    return assemble_canonical_candidates(
        compilation_input,
        normalization_result,
        resolution_result,
        relationship_result,
        property_evidence_result,
        relationship_evidence_result,
        property_confidence_result,
        relationship_confidence_result,
        conflict_result,
    )


__all__ = ["compile"]
