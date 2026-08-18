"""Tests for Phase 5 fact-level confidence aggregation."""

from uuid import UUID

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EvidenceAssociationResult,
    aggregate_fact_confidences,
)
from packages.domain.enums import ExtractionMethod
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation
from packages.domain.proposals import AttributeProposal, ExtractionResult
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ENTITY_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
RELATIONSHIP_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _evidence(*, confidence: float = 0.9, line: int = 1) -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum="a" * 64,
        source_location=SourceLocation(line_start=line),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=confidence,
    )


def _input(*records: Evidence) -> CompilationInput:
    proposal = AttributeProposal(
        subject_proposal_id=ENTITY_ID,
        field_path="properties.hostname",
        proposed_value="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=list(records),
    )
    return CompilationInput(
        extraction_result=ExtractionResult(
            artifact_id=ARTIFACT_ID,
            artifact_version_id=ARTIFACT_VERSION_ID,
            artifact_version_number=1,
            artifact_kind="cisco_ios_running_config",
            artifact_checksum="a" * 64,
            scope=SCOPE,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_name="test-parser",
            extractor_version="1",
            attribute_proposals=[proposal],
        ),
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def test_property_confidence_uses_shared_policy_and_derived_output() -> None:
    evidence = _evidence(confidence=0.9)
    output = aggregate_fact_confidences(
        _input(evidence),
        EvidenceAssociationResult(
            fact_attributions=(
                FactAttribution(
                    evidence_id=evidence.id,
                    fact_kind="property",
                    entity_id=ENTITY_ID,
                    property_path="properties.hostname",
                ),
            )
        ),
    )

    fact_confidence = output.fact_confidences[0]
    assert output.findings == ()
    assert fact_confidence.confidence.score == 0.855
    assert fact_confidence.confidence.level.value == "high"
    assert fact_confidence.confidence.method == "aggregate"
    assert fact_confidence.confidence.rationale == "agreeing evidence increased confidence"
    assert fact_confidence.confidence.auto_commit_eligible


def test_all_supporting_evidence_aggregates_to_one_fact_confidence() -> None:
    first = _evidence(confidence=0.9, line=1)
    second = _evidence(confidence=0.8, line=2)
    output = aggregate_fact_confidences(
        _input(first, second),
        EvidenceAssociationResult(
            fact_attributions=(
                FactAttribution(
                    evidence_id=first.id,
                    fact_kind="property",
                    entity_id=ENTITY_ID,
                    property_path="properties.hostname",
                ),
                FactAttribution(
                    evidence_id=second.id,
                    fact_kind="property",
                    entity_id=ENTITY_ID,
                    property_path="properties.hostname",
                ),
            )
        ),
    )

    assert len(output.fact_confidences) == 1
    assert (
        output.fact_confidences[0].confidence.rationale == "agreeing evidence increased confidence"
    )


def test_missing_attributed_evidence_blocks_confidence_for_only_that_fact() -> None:
    evidence = _evidence()
    output = aggregate_fact_confidences(
        _input(evidence),
        EvidenceAssociationResult(
            fact_attributions=(
                FactAttribution(
                    evidence_id=UUID(int=99),
                    fact_kind="property",
                    entity_id=ENTITY_ID,
                    property_path="properties.hostname",
                ),
            )
        ),
    )

    assert output.fact_confidences == ()
    assert [finding.code for finding in output.findings] == ["missing_attributed_evidence"]


def test_relationship_fact_uses_the_same_policy_when_it_is_available() -> None:
    evidence = _evidence()
    output = aggregate_fact_confidences(
        _input(evidence),
        EvidenceAssociationResult(
            fact_attributions=(
                FactAttribution(
                    evidence_id=evidence.id,
                    fact_kind="relationship",
                    relationship_id=RELATIONSHIP_ID,
                ),
            )
        ),
    )

    fact_confidence = output.fact_confidences[0]
    assert fact_confidence.fact_kind == "relationship"
    assert fact_confidence.relationship_id == RELATIONSHIP_ID


def test_duplicate_attribution_cannot_inflate_relationship_confidence() -> None:
    evidence = _evidence(confidence=0.9)
    attribution = FactAttribution(
        evidence_id=evidence.id,
        fact_kind="relationship",
        relationship_id=RELATIONSHIP_ID,
    )

    output = aggregate_fact_confidences(
        _input(evidence),
        EvidenceAssociationResult(fact_attributions=(attribution, attribution)),
    )

    assert len(output.fact_confidences) == 1
    assert output.fact_confidences[0].confidence.score == 0.855
