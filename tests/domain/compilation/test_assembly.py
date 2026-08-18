"""Tests for immutable canonical candidate assembly."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    ConflictDetectionResult,
    EvidenceAssociationResult,
    FactConfidenceAggregationResult,
    RelationshipCompilationResult,
    aggregate_fact_confidences,
    assemble_canonical_candidates,
    associate_property_evidence,
    associate_relationship_evidence,
    compile_relationship_candidates,
    compile_typed_property_candidates,
    detect_conflicts,
    normalize_proposal_claims,
    resolve_entity_identities,
)
from packages.domain.conflicts import CompetingClaim, Conflict, ConflictType
from packages.domain.entities import DeviceEntity, DeviceProperties
from packages.domain.enums import (
    EntityType,
    ExtractionMethod,
    RelationshipType,
)
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation
from packages.domain.identity import DeviceIdentity
from packages.domain.proposals import (
    AttributeProposal,
    EntityProposal,
    ExtractionResult,
    RelationshipProposal,
)
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
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        confidence=0.95,
    )


def _new_device_pipeline(
    *,
    display_name: str = "Edge Router",
    hostname: str = "router-01",
):
    entity = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name=display_name,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(1)],
    )
    attribute = AttributeProposal(
        subject_proposal_id=entity.proposal_id,
        field_path="properties.hostname",
        proposed_value=hostname,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(2)],
    )
    extraction = ExtractionResult(
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
        attribute_proposals=[attribute],
    )
    compilation_input = CompilationInput(
        extraction_result=extraction,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )
    normalization = normalize_proposal_claims(compilation_input)
    typed = compile_typed_property_candidates(normalization)
    resolution = resolve_entity_identities(compilation_input, typed)
    evidence = associate_property_evidence(
        compilation_input,
        normalization,
        resolution,
    )
    confidence = aggregate_fact_confidences(compilation_input, evidence)
    return compilation_input, normalization, resolution, evidence, confidence


def _assemble(
    compilation_input,
    normalization,
    resolution,
    evidence,
    confidence,
    *,
    conflicts: ConflictDetectionResult | None = None,
):
    return assemble_canonical_candidates(
        compilation_input,
        normalization,
        resolution,
        RelationshipCompilationResult(),
        evidence,
        EvidenceAssociationResult(),
        confidence,
        FactConfidenceAggregationResult(),
        conflicts or ConflictDetectionResult(),
    )


def test_clean_new_entity_assembles_with_typed_fact_evidence_and_confidence() -> None:
    pipeline = _new_device_pipeline()

    output = _assemble(*pipeline)

    assert output.canonical_ready
    assert output.fact_support_complete
    assert output.artifact_id == ARTIFACT_ID
    assert output.artifact_version_id == ARTIFACT_VERSION_ID
    assert output.artifact_kind == "cisco_ios_running_config"
    assert output.artifact_checksum == "a" * 64
    assert output.extraction_method is ExtractionMethod.DETERMINISTIC_PARSER
    assert output.extractor_name == "test-parser"
    assert output.extractor_version == "1"
    assert len(output.canonical_entity_candidates) == 1
    entity = output.canonical_entity_candidates[0]
    assert entity.display_name == "Edge Router"
    assert entity.properties.hostname == "router-01"
    assert entity.id == pipeline[2].resolutions[0].canonical_entity_id
    assert entity.id.version == 5
    assert output.matched_entity_ids == ()
    assert len(output.typed_property_facts) == 1
    fact = output.typed_property_facts[0]
    assert fact.entity_id == entity.id
    assert fact.field_path == "properties.hostname"
    assert fact.value == "router-01"
    assert len(fact.source_attribute_proposal_ids) == 1
    assert len(output.fact_attributions) == 1
    assert len(output.fact_confidences) == 1


def test_display_name_change_does_not_change_internal_entity_id() -> None:
    first = _assemble(*_new_device_pipeline(display_name="Edge Router"))
    second = _assemble(*_new_device_pipeline(display_name="Renamed Presentation Label"))

    assert first.canonical_entity_candidates[0].id == second.canonical_entity_candidates[0].id
    assert (
        first.canonical_entity_candidates[0].display_name
        != second.canonical_entity_candidates[0].display_name
    )


def test_missing_fact_support_excludes_new_entity_and_blocks_readiness() -> None:
    compilation_input, normalization, resolution, _, _ = _new_device_pipeline()

    output = _assemble(
        compilation_input,
        normalization,
        resolution,
        EvidenceAssociationResult(),
        FactConfidenceAggregationResult(),
    )

    assert output.canonical_entity_candidates == ()
    assert output.typed_property_facts == ()
    assert not output.canonical_ready
    assert any(
        finding.code == "incomplete_canonical_fact_support"
        for finding in output.findings
    )


def test_open_property_conflict_blocks_only_affected_new_candidate() -> None:
    pipeline = _new_device_pipeline()
    entity_id = pipeline[2].resolutions[0].canonical_entity_id
    conflict = Conflict(
        subject_type="canonical_entity",
        subject_id=entity_id,
        field_path="properties.hostname",
        competing_claims=(
            CompetingClaim(value='"router-01"', evidence_ids=(uuid4(),)),
            CompetingClaim(value='"router-02"', evidence_ids=(uuid4(),)),
        ),
        conflict_type=ConflictType.PROPERTY,
    )

    output = _assemble(
        *pipeline,
        conflicts=ConflictDetectionResult(conflicts=(conflict,)),
    )

    assert output.canonical_entity_candidates == ()
    assert output.typed_property_facts == ()
    assert output.conflicts == (conflict,)
    assert output.review_required
    assert not output.canonical_ready


def test_matched_identity_is_reference_and_identity_changing_fact_is_rejected() -> None:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    existing = DeviceEntity(
        identity=DeviceIdentity(scope=SCOPE, hostname="router-01"),
        display_name="Existing Router",
        properties=DeviceProperties(hostname="router-01"),
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )
    existing_attribution = FactAttribution(
        evidence_id=uuid4(),
        fact_kind="property",
        entity_id=existing.id,
        property_path="properties.hostname",
    )
    attribute = AttributeProposal(
        subject_canonical_id=existing.id,
        field_path="properties.hostname",
        proposed_value="router-renamed",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(2)],
    )
    extraction = ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        attribute_proposals=[attribute],
    )
    compilation_input = CompilationInput(
        extraction_result=extraction,
        canonical_snapshot=CanonicalSnapshot(
            scope=SCOPE,
            entities=(existing,),
            fact_attributions=(existing_attribution,),
        ),
    )
    normalization = normalize_proposal_claims(compilation_input)
    typed = compile_typed_property_candidates(normalization)
    resolution = resolve_entity_identities(compilation_input, typed)
    evidence = associate_property_evidence(
        compilation_input,
        normalization,
        resolution,
    )
    confidence = aggregate_fact_confidences(compilation_input, evidence)

    output = _assemble(
        compilation_input,
        normalization,
        resolution,
        evidence,
        confidence,
    )

    assert output.canonical_entity_candidates == ()
    assert output.matched_entity_ids == (existing.id,)
    assert output.typed_property_facts == ()
    assert existing.properties.hostname == "router-01"
    assert any(
        finding.code == "identity_changing_property_update"
        for finding in output.findings
    )
    assert not output.canonical_ready


def test_assembled_candidates_and_nested_state_are_immutable() -> None:
    output = _assemble(*_new_device_pipeline())

    with pytest.raises(ValidationError):
        output.typed_property_facts = ()
    with pytest.raises(ValidationError):
        output.canonical_entity_candidates[0].properties.hostname = "changed"


def _topology_pipeline():
    device = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(1)],
    )
    interface = EntityProposal(
        entity_type=EntityType.INTERFACE,
        display_name="GigabitEthernet0/1",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(2)],
    )
    attributes = [
        AttributeProposal(
            subject_proposal_id=device.proposal_id,
            field_path="properties.hostname",
            proposed_value="router-01",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(3)],
        ),
        AttributeProposal(
            subject_proposal_id=interface.proposal_id,
            field_path="properties.interface_name",
            proposed_value="GigabitEthernet0/1",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(4)],
        ),
        AttributeProposal(
            subject_proposal_id=interface.proposal_id,
            field_path="properties.interface_type",
            proposed_value="ethernet",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(5)],
        ),
    ]
    relationship = RelationshipProposal(
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_proposal_id=device.proposal_id,
        target_proposal_id=interface.proposal_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(6)],
    )
    extraction = ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        entity_proposals=[device, interface],
        attribute_proposals=attributes,
        relationship_proposals=[relationship],
    )
    compilation_input = CompilationInput(
        extraction_result=extraction,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )
    normalization = normalize_proposal_claims(compilation_input)
    typed = compile_typed_property_candidates(normalization)
    resolution = resolve_entity_identities(compilation_input, typed)
    relationships = compile_relationship_candidates(compilation_input, resolution)
    property_evidence = associate_property_evidence(
        compilation_input,
        normalization,
        resolution,
    )
    relationship_evidence = associate_relationship_evidence(
        compilation_input,
        relationships,
    )
    property_confidence = aggregate_fact_confidences(
        compilation_input,
        property_evidence,
    )
    relationship_confidence = aggregate_fact_confidences(
        compilation_input,
        relationship_evidence,
    )
    conflicts = detect_conflicts(compilation_input, normalization, resolution)
    return (
        compilation_input,
        normalization,
        resolution,
        relationships,
        property_evidence,
        relationship_evidence,
        property_confidence,
        relationship_confidence,
        conflicts,
    )


def test_clean_relationship_is_assembled_with_separate_fact_support() -> None:
    pipeline = _topology_pipeline()

    output = assemble_canonical_candidates(*pipeline)

    assert output.canonical_ready
    assert len(output.canonical_entity_candidates) == 2
    assert len(output.typed_property_facts) == 3
    assert len(output.canonical_relationship_candidates) == 1
    relationship = output.canonical_relationship_candidates[0]
    assert relationship.relationship_type is RelationshipType.HAS_INTERFACE
    assert len(output.fact_attributions) == 4
    assert len(output.fact_confidences) == 4
    property_attributions = [
        item for item in output.fact_attributions if item.fact_kind == "property"
    ]
    relationship_attributions = [
        item for item in output.fact_attributions if item.fact_kind == "relationship"
    ]
    assert len(property_attributions) == 3
    assert len(relationship_attributions) == 1
    assert relationship_attributions[0].relationship_id == relationship.id


def test_relationship_conflict_blocks_edge_but_keeps_clean_entities() -> None:
    pipeline = _topology_pipeline()
    relationship = pipeline[3].candidates[0]
    conflict = Conflict(
        subject_type="canonical_entity",
        subject_id=relationship.target_id,
        relationship="HAS_INTERFACE:target_cardinality",
        competing_claims=(
            CompetingClaim(value='"first-device"', evidence_ids=(uuid4(),)),
            CompetingClaim(value='"second-device"', evidence_ids=(uuid4(),)),
        ),
        conflict_type=ConflictType.RELATIONSHIP,
    )
    conflicted_pipeline = (*pipeline[:-1], ConflictDetectionResult(conflicts=(conflict,)))

    output = assemble_canonical_candidates(*conflicted_pipeline)

    assert len(output.canonical_entity_candidates) == 2
    assert len(output.typed_property_facts) == 3
    assert output.canonical_relationship_candidates == ()
    assert all(item.fact_kind == "property" for item in output.fact_attributions)
    assert output.review_required
    assert not output.canonical_ready
