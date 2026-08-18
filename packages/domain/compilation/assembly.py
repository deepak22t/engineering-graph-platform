"""Pure assembly of immutable canonical model candidates."""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from packages.domain.compilation.confidence_aggregation import (
    FactConfidenceAggregationResult,
)
from packages.domain.compilation.conflict_detection import ConflictDetectionResult
from packages.domain.compilation.contracts import (
    CompilationInput,
    CompilationResult,
    FactConfidence,
    TypedPropertyFact,
)
from packages.domain.compilation.entity_resolution import (
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
)
from packages.domain.compilation.evidence_association import EvidenceAssociationResult
from packages.domain.compilation.normalization import (
    NormalizationResult,
    NormalizationStatus,
)
from packages.domain.compilation.relationship_resolution import RelationshipCompilationResult
from packages.domain.conflicts import Conflict, ConflictStatus, ConflictType
from packages.domain.entities import (
    CanonicalEntityPayload,
    ComponentEntity,
    ConnectionEntity,
    ContainerEntity,
    DeviceEntity,
    FirewallEntity,
    InterfaceEntity,
    IPAddressEntity,
    NetworkEntity,
    RouteEntity,
    ServiceEntity,
    SiteEntity,
    VlanEntity,
)
from packages.domain.enums import EntityType
from packages.domain.evidence import FactAttribution
from packages.domain.relationships import Relationship
from packages.domain.validation import FindingSeverity, ValidationFinding

FactKey = tuple[str, UUID, str | None]

_ENTITY_MODELS = {
    EntityType.DEVICE: DeviceEntity,
    EntityType.COMPONENT: ComponentEntity,
    EntityType.INTERFACE: InterfaceEntity,
    EntityType.NETWORK: NetworkEntity,
    EntityType.SITE: SiteEntity,
    EntityType.SERVICE: ServiceEntity,
    EntityType.CONTAINER: ContainerEntity,
    EntityType.IP: IPAddressEntity,
    EntityType.VLAN: VlanEntity,
    EntityType.ROUTE: RouteEntity,
    EntityType.FIREWALL: FirewallEntity,
    EntityType.CONNECTION: ConnectionEntity,
}


def assemble_canonical_candidates(
    compilation_input: CompilationInput,
    normalization_result: NormalizationResult,
    resolution_result: EntityResolutionResult,
    relationship_result: RelationshipCompilationResult,
    property_evidence_result: EvidenceAssociationResult,
    relationship_evidence_result: EvidenceAssociationResult,
    property_confidence_result: FactConfidenceAggregationResult,
    relationship_confidence_result: FactConfidenceAggregationResult,
    conflict_result: ConflictDetectionResult,
) -> CompilationResult:
    """Assemble only evidence-complete, resolved, non-conflicting candidates."""

    findings = _unique_findings(
        (
            *compilation_input.extraction_result.findings,
            *normalization_result.findings,
            *resolution_result.findings,
            *relationship_result.findings,
            *property_evidence_result.findings,
            *relationship_evidence_result.findings,
            *property_confidence_result.findings,
            *relationship_confidence_result.findings,
        )
    )
    attributions = _group_attributions(
        (
            *property_evidence_result.fact_attributions,
            *relationship_evidence_result.fact_attributions,
        )
    )
    confidences = _group_confidences(
        (
            *property_confidence_result.fact_confidences,
            *relationship_confidence_result.fact_confidences,
        )
    )
    conflicts = conflict_result.conflicts
    blocked_identity_proposals = _blocked_identity_proposals(conflicts)
    blocked_properties = _blocked_property_keys(conflicts)

    property_facts: list[TypedPropertyFact] = []
    entity_candidates: list[CanonicalEntityPayload] = []
    matched_entity_ids: set[UUID] = set()
    accepted_attributions: list[FactAttribution] = []
    accepted_confidences: list[FactConfidence] = []

    normalized_claims = {
        claim.attribute_proposal_id: claim
        for claim in normalization_result.claims
        if claim.status is NormalizationStatus.NORMALIZED
    }
    snapshot_entities = {
        entity.id: entity for entity in compilation_input.canonical_snapshot.entities
    }

    for resolution in resolution_result.resolutions:
        if resolution.status not in {
            EntityResolutionStatus.MATCHED_EXISTING,
            EntityResolutionStatus.NEW_CANDIDATE,
        }:
            continue
        proposal_id = resolution.candidate.subject_proposal_id
        if proposal_id is not None and proposal_id in blocked_identity_proposals:
            continue
        assert resolution.canonical_entity_id is not None
        entity_id = resolution.canonical_entity_id
        (
            candidate_facts,
            candidate_complete,
            candidate_attributions,
            candidate_confidences,
        ) = _property_facts_for_resolution(
            resolution,
            normalized_claims,
            blocked_properties,
            attributions,
            confidences,
            findings,
        )

        if resolution.status is EntityResolutionStatus.MATCHED_EXISTING:
            existing = snapshot_entities.get(entity_id)
            if existing is None or existing.entity_type is not resolution.candidate.entity_type:
                findings.append(_missing_matched_entity_finding(resolution))
                continue
            matched_entity_ids.add(entity_id)
            if not _matched_properties_preserve_identity(existing, resolution):
                findings.append(_identity_changing_property_finding(resolution))
                continue
            property_facts.extend(candidate_facts)
            accepted_attributions.extend(candidate_attributions)
            accepted_confidences.extend(candidate_confidences)
            continue

        if not candidate_complete:
            continue
        entity = _new_entity_candidate(compilation_input, resolution, findings)
        if entity is not None:
            entity_candidates.append(entity)
            property_facts.extend(candidate_facts)
            accepted_attributions.extend(candidate_attributions)
            accepted_confidences.extend(candidate_confidences)

    new_entity_ids = {entity.id for entity in entity_candidates}
    available_entity_ids = new_entity_ids | set(snapshot_entities)
    relationship_candidates: list[Relationship] = []

    for relationship in relationship_result.candidates:
        if _relationship_is_blocked(relationship, conflicts):
            continue
        if (
            relationship.source_id not in available_entity_ids
            or relationship.target_id not in available_entity_ids
        ):
            findings.append(_missing_relationship_endpoint_finding(relationship))
            continue
        fact_key = ("relationship", relationship.id, None)
        support = _fact_support(
            fact_key,
            attributions,
            confidences,
            findings,
            subject_type="relationship",
            subject_id=relationship.id,
            field_path="relationship",
        )
        if support is None:
            continue
        relationship_candidates.append(relationship)
        accepted_attributions.extend(support[0])
        accepted_confidences.append(support[1])
        if relationship.source_id in snapshot_entities:
            matched_entity_ids.add(relationship.source_id)
        if relationship.target_id in snapshot_entities:
            matched_entity_ids.add(relationship.target_id)

    result = compilation_input.extraction_result
    return CompilationResult(
        artifact_id=result.artifact_id,
        artifact_version_id=result.artifact_version_id,
        artifact_version_number=result.artifact_version_number,
        artifact_kind=result.artifact_kind,
        artifact_checksum=result.artifact_checksum,
        scope=result.scope,
        extraction_method=result.extraction_method,
        extractor_name=result.extractor_name,
        extractor_version=result.extractor_version,
        canonical_entity_candidates=tuple(sorted(entity_candidates, key=lambda item: str(item.id))),
        matched_entity_ids=tuple(sorted(matched_entity_ids, key=str)),
        typed_property_facts=tuple(sorted(property_facts, key=_property_fact_sort_key)),
        canonical_relationship_candidates=tuple(
            sorted(relationship_candidates, key=lambda item: str(item.id))
        ),
        fact_attributions=tuple(_unique_attributions(accepted_attributions)),
        fact_confidences=tuple(_unique_confidences(accepted_confidences)),
        findings=tuple(_unique_findings(findings)),
        conflicts=conflicts,
    )


def _property_facts_for_resolution(
    resolution: EntityResolution,
    normalized_claims,
    blocked_properties: set[tuple[UUID, str]],
    attributions: dict[FactKey, tuple[FactAttribution, ...]],
    confidences: dict[FactKey, tuple[FactConfidence, ...]],
    findings: list[ValidationFinding],
) -> tuple[
    list[TypedPropertyFact],
    bool,
    list[FactAttribution],
    list[FactConfidence],
]:
    assert resolution.canonical_entity_id is not None
    entity_id = resolution.canonical_entity_id
    claims_by_path: dict[str, list[Any]] = defaultdict(list)
    for attribute_id in resolution.candidate.attribute_proposal_ids:
        claim = normalized_claims.get(attribute_id)
        if claim is not None:
            claims_by_path[claim.field_path].append(claim)

    complete = len(
        {
            claim.attribute_proposal_id
            for claims in claims_by_path.values()
            for claim in claims
        }
    ) == len(set(resolution.candidate.attribute_proposal_ids))
    if not complete:
        findings.append(_missing_candidate_claims_finding(resolution))
    facts: list[TypedPropertyFact] = []
    fact_attributions: list[FactAttribution] = []
    fact_confidences: list[FactConfidence] = []

    for field_path, claims in sorted(claims_by_path.items()):
        if (entity_id, field_path) in blocked_properties:
            complete = False
            continue
        fact_key = ("property", entity_id, field_path)
        support = _fact_support(
            fact_key,
            attributions,
            confidences,
            findings,
            subject_type="canonical_property",
            subject_id=entity_id,
            field_path=field_path,
        )
        if support is None:
            complete = False
            continue
        property_name = field_path.removeprefix("properties.")
        value = getattr(resolution.candidate.properties, property_name)
        facts.append(
            TypedPropertyFact(
                entity_id=entity_id,
                entity_type=resolution.candidate.entity_type,
                field_path=field_path,
                value=value,
                source_attribute_proposal_ids=tuple(
                    claim.attribute_proposal_id for claim in claims
                ),
            )
        )
        fact_attributions.extend(support[0])
        fact_confidences.append(support[1])

    return facts, complete, fact_attributions, fact_confidences


def _matched_properties_preserve_identity(
    existing: CanonicalEntityPayload,
    resolution: EntityResolution,
) -> bool:
    try:
        type(existing)(
            identity=existing.identity,
            display_name=existing.display_name,
            properties=resolution.candidate.properties,
            lifecycle_state=existing.lifecycle_state,
            first_observed_at=existing.first_observed_at,
            last_observed_at=existing.last_observed_at,
            valid_from=existing.valid_from,
            valid_to=existing.valid_to,
            superseded_by=existing.superseded_by,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
    except ValidationError:
        return False
    return True


def _new_entity_candidate(
    compilation_input: CompilationInput,
    resolution: EntityResolution,
    findings: list[ValidationFinding],
) -> CanonicalEntityPayload | None:
    proposal_id = resolution.candidate.subject_proposal_id
    proposals = {
        proposal.proposal_id: proposal
        for proposal in compilation_input.extraction_result.entity_proposals
    }
    proposal = proposals.get(proposal_id)
    if proposal is None or resolution.identity is None or resolution.canonical_entity_id is None:
        findings.append(_missing_entity_proposal_finding(resolution))
        return None

    observed_times = [
        evidence.observed_at or evidence.recorded_at for evidence in proposal.evidence
    ]
    entity_model = _ENTITY_MODELS[resolution.candidate.entity_type]
    try:
        entity = entity_model(
            identity=resolution.identity,
            display_name=proposal.display_name,
            properties=resolution.candidate.properties,
            first_observed_at=min(observed_times),
            last_observed_at=max(observed_times),
            created_at=proposal.created_at,
            updated_at=proposal.created_at,
        )
    except ValidationError:
        findings.append(_invalid_entity_candidate_finding(resolution))
        return None
    if entity.id != resolution.canonical_entity_id:
        findings.append(_inconsistent_entity_id_finding(resolution))
        return None
    return entity


def _fact_support(
    fact_key: FactKey,
    attributions: dict[FactKey, tuple[FactAttribution, ...]],
    confidences: dict[FactKey, tuple[FactConfidence, ...]],
    findings: list[ValidationFinding],
    *,
    subject_type: str,
    subject_id: UUID,
    field_path: str,
) -> tuple[tuple[FactAttribution, ...], FactConfidence] | None:
    fact_attributions = attributions.get(fact_key, ())
    fact_confidences = confidences.get(fact_key, ())
    if fact_attributions and len(fact_confidences) == 1:
        return fact_attributions, fact_confidences[0]
    findings.append(
        ValidationFinding(
            code="incomplete_canonical_fact_support",
            severity=FindingSeverity.ERROR,
            message=(
                "Canonical fact requires exact evidence attribution and one shared-policy "
                "confidence result."
            ),
            subject_type=subject_type,
            subject_id=subject_id,
            field_path=field_path,
            evidence_ids=[item.evidence_id for item in fact_attributions],
            remediation_hint="Complete evidence association and confidence aggregation.",
        )
    )
    return None


def _blocked_identity_proposals(conflicts: tuple[Conflict, ...]) -> set[UUID]:
    return {
        conflict.subject_id
        for conflict in conflicts
        if conflict.status is ConflictStatus.OPEN
        and conflict.conflict_type is ConflictType.IDENTITY
        and conflict.subject_id is not None
    }


def _blocked_property_keys(conflicts: tuple[Conflict, ...]) -> set[tuple[UUID, str]]:
    return {
        (conflict.subject_id, conflict.field_path)
        for conflict in conflicts
        if conflict.status is ConflictStatus.OPEN
        and conflict.conflict_type is ConflictType.PROPERTY
        and conflict.subject_id is not None
        and conflict.field_path is not None
    }


def _relationship_is_blocked(
    relationship: Relationship,
    conflicts: tuple[Conflict, ...],
) -> bool:
    for conflict in conflicts:
        if (
            conflict.status is not ConflictStatus.OPEN
            or conflict.conflict_type is not ConflictType.RELATIONSHIP
        ):
            continue
        if conflict.subject_type == "canonical_relationship":
            if conflict.subject_id == relationship.id:
                return True
            continue
        if conflict.relationship is None or conflict.subject_id is None:
            continue
        relationship_type, _, rule = conflict.relationship.partition(":")
        if relationship_type != relationship.relationship_type.value:
            continue
        if rule == "source_cardinality" and conflict.subject_id == relationship.source_id:
            return True
        if rule == "target_cardinality" and conflict.subject_id == relationship.target_id:
            return True
    return False


def _group_attributions(
    records: Iterable[FactAttribution],
) -> dict[FactKey, tuple[FactAttribution, ...]]:
    grouped: dict[FactKey, dict[UUID, FactAttribution]] = defaultdict(dict)
    for record in records:
        key = _attribution_key(record)
        grouped[key][record.evidence_id] = record
    return {key: tuple(values.values()) for key, values in grouped.items()}


def _group_confidences(
    records: Iterable[FactConfidence],
) -> dict[FactKey, tuple[FactConfidence, ...]]:
    grouped: dict[FactKey, list[FactConfidence]] = defaultdict(list)
    for record in records:
        grouped[_confidence_key(record)].append(record)
    return {key: tuple(values) for key, values in grouped.items()}


def _attribution_key(record: FactAttribution) -> FactKey:
    if record.fact_kind == "property":
        assert record.entity_id is not None
        return "property", record.entity_id, record.property_path
    assert record.relationship_id is not None
    return "relationship", record.relationship_id, None


def _confidence_key(record: FactConfidence) -> FactKey:
    if record.fact_kind == "property":
        assert record.entity_id is not None
        return "property", record.entity_id, record.property_path
    assert record.relationship_id is not None
    return "relationship", record.relationship_id, None


def _unique_attributions(records: Iterable[FactAttribution]) -> list[FactAttribution]:
    unique = {
        (_attribution_key(record), record.evidence_id): record for record in records
    }
    ordered_keys = sorted(
        unique,
        key=lambda item: (*_fact_sort_key(item[0]), str(item[1])),
    )
    return [unique[key] for key in ordered_keys]


def _unique_confidences(records: Iterable[FactConfidence]) -> list[FactConfidence]:
    unique = {_confidence_key(record): record for record in records}
    return [unique[key] for key in sorted(unique, key=_fact_sort_key)]


def _unique_findings(records: Iterable[ValidationFinding]) -> list[ValidationFinding]:
    unique: dict[tuple[Any, ...], ValidationFinding] = {}
    for record in records:
        key = (
            record.code,
            record.severity,
            record.subject_type,
            record.subject_id,
            record.proposal_id,
            record.field_path,
            tuple(record.evidence_ids),
            record.message,
        )
        unique[key] = record
    return list(unique.values())


def _fact_sort_key(key: FactKey) -> tuple[str, str, str]:
    return key[0], str(key[1]), key[2] or ""


def _property_fact_sort_key(fact: TypedPropertyFact) -> tuple[str, str]:
    return str(fact.entity_id), fact.field_path


def _missing_candidate_claims_finding(resolution: EntityResolution) -> ValidationFinding:
    return _resolution_finding(
        resolution,
        "missing_normalized_candidate_claims",
        "Resolved entity candidate has no complete normalized property claims.",
    )


def _missing_entity_proposal_finding(resolution: EntityResolution) -> ValidationFinding:
    return _resolution_finding(
        resolution,
        "missing_entity_proposal",
        "New canonical entity candidate requires its original entity proposal.",
    )


def _invalid_entity_candidate_finding(resolution: EntityResolution) -> ValidationFinding:
    return _resolution_finding(
        resolution,
        "invalid_canonical_entity_candidate",
        "Resolved identity and typed properties cannot form a valid canonical entity.",
    )


def _inconsistent_entity_id_finding(resolution: EntityResolution) -> ValidationFinding:
    return _resolution_finding(
        resolution,
        "inconsistent_internal_entity_id",
        "Canonical entity ID does not match internal typed identity generation.",
    )


def _identity_changing_property_finding(
    resolution: EntityResolution,
) -> ValidationFinding:
    return _resolution_finding(
        resolution,
        "identity_changing_property_update",
        "Proposed properties conflict with the immutable canonical entity identity.",
    )


def _missing_matched_entity_finding(resolution: EntityResolution) -> ValidationFinding:
    return _resolution_finding(
        resolution,
        "missing_matched_canonical_entity",
        "Matched entity resolution must reference the immutable canonical snapshot.",
    )


def _resolution_finding(
    resolution: EntityResolution,
    code: str,
    message: str,
) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=FindingSeverity.ERROR,
        message=message,
        subject_type="entity_resolution",
        subject_id=resolution.canonical_entity_id,
        proposal_id=resolution.candidate.subject_proposal_id,
        field_path="entity",
        evidence_ids=[],
    )


def _missing_relationship_endpoint_finding(
    relationship: Relationship,
) -> ValidationFinding:
    return ValidationFinding(
        code="missing_canonical_relationship_endpoint",
        severity=FindingSeverity.ERROR,
        message="Relationship candidate endpoints must exist in the assembled candidate set.",
        subject_type="relationship",
        subject_id=relationship.id,
        field_path="endpoints",
    )


__all__ = ["assemble_canonical_candidates"]
