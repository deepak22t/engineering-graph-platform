"""Tests for Phase 5 cross-proposal schema validation."""

from uuid import UUID

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    validate_proposal_batch,
)
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
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


def evidence(**overrides) -> Evidence:
    values = {
        "source_artifact_id": ARTIFACT_ID,
        "source_artifact_version": "1",
        "source_artifact_checksum": "a" * 64,
        "source_location": SourceLocation(line_start=1),
        "extraction_method": ExtractionMethod.DETERMINISTIC_PARSER,
        "extractor_version": "1",
        "confidence": 0.95,
    }
    values.update(overrides)
    return Evidence(**values)


def compilation_input(*, entities=(), attributes=(), relationships=()):
    result = ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="cisco_ios_running_config_parser",
        extractor_version="1",
        entity_proposals=list(entities),
        attribute_proposals=list(attributes),
        relationship_proposals=list(relationships),
    )
    return CompilationInput(
        extraction_result=result,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def device_proposal() -> EntityProposal:
    return EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence()],
    )


def test_valid_same_artifact_proposals_have_no_batch_findings() -> None:
    device = device_proposal()
    hostname = AttributeProposal(
        subject_proposal_id=device.proposal_id,
        field_path="properties.hostname",
        proposed_value="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence()],
    )

    findings = validate_proposal_batch(
        compilation_input(entities=(device,), attributes=(hostname,))
    )

    assert findings == ()


def test_dangling_and_mixed_relationship_references_become_findings() -> None:
    device = device_proposal()
    relationship = RelationshipProposal(
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_proposal_id=device.proposal_id,
        source_canonical_id=UUID(int=100),
        target_proposal_id=UUID(int=200),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence()],
    )

    findings = validate_proposal_batch(
        compilation_input(entities=(device,), relationships=(relationship,))
    )

    assert [finding.code for finding in findings] == [
        "mixed_reference_kind",
        "unknown_proposal_reference",
    ]


def test_wrong_evidence_traceability_is_rejected_before_resolution() -> None:
    proposal = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence(source_artifact_checksum="b" * 64)],
    )

    findings = validate_proposal_batch(compilation_input(entities=(proposal,)))

    assert [finding.code for finding in findings] == ["evidence_checksum_mismatch"]
    assert findings[0].proposal_id == proposal.proposal_id


def test_unknown_property_path_is_retained_as_a_noncanonical_raw_claim() -> None:
    device = device_proposal()
    raw_platform = AttributeProposal(
        subject_proposal_id=device.proposal_id,
        field_path="properties.platform",
        proposed_value="Cisco C9300",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence()],
    )

    findings = validate_proposal_batch(
        compilation_input(entities=(device,), attributes=(raw_platform,))
    )

    assert [(finding.code, finding.severity.value) for finding in findings] == [
        ("noncanonical_property_path", "warning")
    ]
