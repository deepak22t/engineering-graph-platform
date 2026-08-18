"""Tests for Phase 5 shared-normalizer compilation claims."""

from uuid import UUID

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    NormalizationStatus,
    normalize_proposal_claims,
)
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation
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


def _evidence() -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum="a" * 64,
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.95,
    )


def _input(*, entity_type: EntityType, field_path: str, value: object) -> CompilationInput:
    entity = EntityProposal(
        entity_type=entity_type,
        display_name="source display name",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence()],
    )
    attribute = AttributeProposal(
        subject_proposal_id=entity.proposal_id,
        field_path=field_path,
        proposed_value=value,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence()],
    )
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
        attribute_proposals=[attribute],
    )
    return CompilationInput(
        extraction_result=result,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def test_normalization_creates_an_audited_immutable_copy() -> None:
    compilation_input = _input(
        entity_type=EntityType.DEVICE,
        field_path="properties.hostname",
        value="  Router-01  ",
    )
    original = compilation_input.extraction_result.attribute_proposals[0]

    output = normalize_proposal_claims(compilation_input)

    claim = output.claims[0]
    assert claim.status is NormalizationStatus.NORMALIZED
    assert claim.raw_value == "  Router-01  "
    assert claim.normalized_value == "router-01"
    assert claim.attribute_proposal_id == original.proposal_id
    assert claim.evidence_ids == (original.evidence[0].id,)
    assert original.proposed_value == "  Router-01  "
    assert output.findings == ()


def test_normalization_uses_exact_shared_ip_cidr_mac_and_vlan_rules() -> None:
    cases = (
        (EntityType.DEVICE, "properties.management_ip", " 2001:0db8::1 ", "2001:db8::1"),
        (EntityType.NETWORK, "properties.cidr", "192.168.1.9/24", "192.168.1.0/24"),
        (EntityType.INTERFACE, "properties.mac_address", "00-11-22-33-44-55", "00:11:22:33:44:55"),
        (EntityType.VLAN, "properties.vlan_id", " 010 ", 10),
    )

    for entity_type, field_path, raw_value, normalized_value in cases:
        output = normalize_proposal_claims(
            _input(entity_type=entity_type, field_path=field_path, value=raw_value)
        )

        assert output.claims[0].normalized_value == normalized_value
        assert output.claims[0].status is NormalizationStatus.NORMALIZED
        assert output.findings == ()


def test_invalid_value_is_not_guessed_and_retains_raw_claim_and_evidence() -> None:
    output = normalize_proposal_claims(
        _input(
            entity_type=EntityType.DEVICE,
            field_path="properties.management_ip",
            value="192.168.1.5/24",
        )
    )

    claim = output.claims[0]
    assert claim.status is NormalizationStatus.REJECTED
    assert claim.raw_value == "192.168.1.5/24"
    assert claim.normalized_value is None
    assert claim.evidence_ids
    assert [finding.code for finding in output.findings] == ["normalization_failed"]


def test_future_property_remains_noncanonical_raw_claim() -> None:
    output = normalize_proposal_claims(
        _input(
            entity_type=EntityType.DEVICE,
            field_path="properties.platform",
            value="Cisco C9300",
        )
    )

    claim = output.claims[0]
    assert claim.status is NormalizationStatus.NONCANONICAL
    assert claim.raw_value == "Cisco C9300"
    assert claim.normalized_value is None
    assert [(finding.code, finding.severity.value) for finding in output.findings] == [
        ("noncanonical_property_path", "warning")
    ]
