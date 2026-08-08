"""Phase 1 gate: construct a small evidence-backed topology safely."""

from datetime import datetime, timezone
from uuid import UUID

from packages.domain.confidence import Confidence
from packages.domain.entities import (
    AddressFamily,
    DeviceEntity,
    DeviceProperties,
    EvidenceBackedEntity,
    InterfaceEntity,
    InterfaceProperties,
    IPAddressEntity,
    IPAddressProperties,
    NetworkEntity,
    NetworkProperties,
    ServiceEntity,
    ServiceProperties,
    SiteEntity,
    SiteProperties,
    VlanEntity,
    VlanProperties,
)
from packages.domain.enums import ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, FactAttribution, SourceLocation
from packages.domain.identity import (
    DeviceIdentity,
    InterfaceIdentity,
    IPIdentity,
    NetworkIdentity,
    ServiceIdentity,
    SiteIdentity,
    VlanIdentity,
)
from packages.domain.ids import generate_relationship_id
from packages.domain.relationship_specs import validate_relationship
from packages.domain.relationships import EvidenceBackedRelationship, Relationship
from packages.domain.scope import GraphScope


def _scope() -> GraphScope:
    return GraphScope(
        organization_id=UUID(int=1),
        project_id=UUID(int=2),
        environment="prod",
        site_id=UUID(int=3),
    )


def _canonical(entity_class, identity, display_name, properties):
    now = datetime.now(timezone.utc)
    return entity_class(
        identity=identity,
        display_name=display_name,
        properties=properties,
        first_observed_at=now,
        last_observed_at=now,
        created_at=now,
        updated_at=now,
    )


def _evidence(line: int) -> Evidence:
    return Evidence(
        source_artifact_id=UUID(int=99),
        source_location=SourceLocation(artifact_type="configuration", line_start=line),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="phase-1-topology-test",
        observed_at=datetime.now(timezone.utc),
        confidence=0.95,
    )


def _relationship(kind, source, target) -> Relationship:
    now = datetime.now(timezone.utc)
    return Relationship(
        id=generate_relationship_id(kind, source.id, target.id),
        relationship_type=kind,
        source_id=source.id,
        target_id=target.id,
        created_at=now,
        updated_at=now,
    )


def test_small_evidence_backed_topology_is_valid():
    scope = _scope()
    site = _canonical(
        SiteEntity,
        SiteIdentity(scope=scope, site_code="blr-1"),
        "Bengaluru DC",
        SiteProperties(site_type="datacenter", region="India"),
    )
    router = _canonical(
        DeviceEntity,
        DeviceIdentity(scope=scope, hostname="router-01"),
        "Core Router",
        DeviceProperties(hostname="router-01", vendor="Cisco", management_ip="10.0.0.1"),
    )
    interface = _canonical(
        InterfaceEntity,
        InterfaceIdentity(
            scope=scope, parent_device_identity=router.identity, interface_name="GigabitEthernet0/1"
        ),
        "Router uplink",
        InterfaceProperties(interface_name="GigabitEthernet0/1", interface_type="ethernet"),
    )
    network_identity = NetworkIdentity(scope=scope, cidr="10.0.0.0/24")
    network = _canonical(
        NetworkEntity,
        network_identity,
        "Operations network",
        NetworkProperties(
            cidr="10.0.0.0/24", address_family=AddressFamily.IPV4, network_type="lan"
        ),
    )
    ip_address = _canonical(
        IPAddressEntity,
        IPIdentity(scope=scope, network_identity=network_identity, address="10.0.0.1"),
        "Router management IP",
        IPAddressProperties(address="10.0.0.1", address_family=AddressFamily.IPV4),
    )
    vlan = _canonical(
        VlanEntity,
        VlanIdentity(scope=scope, network_identity=network_identity, vlan_id=10),
        "Operations VLAN",
        VlanProperties(vlan_id=10, vlan_name="Operations"),
    )
    service = _canonical(
        ServiceEntity,
        ServiceIdentity(scope=scope, service_name="inventory-api", namespace="operations"),
        "Inventory API",
        ServiceProperties(
            service_name="inventory-api", service_type="application", application="inventory"
        ),
    )

    entities = (site, router, interface, network, ip_address, vlan, service)
    entity_evidence = tuple(_evidence(line) for line in range(1, len(entities) + 1))
    backed_entities = tuple(
        EvidenceBackedEntity(
            entity=entity, evidence=[evidence], confidence=Confidence.from_score(0.95)
        )
        for entity, evidence in zip(entities, entity_evidence, strict=True)
    )
    assert len(backed_entities) == 7

    relationships = (
        _relationship(RelationshipType.CONTAINS, site, router),
        _relationship(RelationshipType.LOCATED_AT, router, site),
        _relationship(RelationshipType.HAS_INTERFACE, router, interface),
        _relationship(RelationshipType.MEMBER_OF, interface, vlan),
        _relationship(RelationshipType.MEMBER_OF, interface, network),
        _relationship(RelationshipType.ATTACHED_TO, ip_address, interface),
        _relationship(RelationshipType.ATTACHED_TO, vlan, network),
        _relationship(RelationshipType.RUNS_ON, service, router),
    )
    entity_by_id = {entity.id: entity for entity in entities}
    existing_relationships: list[Relationship] = []
    for relationship in relationships:
        findings = validate_relationship(
            relationship,
            entity_by_id[relationship.source_id],
            entity_by_id[relationship.target_id],
            existing_relationships,
        )
        assert findings == []
        existing_relationships.append(relationship)

    relationship_evidence = tuple(_evidence(line) for line in range(20, 20 + len(relationships)))
    backed_relationships = tuple(
        EvidenceBackedRelationship(
            relationship=relationship,
            evidence=[evidence],
            confidence=Confidence.from_score(0.95),
        )
        for relationship, evidence in zip(relationships, relationship_evidence, strict=True)
    )
    assert len(backed_relationships) == 8

    property_attributions = tuple(
        FactAttribution(
            evidence_id=evidence.id,
            fact_kind="property",
            entity_id=entity.id,
            property_path="properties",
        )
        for entity, evidence in zip(entities, entity_evidence, strict=True)
    )
    relationship_attributions = tuple(
        FactAttribution(
            evidence_id=evidence.id,
            fact_kind="relationship",
            relationship_id=relationship.id,
        )
        for relationship, evidence in zip(relationships, relationship_evidence, strict=True)
    )
    assert len(property_attributions) == len(entities)
    assert len(relationship_attributions) == len(relationships)
