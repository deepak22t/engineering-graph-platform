"""Pure batch validation for Phase 5 semantic compilation inputs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeAlias
from uuid import UUID

from packages.domain.compilation.contracts import CompilationInput
from packages.domain.compilation.property_contracts import is_canonical_property_path
from packages.domain.enums import EntityType
from packages.domain.evidence import Evidence
from packages.domain.proposals import (
    AttributeProposal,
    EntityProposal,
    ProposalBase,
    RelationshipProposal,
)
from packages.domain.validation import FindingSeverity, ValidationFinding

Proposal: TypeAlias = EntityProposal | AttributeProposal | RelationshipProposal


def validate_proposal_batch(compilation_input: CompilationInput) -> tuple[ValidationFinding, ...]:
    """Return structured findings for invalid cross-proposal compilation input."""
    result = compilation_input.extraction_result
    entity_proposals = {proposal.proposal_id: proposal for proposal in result.entity_proposals}
    snapshot_entities = {
        entity.id: entity for entity in compilation_input.canonical_snapshot.entities
    }
    findings: list[ValidationFinding] = []

    for proposal in result.entity_proposals:
        findings.extend(_validate_proposal_metadata(proposal, result, "entity"))
        if not proposal.display_name.strip():
            findings.append(
                _finding(
                    code="blank_entity_display_name",
                    message="Entity proposal display_name must not be whitespace-only.",
                    subject_type="entity_proposal",
                    proposal_id=proposal.proposal_id,
                    field_path="display_name",
                    evidence_ids=_evidence_ids(proposal.evidence),
                )
            )

    for proposal in result.attribute_proposals:
        findings.extend(_validate_proposal_metadata(proposal, result, "attribute"))
        entity_type = _resolve_attribute_subject(
            proposal, entity_proposals, snapshot_entities, findings
        )
        if entity_type is not None:
            finding = _validate_property_path(proposal, entity_type)
            if finding is not None:
                findings.append(finding)

    for proposal in result.relationship_proposals:
        findings.extend(_validate_proposal_metadata(proposal, result, "relationship"))
        _validate_relationship_endpoint(
            proposal,
            endpoint="source",
            entity_proposals=entity_proposals,
            snapshot_entities=snapshot_entities,
            findings=findings,
        )
        _validate_relationship_endpoint(
            proposal,
            endpoint="target",
            entity_proposals=entity_proposals,
            snapshot_entities=snapshot_entities,
            findings=findings,
        )

    for evidence in result.evidence_records:
        findings.extend(_validate_evidence(evidence, result, "artifact_version", None))

    return tuple(findings)


def _validate_proposal_metadata(
    proposal: ProposalBase,
    result,
    subject_type: str,
) -> list[ValidationFinding]:
    findings = _validate_evidence_collection(
        proposal.evidence,
        result,
        subject_type,
        proposal.proposal_id,
    )
    if proposal.extraction_method is not result.extraction_method:
        findings.append(
            _finding(
                code="proposal_extraction_method_mismatch",
                message="Proposal extraction method must match its extraction result.",
                subject_type=subject_type,
                proposal_id=proposal.proposal_id,
                evidence_ids=_evidence_ids(proposal.evidence),
            )
        )
    if proposal.extractor_version != result.extractor_version:
        findings.append(
            _finding(
                code="proposal_extractor_version_mismatch",
                message="Proposal extractor version must match its extraction result.",
                subject_type=subject_type,
                proposal_id=proposal.proposal_id,
                evidence_ids=_evidence_ids(proposal.evidence),
            )
        )
    return findings


def _validate_evidence_collection(
    evidence_records: Iterable[Evidence],
    result,
    subject_type: str,
    proposal_id: UUID | None,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for evidence in evidence_records:
        findings.extend(_validate_evidence(evidence, result, subject_type, proposal_id))
    return findings


def _validate_evidence(
    evidence: Evidence,
    result,
    subject_type: str,
    proposal_id: UUID | None,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if evidence.source_artifact_id != result.artifact_id:
        findings.append(
            _finding(
                code="evidence_artifact_mismatch",
                message="Evidence must refer to the extraction result artifact ID.",
                subject_type=subject_type,
                proposal_id=proposal_id,
                evidence_ids=(evidence.id,),
            )
        )
    if evidence.source_artifact_version != str(result.artifact_version_number):
        findings.append(
            _finding(
                code="evidence_version_mismatch",
                message="Evidence must refer to the exact extraction result version.",
                subject_type=subject_type,
                proposal_id=proposal_id,
                evidence_ids=(evidence.id,),
            )
        )
    if evidence.source_artifact_checksum != result.artifact_checksum:
        findings.append(
            _finding(
                code="evidence_checksum_mismatch",
                message="Evidence must refer to the exact extraction result checksum.",
                subject_type=subject_type,
                proposal_id=proposal_id,
                evidence_ids=(evidence.id,),
            )
        )
    if not evidence.source_location.is_precise:
        findings.append(
            _finding(
                code="imprecise_evidence_location",
                message="Canonical compilation requires a precise evidence source location.",
                subject_type=subject_type,
                proposal_id=proposal_id,
                evidence_ids=(evidence.id,),
            )
        )
    if evidence.extraction_method is not result.extraction_method:
        findings.append(
            _finding(
                code="evidence_extraction_method_mismatch",
                message="Evidence extraction method must match its extraction result.",
                subject_type=subject_type,
                proposal_id=proposal_id,
                evidence_ids=(evidence.id,),
            )
        )
    if evidence.extractor_version != result.extractor_version:
        findings.append(
            _finding(
                code="evidence_extractor_version_mismatch",
                message="Evidence extractor version must match its extraction result.",
                subject_type=subject_type,
                proposal_id=proposal_id,
                evidence_ids=(evidence.id,),
            )
        )
    return findings


def _resolve_attribute_subject(
    proposal: AttributeProposal,
    entity_proposals: dict[UUID, EntityProposal],
    snapshot_entities: dict[UUID, object],
    findings: list[ValidationFinding],
) -> EntityType | None:
    subject = _resolve_reference(
        proposal_id=proposal.subject_proposal_id,
        canonical_id=proposal.subject_canonical_id,
        proposal_entities=entity_proposals,
        snapshot_entities=snapshot_entities,
        subject_type="attribute_proposal",
        owner_proposal_id=proposal.proposal_id,
        endpoint_name="subject",
        findings=findings,
        evidence_ids=_evidence_ids(proposal.evidence),
    )
    return subject.entity_type if subject is not None else None


def _validate_relationship_endpoint(
    proposal: RelationshipProposal,
    *,
    endpoint: str,
    entity_proposals: dict[UUID, EntityProposal],
    snapshot_entities: dict[UUID, object],
    findings: list[ValidationFinding],
) -> None:
    _resolve_reference(
        proposal_id=getattr(proposal, f"{endpoint}_proposal_id"),
        canonical_id=getattr(proposal, f"{endpoint}_canonical_id"),
        proposal_entities=entity_proposals,
        snapshot_entities=snapshot_entities,
        subject_type="relationship_proposal",
        owner_proposal_id=proposal.proposal_id,
        endpoint_name=endpoint,
        findings=findings,
        evidence_ids=_evidence_ids(proposal.evidence),
    )


def _resolve_reference(
    *,
    proposal_id: UUID | None,
    canonical_id: UUID | None,
    proposal_entities: dict[UUID, EntityProposal],
    snapshot_entities: dict[UUID, object],
    subject_type: str,
    owner_proposal_id: UUID,
    endpoint_name: str,
    findings: list[ValidationFinding],
    evidence_ids: tuple[UUID, ...],
):
    if proposal_id is not None and canonical_id is not None:
        findings.append(
            _finding(
                code="mixed_reference_kind",
                message=f"{endpoint_name} must use either a proposal ID or canonical ID, not both.",
                subject_type=subject_type,
                proposal_id=owner_proposal_id,
                field_path=endpoint_name,
                evidence_ids=evidence_ids,
            )
        )
        return None
    if proposal_id is None and canonical_id is None:
        findings.append(
            _finding(
                code="missing_reference",
                message=f"{endpoint_name} requires a proposal ID or canonical ID.",
                subject_type=subject_type,
                proposal_id=owner_proposal_id,
                field_path=endpoint_name,
                evidence_ids=evidence_ids,
            )
        )
        return None
    if proposal_id is not None:
        entity = proposal_entities.get(proposal_id)
        if entity is None:
            findings.append(
                _finding(
                    code="unknown_proposal_reference",
                    message=f"{endpoint_name} proposal ID does not reference an entity proposal.",
                    subject_type=subject_type,
                    proposal_id=owner_proposal_id,
                    field_path=endpoint_name,
                    evidence_ids=evidence_ids,
                )
            )
        return entity
    entity = snapshot_entities.get(canonical_id)
    if entity is None:
        findings.append(
            _finding(
                code="unknown_canonical_reference",
                message=f"{endpoint_name} canonical ID is not in the same-scope snapshot.",
                subject_type=subject_type,
                proposal_id=owner_proposal_id,
                field_path=endpoint_name,
                evidence_ids=evidence_ids,
            )
        )
    return entity


def _validate_property_path(
    proposal: AttributeProposal,
    entity_type: EntityType,
) -> ValidationFinding | None:
    if not proposal.field_path.startswith("properties."):
        return _finding(
            code="invalid_property_path",
            message="Attribute proposal field_path must name a canonical properties field.",
            subject_type="attribute_proposal",
            proposal_id=proposal.proposal_id,
            field_path=proposal.field_path,
            evidence_ids=_evidence_ids(proposal.evidence),
        )
    if not is_canonical_property_path(entity_type, proposal.field_path):
        return _finding(
            code="noncanonical_property_path",
            message=(
                "Attribute proposal field_path has no typed canonical property contract; "
                "it remains a non-canonical raw claim."
            ),
            subject_type="attribute_proposal",
            proposal_id=proposal.proposal_id,
            field_path=proposal.field_path,
            evidence_ids=_evidence_ids(proposal.evidence),
            severity=FindingSeverity.WARNING,
        )
    return None


def _evidence_ids(evidence_records: Iterable[Evidence]) -> tuple[UUID, ...]:
    return tuple(evidence.id for evidence in evidence_records)


def _finding(
    *,
    code: str,
    message: str,
    subject_type: str,
    proposal_id: UUID | None = None,
    field_path: str | None = None,
    evidence_ids: tuple[UUID, ...] = (),
    severity: FindingSeverity = FindingSeverity.ERROR,
) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=severity,
        message=message,
        subject_type=subject_type,
        proposal_id=proposal_id,
        field_path=field_path,
        evidence_ids=list(evidence_ids),
    )


__all__ = ["validate_proposal_batch"]
