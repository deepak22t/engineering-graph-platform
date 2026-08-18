"""Required Phase 5 validation-matrix tests from the Step 13 gate."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    NormalizationStatus,
    compile,
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


def _evidence(*, checksum: str = "a" * 64) -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum=checksum,
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.95,
    )


def _extraction_payload() -> dict[str, object]:
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_version_id": ARTIFACT_VERSION_ID,
        "artifact_version_number": 1,
        "artifact_kind": "cisco_ios_running_config",
        "artifact_checksum": "a" * 64,
        "scope": SCOPE,
        "extraction_method": ExtractionMethod.DETERMINISTIC_PARSER,
        "extractor_name": "test-parser",
        "extractor_version": "1",
    }


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("artifact_version_number", 0),
        ("artifact_kind", "   "),
        ("artifact_checksum", "not-a-sha256-checksum"),
        (
            "scope",
            {
                "organization_id": "not-a-uuid",
                "project_id": str(SCOPE.project_id),
                "environment": "production",
            },
        ),
    ),
)
def test_invalid_artifact_checksum_and_scope_metadata_are_rejected(
    field_name: str,
    invalid_value: object,
) -> None:
    payload = _extraction_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


@pytest.mark.parametrize(
    ("entity_type", "field_path", "invalid_value"),
    (
        (EntityType.DEVICE, "properties.hostname", "   "),
        (EntityType.INTERFACE, "properties.interface_name", "   "),
        (EntityType.DEVICE, "properties.management_ip", "999.999.1.1"),
        (EntityType.NETWORK, "properties.cidr", "10.0.0.0/99"),
        (EntityType.INTERFACE, "properties.mac_address", "not-a-mac"),
        (EntityType.VLAN, "properties.vlan_id", 4095),
    ),
)
def test_invalid_engineering_identity_values_produce_normalization_findings(
    entity_type: EntityType,
    field_path: str,
    invalid_value: object,
) -> None:
    entity = EntityProposal(
        entity_type=entity_type,
        display_name="sanitized proposal",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence()],
    )
    attribute = AttributeProposal(
        subject_proposal_id=entity.proposal_id,
        field_path=field_path,
        proposed_value=invalid_value,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence()],
    )
    extraction = ExtractionResult(
        **_extraction_payload(),
        entity_proposals=[entity],
        attribute_proposals=[attribute],
    )
    compilation_input = CompilationInput(
        extraction_result=extraction,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )

    result = normalize_proposal_claims(compilation_input)

    assert result.claims[0].status is NormalizationStatus.REJECTED
    assert result.claims[0].raw_value == invalid_value
    assert result.claims[0].evidence_ids == (attribute.evidence[0].id,)
    assert [finding.code for finding in result.findings] == ["normalization_failed"]


def test_missing_proposal_evidence_is_rejected_by_the_contract() -> None:
    with pytest.raises(ValidationError):
        EntityProposal(
            entity_type=EntityType.DEVICE,
            display_name="router-01",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[],
        )


def test_invalid_evidence_trace_cannot_become_canonical_ready() -> None:
    invalid_evidence = _evidence(checksum="b" * 64)
    device = EntityProposal(
        entity_type=EntityType.DEVICE,
        display_name="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[invalid_evidence],
    )
    hostname = AttributeProposal(
        subject_proposal_id=device.proposal_id,
        field_path="properties.hostname",
        proposed_value="router-01",
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[invalid_evidence],
    )
    extraction = ExtractionResult(
        **_extraction_payload(),
        entity_proposals=[device],
        attribute_proposals=[hostname],
    )

    result = compile(extraction, CanonicalSnapshot(scope=SCOPE))

    assert not result.canonical_ready
    assert result.canonical_entity_candidates == ()
    assert result.typed_property_facts == ()
    assert any(finding.code == "evidence_checksum_mismatch" for finding in result.findings)

def test_case_and_whitespace_variants_compile_to_the_same_identity() -> None:
    def compiled_device_id(hostname: str) -> UUID:
        device = EntityProposal(
            entity_type=EntityType.DEVICE,
            display_name="router display label",
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence()],
        )
        attribute = AttributeProposal(
            subject_proposal_id=device.proposal_id,
            field_path="properties.hostname",
            proposed_value=hostname,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence()],
        )
        extraction = ExtractionResult(
            **_extraction_payload(),
            entity_proposals=[device],
            attribute_proposals=[attribute],
        )
        result = compile(extraction, CanonicalSnapshot(scope=SCOPE))
        assert result.canonical_ready
        return result.canonical_entity_candidates[0].id

    assert compiled_device_id("Router-01") == compiled_device_id("  router-01  ")
