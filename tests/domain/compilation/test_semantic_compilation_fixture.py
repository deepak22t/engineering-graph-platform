"""Sanitized end-to-end topology fixture required by the Phase 5 test gate."""

from datetime import datetime, timezone
from uuid import UUID

from packages.domain.compilation import CanonicalSnapshot, compile
from packages.domain.conflicts import ConflictStatus, ConflictType
from packages.domain.entities import SiteEntity, SiteProperties
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation
from packages.domain.identity import SiteIdentity
from packages.domain.proposals import (
    AttributeProposal,
    EntityProposal,
    ExtractionResult,
    RelationshipProposal,
)
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SITE_EVIDENCE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
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


def _entity(entity_type: EntityType, display_name: str, line: int) -> EntityProposal:
    return EntityProposal(
        entity_type=entity_type,
        display_name=display_name,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(line)],
    )


def _attribute(
    subject: EntityProposal,
    field_path: str,
    value: object,
    line: int,
) -> AttributeProposal:
    return AttributeProposal(
        subject_proposal_id=subject.proposal_id,
        field_path=field_path,
        proposed_value=value,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(line)],
    )


def _relationship(
    relationship_type: RelationshipType,
    source: EntityProposal,
    target: EntityProposal,
    line: int,
) -> RelationshipProposal:
    return RelationshipProposal(
        relationship_type=relationship_type,
        source_proposal_id=source.proposal_id,
        target_proposal_id=target.proposal_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[_evidence(line)],
    )


def _existing_site() -> SiteEntity:
    return SiteEntity(
        identity=SiteIdentity(scope=SCOPE, site_code="blr-1"),
        display_name="Bengaluru DC",
        properties=SiteProperties(site_type="datacenter"),
        first_observed_at=OBSERVED_AT,
        last_observed_at=OBSERVED_AT,
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
    )


def _snapshot(site: SiteEntity) -> CanonicalSnapshot:
    return CanonicalSnapshot(
        scope=SCOPE,
        entities=(site,),
        fact_attributions=(
            FactAttribution(
                evidence_id=SITE_EVIDENCE_ID,
                fact_kind="property",
                entity_id=site.id,
                property_path="properties.site_type",
            ),
        ),
    )


def _topology_extraction(
    site: SiteEntity,
    *,
    proposed_site_type: str = "datacenter",
) -> ExtractionResult:
    router = _entity(EntityType.DEVICE, "Router 01", 1)
    interface = _entity(EntityType.INTERFACE, "GigabitEthernet0/0", 2)
    network = _entity(EntityType.NETWORK, "Campus Network", 3)
    ip_address = _entity(EntityType.IP, "Router management IP", 4)
    vlan = _entity(EntityType.VLAN, "Management VLAN", 5)
    service = _entity(EntityType.SERVICE, "Network monitoring", 6)

    attributes = (
        _attribute(router, "properties.hostname", " Router-01 ", 10),
        _attribute(interface, "properties.interface_name", " GigabitEthernet0/0 ", 11),
        _attribute(interface, "properties.interface_type", " ethernet ", 12),
        _attribute(network, "properties.cidr", "10.0.0.9/24", 13),
        _attribute(network, "properties.address_family", "ipv4", 14),
        _attribute(network, "properties.network_type", "management", 15),
        _attribute(ip_address, "properties.address", "10.0.0.10", 16),
        _attribute(ip_address, "properties.address_family", "ipv4", 17),
        _attribute(vlan, "properties.vlan_id", " 010 ", 18),
        _attribute(service, "properties.service_name", "snmp-monitoring", 19),
        _attribute(service, "properties.service_type", "monitoring", 20),
        _attribute(service, "properties.application", "network-operations", 21),
        AttributeProposal(
            subject_canonical_id=site.id,
            field_path="properties.site_type",
            proposed_value=proposed_site_type,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(22)],
        ),
    )
    relationships = (
        _relationship(RelationshipType.HAS_INTERFACE, router, interface, 30),
        _relationship(RelationshipType.ATTACHED_TO, ip_address, interface, 31),
        _relationship(RelationshipType.MEMBER_OF, interface, vlan, 32),
        _relationship(RelationshipType.ATTACHED_TO, vlan, network, 33),
        RelationshipProposal(
            relationship_type=RelationshipType.LOCATED_AT,
            source_proposal_id=router.proposal_id,
            target_canonical_id=site.id,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version="1",
            evidence=[_evidence(34)],
        ),
        _relationship(RelationshipType.RUNS_ON, service, router, 35),
    )
    return ExtractionResult(
        artifact_id=ARTIFACT_ID,
        artifact_version_id=ARTIFACT_VERSION_ID,
        artifact_version_number=1,
        artifact_kind="cisco_ios_running_config",
        artifact_checksum="a" * 64,
        scope=SCOPE,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_name="sanitized-topology-fixture",
        extractor_version="1",
        entity_proposals=(router, interface, network, ip_address, vlan, service),
        attribute_proposals=attributes,
        relationship_proposals=relationships,
    )


def test_sanitized_topology_compiles_to_a_complete_canonical_candidate_set() -> None:
    site = _existing_site()
    snapshot = _snapshot(site)
    extraction = _topology_extraction(site)
    extraction_before = extraction.model_dump(mode="json")
    snapshot_before = snapshot.model_dump(mode="json")

    result = compile(extraction, snapshot)

    assert result.canonical_ready
    assert result.conflicts == ()
    assert len(result.canonical_entity_candidates) == 6
    assert result.matched_entity_ids == (site.id,)
    assert len(result.typed_property_facts) == 13
    assert len(result.canonical_relationship_candidates) == 6
    assert len(result.fact_attributions) == 19
    assert len(result.fact_confidences) == 19
    assert {entity.entity_type for entity in result.canonical_entity_candidates} == {
        EntityType.DEVICE,
        EntityType.INTERFACE,
        EntityType.NETWORK,
        EntityType.IP,
        EntityType.VLAN,
        EntityType.SERVICE,
    }
    assert {item.relationship_type for item in result.canonical_relationship_candidates} >= {
        RelationshipType.HAS_INTERFACE,
        RelationshipType.ATTACHED_TO,
        RelationshipType.MEMBER_OF,
    }
    assert extraction.model_dump(mode="json") == extraction_before
    assert snapshot.model_dump(mode="json") == snapshot_before


def test_deliberate_topology_conflict_requires_review_and_blocks_only_its_fact() -> None:
    site = _existing_site()

    result = compile(
        _topology_extraction(site, proposed_site_type="branch"),
        _snapshot(site),
    )

    assert result.review_required
    assert not result.canonical_ready
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.conflict_type is ConflictType.PROPERTY
    assert conflict.status is ConflictStatus.OPEN
    assert conflict.subject_id == site.id
    assert conflict.field_path == "properties.site_type"
    assert not any(
        fact.entity_id == site.id and fact.field_path == "properties.site_type"
        for fact in result.typed_property_facts
    )
    assert len(result.canonical_entity_candidates) == 6
    assert len(result.canonical_relationship_candidates) == 6
    assert site.properties.site_type == "datacenter"
