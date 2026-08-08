"""Executable relationship rules for the canonical engineering graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from packages.domain.enums import EntityType, RelationshipType
from packages.domain.relationships import Relationship
from packages.domain.validation import FindingSeverity, ValidationFinding


@dataclass(frozen=True)
class RelationshipSpec:
    relationship_type: RelationshipType
    allowed_source_types: frozenset[EntityType]
    allowed_target_types: frozenset[EntityType]
    directed: bool
    symmetric: bool
    cardinality_rule: str
    uniqueness_rule: str
    required_attributes: frozenset[str] = frozenset()
    allowed_attributes: frozenset[str] = frozenset()
    allowed_endpoint_pairs: frozenset[tuple[EntityType, EntityType]] = frozenset()
    forbid_self_loops: bool = True
    max_source_occurrences: int | None = None
    max_target_occurrences: int | None = None


E = EntityType
R = RelationshipType
RELATIONSHIP_SPECS = {
    R.HAS_INTERFACE: RelationshipSpec(
        R.HAS_INTERFACE,
        frozenset({E.DEVICE}),
        frozenset({E.INTERFACE}),
        True,
        False,
        "one owner per interface",
        "source-target-type",
        max_target_occurrences=1,
    ),
    R.CONNECTED_TO: RelationshipSpec(
        R.CONNECTED_TO,
        frozenset({E.INTERFACE}),
        frozenset({E.INTERFACE}),
        False,
        True,
        "many-to-many",
        "unordered endpoint pair",
        allowed_attributes=frozenset({"medium", "capacity_bps", "state"}),
    ),
    R.LOCATED_AT: RelationshipSpec(
        R.LOCATED_AT,
        frozenset({E.DEVICE, E.SERVICE, E.FIREWALL, E.CONTAINER}),
        frozenset({E.SITE}),
        True,
        False,
        "one active location per source",
        "source-target-type",
        max_source_occurrences=1,
    ),
    R.MEMBER_OF: RelationshipSpec(
        R.MEMBER_OF,
        frozenset({E.INTERFACE, E.DEVICE}),
        frozenset({E.VLAN, E.NETWORK}),
        True,
        False,
        "many-to-many",
        "source-target-type",
        allowed_endpoint_pairs=frozenset(
            {
                (E.INTERFACE, E.VLAN),
                (E.DEVICE, E.NETWORK),
                (E.INTERFACE, E.NETWORK),
            }
        ),
    ),
    R.RUNS_ON: RelationshipSpec(
        R.RUNS_ON,
        frozenset({E.SERVICE, E.CONTAINER}),
        frozenset({E.DEVICE, E.CONTAINER}),
        True,
        False,
        "many-to-many",
        "source-target-type",
    ),
    R.HOSTS: RelationshipSpec(
        R.HOSTS,
        frozenset({E.DEVICE}),
        frozenset({E.SERVICE, E.CONTAINER}),
        True,
        False,
        "many-to-many",
        "source-target-type",
    ),
    R.ROUTES_TO: RelationshipSpec(
        R.ROUTES_TO,
        frozenset({E.ROUTE, E.DEVICE}),
        frozenset({E.NETWORK}),
        True,
        False,
        "many-to-many",
        "source-target-type",
    ),
    R.CONTROLS: RelationshipSpec(
        R.CONTROLS,
        frozenset({E.FIREWALL}),
        frozenset({E.CONNECTION, E.INTERFACE, E.NETWORK}),
        True,
        False,
        "many-to-many",
        "source-target-type",
    ),
    R.CONTAINS: RelationshipSpec(
        R.CONTAINS,
        frozenset({E.SITE, E.NETWORK}),
        frozenset({E.DEVICE, E.FIREWALL, E.NETWORK}),
        True,
        False,
        "one parent per contained device",
        "source-target-type",
        allowed_endpoint_pairs=frozenset(
            {
                (E.SITE, E.DEVICE),
                (E.NETWORK, E.NETWORK),
            }
        ),
        max_target_occurrences=1,
    ),
    R.DEPENDS_ON: RelationshipSpec(
        R.DEPENDS_ON,
        frozenset({E.SERVICE}),
        frozenset({E.SERVICE}),
        True,
        False,
        "many-to-many",
        "source-target-type",
    ),
    R.PART_OF: RelationshipSpec(
        R.PART_OF,
        frozenset({E.COMPONENT}),
        frozenset({E.DEVICE, E.COMPONENT}),
        True,
        False,
        "one parent per component",
        "source-target-type",
        max_source_occurrences=1,
    ),
    R.ATTACHED_TO: RelationshipSpec(
        R.ATTACHED_TO,
        frozenset({E.IP, E.VLAN}),
        frozenset({E.INTERFACE, E.NETWORK}),
        True,
        False,
        "one interface per IP",
        "source-target-type",
        allowed_endpoint_pairs=frozenset(
            {
                (E.IP, E.INTERFACE),
                (E.VLAN, E.NETWORK),
            }
        ),
        max_source_occurrences=1,
    ),
}


def _relationship_finding(
    relationship: Relationship,
    code: str,
    message: str,
    field_path: str | None = None,
) -> ValidationFinding:
    """Create a canonical validation finding for one relationship violation."""
    return ValidationFinding(
        code=code,
        severity=FindingSeverity.ERROR,
        message=message,
        subject_type="relationship",
        subject_id=relationship.id,
        field_path=field_path,
    )


def validate_relationship(
    relationship: Relationship,
    source_entity,
    target_entity,
    existing_relationships: Iterable[Relationship],
) -> list[ValidationFinding]:
    """Validate endpoints, attributes, uniqueness, and cardinality without persistence."""
    spec = RELATIONSHIP_SPECS[relationship.relationship_type]
    findings: list[ValidationFinding] = []
    if relationship.source_id != source_entity.id or relationship.target_id != target_entity.id:
        findings.append(
            _relationship_finding(
                relationship,
                "endpoint_identity_mismatch",
                "Relationship endpoint IDs must match the supplied canonical entities.",
                "endpoints",
            )
        )
    endpoint_pair = (source_entity.entity_type, target_entity.entity_type)
    if spec.allowed_endpoint_pairs:
        endpoint_types_are_valid = endpoint_pair in spec.allowed_endpoint_pairs
    else:
        endpoint_types_are_valid = (
            source_entity.entity_type in spec.allowed_source_types
            and target_entity.entity_type in spec.allowed_target_types
        )
    if not endpoint_types_are_valid:
        findings.append(
            _relationship_finding(
                relationship,
                "invalid_endpoint_types",
                "Relationship endpoint types are not allowed by its specification.",
                "endpoints",
            )
        )
    if spec.forbid_self_loops and relationship.source_id == relationship.target_id:
        findings.append(
            _relationship_finding(
                relationship,
                "self_loop_forbidden",
                "This relationship type does not permit self-loops.",
                "endpoints",
            )
        )
    unknown = set(relationship.attributes) - spec.allowed_attributes
    missing = spec.required_attributes - set(relationship.attributes)
    if unknown:
        findings.append(
            _relationship_finding(
                relationship,
                "unknown_attributes",
                f"Unsupported relationship attributes: {sorted(unknown)}.",
                "attributes",
            )
        )
    if missing:
        findings.append(
            _relationship_finding(
                relationship,
                "missing_attributes",
                f"Required relationship attributes are missing: {sorted(missing)}.",
                "attributes",
            )
        )
    for existing in existing_relationships:
        if existing.relationship_type != relationship.relationship_type:
            continue
        same_pair = (
            {existing.source_id, existing.target_id}
            == {relationship.source_id, relationship.target_id}
            if spec.symmetric
            else (existing.source_id, existing.target_id)
            == (relationship.source_id, relationship.target_id)
        )
        if same_pair:
            findings.append(
                _relationship_finding(
                    relationship,
                    "duplicate_relationship",
                    "An equivalent relationship already exists.",
                    "endpoints",
                )
            )
            break
    same_type = [
        r for r in existing_relationships if r.relationship_type == relationship.relationship_type
    ]
    if (
        spec.max_source_occurrences is not None
        and sum(r.source_id == relationship.source_id for r in same_type)
        >= spec.max_source_occurrences
    ):
        findings.append(
            _relationship_finding(
                relationship,
                "source_cardinality",
                "Source cardinality would be exceeded.",
                "source_id",
            )
        )
    if (
        spec.max_target_occurrences is not None
        and sum(r.target_id == relationship.target_id for r in same_type)
        >= spec.max_target_occurrences
    ):
        findings.append(
            _relationship_finding(
                relationship,
                "target_cardinality",
                "Target cardinality would be exceeded.",
                "target_id",
            )
        )
    return findings
