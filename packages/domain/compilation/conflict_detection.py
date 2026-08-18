"""Evidence-preserving conflict detection before canonical model assembly."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.domain.compilation.contracts import (
    CanonicalSnapshot,
    CompilationInput,
)
from packages.domain.compilation.entity_resolution import (
    EntityResolutionResult,
    EntityResolutionStatus,
)
from packages.domain.compilation.normalization import (
    NormalizationResult,
    NormalizationStatus,
)
from packages.domain.compilation.relationship_resolution import (
    normalize_relationship_attributes,
    validate_relationship_origin,
)
from packages.domain.conflicts import CompetingClaim, Conflict, ConflictType
from packages.domain.enums import EntityType
from packages.domain.ids import generate_relationship_id
from packages.domain.proposals import AttributeProposal, ExtractionResult
from packages.domain.relationship_specs import RELATIONSHIP_SPECS, validate_relationship
from packages.domain.relationships import Relationship


@dataclass(frozen=True)
class _Claim:
    value: object
    evidence_ids: tuple[UUID, ...]
    source_method: str | None


@dataclass(frozen=True)
class _Endpoint:
    id: UUID
    entity_type: EntityType


@dataclass(frozen=True)
class _RelationshipClaim:
    relationship: Relationship
    evidence_ids: tuple[UUID, ...]
    source_method: str | None


class ConflictDetectionResult(BaseModel):
    """Conflicts found without choosing, mutating, or discarding a claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conflicts: tuple[Conflict, ...] = ()


def detect_property_conflicts(
    extraction_result: ExtractionResult,
    normalization_result: NormalizationResult,
    resolution_result: EntityResolutionResult,
    canonical_snapshot: CanonicalSnapshot | None = None,
) -> ConflictDetectionResult:
    """Detect incompatible normalized values for one resolved canonical property."""

    canonical_ids_by_proposal = {
        resolution.candidate.subject_proposal_id: resolution.canonical_entity_id
        for resolution in resolution_result.resolutions
        if resolution.status
        in {
            EntityResolutionStatus.MATCHED_EXISTING,
            EntityResolutionStatus.NEW_CANDIDATE,
        }
        and resolution.candidate.subject_proposal_id is not None
        and resolution.canonical_entity_id is not None
    }
    proposals_by_id = {
        proposal.proposal_id: proposal for proposal in extraction_result.attribute_proposals
    }
    claims_by_fact: dict[tuple[UUID, str], list[_Claim]] = defaultdict(list)

    for claim in normalization_result.claims:
        if claim.status is not NormalizationStatus.NORMALIZED:
            continue
        entity_id = claim.subject_canonical_id
        if entity_id is None and claim.subject_proposal_id is not None:
            entity_id = canonical_ids_by_proposal.get(claim.subject_proposal_id)
        proposal = proposals_by_id.get(claim.attribute_proposal_id)
        if entity_id is None or proposal is None:
            continue
        claims_by_fact[(entity_id, claim.field_path)].append(
            _proposal_claim(claim.normalized_value, proposal)
        )

    if canonical_snapshot is not None:
        _add_existing_property_claims(claims_by_fact, canonical_snapshot)

    conflicts = [
        _fact_conflict(
            subject_type="canonical_entity",
            subject_id=entity_id,
            field_path=field_path,
            relationship=None,
            conflict_type=ConflictType.PROPERTY,
            claims=claims,
        )
        for (entity_id, field_path), claims in sorted(
            claims_by_fact.items(), key=lambda item: (str(item[0][0]), item[0][1])
        )
        if _has_competing_values(claims)
    ]
    return ConflictDetectionResult(conflicts=tuple(conflicts))


def detect_identity_conflicts(
    extraction_result: ExtractionResult,
    resolution_result: EntityResolutionResult,
) -> ConflictDetectionResult:
    """Represent ambiguous entity resolution without selecting a plausible identity."""

    entity_proposals = {
        proposal.proposal_id: proposal for proposal in extraction_result.entity_proposals
    }
    attribute_proposals = {
        proposal.proposal_id: proposal for proposal in extraction_result.attribute_proposals
    }
    conflicts: list[Conflict] = []

    for resolution in resolution_result.resolutions:
        if resolution.status is not EntityResolutionStatus.AMBIGUOUS:
            continue
        proposal_id = resolution.candidate.subject_proposal_id
        if proposal_id is None:
            continue
        evidence_ids: list[UUID] = []
        entity_proposal = entity_proposals.get(proposal_id)
        if entity_proposal is not None:
            evidence_ids.extend(record.id for record in entity_proposal.evidence)
        for attribute_id in resolution.candidate.attribute_proposal_ids:
            attribute = attribute_proposals.get(attribute_id)
            if attribute is not None:
                evidence_ids.extend(record.id for record in attribute.evidence)
        unique_evidence_ids = tuple(dict.fromkeys(evidence_ids))
        if not unique_evidence_ids:
            continue
        claims = [
            _Claim(
                value=entity_id,
                evidence_ids=unique_evidence_ids,
                source_method=(
                    entity_proposal.extraction_method.value
                    if entity_proposal is not None
                    else None
                ),
            )
            for entity_id in resolution.plausible_entity_ids
        ]
        conflicts.append(
            _fact_conflict(
                subject_type="entity_proposal",
                subject_id=proposal_id,
                field_path="identity",
                relationship=None,
                conflict_type=ConflictType.IDENTITY,
                claims=claims,
            )
        )

    return ConflictDetectionResult(conflicts=tuple(conflicts))


def detect_relationship_conflicts(
    compilation_input: CompilationInput,
    resolution_result: EntityResolutionResult,
) -> ConflictDetectionResult:
    """Detect incompatible resolved relationship claims without choosing a winner."""

    claims = _resolved_relationship_claims(compilation_input, resolution_result)
    conflicts = [
        *_relationship_attribute_conflicts(claims),
        *_relationship_cardinality_conflicts(claims),
    ]
    return ConflictDetectionResult(conflicts=tuple(conflicts))


def detect_conflicts(
    compilation_input: CompilationInput,
    normalization_result: NormalizationResult,
    resolution_result: EntityResolutionResult,
) -> ConflictDetectionResult:
    """Run all current conflict checks before canonical candidate assembly."""

    result = compilation_input.extraction_result
    conflicts = (
        *detect_property_conflicts(
            result,
            normalization_result,
            resolution_result,
            compilation_input.canonical_snapshot,
        ).conflicts,
        *detect_identity_conflicts(result, resolution_result).conflicts,
        *detect_relationship_conflicts(compilation_input, resolution_result).conflicts,
    )
    return ConflictDetectionResult(conflicts=tuple(conflicts))


def _proposal_claim(value: object, proposal: AttributeProposal) -> _Claim:
    return _Claim(
        value=value,
        evidence_ids=tuple(record.id for record in proposal.evidence),
        source_method=proposal.extraction_method.value,
    )


def _add_existing_property_claims(
    claims_by_fact: dict[tuple[UUID, str], list[_Claim]],
    snapshot: CanonicalSnapshot,
) -> None:
    entities = {entity.id: entity for entity in snapshot.entities}
    for entity_id, field_path in tuple(claims_by_fact):
        entity = entities.get(entity_id)
        if entity is None:
            continue
        value = _canonical_property_value(entity, field_path)
        evidence_ids = tuple(
            dict.fromkeys(
                attribution.evidence_id
                for attribution in snapshot.fact_attributions
                if attribution.fact_kind == "property"
                and attribution.entity_id == entity_id
                and attribution.property_path == field_path
            )
        )
        if value is not None and evidence_ids:
            claims_by_fact[(entity_id, field_path)].append(
                _Claim(value=value, evidence_ids=evidence_ids, source_method=None)
            )


def _canonical_property_value(entity, field_path: str) -> object | None:
    prefix = "properties."
    if not field_path.startswith(prefix):
        return None
    field_name = field_path[len(prefix) :]
    if "." in field_name:
        return None
    return getattr(entity.properties, field_name, None)


def _resolved_relationship_claims(
    compilation_input: CompilationInput,
    resolution_result: EntityResolutionResult,
) -> tuple[_RelationshipClaim, ...]:
    proposal_endpoints = {
        resolution.candidate.subject_proposal_id: _Endpoint(
            id=resolution.canonical_entity_id,
            entity_type=resolution.candidate.entity_type,
        )
        for resolution in resolution_result.resolutions
        if resolution.status
        in {
            EntityResolutionStatus.MATCHED_EXISTING,
            EntityResolutionStatus.NEW_CANDIDATE,
        }
        and resolution.candidate.subject_proposal_id is not None
        and resolution.canonical_entity_id is not None
    }
    canonical_endpoints = {
        entity.id: _Endpoint(id=entity.id, entity_type=entity.entity_type)
        for entity in compilation_input.canonical_snapshot.entities
    }
    claims: list[_RelationshipClaim] = []

    for proposal in compilation_input.extraction_result.relationship_proposals:
        if validate_relationship_origin(compilation_input, proposal) is not None:
            continue
        source = _resolve_endpoint(
            proposal.source_proposal_id,
            proposal.source_canonical_id,
            proposal_endpoints,
            canonical_endpoints,
        )
        target = _resolve_endpoint(
            proposal.target_proposal_id,
            proposal.target_canonical_id,
            proposal_endpoints,
            canonical_endpoints,
        )
        if source is None or target is None:
            continue
        attributes, finding = normalize_relationship_attributes(proposal)
        if finding is not None:
            continue
        source, target = _canonicalize_endpoints(proposal.relationship_type, source, target)
        relationship = Relationship(
            id=generate_relationship_id(proposal.relationship_type, source.id, target.id),
            relationship_type=proposal.relationship_type,
            source_id=source.id,
            target_id=target.id,
            attributes=attributes,
            created_at=proposal.created_at,
            updated_at=proposal.created_at,
        )
        if validate_relationship(relationship, source, target, ()):
            continue
        claims.append(
            _RelationshipClaim(
                relationship=relationship,
                evidence_ids=tuple(record.id for record in proposal.evidence),
                source_method=proposal.extraction_method.value,
            )
        )

    existing_evidence = _existing_relationship_evidence(compilation_input.canonical_snapshot)
    for relationship in compilation_input.canonical_snapshot.relationships:
        evidence_ids = existing_evidence.get(relationship.id, ())
        source = canonical_endpoints.get(relationship.source_id)
        target = canonical_endpoints.get(relationship.target_id)
        if not evidence_ids or source is None or target is None:
            continue
        source, target = _canonicalize_endpoints(
            relationship.relationship_type, source, target
        )
        normalized_relationship = relationship.model_copy(
            update={"source_id": source.id, "target_id": target.id}
        )
        if validate_relationship(normalized_relationship, source, target, ()):
            continue
        claims.append(
            _RelationshipClaim(
                relationship=normalized_relationship,
                evidence_ids=evidence_ids,
                source_method=None,
            )
        )

    return tuple(claims)


def _resolve_endpoint(
    proposal_id: UUID | None,
    canonical_id: UUID | None,
    proposal_endpoints: dict[UUID, _Endpoint],
    canonical_endpoints: dict[UUID, _Endpoint],
) -> _Endpoint | None:
    if proposal_id is not None and canonical_id is None:
        return proposal_endpoints.get(proposal_id)
    if canonical_id is not None and proposal_id is None:
        return canonical_endpoints.get(canonical_id)
    return None


def _canonicalize_endpoints(relationship_type, source, target):
    spec = RELATIONSHIP_SPECS[relationship_type]
    if spec.symmetric and str(source.id) > str(target.id):
        return target, source
    return source, target


def _existing_relationship_evidence(
    snapshot: CanonicalSnapshot,
) -> dict[UUID, tuple[UUID, ...]]:
    evidence: dict[UUID, list[UUID]] = defaultdict(list)
    for attribution in snapshot.fact_attributions:
        if attribution.fact_kind == "relationship" and attribution.relationship_id is not None:
            evidence[attribution.relationship_id].append(attribution.evidence_id)
    return {
        relationship_id: tuple(dict.fromkeys(evidence_ids))
        for relationship_id, evidence_ids in evidence.items()
    }


def _relationship_attribute_conflicts(
    claims: tuple[_RelationshipClaim, ...],
) -> list[Conflict]:
    grouped: dict[tuple[object, UUID, UUID], list[_RelationshipClaim]] = defaultdict(list)
    for claim in claims:
        relationship = claim.relationship
        grouped[
            (
                relationship.relationship_type,
                relationship.source_id,
                relationship.target_id,
            )
        ].append(claim)

    conflicts: list[Conflict] = []
    for (relationship_type, source_id, target_id), grouped_claims in sorted(
        grouped.items(),
        key=lambda item: (item[0][0].value, str(item[0][1]), str(item[0][2])),
    ):
        fact_claims = [
            _Claim(
                value=dict(claim.relationship.attributes),
                evidence_ids=claim.evidence_ids,
                source_method=claim.source_method,
            )
            for claim in grouped_claims
        ]
        if not _has_competing_values(fact_claims):
            continue
        conflicts.append(
            _fact_conflict(
                subject_type="canonical_relationship",
                subject_id=generate_relationship_id(
                    relationship_type, source_id, target_id
                ),
                field_path=None,
                relationship=(
                    f"{relationship_type.value}:{source_id}:{target_id}:attributes"
                ),
                conflict_type=ConflictType.RELATIONSHIP,
                claims=fact_claims,
            )
        )
    return conflicts


def _relationship_cardinality_conflicts(
    claims: tuple[_RelationshipClaim, ...],
) -> list[Conflict]:
    conflicts: list[Conflict] = []
    by_type: dict[object, list[_RelationshipClaim]] = defaultdict(list)
    for claim in claims:
        by_type[claim.relationship.relationship_type].append(claim)

    for relationship_type, typed_claims in sorted(
        by_type.items(), key=lambda item: item[0].value
    ):
        spec = RELATIONSHIP_SPECS[relationship_type]
        if spec.max_source_occurrences == 1:
            conflicts.extend(
                _endpoint_cardinality_conflicts(
                    relationship_type,
                    typed_claims,
                    dimension="source",
                )
            )
        if spec.max_target_occurrences == 1:
            conflicts.extend(
                _endpoint_cardinality_conflicts(
                    relationship_type,
                    typed_claims,
                    dimension="target",
                )
            )
    return conflicts


def _endpoint_cardinality_conflicts(
    relationship_type,
    claims: list[_RelationshipClaim],
    *,
    dimension: str,
) -> list[Conflict]:
    grouped: dict[UUID, list[_RelationshipClaim]] = defaultdict(list)
    for claim in claims:
        relationship = claim.relationship
        subject_id = (
            relationship.source_id if dimension == "source" else relationship.target_id
        )
        grouped[subject_id].append(claim)

    conflicts: list[Conflict] = []
    for subject_id, grouped_claims in sorted(grouped.items(), key=lambda item: str(item[0])):
        fact_claims = [
            _Claim(
                value=(
                    claim.relationship.target_id
                    if dimension == "source"
                    else claim.relationship.source_id
                ),
                evidence_ids=claim.evidence_ids,
                source_method=claim.source_method,
            )
            for claim in grouped_claims
        ]
        if not _has_competing_values(fact_claims):
            continue
        conflicts.append(
            _fact_conflict(
                subject_type="canonical_entity",
                subject_id=subject_id,
                field_path=None,
                relationship=f"{relationship_type.value}:{dimension}_cardinality",
                conflict_type=ConflictType.RELATIONSHIP,
                claims=fact_claims,
            )
        )
    return conflicts


def _has_competing_values(claims: list[_Claim]) -> bool:
    return len({_serialized_value(claim.value) for claim in claims}) > 1


def _fact_conflict(
    *,
    subject_type: str,
    subject_id: UUID,
    field_path: str | None,
    relationship: str | None,
    conflict_type: ConflictType,
    claims: list[_Claim],
) -> Conflict:
    return Conflict(
        subject_type=subject_type,
        subject_id=subject_id,
        field_path=field_path,
        relationship=relationship,
        competing_claims=_competing_claims(claims),
        conflict_type=conflict_type,
    )


def _competing_claims(claims: list[_Claim]) -> list[CompetingClaim]:
    evidence_by_value: dict[str, list[UUID]] = defaultdict(list)
    methods_by_value: dict[str, set[str]] = defaultdict(set)
    for claim in claims:
        serialized_value = _serialized_value(claim.value)
        evidence_by_value[serialized_value].extend(claim.evidence_ids)
        if claim.source_method is not None:
            methods_by_value[serialized_value].add(claim.source_method)

    competing_claims: list[CompetingClaim] = []
    for value, evidence_ids in sorted(evidence_by_value.items()):
        methods = methods_by_value[value]
        competing_claims.append(
            CompetingClaim(
                value=value,
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                source_method=next(iter(methods)) if len(methods) == 1 else None,
            )
        )
    return competing_claims


def _serialized_value(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


__all__ = [
    "ConflictDetectionResult",
    "detect_conflicts",
    "detect_identity_conflicts",
    "detect_property_conflicts",
    "detect_relationship_conflicts",
]
