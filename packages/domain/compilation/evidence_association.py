"""Exact property and relationship evidence association for resolved facts."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.domain.compilation.contracts import CompilationInput
from packages.domain.compilation.entity_resolution import (
    EntityResolutionResult,
    EntityResolutionStatus,
)
from packages.domain.compilation.normalization import (
    NormalizationResult,
    NormalizationStatus,
    NormalizedAttributeClaim,
)
from packages.domain.compilation.relationship_resolution import RelationshipCompilationResult
from packages.domain.evidence import Evidence, FactAttribution
from packages.domain.validation import FindingSeverity, ValidationFinding


class EvidenceAssociationResult(BaseModel):
    """Exact evidence attribution for resolved property or relationship facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_attributions: tuple[FactAttribution, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()


def associate_property_evidence(
    compilation_input: CompilationInput,
    normalization_result: NormalizationResult,
    resolution_result: EntityResolutionResult,
) -> EvidenceAssociationResult:
    """Create exact property attributions without treating entity evidence as fact evidence."""

    findings = list(resolution_result.findings)
    claims_by_id = {
        claim.attribute_proposal_id: claim
        for claim in normalization_result.claims
        if claim.status is NormalizationStatus.NORMALIZED
    }
    proposal_evidence = {
        proposal.proposal_id: tuple(proposal.evidence)
        for proposal in compilation_input.extraction_result.attribute_proposals
    }
    attributions: list[FactAttribution] = []

    for resolution in resolution_result.resolutions:
        if resolution.status not in {
            EntityResolutionStatus.MATCHED_EXISTING,
            EntityResolutionStatus.NEW_CANDIDATE,
        }:
            continue
        property_claims = _property_claims_for_resolution(resolution, claims_by_id)
        for field_path, field_claims in property_claims.items():
            evidence, finding = _verify_property_evidence(
                field_path,
                field_claims,
                proposal_evidence,
                compilation_input,
            )
            if finding is not None:
                findings.append(finding)
                continue
            attributions.extend(
                FactAttribution(
                    evidence_id=record.id,
                    fact_kind="property",
                    entity_id=resolution.canonical_entity_id,
                    property_path=field_path,
                )
                for record in evidence
            )

    return EvidenceAssociationResult(
        fact_attributions=tuple(_unique_attributions(attributions)),
        findings=tuple(findings),
    )


def associate_relationship_evidence(
    compilation_input: CompilationInput,
    relationship_result: RelationshipCompilationResult,
) -> EvidenceAssociationResult:
    """Attach only each accepted relationship proposal's exact current evidence."""

    findings = list(relationship_result.findings)
    proposals = {
        proposal.proposal_id: proposal
        for proposal in compilation_input.extraction_result.relationship_proposals
    }
    attributions: list[FactAttribution] = []

    for source in relationship_result.evidence_sources:
        for proposal_id in source.proposal_ids:
            proposal = proposals.get(proposal_id)
            if proposal is None or any(
                not is_evidence_current_for_input(record, compilation_input)
                for record in proposal.evidence
            ):
                findings.append(
                    _unverifiable_relationship_evidence_finding(
                        proposal_id,
                        tuple(proposal.evidence) if proposal is not None else (),
                    )
                )
                continue
            attributions.extend(
                FactAttribution(
                    evidence_id=record.id,
                    fact_kind="relationship",
                    relationship_id=source.relationship_id,
                )
                for record in proposal.evidence
            )

    return EvidenceAssociationResult(
        fact_attributions=tuple(_unique_attributions(attributions)),
        findings=tuple(findings),
    )


def _property_claims_for_resolution(
    resolution,
    claims_by_id: dict[UUID, NormalizedAttributeClaim],
) -> dict[str, list[NormalizedAttributeClaim]]:
    grouped: dict[str, list[NormalizedAttributeClaim]] = defaultdict(list)
    for proposal_id in resolution.candidate.attribute_proposal_ids:
        claim = claims_by_id.get(proposal_id)
        if claim is not None:
            grouped[claim.field_path].append(claim)
    return grouped


def _verify_property_evidence(
    field_path: str,
    claims: list[NormalizedAttributeClaim],
    proposal_evidence: dict[UUID, tuple[Evidence, ...]],
    compilation_input: CompilationInput,
) -> tuple[tuple[Evidence, ...], ValidationFinding | None]:
    verified: list[Evidence] = []
    for claim in claims:
        evidence = proposal_evidence.get(claim.attribute_proposal_id)
        if evidence is None or {record.id for record in evidence} != set(claim.evidence_ids):
            return (), _unverifiable_evidence_finding(field_path, claims)
        if any(not is_evidence_current_for_input(record, compilation_input) for record in evidence):
            return (), _unverifiable_evidence_finding(field_path, claims)
        verified.extend(evidence)
    if not verified:
        return (), _unverifiable_evidence_finding(field_path, claims)
    return tuple(verified), None


def is_evidence_current_for_input(record: Evidence, compilation_input: CompilationInput) -> bool:
    result = compilation_input.extraction_result
    return (
        record.source_artifact_id == result.artifact_id
        and record.source_artifact_version == str(result.artifact_version_number)
        and record.source_artifact_checksum == result.artifact_checksum
        and record.source_location.is_precise
        and record.extraction_method is result.extraction_method
        and record.extractor_version == result.extractor_version
    )


def _unverifiable_relationship_evidence_finding(
    proposal_id: UUID,
    evidence: tuple[Evidence, ...],
) -> ValidationFinding:
    return ValidationFinding(
        code="unverifiable_relationship_evidence",
        severity=FindingSeverity.ERROR,
        message=(
            "A resolved relationship proposal does not have complete, current evidence; "
            "no fact attribution was created."
        ),
        subject_type="relationship_proposal",
        proposal_id=proposal_id,
        field_path="relationship",
        evidence_ids=[record.id for record in evidence],
        remediation_hint="Attach exact evidence from the current artifact version.",
    )


def _unverifiable_evidence_finding(
    field_path: str, claims: list[NormalizedAttributeClaim]
) -> ValidationFinding:
    return ValidationFinding(
        code="unverifiable_property_evidence",
        severity=FindingSeverity.ERROR,
        message=(
            "A resolved property claim does not have complete, verifiable evidence; "
            "no fact attribution was created."
        ),
        subject_type="entity_property_candidate",
        proposal_id=claims[0].attribute_proposal_id,
        field_path=field_path,
        evidence_ids=[evidence_id for claim in claims for evidence_id in claim.evidence_ids],
        remediation_hint="Attach exact evidence from the current artifact version.",
    )


def _unique_attributions(
    attributions: list[FactAttribution],
) -> list[FactAttribution]:
    unique: dict[tuple[str, UUID | None, str, UUID | None, UUID], FactAttribution] = {}
    for attribution in attributions:
        key = (
            attribution.fact_kind,
            attribution.entity_id,
            attribution.property_path or "",
            attribution.relationship_id,
            attribution.evidence_id,
        )
        unique[key] = attribution
    return list(unique.values())


__all__ = [
    "EvidenceAssociationResult",
    "associate_property_evidence",
    "associate_relationship_evidence",
    "is_evidence_current_for_input",
]
