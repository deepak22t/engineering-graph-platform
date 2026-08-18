"""Shared-normalizer stage for immutable semantic-compilation working claims."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.compilation.contracts import CompilationInput
from packages.domain.compilation.property_contracts import is_canonical_property_path
from packages.domain.compilation.schema_validation import validate_proposal_batch
from packages.domain.enums import EntityType
from packages.domain.normalization import (
    normalize_cidr,
    normalize_hostname,
    normalize_interface_name,
    normalize_ip_address,
    normalize_mac_address,
    normalize_text,
    normalize_vendor,
    normalize_vlan_id,
)
from packages.domain.proposals import AttributeProposal, EntityProposal
from packages.domain.validation import FindingSeverity, ValidationFinding

Normalizer = Callable[[Any], Any]


class NormalizationStatus(str, Enum):
    """The outcome of normalizing one raw attribute proposal."""

    NORMALIZED = "normalized"
    REJECTED = "rejected"
    NONCANONICAL = "noncanonical"


class NormalizedAttributeClaim(BaseModel):
    """Immutable audited copy of one attribute proposal after normalization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attribute_proposal_id: UUID
    subject_proposal_id: UUID | None = None
    subject_canonical_id: UUID | None = None
    entity_type: EntityType | None = None
    field_path: str
    raw_value: Any
    normalized_value: Any | None = None
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    status: NormalizationStatus


class NormalizationResult(BaseModel):
    """Normalized working claims and findings; not a canonical graph write."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[NormalizedAttributeClaim, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()


def normalize_proposal_claims(
    compilation_input: CompilationInput,
    *,
    batch_findings: tuple[ValidationFinding, ...] | None = None,
) -> NormalizationResult:
    """Normalize attribute claims without mutating extraction proposals or evidence."""

    result = compilation_input.extraction_result
    findings = list(
        validate_proposal_batch(compilation_input)
        if batch_findings is None
        else batch_findings
    )
    blocked_proposal_ids = {
        finding.proposal_id
        for finding in findings
        if finding.severity is FindingSeverity.ERROR and finding.proposal_id is not None
    }
    proposal_entities = {proposal.proposal_id: proposal for proposal in result.entity_proposals}
    snapshot_entities = {
        entity.id: entity for entity in compilation_input.canonical_snapshot.entities
    }
    claims: list[NormalizedAttributeClaim] = []

    for proposal in result.attribute_proposals:
        entity_type = _resolve_subject_entity_type(
            proposal, proposal_entities, snapshot_entities
        )
        claim = _claim_from_proposal(proposal, entity_type)

        if proposal.proposal_id in blocked_proposal_ids:
            claims.append(claim.model_copy(update={"status": NormalizationStatus.REJECTED}))
            continue
        if entity_type is None or not is_canonical_property_path(entity_type, proposal.field_path):
            claims.append(claim.model_copy(update={"status": NormalizationStatus.NONCANONICAL}))
            continue

        normalizer = _PROPERTY_NORMALIZERS.get((entity_type, proposal.field_path))
        if normalizer is None:
            claims.append(
                claim.model_copy(
                    update={
                        "normalized_value": proposal.proposed_value,
                        "status": NormalizationStatus.NORMALIZED,
                    }
                )
            )
            continue

        try:
            normalized_value = normalizer(proposal.proposed_value)
        except (TypeError, ValueError) as error:
            claims.append(claim.model_copy(update={"status": NormalizationStatus.REJECTED}))
            findings.append(
                ValidationFinding(
                    code="normalization_failed",
                    severity=FindingSeverity.ERROR,
                    message=f"Cannot safely normalize canonical claim: {error}",
                    subject_type="attribute_proposal",
                    proposal_id=proposal.proposal_id,
                    field_path=proposal.field_path,
                    evidence_ids=[evidence.id for evidence in proposal.evidence],
                    remediation_hint="Correct the source value or leave the claim for review.",
                )
            )
            continue

        claims.append(
            claim.model_copy(
                update={
                    "normalized_value": normalized_value,
                    "status": NormalizationStatus.NORMALIZED,
                }
            )
        )

    return NormalizationResult(claims=tuple(claims), findings=tuple(findings))


def _claim_from_proposal(
    proposal: AttributeProposal, entity_type: EntityType | None
) -> NormalizedAttributeClaim:
    return NormalizedAttributeClaim(
        attribute_proposal_id=proposal.proposal_id,
        subject_proposal_id=proposal.subject_proposal_id,
        subject_canonical_id=proposal.subject_canonical_id,
        entity_type=entity_type,
        field_path=proposal.field_path,
        raw_value=proposal.proposed_value,
        evidence_ids=tuple(evidence.id for evidence in proposal.evidence),
        status=NormalizationStatus.REJECTED,
    )


def _resolve_subject_entity_type(
    proposal: AttributeProposal,
    proposal_entities: dict[UUID, EntityProposal],
    snapshot_entities: dict[UUID, Any],
) -> EntityType | None:
    if proposal.subject_proposal_id is not None and proposal.subject_canonical_id is None:
        entity = proposal_entities.get(proposal.subject_proposal_id)
        return entity.entity_type if entity is not None else None
    if proposal.subject_canonical_id is not None and proposal.subject_proposal_id is None:
        entity = snapshot_entities.get(proposal.subject_canonical_id)
        return entity.entity_type if entity is not None else None
    return None


def _preserve_case_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Text value must be a string.")
    return normalize_text(value, casefold=False)


def _normalize_text_value(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Text value must be a string.")
    return normalize_text(value)


_PROPERTY_NORMALIZERS: dict[tuple[EntityType, str], Normalizer] = {
    (EntityType.DEVICE, "properties.hostname"): normalize_hostname,
    (EntityType.DEVICE, "properties.vendor"): normalize_vendor,
    (EntityType.DEVICE, "properties.model"): _normalize_text_value,
    (EntityType.DEVICE, "properties.serial_number"): _normalize_text_value,
    (EntityType.DEVICE, "properties.device_role"): _normalize_text_value,
    (EntityType.DEVICE, "properties.operating_system"): _normalize_text_value,
    (EntityType.DEVICE, "properties.management_ip"): normalize_ip_address,
    (EntityType.COMPONENT, "properties.component_type"): _normalize_text_value,
    (EntityType.COMPONENT, "properties.slot"): _normalize_text_value,
    (EntityType.COMPONENT, "properties.module"): _normalize_text_value,
    (EntityType.COMPONENT, "properties.serial_number"): _normalize_text_value,
    (EntityType.INTERFACE, "properties.interface_name"): normalize_interface_name,
    (EntityType.INTERFACE, "properties.interface_type"): _normalize_text_value,
    (EntityType.INTERFACE, "properties.description"): _preserve_case_text,
    (EntityType.INTERFACE, "properties.mac_address"): normalize_mac_address,
    (EntityType.INTERFACE, "properties.admin_status"): _normalize_text_value,
    (EntityType.INTERFACE, "properties.operational_status"): _normalize_text_value,
    (EntityType.NETWORK, "properties.cidr"): normalize_cidr,
    (EntityType.NETWORK, "properties.address_family"): _normalize_text_value,
    (EntityType.NETWORK, "properties.network_type"): _normalize_text_value,
    (EntityType.SITE, "properties.site_type"): _preserve_case_text,
    (EntityType.SITE, "properties.region"): _preserve_case_text,
    (EntityType.SITE, "properties.address"): _preserve_case_text,
    (EntityType.SERVICE, "properties.service_name"): _normalize_text_value,
    (EntityType.SERVICE, "properties.service_type"): _normalize_text_value,
    (EntityType.SERVICE, "properties.owner"): _normalize_text_value,
    (EntityType.SERVICE, "properties.application"): _normalize_text_value,
    (EntityType.CONTAINER, "properties.workload_name"): _normalize_text_value,
    (EntityType.CONTAINER, "properties.image"): _normalize_text_value,
    (EntityType.CONTAINER, "properties.runtime"): _normalize_text_value,
    (EntityType.IP, "properties.address"): normalize_ip_address,
    (EntityType.IP, "properties.address_family"): _normalize_text_value,
    (EntityType.VLAN, "properties.vlan_id"): normalize_vlan_id,
    (EntityType.VLAN, "properties.vlan_name"): _preserve_case_text,
    (EntityType.ROUTE, "properties.destination_cidr"): normalize_cidr,
    (EntityType.ROUTE, "properties.next_hop"): normalize_ip_address,
    (EntityType.ROUTE, "properties.protocol"): _normalize_text_value,
    (EntityType.FIREWALL, "properties.firewall_type"): _normalize_text_value,
    (EntityType.FIREWALL, "properties.vendor"): normalize_vendor,
    (EntityType.FIREWALL, "properties.model"): _normalize_text_value,
    (EntityType.FIREWALL, "properties.policy_id"): _normalize_text_value,
    (EntityType.CONNECTION, "properties.connection_type"): _normalize_text_value,
    (EntityType.CONNECTION, "properties.medium"): _normalize_text_value,
    (EntityType.CONNECTION, "properties.operational_status"): _normalize_text_value,
}


__all__ = [
    "NormalizedAttributeClaim",
    "NormalizationResult",
    "NormalizationStatus",
    "normalize_proposal_claims",
]
