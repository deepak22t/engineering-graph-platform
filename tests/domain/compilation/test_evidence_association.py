"""Tests for Phase 5 property-level evidence association."""

from uuid import UUID

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
    associate_property_evidence,
)
from packages.domain.entities.properties import DeviceProperties
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import DeviceIdentity
from packages.domain.ids import generate_entity_id
from packages.domain.proposals import AttributeProposal, ExtractionResult
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
HOSTNAME_PROPOSAL_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
IP_PROPOSAL_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
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


def _attribute(
    proposal_id: UUID, field_path: str, value: str, evidence: list[Evidence]
) -> AttributeProposal:
    return AttributeProposal(
        proposal_id=proposal_id,
        subject_proposal_id=UUID(int=9),
        field_path=field_path,
        proposed_value=value,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=evidence,
    )


def _input(attributes: list[AttributeProposal]) -> CompilationInput:
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
        attribute_proposals=attributes,
    )
    return CompilationInput(
        extraction_result=result,
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def _claim(proposal: AttributeProposal, value: str) -> NormalizedAttributeClaim:
    return NormalizedAttributeClaim(
        attribute_proposal_id=proposal.proposal_id,
        subject_proposal_id=proposal.subject_proposal_id,
        entity_type=EntityType.DEVICE,
        field_path=proposal.field_path,
        raw_value=value,
        normalized_value=value,
        evidence_ids=tuple(record.id for record in proposal.evidence),
        status=NormalizationStatus.NORMALIZED,
    )


def _resolution(proposal_ids: tuple[UUID, ...]) -> EntityResolution:
    identity = DeviceIdentity(scope=SCOPE, hostname="router-01")
    return EntityResolution(
        candidate=TypedPropertyCandidate(
            entity_type=EntityType.DEVICE,
            subject_proposal_id=UUID(int=9),
            properties=DeviceProperties(hostname="router-01", management_ip="192.0.2.1"),
            attribute_proposal_ids=proposal_ids,
        ),
        status=EntityResolutionStatus.NEW_CANDIDATE,
        identity=identity,
        canonical_entity_id=generate_entity_id(identity),
    )


def test_property_attribution_uses_each_propertys_exact_evidence_only() -> None:
    hostname_evidence = _evidence(2)
    ip_evidence = _evidence(8)
    hostname = _attribute(
        HOSTNAME_PROPOSAL_ID,
        "properties.hostname",
        "router-01",
        [hostname_evidence],
    )
    management_ip = _attribute(
        IP_PROPOSAL_ID,
        "properties.management_ip",
        "192.0.2.1",
        [ip_evidence],
    )

    output = associate_property_evidence(
        _input([hostname, management_ip]),
        NormalizationResult(
            claims=(_claim(hostname, "router-01"), _claim(management_ip, "192.0.2.1"))
        ),
        EntityResolutionResult(
            resolutions=(_resolution((hostname.proposal_id, management_ip.proposal_id)),)
        ),
    )

    assert output.findings == ()
    assert {
        (attribution.property_path, attribution.evidence_id)
        for attribution in output.fact_attributions
    } == {
        ("properties.hostname", hostname_evidence.id),
        ("properties.management_ip", ip_evidence.id),
    }


def test_agreeing_claims_preserve_all_supporting_evidence() -> None:
    first_evidence = _evidence(2)
    second_evidence = _evidence(3)
    first = _attribute(HOSTNAME_PROPOSAL_ID, "properties.hostname", "router-01", [first_evidence])
    second = _attribute(IP_PROPOSAL_ID, "properties.hostname", "router-01", [second_evidence])

    output = associate_property_evidence(
        _input([first, second]),
        NormalizationResult(claims=(_claim(first, "router-01"), _claim(second, "router-01"))),
        EntityResolutionResult(resolutions=(_resolution((first.proposal_id, second.proposal_id)),)),
    )

    assert {attribution.evidence_id for attribution in output.fact_attributions} == {
        first_evidence.id,
        second_evidence.id,
    }
    assert {attribution.property_path for attribution in output.fact_attributions} == {
        "properties.hostname"
    }


def test_missing_or_unverifiable_evidence_does_not_create_an_attribution() -> None:
    hostname = _attribute(
        HOSTNAME_PROPOSAL_ID,
        "properties.hostname",
        "router-01",
        [_evidence(2)],
    )
    claim = _claim(hostname, "router-01").model_copy(update={"evidence_ids": (UUID(int=99),)})

    output = associate_property_evidence(
        _input([hostname]),
        NormalizationResult(claims=(claim,)),
        EntityResolutionResult(resolutions=(_resolution((hostname.proposal_id,)),)),
    )

    assert output.fact_attributions == ()
    assert [finding.code for finding in output.findings] == ["unverifiable_property_evidence"]
