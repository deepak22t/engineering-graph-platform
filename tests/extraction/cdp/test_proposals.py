"""Tests for direct-fact Cisco CDP neighbor-detail extraction."""

from uuid import UUID

from packages.artifacts import ArtifactKind, ArtifactScope
from packages.domain.enums import EntityType, RelationshipType
from packages.extraction.cdp import CdpNeighborsDetailParser, CdpNeighborsDetailProposalBuilder
from packages.ingestion.models import ExtractionInput


def extraction_input() -> ExtractionInput:
    return ExtractionInput(
        artifact_id=UUID("11111111-1111-1111-1111-111111111111"),
        artifact_version_id=UUID("22222222-2222-2222-2222-222222222222"),
        version_number=2,
        scope=ArtifactScope(
            organization_id=UUID("33333333-3333-3333-3333-333333333333"),
            project_id=UUID("44444444-4444-4444-4444-444444444444"),
            environment="production",
            site_id=UUID("55555555-5555-5555-5555-555555555555"),
        ),
        artifact_kind=ArtifactKind.CDP_NEIGHBORS_DETAIL,
        sha256_checksum="a" * 64,
        original_filename="show-cdp-neighbors-detail.txt",
        storage_key="artifacts/trusted/versions/2/original",
        adapter_name="cisco_cdp_neighbors_detail",
        adapter_version="1",
    )


def build(text: str):
    parsed = CdpNeighborsDetailParser().parse(text)
    return CdpNeighborsDetailProposalBuilder().build(
        extraction_input=extraction_input(), parsed=parsed
    )


def test_parser_and_builder_extract_multiple_independent_neighbors_with_evidence() -> None:
    result = build(
        """-------------------------
Device ID: distribution-01
Entry address(es):
  IP address: 192.0.2.10
Platform: cisco C9300-48P, Capabilities: Switch IGMP
Interface: GigabitEthernet0/1, Port ID (outgoing port): GigabitEthernet1/0/24
-------------------------
Device ID: access-02
Interface: GigabitEthernet0/2, Port ID (outgoing port): GigabitEthernet0/48
"""
    )

    assert [proposal.entity_type for proposal in result.entity_proposals] == [
        EntityType.DEVICE,
        EntityType.INTERFACE,
        EntityType.INTERFACE,
        EntityType.DEVICE,
        EntityType.INTERFACE,
        EntityType.INTERFACE,
    ]
    assert [proposal.display_name for proposal in result.entity_proposals] == [
        "distribution-01",
        "GigabitEthernet0/1",
        "GigabitEthernet1/0/24",
        "access-02",
        "GigabitEthernet0/2",
        "GigabitEthernet0/48",
    ]
    assert [proposal.relationship_type for proposal in result.relationship_proposals] == [
        RelationshipType.CONNECTED_TO,
        RelationshipType.CONNECTED_TO,
    ]
    assert all(
        proposal.source_canonical_id is None and proposal.target_canonical_id is None
        for proposal in result.relationship_proposals
    )
    assert any(
        proposal.field_path == "properties.management_ip"
        and proposal.proposed_value == "192.0.2.10"
        for proposal in result.attribute_proposals
    )
    assert all(
        evidence.source_location.line_start == evidence.source_location.line_end
        and evidence.evidence_reference.endswith(
            f"#line={evidence.source_location.line_start}"
        )
        for proposal in (*result.entity_proposals, *result.attribute_proposals)
        for evidence in proposal.evidence
    )


def test_incomplete_record_creates_finding_and_never_creates_connection() -> None:
    result = build("Device ID: distribution-01\nPlatform: cisco C9300, Capabilities: Switch\n")

    assert [proposal.entity_type for proposal in result.entity_proposals] == [EntityType.DEVICE]
    assert result.relationship_proposals == []
    assert [(finding.code, finding.severity.value) for finding in result.findings] == [
        ("cdp_connection_endpoint_missing", "warning")
    ]


def test_invalid_management_address_is_finding_not_a_fact() -> None:
    result = build(
        """Device ID: distribution-01
IP address: definitely-not-an-ip
Interface: GigabitEthernet0/1, Port ID (outgoing port): GigabitEthernet1/0/24
"""
    )

    assert all(
        proposal.field_path != "properties.management_ip"
        for proposal in result.attribute_proposals
    )
    assert [(finding.code, finding.severity.value) for finding in result.findings] == [
        ("invalid_cdp_management_address", "error")
    ]
    assert len(result.evidence_records) == 1
