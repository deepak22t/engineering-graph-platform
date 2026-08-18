"""Tests for the Phase 5 semantic compilation contracts."""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    CompilationResult,
    FactConfidence,
)
from packages.domain.confidence import Confidence
from packages.domain.conflicts import CompetingClaim, Conflict, ConflictType
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation
from packages.domain.proposals import EntityProposal, ExtractionResult
from packages.domain.scope import GraphScope
from packages.domain.validation import FindingSeverity, ValidationFinding

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def extraction_result(scope: GraphScope = SCOPE) -> ExtractionResult:
    evidence = Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum="a" * 64,
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        observed_at=datetime.now(timezone.utc),
        confidence=0.95,
    )
    proposal = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence],
    )
    return ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=scope,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="cisco_ios_running_config_parser",
        extractor_version="1",
        entity_proposals=[proposal],
    )


def test_compilation_input_accepts_one_same_scope_snapshot() -> None:
    input_value = CompilationInput(
        extraction_result=extraction_result(),
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )

    result = CompilationResult.from_input(input_value)

    assert result.artifact_id == ARTIFACT_ID
    assert result.artifact_version_id == ARTIFACT_VERSION_ID
    assert result.artifact_checksum == "a" * 64
    assert result.scope == SCOPE
    assert result.canonical_ready
    assert not result.review_required


def test_compilation_input_rejects_a_snapshot_from_another_scope() -> None:
    other_scope = SCOPE.model_copy(update={"environment": "development"})

    with pytest.raises(ValidationError, match="scopes must match"):
        CompilationInput(
            extraction_result=extraction_result(),
            canonical_snapshot=CanonicalSnapshot(scope=other_scope),
        )


def test_fact_confidence_requires_one_target_of_its_declared_kind() -> None:
    confidence = Confidence.from_score(0.95, method="aggregate")

    property_confidence = FactConfidence(
        confidence=confidence,
        fact_kind="property",
        entity_id=UUID(int=1),
        property_path="properties.hostname",
    )
    assert property_confidence.property_path == "properties.hostname"

    with pytest.raises(ValidationError, match="exactly one declared fact"):
        FactConfidence(
            confidence=confidence,
            fact_kind="relationship",
            entity_id=UUID(int=1),
            property_path="properties.hostname",
        )


def test_open_conflicts_and_error_findings_block_canonical_readiness() -> None:
    conflict = Conflict(
        subject_type="entity",
        field_path="properties.hostname",
        conflict_type=ConflictType.PROPERTY,
        competing_claims=[
            CompetingClaim(value="router-01", evidence_ids=[UUID(int=1)]),
            CompetingClaim(value="router-02", evidence_ids=[UUID(int=2)]),
        ],
    )
    finding = ValidationFinding(
        code="invalid_reference",
        severity=FindingSeverity.ERROR,
        message="Relationship references an unknown proposal.",
        subject_type="proposal",
    )

    result = CompilationResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        findings=(finding,),
        conflicts=(conflict,),
    )

    assert result.review_required
    assert not result.canonical_ready


def test_dangling_fact_support_cannot_be_canonical_ready() -> None:
    result = CompilationResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        fact_attributions=(
            FactAttribution(
                evidence_id=UUID(int=10),
                fact_kind="property",
                entity_id=UUID(int=11),
                property_path="properties.hostname",
            ),
        ),
    )

    assert not result.fact_support_complete
    assert not result.canonical_ready
