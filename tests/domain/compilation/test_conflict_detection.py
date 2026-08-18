"""Tests for Phase 5 evidence-backed property conflict detection."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
    NormalizationResult,
    NormalizationStatus,
    NormalizedAttributeClaim,
    TypedPropertyCandidate,
    detect_conflicts,
    detect_identity_conflicts,
    detect_property_conflicts,
)
from packages.domain.entities import DeviceEntity
from packages.domain.entities.properties import DeviceProperties
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation
from packages.domain.identity import DeviceIdentity
from packages.domain.ids import generate_entity_id
from packages.domain.proposals import AttributeProposal, EntityProposal, ExtractionResult
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _evidence(line: int) -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum="a" * 64,
        source_location=SourceLocation(line_start=line),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.95,
    )


def _inputs(values: tuple[str, ...], field_path: str = "properties.hostname"):
    entity = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="Router 01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(1)],
    )
    attributes = [
        AttributeProposal(
            subject_proposal_id=entity.proposal_id,
            field_path=field_path,
            proposed_value=value,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(index + 2)],
        )
        for index, value in enumerate(values)
    ]
    result = ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        entity_proposals=[entity],
        attribute_proposals=attributes,
    )
    identity = DeviceIdentity(scope=SCOPE, hostname="router-01")
    resolution = EntityResolution(
        candidate=TypedPropertyCandidate(
            entity_type=EntityType.DEVICE,
            subject_proposal_id=entity.proposal_id,
            properties=DeviceProperties(hostname="router-01"),
            attribute_proposal_ids=tuple(attribute.proposal_id for attribute in attributes),
        ),
        status=EntityResolutionStatus.NEW_CANDIDATE,
        identity=identity,
        canonical_entity_id=generate_entity_id(identity),
    )
    claims = tuple(
        NormalizedAttributeClaim(
            attribute_proposal_id=attribute.proposal_id,
            subject_proposal_id=entity.proposal_id,
            entity_type=EntityType.DEVICE,
            field_path=attribute.field_path,
            raw_value=attribute.proposed_value,
            normalized_value=attribute.proposed_value.strip().casefold(),
            evidence_ids=(attribute.evidence[0].id,),
            status=NormalizationStatus.NORMALIZED,
        )
        for attribute in attributes
    )
    return (
        result,
        NormalizationResult(claims=claims),
        EntityResolutionResult(resolutions=(resolution,)),
    )


def test_different_normalized_values_for_one_resolved_property_create_conflict() -> None:
    extraction_result, normalization_result, resolution_result = _inputs(("Router-01", "Router-02"))

    output = detect_property_conflicts(extraction_result, normalization_result, resolution_result)

    assert len(output.conflicts) == 1
    conflict = output.conflicts[0]
    assert conflict.subject_id == resolution_result.resolutions[0].canonical_entity_id
    assert conflict.field_path == "properties.hostname"
    assert conflict.conflict_type.value == "property"
    assert conflict.status.value == "open"
    assert [claim.value for claim in conflict.competing_claims] == [
        '"router-01"',
        '"router-02"',
    ]
    assert all(claim.evidence_ids for claim in conflict.competing_claims)


def test_same_normalized_value_with_multiple_evidence_records_is_not_a_conflict() -> None:
    extraction_result, normalization_result, resolution_result = _inputs(
        (" Router-01 ", "router-01")
    )

    output = detect_property_conflicts(extraction_result, normalization_result, resolution_result)

    assert output.conflicts == ()


def test_rejected_claims_never_create_a_false_conflict() -> None:
    extraction_result, normalization_result, resolution_result = _inputs(("Router-01", "Router-02"))
    rejected_claims = tuple(
        claim.model_copy(update={"status": NormalizationStatus.REJECTED})
        for claim in normalization_result.claims
    )

    output = detect_property_conflicts(
        extraction_result,
        NormalizationResult(claims=rejected_claims),
        resolution_result,
    )

    assert output.conflicts == ()


def test_same_device_identity_with_different_serial_numbers_creates_conflict() -> None:
    extraction_result, normalization_result, resolution_result = _inputs(
        ("ABC123", "XYZ789"),
        field_path="properties.serial_number",
    )

    output = detect_property_conflicts(
        extraction_result, normalization_result, resolution_result
    )

    assert len(output.conflicts) == 1
    conflict = output.conflicts[0]
    assert conflict.field_path == "properties.serial_number"
    assert [claim.value for claim in conflict.competing_claims] == [
        '"abc123"',
        '"xyz789"',
    ]
    assert conflict.competing_claims[0].evidence_ids != conflict.competing_claims[1].evidence_ids


def test_proposed_property_conflict_with_existing_canonical_fact_is_detected() -> None:
    extraction_result, normalization_result, resolution_result = _inputs(
        ("XYZ789",),
        field_path="properties.serial_number",
    )
    identity = resolution_result.resolutions[0].identity
    assert isinstance(identity, DeviceIdentity)
    now = datetime.now(timezone.utc)
    existing = DeviceEntity(
        identity=identity,
        display_name="router-01",
        properties=DeviceProperties(hostname="router-01", serial_number="abc123"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )
    existing_evidence_id = uuid4()
    snapshot = CanonicalSnapshot(
        scope=SCOPE,
        entities=(existing,),
        fact_attributions=(
            FactAttribution(
                evidence_id=existing_evidence_id,
                fact_kind="property",
                entity_id=existing.id,
                property_path="properties.serial_number",
            ),
        ),
    )
    matched_resolution = resolution_result.resolutions[0].model_copy(
        update={
            "status": EntityResolutionStatus.MATCHED_EXISTING,
            "canonical_entity_id": existing.id,
        }
    )

    output = detect_property_conflicts(
        extraction_result,
        normalization_result,
        EntityResolutionResult(resolutions=(matched_resolution,)),
        snapshot,
    )

    assert len(output.conflicts) == 1
    claims = output.conflicts[0].competing_claims
    assert [claim.value for claim in claims] == ['"abc123"', '"xyz789"']
    assert existing_evidence_id in claims[0].evidence_ids


def test_ambiguous_identity_retains_all_plausible_ids_as_open_conflict() -> None:
    extraction_result, _, resolution_result = _inputs(("router-01",))
    first_id, second_id = uuid4(), uuid4()
    ambiguous = resolution_result.resolutions[0].model_copy(
        update={
            "status": EntityResolutionStatus.AMBIGUOUS,
            "identity": None,
            "canonical_entity_id": None,
            "plausible_entity_ids": (first_id, second_id),
        }
    )

    output = detect_identity_conflicts(
        extraction_result,
        EntityResolutionResult(resolutions=(ambiguous,)),
    )

    assert len(output.conflicts) == 1
    conflict = output.conflicts[0]
    assert conflict.conflict_type.value == "identity"
    assert conflict.status.value == "open"
    assert conflict.field_path == "identity"
    assert {claim.value for claim in conflict.competing_claims} == {
        f'"{first_id}"',
        f'"{second_id}"',
    }
    assert all(claim.evidence_ids for claim in conflict.competing_claims)


def test_ambiguous_resolution_requires_two_distinct_plausible_ids() -> None:
    _, _, resolution_result = _inputs(("router-01",))

    with pytest.raises(ValueError, match="at least two plausible IDs"):
        EntityResolution(
            candidate=resolution_result.resolutions[0].candidate,
            status=EntityResolutionStatus.AMBIGUOUS,
            plausible_entity_ids=(uuid4(),),
        )


def test_combined_conflict_detector_includes_property_conflicts() -> None:
    extraction_result, normalization_result, resolution_result = _inputs(
        ("Router-01", "Router-02")
    )
    compilation_input = CompilationInput(
        extraction_result=extraction_result,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )

    output = detect_conflicts(
        compilation_input,
        normalization_result,
        resolution_result,
    )

    assert len(output.conflicts) == 1
    assert output.conflicts[0].conflict_type.value == "property"
