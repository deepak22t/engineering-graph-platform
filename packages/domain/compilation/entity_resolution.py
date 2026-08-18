"""Scope-safe entity identity resolution for typed property candidates."""

from __future__ import annotations

import ipaddress
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from packages.domain.compilation.contracts import CompilationInput
from packages.domain.compilation.typed_properties import (
    TypedPropertyCandidate,
    TypedPropertyCompilationResult,
)
from packages.domain.entities.properties import (
    ComponentProperties,
    DeviceProperties,
    FirewallProperties,
    InterfaceProperties,
    IPAddressProperties,
    NetworkProperties,
    ServiceProperties,
    VlanProperties,
)
from packages.domain.enums import EntityType, RelationshipType
from packages.domain.identity import (
    ComponentIdentity,
    DeviceIdentity,
    EntityIdentity,
    FirewallIdentity,
    InterfaceIdentity,
    IPIdentity,
    NetworkIdentity,
    ServiceIdentity,
    VlanIdentity,
)
from packages.domain.ids import generate_entity_id
from packages.domain.validation import FindingSeverity, ValidationFinding


class EntityResolutionStatus(str, Enum):
    """The one allowed outcome for resolving a typed entity candidate."""

    MATCHED_EXISTING = "matched_existing"
    NEW_CANDIDATE = "new_candidate"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


class EntityResolution(BaseModel):
    """Identity resolution outcome without mutating canonical state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate: TypedPropertyCandidate
    status: EntityResolutionStatus
    identity: EntityIdentity | None = None
    canonical_entity_id: UUID | None = None
    plausible_entity_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def require_consistent_resolution_data(self) -> "EntityResolution":
        resolved = {
            EntityResolutionStatus.MATCHED_EXISTING,
            EntityResolutionStatus.NEW_CANDIDATE,
        }
        if self.status in resolved:
            if self.identity is None or self.canonical_entity_id is None:
                raise ValueError("A resolved candidate requires an identity and canonical UUID.")
            if self.plausible_entity_ids:
                raise ValueError("A resolved candidate cannot retain plausible alternatives.")
        elif self.identity is not None or self.canonical_entity_id is not None:
            raise ValueError(
                "An unresolved candidate must not expose a canonical identity or UUID."
            )
        if self.status is EntityResolutionStatus.AMBIGUOUS:
            if len(set(self.plausible_entity_ids)) < 2:
                raise ValueError("An ambiguous resolution requires at least two plausible IDs.")
        elif self.plausible_entity_ids:
            raise ValueError("Only an ambiguous resolution may retain plausible entity IDs.")
        return self


class EntityResolutionResult(BaseModel):
    """Pure, same-scope entity-resolution output for later compilation stages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolutions: tuple[EntityResolution, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()


def resolve_entity_identities(
    compilation_input: CompilationInput,
    property_result: TypedPropertyCompilationResult,
) -> EntityResolutionResult:
    """Resolve typed candidates against the immutable same-scope snapshot only."""

    findings = list(property_result.findings)
    snapshot_by_identity = _same_scope_snapshot_identities(compilation_input)
    snapshot_by_id = {entity.id: entity for entity in compilation_input.canonical_snapshot.entities}
    interface_parents = _interface_parent_proposals(compilation_input)
    component_parents = _component_parent_proposals(compilation_input)
    canonical_devices = _canonical_device_identities(compilation_input)
    canonical_networks = _canonical_network_identities(compilation_input)
    resolved_devices: dict[UUID, DeviceIdentity] = {}
    resolved_networks: dict[UUID, NetworkIdentity] = {}
    resolutions: list[EntityResolution] = []

    indexed_candidates = enumerate(property_result.candidates)
    for _, candidate in sorted(indexed_candidates, key=_resolution_order):
        if candidate.subject_canonical_id is not None:
            existing = snapshot_by_id.get(candidate.subject_canonical_id)
            if existing is not None and existing.entity_type is candidate.entity_type:
                resolutions.append(
                    EntityResolution(
                        candidate=candidate,
                        status=EntityResolutionStatus.MATCHED_EXISTING,
                        identity=existing.identity,
                        canonical_entity_id=existing.id,
                    )
                )
            else:
                resolutions.append(
                    EntityResolution(candidate=candidate, status=EntityResolutionStatus.REJECTED)
                )
                findings.append(_invalid_canonical_reference_finding(candidate))
            continue
        identity, finding = _build_identity(
            candidate,
            compilation_input.canonical_snapshot.scope,
            _resolved_device_parent(
                candidate,
                interface_parents,
                component_parents,
                resolved_devices,
                canonical_devices,
            ),
            _resolved_ip_network(candidate, resolved_networks, canonical_networks),
        )
        if finding is not None:
            resolutions.append(
                EntityResolution(candidate=candidate, status=EntityResolutionStatus.UNRESOLVED)
            )
            findings.append(finding)
            continue
        if identity is None:
            resolutions.append(
                EntityResolution(candidate=candidate, status=EntityResolutionStatus.REJECTED)
            )
            findings.append(_rejected_identity_finding(candidate))
            continue

        canonical_entity_id = generate_entity_id(identity)
        matches = snapshot_by_identity.get(identity.canonical_serialization(), ())
        if len(matches) == 1:
            resolutions.append(
                EntityResolution(
                    candidate=candidate,
                    status=EntityResolutionStatus.MATCHED_EXISTING,
                    identity=identity,
                    canonical_entity_id=canonical_entity_id,
                )
            )
        elif len(matches) == 0:
            resolutions.append(
                EntityResolution(
                    candidate=candidate,
                    status=EntityResolutionStatus.NEW_CANDIDATE,
                    identity=identity,
                    canonical_entity_id=canonical_entity_id,
                )
            )
        else:
            resolutions.append(
                EntityResolution(
                    candidate=candidate,
                    status=EntityResolutionStatus.AMBIGUOUS,
                    plausible_entity_ids=tuple(dict.fromkeys(matches)),
                )
            )
            findings.append(_ambiguous_identity_finding(candidate))

        if (
            len(matches) <= 1
            and isinstance(identity, DeviceIdentity)
            and candidate.subject_proposal_id is not None
        ):
            resolved_devices[candidate.subject_proposal_id] = identity
        if (
            len(matches) <= 1
            and isinstance(identity, NetworkIdentity)
            and candidate.subject_proposal_id is not None
        ):
            resolved_networks[candidate.subject_proposal_id] = identity

    return EntityResolutionResult(resolutions=tuple(resolutions), findings=tuple(findings))


def _interface_parent_proposals(
    compilation_input: CompilationInput,
) -> dict[UUID, tuple[tuple[str, UUID], ...]]:
    parents: dict[UUID, set[tuple[str, UUID]]] = {}
    for proposal in compilation_input.extraction_result.relationship_proposals:
        if (
            proposal.relationship_type is not RelationshipType.HAS_INTERFACE
            or proposal.target_proposal_id is None
            or proposal.target_canonical_id is not None
        ):
            continue
        if proposal.source_proposal_id is not None and proposal.source_canonical_id is None:
            parent = ("proposal", proposal.source_proposal_id)
        elif proposal.source_canonical_id is not None and proposal.source_proposal_id is None:
            parent = ("canonical", proposal.source_canonical_id)
        else:
            continue
        parents.setdefault(proposal.target_proposal_id, set()).add(parent)
    return {
        interface_id: tuple(sorted(parent_refs, key=lambda item: (item[0], str(item[1]))))
        for interface_id, parent_refs in parents.items()
    }


def _canonical_device_identities(
    compilation_input: CompilationInput,
) -> dict[UUID, DeviceIdentity]:
    return {
        entity.id: entity.identity
        for entity in compilation_input.canonical_snapshot.entities
        if isinstance(entity.identity, DeviceIdentity)
    }


def _component_parent_proposals(
    compilation_input: CompilationInput,
) -> dict[UUID, tuple[tuple[str, UUID], ...]]:
    parents: dict[UUID, set[tuple[str, UUID]]] = {}
    for proposal in compilation_input.extraction_result.relationship_proposals:
        if (
            proposal.relationship_type is not RelationshipType.PART_OF
            or proposal.source_proposal_id is None
            or proposal.source_canonical_id is not None
        ):
            continue
        if proposal.target_proposal_id is not None and proposal.target_canonical_id is None:
            parent = ("proposal", proposal.target_proposal_id)
        elif proposal.target_canonical_id is not None and proposal.target_proposal_id is None:
            parent = ("canonical", proposal.target_canonical_id)
        else:
            continue
        parents.setdefault(proposal.source_proposal_id, set()).add(parent)
    return {
        component_id: tuple(sorted(parent_refs, key=lambda item: (item[0], str(item[1]))))
        for component_id, parent_refs in parents.items()
    }


def _resolved_device_parent(
    candidate: TypedPropertyCandidate,
    interface_parents: dict[UUID, tuple[tuple[str, UUID], ...]],
    component_parents: dict[UUID, tuple[tuple[str, UUID], ...]],
    resolved_devices: dict[UUID, DeviceIdentity],
    canonical_devices: dict[UUID, DeviceIdentity],
) -> DeviceIdentity | None:
    if candidate.subject_proposal_id is None:
        return None
    if candidate.entity_type is EntityType.INTERFACE:
        parent_refs = interface_parents.get(candidate.subject_proposal_id, ())
    elif candidate.entity_type is EntityType.COMPONENT:
        parent_refs = component_parents.get(candidate.subject_proposal_id, ())
    else:
        return None
    if len(parent_refs) != 1:
        return None
    reference_kind, parent_id = parent_refs[0]
    if reference_kind == "proposal":
        return resolved_devices.get(parent_id)
    return canonical_devices.get(parent_id)


def _canonical_network_identities(
    compilation_input: CompilationInput,
) -> tuple[NetworkIdentity, ...]:
    return tuple(
        entity.identity
        for entity in compilation_input.canonical_snapshot.entities
        if isinstance(entity.identity, NetworkIdentity)
    )


def _resolved_ip_network(
    candidate: TypedPropertyCandidate,
    resolved_networks: dict[UUID, NetworkIdentity],
    canonical_networks: tuple[NetworkIdentity, ...],
) -> NetworkIdentity | None:
    if candidate.entity_type is not EntityType.IP or not isinstance(
        candidate.properties, IPAddressProperties
    ):
        return None
    address = ipaddress.ip_address(candidate.properties.address)
    unique_networks = {
        identity.canonical_serialization(): identity
        for identity in (*resolved_networks.values(), *canonical_networks)
        if address in ipaddress.ip_network(identity.cidr)
    }
    if len(unique_networks) != 1:
        return None
    return next(iter(unique_networks.values()))


def _same_scope_snapshot_identities(
    compilation_input: CompilationInput,
) -> dict[str, tuple[UUID, ...]]:
    identities: dict[str, list[UUID]] = {}
    for entity in compilation_input.canonical_snapshot.entities:
        if entity.scope != compilation_input.canonical_snapshot.scope:
            continue
        identities.setdefault(entity.identity.canonical_serialization(), []).append(entity.id)
    return {key: tuple(value) for key, value in identities.items()}


def _resolution_order(item: tuple[int, TypedPropertyCandidate]) -> tuple[int, int]:
    index, candidate = item
    order = {
        EntityType.SITE: 1,
        EntityType.NETWORK: 1,
        EntityType.DEVICE: 2,
        EntityType.COMPONENT: 3,
        EntityType.INTERFACE: 4,
        EntityType.VLAN: 5,
        EntityType.IP: 6,
        EntityType.SERVICE: 7,
        EntityType.CONTAINER: 7,
        EntityType.FIREWALL: 7,
        EntityType.ROUTE: 7,
        EntityType.CONNECTION: 7,
    }
    return order[candidate.entity_type], index


def _build_identity(
    candidate: TypedPropertyCandidate,
    scope,
    parent_device_identity: DeviceIdentity | None,
    network_identity: NetworkIdentity | None,
) -> tuple[EntityIdentity | None, ValidationFinding | None]:
    if candidate.entity_type is EntityType.DEVICE:
        properties = candidate.properties
        if not isinstance(properties, DeviceProperties):
            return None, None
        if properties.serial_number is None and scope.site_id is None:
            return None, _unresolved_identity_finding(
                candidate,
                "Device hostname fallback requires a site-scoped GraphScope or a serial number.",
            )
        return (
            DeviceIdentity(
                scope=scope,
                serial_number=properties.serial_number,
                hostname=properties.hostname,
            ),
            None,
        )
    if candidate.entity_type is EntityType.COMPONENT:
        properties = candidate.properties
        if not isinstance(properties, ComponentProperties):
            return None, None
        if parent_device_identity is None:
            return None, _unresolved_identity_finding(
                candidate,
                "Component identity requires exactly one resolved PART_OF parent device.",
            )
        locator_parts = [
            value for value in (properties.slot, properties.module) if value is not None
        ]
        if not locator_parts and properties.serial_number is not None:
            locator_parts.append(f"serial:{properties.serial_number}")
        if not locator_parts:
            return None, _unresolved_identity_finding(
                candidate,
                "Component identity requires a slot, module, or serial number locator.",
            )
        return (
            ComponentIdentity(
                scope=scope,
                parent_device_identity=parent_device_identity,
                component_locator="/".join(locator_parts),
                serial_number=properties.serial_number,
            ),
            None,
        )
    if candidate.entity_type is EntityType.INTERFACE:
        properties = candidate.properties
        if not isinstance(properties, InterfaceProperties):
            return None, None
        if parent_device_identity is None:
            return None, _unresolved_identity_finding(
                candidate,
                "Interface identity requires exactly one resolved HAS_INTERFACE parent device.",
            )
        return (
            InterfaceIdentity(
                scope=scope,
                parent_device_identity=parent_device_identity,
                interface_name=properties.interface_name,
            ),
            None,
        )
    if candidate.entity_type is EntityType.NETWORK:
        properties = candidate.properties
        if not isinstance(properties, NetworkProperties):
            return None, None
        return NetworkIdentity(scope=scope, cidr=properties.cidr), None
    if candidate.entity_type is EntityType.IP:
        properties = candidate.properties
        if not isinstance(properties, IPAddressProperties):
            return None, None
        if network_identity is None:
            return None, _unresolved_identity_finding(
                candidate,
                "IP identity requires exactly one resolved containing Network.",
            )
        return (
            IPIdentity(scope=scope, network_identity=network_identity, address=properties.address),
            None,
        )
    if candidate.entity_type is EntityType.SERVICE:
        properties = candidate.properties
        if not isinstance(properties, ServiceProperties):
            return None, None
        if properties.application is None:
            return None, _unresolved_identity_finding(
                candidate,
                "Service identity requires an explicit application or namespace context.",
            )
        return (
            ServiceIdentity(
                scope=scope,
                service_name=properties.service_name,
                application=properties.application,
            ),
            None,
        )
    if candidate.entity_type is EntityType.FIREWALL:
        properties = candidate.properties
        if not isinstance(properties, FirewallProperties):
            return None, None
        if properties.firewall_type != "policy" or properties.policy_id is None:
            return None, _unresolved_identity_finding(
                candidate,
                "Firewall appliance identity requires a serial number or appliance name "
                "not present in typed properties.",
            )
        return (
            FirewallIdentity(
                scope=scope,
                firewall_kind="policy",
                policy_id=properties.policy_id,
            ),
            None,
        )
    if candidate.entity_type is EntityType.VLAN:
        properties = candidate.properties
        if not isinstance(properties, VlanProperties):
            return None, None
        if scope.site_id is None:
            return None, _unresolved_identity_finding(
                candidate,
                "VLAN identity requires a site-scoped GraphScope or a resolved network identity.",
            )
        return VlanIdentity(scope=scope, vlan_id=properties.vlan_id), None
    return None, _unresolved_identity_finding(
        candidate,
        "This entity type requires parent or context identity inputs not available in Step 5.",
    )


def _invalid_canonical_reference_finding(
    candidate: TypedPropertyCandidate,
) -> ValidationFinding:
    return ValidationFinding(
        code="invalid_canonical_entity_reference",
        severity=FindingSeverity.ERROR,
        message="Canonical entity reference is missing or has a different entity type.",
        subject_type="entity_property_candidate",
        subject_id=candidate.subject_canonical_id,
        proposal_id=candidate.attribute_proposal_ids[0],
    )


def _unresolved_identity_finding(
    candidate: TypedPropertyCandidate, message: str
) -> ValidationFinding:
    return ValidationFinding(
        code="unresolved_entity_identity",
        severity=FindingSeverity.ERROR,
        message=message,
        subject_type="entity_property_candidate",
        proposal_id=candidate.attribute_proposal_ids[0],
        remediation_hint="Provide the required typed identity context from evidence.",
    )


def _rejected_identity_finding(candidate: TypedPropertyCandidate) -> ValidationFinding:
    return ValidationFinding(
        code="rejected_entity_identity",
        severity=FindingSeverity.ERROR,
        message="Typed properties do not match the declared entity type for identity resolution.",
        subject_type="entity_property_candidate",
        proposal_id=candidate.attribute_proposal_ids[0],
    )


def _ambiguous_identity_finding(candidate: TypedPropertyCandidate) -> ValidationFinding:
    return ValidationFinding(
        code="ambiguous_existing_identity",
        severity=FindingSeverity.ERROR,
        message="More than one same-scope canonical entity matches this typed identity.",
        subject_type="entity_property_candidate",
        proposal_id=candidate.attribute_proposal_ids[0],
        remediation_hint="Resolve the duplicate canonical identities through review.",
    )


__all__ = [
    "EntityResolution",
    "EntityResolutionResult",
    "EntityResolutionStatus",
    "resolve_entity_identities",
]
