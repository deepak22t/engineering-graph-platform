"""Tests for direct-fact Cisco LLDP neighbor-detail extraction."""

from uuid import UUID

from packages.artifacts import ArtifactKind, ArtifactScope
from packages.domain.enums import EntityType, RelationshipType
from packages.extraction.lldp import LldpNeighborsDetailParser, LldpNeighborsDetailProposalBuilder
from packages.ingestion.models import ExtractionInput


def extraction_input() -> ExtractionInput:
    return ExtractionInput(
        artifact_id=UUID("11111111-1111-1111-1111-111111111111"),
        artifact_version_id=UUID("22222222-2222-2222-2222-222222222222"),
        version_number=4,
        scope=ArtifactScope(
            organization_id=UUID("33333333-3333-3333-3333-333333333333"),
            project_id=UUID("44444444-4444-4444-4444-444444444444"),
            environment="production",
            site_id=UUID("55555555-5555-5555-5555-555555555555"),
        ),
        artifact_kind=ArtifactKind.LLDP_NEIGHBORS_DETAIL,
        sha256_checksum="a" * 64,
        original_filename="show-lldp-neighbors-detail.txt",
        storage_key="artifacts/trusted/versions/4/original",
        adapter_name="cisco_lldp_neighbors_detail",
        adapter_version="1",
    )


def build(text: str):
    return LldpNeighborsDetailProposalBuilder().build(
        extraction_input=extraction_input(),
        parsed=LldpNeighborsDetailParser().parse(text),
    )


def test_lldp_preserves_system_name_and_chassis_id_as_separate_claims() -> None:
    result = build(
        """------------------------------------------------
Local Intf: GigabitEthernet0/1
Chassis id: 0011.2233.4455
Port id: GigabitEthernet1/0/24
System Name: distribution-01
System Description: Cisco IOS XE Software
System Capabilities: Bridge, Router
Management Addresses:
  IP: 2001:db8::10
"""
    )

    assert [proposal.entity_type for proposal in result.entity_proposals] == [
        EntityType.DEVICE,
        EntityType.INTERFACE,
        EntityType.INTERFACE,
    ]
    assert result.entity_proposals[0].display_name == "distribution-01"
    assert any(
        proposal.field_path == "properties.hostname"
        and proposal.proposed_value == "distribution-01"
        for proposal in result.attribute_proposals
    )
    assert any(
        proposal.field_path == "properties.chassis_id"
        and proposal.proposed_value == "0011.2233.4455"
        for proposal in result.attribute_proposals
    )
    assert any(
        proposal.field_path == "properties.management_ip"
        and proposal.proposed_value == "2001:db8::10"
        for proposal in result.attribute_proposals
    )
    assert [proposal.relationship_type for proposal in result.relationship_proposals] == [
        RelationshipType.CONNECTED_TO
    ]
    assert all(
        proposal.source_canonical_id is None and proposal.target_canonical_id is None
        for proposal in result.relationship_proposals
    )


def test_lldp_missing_remote_port_creates_finding_without_connection() -> None:
    result = build("Local Intf: GigabitEthernet0/1\nSystem Name: distribution-01\n")

    assert [proposal.entity_type for proposal in result.entity_proposals] == [EntityType.DEVICE]
    assert result.relationship_proposals == []
    assert [(finding.code, finding.severity.value) for finding in result.findings] == [
        ("lldp_connection_endpoint_missing", "warning")
    ]


def test_lldp_invalid_management_address_becomes_a_finding_not_a_fact() -> None:
    result = build(
        """Local Intf: GigabitEthernet0/1
Chassis id: 0011.2233.4455
Port id: GigabitEthernet1/0/24
Management Addresses:
 IP: invalid-address
"""
    )

    assert all(
        proposal.field_path != "properties.management_ip" for proposal in result.attribute_proposals
    )
    assert [(finding.code, finding.severity.value) for finding in result.findings] == [
        ("invalid_lldp_management_address", "error")
    ]
