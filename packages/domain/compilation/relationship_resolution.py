"""Relationship candidate compilation after endpoint identity resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from packages.domain.compilation.contracts import CompilationInput
from packages.domain.compilation.entity_resolution import (
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
)
from packages.domain.enums import EntityType, RelationshipType
from packages.domain.ids import generate_relationship_id
from packages.domain.normalization import normalize_text
from packages.domain.proposals import RelationshipProposal
from packages.domain.relationship_specs import RELATIONSHIP_SPECS, validate_relationship
from packages.domain.relationships import Relationship
from packages.domain.validation import FindingSeverity, ValidationFinding

_DIRECT_CONNECTION_ARTIFACT_KINDS = frozenset(
    {"cdp_neighbors_detail", "lldp_neighbors_detail"}
)


@dataclass(frozen=True)
class _ResolvedEndpoint:
    """Minimal identity view required by the pure relationship validator."""

    id: UUID
    entity_type: EntityType


class RelationshipEvidenceSource(BaseModel):
    """Proposal IDs whose evidence supports one compiled relationship candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relationship_id: UUID
    proposal_ids: tuple[UUID, ...]


class RelationshipCompilationResult(BaseModel):
    """Validated relationship candidates and findings; never a graph-write request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[Relationship, ...] = ()
    evidence_sources: tuple[RelationshipEvidenceSource, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()

    @model_validator(mode="after")
    def require_one_source_mapping_per_candidate(self) -> "RelationshipCompilationResult":
        candidate_ids = [candidate.id for candidate in self.candidates]
        source_ids = [source.relationship_id for source in self.evidence_sources]
        if candidate_ids != source_ids:
            raise ValueError("Relationship evidence sources must align exactly with candidates.")
        if any(not source.proposal_ids for source in self.evidence_sources):
            raise ValueError("Every relationship candidate requires a source proposal.")
        return self


def compile_relationship_candidates(
    compilation_input: CompilationInput,
    resolution_result: EntityResolutionResult,
) -> RelationshipCompilationResult:
    """Resolve proposal endpoints and validate only safe relationship candidates."""

    findings = list(resolution_result.findings)
    proposal_endpoints = _proposal_endpoints(resolution_result.resolutions)
    canonical_endpoints = _canonical_endpoints(compilation_input)
    accepted: list[Relationship] = []
    source_proposals: dict[UUID, list[UUID]] = {}

    for proposal in compilation_input.extraction_result.relationship_proposals:
        origin_finding = validate_relationship_origin(compilation_input, proposal)
        if origin_finding is not None:
            findings.append(origin_finding)
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
            findings.append(_unresolved_endpoint_finding(proposal))
            continue

        attributes, attribute_finding = normalize_relationship_attributes(proposal)
        if attribute_finding is not None:
            findings.append(attribute_finding)
            continue
        source, target = _canonicalize_symmetric_endpoints(
            proposal.relationship_type, source, target
        )
        relationship = Relationship(
            id=generate_relationship_id(proposal.relationship_type, source.id, target.id),
            relationship_type=proposal.relationship_type,
            source_id=source.id,
            target_id=target.id,
            attributes=attributes,
            created_at=proposal.created_at,
            updated_at=proposal.created_at,
        )
        equivalent = next(
            (
                candidate
                for candidate in accepted
                if candidate.id == relationship.id
                and candidate.attributes == relationship.attributes
            ),
            None,
        )
        if equivalent is not None:
            source_proposals[equivalent.id].append(proposal.proposal_id)
            continue

        validation = validate_relationship(
            relationship,
            source,
            target,
            (*compilation_input.canonical_snapshot.relationships, *accepted),
        )
        if validation:
            findings.extend(validation)
            continue
        accepted.append(relationship)
        source_proposals[relationship.id] = [proposal.proposal_id]

    evidence_sources = tuple(
        RelationshipEvidenceSource(
            relationship_id=candidate.id,
            proposal_ids=tuple(source_proposals[candidate.id]),
        )
        for candidate in accepted
    )
    return RelationshipCompilationResult(
        candidates=tuple(accepted),
        evidence_sources=evidence_sources,
        findings=tuple(findings),
    )


def _proposal_endpoints(
    resolutions: tuple[EntityResolution, ...],
) -> dict[UUID, _ResolvedEndpoint]:
    endpoints: dict[UUID, _ResolvedEndpoint] = {}
    for resolution in resolutions:
        if resolution.status not in {
            EntityResolutionStatus.MATCHED_EXISTING,
            EntityResolutionStatus.NEW_CANDIDATE,
        }:
            continue
        proposal_id = resolution.candidate.subject_proposal_id
        if proposal_id is None or resolution.canonical_entity_id is None:
            continue
        endpoints[proposal_id] = _ResolvedEndpoint(
            id=resolution.canonical_entity_id,
            entity_type=resolution.candidate.entity_type,
        )
    return endpoints


def _canonical_endpoints(compilation_input: CompilationInput) -> dict[UUID, _ResolvedEndpoint]:
    return {
        entity.id: _ResolvedEndpoint(id=entity.id, entity_type=entity.entity_type)
        for entity in compilation_input.canonical_snapshot.entities
    }


def _resolve_endpoint(
    proposal_id: UUID | None,
    canonical_id: UUID | None,
    proposal_endpoints: dict[UUID, _ResolvedEndpoint],
    canonical_endpoints: dict[UUID, _ResolvedEndpoint],
) -> _ResolvedEndpoint | None:
    if proposal_id is not None and canonical_id is None:
        return proposal_endpoints.get(proposal_id)
    if canonical_id is not None and proposal_id is None:
        return canonical_endpoints.get(canonical_id)
    return None


def validate_relationship_origin(
    compilation_input: CompilationInput,
    proposal: RelationshipProposal,
) -> ValidationFinding | None:
    if (
        proposal.relationship_type is RelationshipType.CONNECTED_TO
        and compilation_input.extraction_result.artifact_kind
        not in _DIRECT_CONNECTION_ARTIFACT_KINDS
    ):
        return ValidationFinding(
            code="unsupported_connected_to_artifact",
            severity=FindingSeverity.ERROR,
            message=(
                "CONNECTED_TO requires a direct CDP or LLDP neighbor-detail assertion."
            ),
            subject_type="relationship_proposal",
            proposal_id=proposal.proposal_id,
            field_path="relationship_type",
            evidence_ids=[record.id for record in proposal.evidence],
            remediation_hint="Provide direct CDP/LLDP relationship evidence; do not infer a link.",
        )
    return None


def normalize_relationship_attributes(
    proposal: RelationshipProposal,
) -> tuple[dict[str, Any], ValidationFinding | None]:
    attributes = dict(proposal.proposed_attributes)
    if proposal.relationship_type is RelationshipType.CONNECTED_TO:
        try:
            for field_name in ("medium", "state"):
                if field_name in attributes:
                    attributes[field_name] = normalize_text(attributes[field_name])
            if "capacity_bps" in attributes and (
                isinstance(attributes["capacity_bps"], bool)
                or not isinstance(attributes["capacity_bps"], int)
                or attributes["capacity_bps"] <= 0
            ):
                raise ValueError("capacity_bps must be a positive integer.")
        except ValueError as error:
            return {}, ValidationFinding(
                code="invalid_relationship_attributes",
                severity=FindingSeverity.ERROR,
                message=f"Relationship attributes cannot be safely normalized: {error}",
                subject_type="relationship_proposal",
                proposal_id=proposal.proposal_id,
                field_path="attributes",
                evidence_ids=[record.id for record in proposal.evidence],
            )
    return attributes, None


def _canonicalize_symmetric_endpoints(
    relationship_type: RelationshipType,
    source: _ResolvedEndpoint,
    target: _ResolvedEndpoint,
) -> tuple[_ResolvedEndpoint, _ResolvedEndpoint]:
    if RELATIONSHIP_SPECS[relationship_type].symmetric and str(source.id) > str(target.id):
        return target, source
    return source, target


def _unresolved_endpoint_finding(proposal: RelationshipProposal) -> ValidationFinding:
    return ValidationFinding(
        code="unresolved_relationship_endpoint",
        severity=FindingSeverity.ERROR,
        message=(
            "Relationship endpoints must resolve to canonical identities before a "
            "relationship candidate can be created."
        ),
        subject_type="relationship_proposal",
        proposal_id=proposal.proposal_id,
        field_path="endpoints",
        evidence_ids=[record.id for record in proposal.evidence],
        remediation_hint="Resolve both endpoint identities from supported evidence.",
    )


__all__ = [
    "RelationshipCompilationResult",
    "RelationshipEvidenceSource",
    "compile_relationship_candidates",
    "normalize_relationship_attributes",
    "validate_relationship_origin",
]
