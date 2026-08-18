"""Typed-property candidate compilation from normalized attribute claims."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from packages.domain.compilation.normalization import (
    NormalizationResult,
    NormalizationStatus,
    NormalizedAttributeClaim,
)
from packages.domain.compilation.property_contracts import PROPERTY_MODELS
from packages.domain.entities.properties import (
    ComponentProperties,
    ConnectionProperties,
    ContainerProperties,
    DeviceProperties,
    FirewallProperties,
    InterfaceProperties,
    IPAddressProperties,
    NetworkProperties,
    RouteProperties,
    ServiceProperties,
    SiteProperties,
    VlanProperties,
)
from packages.domain.enums import EntityType
from packages.domain.validation import FindingSeverity, ValidationFinding

TypedProperties = (
    DeviceProperties
    | ComponentProperties
    | InterfaceProperties
    | NetworkProperties
    | SiteProperties
    | ServiceProperties
    | ContainerProperties
    | IPAddressProperties
    | VlanProperties
    | RouteProperties
    | FirewallProperties
    | ConnectionProperties
)


class TypedPropertyCandidate(BaseModel):
    """One fully validated typed property set for an unresolved entity reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: EntityType
    subject_proposal_id: UUID | None = None
    subject_canonical_id: UUID | None = None
    properties: TypedProperties
    attribute_proposal_ids: tuple[UUID, ...] = Field(min_length=1)


class TypedPropertyCompilationResult(BaseModel):
    """Typed candidates and findings; it does not resolve identities or conflicts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[TypedPropertyCandidate, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()


def compile_typed_property_candidates(
    normalization_result: NormalizationResult,
) -> TypedPropertyCompilationResult:
    """Compile only complete, unambiguous normalized claims into typed properties."""

    findings = list(normalization_result.findings)
    grouped_claims = _group_normalized_claims(normalization_result.claims)
    candidates: list[TypedPropertyCandidate] = []

    for _, claims in grouped_claims.items():
        entity_type = claims[0].entity_type
        if entity_type is None:
            continue
        properties, property_claims, conflict_findings = _select_property_values(claims)
        findings.extend(conflict_findings)
        if conflict_findings:
            continue

        try:
            typed_properties = PROPERTY_MODELS[entity_type].model_validate(properties)
        except ValidationError as error:
            findings.extend(_typed_property_findings(claims, error))
            continue

        first_claim = claims[0]
        candidates.append(
            TypedPropertyCandidate(
                entity_type=entity_type,
                subject_proposal_id=first_claim.subject_proposal_id,
                subject_canonical_id=first_claim.subject_canonical_id,
                properties=typed_properties,
                attribute_proposal_ids=tuple(
                    claim.attribute_proposal_id for claim in property_claims
                ),
            )
        )

    return TypedPropertyCompilationResult(
        candidates=tuple(candidates), findings=tuple(findings)
    )


def _group_normalized_claims(
    claims: tuple[NormalizedAttributeClaim, ...],
) -> dict[tuple[EntityType, UUID | None, UUID | None], list[NormalizedAttributeClaim]]:
    grouped: dict[
        tuple[EntityType, UUID | None, UUID | None], list[NormalizedAttributeClaim]
    ] = defaultdict(list)
    for claim in claims:
        if claim.status is not NormalizationStatus.NORMALIZED or claim.entity_type is None:
            continue
        grouped[
            (claim.entity_type, claim.subject_proposal_id, claim.subject_canonical_id)
        ].append(claim)
    return grouped


def _select_property_values(
    claims: list[NormalizedAttributeClaim],
) -> tuple[dict[str, Any], list[NormalizedAttributeClaim], list[ValidationFinding]]:
    values_by_field: dict[str, list[NormalizedAttributeClaim]] = defaultdict(list)
    for claim in claims:
        values_by_field[claim.field_path].append(claim)

    properties: dict[str, Any] = {}
    selected_claims: list[NormalizedAttributeClaim] = []
    findings: list[ValidationFinding] = []
    for field_path, field_claims in values_by_field.items():
        first_value = field_claims[0].normalized_value
        if any(claim.normalized_value != first_value for claim in field_claims[1:]):
            findings.append(_conflicting_values_finding(field_path, field_claims))
            continue
        _, _, property_name = field_path.partition(".")
        properties[property_name] = field_claims[0].normalized_value
        selected_claims.extend(field_claims)
    return properties, selected_claims, findings


def _conflicting_values_finding(
    field_path: str,
    claims: list[NormalizedAttributeClaim],
) -> ValidationFinding:
    return ValidationFinding(
        code="conflicting_normalized_property_values",
        severity=FindingSeverity.WARNING,
        message=(
            "Multiple normalized values exist for one canonical property; "
            "the property candidate remains unresolved for conflict handling."
        ),
        subject_type="attribute_proposal",
        proposal_id=claims[0].attribute_proposal_id,
        field_path=field_path,
        evidence_ids=[
            evidence_id for claim in claims for evidence_id in claim.evidence_ids
        ],
        remediation_hint="Resolve the competing claims through the conflict review workflow.",
    )


def _typed_property_findings(
    claims: list[NormalizedAttributeClaim], error: ValidationError
) -> list[ValidationFinding]:
    evidence_ids = [evidence_id for claim in claims for evidence_id in claim.evidence_ids]
    findings: list[ValidationFinding] = []
    for item in error.errors():
        location = item["loc"]
        field_path = f"properties.{location[0]}" if location else "properties"
        findings.append(
            ValidationFinding(
                code="incomplete_or_invalid_typed_properties",
                severity=FindingSeverity.ERROR,
                message=(
                    "Normalized claims do not satisfy the typed canonical property "
                    "contract; no property candidate was created."
                ),
                subject_type="entity_property_candidate",
                proposal_id=claims[0].attribute_proposal_id,
                field_path=field_path,
                evidence_ids=evidence_ids,
                remediation_hint="Supply the required valid property claim from evidence.",
            )
        )
    return findings


__all__ = [
    "TypedProperties",
    "TypedPropertyCandidate",
    "TypedPropertyCompilationResult",
    "compile_typed_property_candidates",
]
