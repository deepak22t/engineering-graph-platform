"""Tests for converting Cisco IOS parsed claims into proposal-stage contracts."""

from pathlib import Path
from uuid import UUID

from packages.artifacts import ArtifactKind, ArtifactScope
from packages.domain.confidence import confidence_score_for_method
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.extraction.cisco_ios import CiscoIosRunningConfigParser
from packages.extraction.cisco_ios.proposals import CiscoIosProposalBuilder
from packages.ingestion.models import ExtractionInput

FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "artifacts" / "edge-router-01-running-config.cfg"
)


def extraction_input() -> ExtractionInput:
    return ExtractionInput(
        artifact_id=UUID("11111111-1111-1111-1111-111111111111"),
        artifact_version_id=UUID("22222222-2222-2222-2222-222222222222"),
        version_number=3,
        scope=ArtifactScope(
            organization_id=UUID("33333333-3333-3333-3333-333333333333"),
            project_id=UUID("44444444-4444-4444-4444-444444444444"),
            environment="production",
            site_id=UUID("55555555-5555-5555-5555-555555555555"),
        ),
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        sha256_checksum="a" * 64,
        original_filename="ignored.cfg",
        storage_key="artifacts/trusted/versions/3/original",
        adapter_name="cisco_ios_config",
        adapter_version="1",
    )


def build(text: str):
    parsed = CiscoIosRunningConfigParser().parse(text)
    return CiscoIosProposalBuilder().build(extraction_input=extraction_input(), parsed=parsed)


def test_builder_emits_fixture_entities_attributes_relationships_and_line_evidence():
    result = build(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert [proposal.entity_type for proposal in result.entity_proposals] == [
        EntityType.DEVICE,
        EntityType.INTERFACE,
        EntityType.IP,
        EntityType.NETWORK,
    ]
    assert [proposal.display_name for proposal in result.entity_proposals] == [
        "edge-router-01",
        "GigabitEthernet0/1",
        "192.0.2.1",
        "192.0.2.0/30",
    ]
    assert [proposal.field_path for proposal in result.attribute_proposals] == [
        "properties.hostname",
        "properties.interface_name",
        "properties.interface_type",
        "properties.address",
        "properties.address_family",
        "properties.cidr",
        "properties.address_family",
        "properties.network_type",
        "properties.description",
        "properties.admin_status",
    ]
    assert [proposal.relationship_type for proposal in result.relationship_proposals] == [
        RelationshipType.HAS_INTERFACE,
        RelationshipType.ATTACHED_TO,
    ]
    assert all(
        proposal.source_canonical_id is None and proposal.target_canonical_id is None
        for proposal in result.relationship_proposals
    )
    assert all(
        evidence.source_artifact_version == "3"
        and evidence.source_artifact_checksum == "a" * 64
        and evidence.source_location.line_start == evidence.source_location.line_end
        and evidence.evidence_reference.endswith(f"#line={evidence.source_location.line_start}")
        for proposal in (
            *result.entity_proposals,
            *result.attribute_proposals,
            *result.relationship_proposals,
        )
        for evidence in proposal.evidence
    )
    assert result.findings == []


def test_builder_creates_vlan_membership_without_connected_to_relationship():
    result = build(
        """hostname switch-01
interface GigabitEthernet1/0/1
 switchport access vlan 10
!
vlan 10
 name Users
"""
    )

    assert [proposal.entity_type for proposal in result.entity_proposals] == [
        EntityType.DEVICE,
        EntityType.INTERFACE,
        EntityType.VLAN,
    ]
    assert [proposal.relationship_type for proposal in result.relationship_proposals] == [
        RelationshipType.HAS_INTERFACE,
        RelationshipType.MEMBER_OF,
    ]
    assert RelationshipType.CONNECTED_TO not in {
        proposal.relationship_type for proposal in result.relationship_proposals
    }
    assert any(
        proposal.field_path == "properties.vlan_name" and proposal.proposed_value == "Users"
        for proposal in result.attribute_proposals
    )


def test_builder_does_not_invent_device_or_has_interface_without_one_reliable_hostname():
    result = build("interface GigabitEthernet0/1\n description orphaned-device\n")

    assert [proposal.entity_type for proposal in result.entity_proposals] == [EntityType.INTERFACE]
    assert result.relationship_proposals == []
    assert [(finding.code, finding.severity.value) for finding in result.findings] == [
        ("source_device_missing", "warning")
    ]


def test_builder_preserves_parser_findings_without_creating_invalid_facts():
    result = build("interface GigabitEthernet0/1\n ip address 192.0.2.1 invalid\n")

    assert [proposal.entity_type for proposal in result.entity_proposals] == [EntityType.INTERFACE]
    assert [(finding.code, finding.field_path) for finding in result.findings] == [
        ("invalid_interface_ipv4_address", "properties.address"),
        ("source_device_missing", "properties.hostname"),
    ]


def test_builder_uses_shared_deterministic_metadata_and_confidence_policy():
    result = build("hostname router-01\n")

    assert result.extractor_name == "cisco_ios_running_config_parser"
    assert result.extractor_version == "1"
    assert result.extraction_method is ExtractionMethod.DETERMINISTIC_PARSER
    assert result.entity_proposals[0].extraction_method is ExtractionMethod.DETERMINISTIC_PARSER
    assert result.entity_proposals[0].evidence[0].confidence == confidence_score_for_method(
        ExtractionMethod.DETERMINISTIC_PARSER
    )


def test_same_source_bytes_produce_equivalent_proposal_structure() -> None:
    text = """hostname router-01
interface GigabitEthernet0/1
 description Uplink
 ip address 192.0.2.1 255.255.255.252
"""

    first = build(text)
    second = build(text)

    def structure(result):
        return {
            "entities": [
                (proposal.entity_type, proposal.display_name)
                for proposal in result.entity_proposals
            ],
            "attributes": [
                (proposal.field_path, proposal.proposed_value)
                for proposal in result.attribute_proposals
            ],
            "relationships": [
                proposal.relationship_type for proposal in result.relationship_proposals
            ],
            "entity_evidence_lines": [
                [evidence.source_location.line_start for evidence in proposal.evidence]
                for proposal in result.entity_proposals
            ],
            "findings": [(finding.code, finding.field_path) for finding in result.findings],
        }

    assert structure(first) == structure(second)
