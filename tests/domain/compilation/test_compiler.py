"""End-to-end tests for the persistence-free semantic compiler."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from packages.domain.compilation import CanonicalSnapshot, compile
from packages.domain.conflicts import ConflictStatus, ConflictType
from packages.domain.entities import DeviceEntity, DeviceProperties
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
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
OBSERVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
        observed_at=OBSERVED_AT,
        confidence=0.95,
    )


def _extraction_result(
    *,
    entities: tuple[EntityProposal, ...] = (),
    attributes: tuple[AttributeProposal, ...] = (),
    relationships: tuple[RelationshipProposal, ...] = (),
) -> ExtractionResult:
    return ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="test-parser",
        extractor_version="1",
        entity_proposals=entities,
        attribute_proposals=attributes,
        relationship_proposals=relationships,
    )


def _topology_extraction() -> ExtractionResult:
    device = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="Router 01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(1)],
    )
    interface = EntityProposal(
        entity_type=EntityType.INTERFACE,
        display_name="GigabitEthernet0/0",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(2)],
    )
    attributes = (
        AttributeProposal(
            subject_proposal_id=device.proposal_id,
            field_path="properties.hostname",
            proposed_value=" Router-01 ",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(3)],
        ),
        AttributeProposal(
            subject_proposal_id=interface.proposal_id,
            field_path="properties.interface_name",
            proposed_value=" GigabitEthernet0/0 ",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(4)],
        ),
        AttributeProposal(
            subject_proposal_id=interface.proposal_id,
            field_path="properties.interface_type",
            proposed_value=" ethernet ",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(5)],
        ),
    )
    relationship = RelationshipProposal(
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_proposal_id=device.proposal_id,
        target_proposal_id=interface.proposal_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(6)],
    )
    return _extraction_result(
        entities=(device, interface),
        attributes=attributes,
        relationships=(relationship,),
    )


def test_compile_runs_the_complete_pure_pipeline_in_one_call() -> None:
    extraction = _topology_extraction()
    source_before = extraction.model_dump(mode="json")

    result = compile(extraction, CanonicalSnapshot(scope=SCOPE))

    assert result.canonical_ready
    assert len(result.canonical_entity_candidates) == 2
    assert len(result.typed_property_facts) == 3
    assert len(result.canonical_relationship_candidates) == 1
    assert len(result.fact_attributions) == 4
    assert len(result.fact_confidences) == 4
    assert result.conflicts == ()
    assert extraction.model_dump(mode="json") == source_before


def test_compile_preserves_conflict_for_review_instead_of_overwriting() -> None:
    existing = DeviceEntity(
        identity=DeviceIdentity(scope=SCOPE, hostname="router-01"),
        display_name="Router 01",
        properties=DeviceProperties(hostname="router-01", model="ISR 1000"),
        first_observed_at=OBSERVED_AT,
        last_observed_at=OBSERVED_AT,
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )
    conflicting_claim = AttributeProposal(
        subject_canonical_id=existing.id,
        field_path="properties.model",
        proposed_value="ASR 1000",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(10)],
    )

    existing_attribution = FactAttribution(
        evidence_id=uuid4(),
        fact_kind="property",
        entity_id=existing.id,
        property_path="properties.model",
    )
    result = compile(
        _extraction_result(attributes=(conflicting_claim,)),
        CanonicalSnapshot(
            scope=SCOPE,
            entities=(existing,),
            fact_attributions=(existing_attribution,),
        ),
    )

    assert result.review_required
    assert not result.canonical_ready
    assert len(result.conflicts) == 1
    assert result.conflicts[0].conflict_type is ConflictType.PROPERTY
    assert result.conflicts[0].status is ConflictStatus.OPEN
    assert result.typed_property_facts == ()
    assert existing.properties.model == "isr 1000"


def test_compile_keeps_dangling_claim_as_finding_not_canonical_data() -> None:
    dangling_claim = AttributeProposal(
        subject_proposal_id=uuid4(),
        field_path="properties.hostname",
        proposed_value="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(20)],
    )

    result = compile(
        _extraction_result(attributes=(dangling_claim,)),
        CanonicalSnapshot(scope=SCOPE),
    )

    assert not result.canonical_ready
    assert result.canonical_entity_candidates == ()
    assert result.typed_property_facts == ()
    assert any(finding.code == "unknown_proposal_reference" for finding in result.findings)


def test_compile_rejects_a_snapshot_from_another_scope() -> None:
    other_scope = SCOPE.model_copy(update={"environment": "development"})

    with pytest.raises(ValidationError, match="scopes must match"):
        compile(_topology_extraction(), CanonicalSnapshot(scope=other_scope))
