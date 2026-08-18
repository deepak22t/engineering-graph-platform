"""Fact-level confidence aggregation using the single shared policy."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from packages.domain.compilation.contracts import CompilationInput, FactConfidence
from packages.domain.compilation.evidence_association import (
    EvidenceAssociationResult,
    is_evidence_current_for_input,
)
from packages.domain.confidence import aggregate_confidence
from packages.domain.evidence import Evidence, FactAttribution
from packages.domain.validation import FindingSeverity, ValidationFinding


class FactConfidenceAggregationResult(BaseModel):
    """Reproducible confidence for evidence-backed facts; never a persistence request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_confidences: tuple[FactConfidence, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()


def aggregate_fact_confidences(
    compilation_input: CompilationInput,
    evidence_result: EvidenceAssociationResult,
) -> FactConfidenceAggregationResult:
    """Aggregate each attributed fact with the shared confidence policy only."""

    findings = list(evidence_result.findings)
    evidence_by_id = _evidence_by_id(compilation_input)
    fact_attributions = _group_attributions(evidence_result.fact_attributions)
    fact_confidences: list[FactConfidence] = []

    for fact_key, attributions in sorted(
        fact_attributions.items(), key=lambda item: _fact_sort_key(item[0])
    ):
        evidence = [evidence_by_id.get(attribution.evidence_id) for attribution in attributions]
        if any(
            record is None or not is_evidence_current_for_input(record, compilation_input)
            for record in evidence
        ):
            findings.append(_missing_evidence_finding(attributions))
            continue
        confidence = aggregate_confidence(record for record in evidence if record is not None)
        fact_confidences.append(_fact_confidence(fact_key, confidence))

    return FactConfidenceAggregationResult(
        fact_confidences=tuple(fact_confidences), findings=tuple(findings)
    )


def _evidence_by_id(compilation_input: CompilationInput) -> dict[UUID, Evidence]:
    result = compilation_input.extraction_result
    evidence: dict[UUID, Evidence] = {}
    for record in result.evidence_records:
        evidence[record.id] = record
    for proposal in (
        *result.entity_proposals,
        *result.attribute_proposals,
        *result.relationship_proposals,
    ):
        for record in proposal.evidence:
            evidence[record.id] = record
    return evidence


def _group_attributions(
    attributions: tuple[FactAttribution, ...],
) -> dict[tuple[str, UUID, str | None], list[FactAttribution]]:
    grouped: dict[
        tuple[str, UUID, str | None], dict[UUID, FactAttribution]
    ] = defaultdict(dict)
    for attribution in attributions:
        if attribution.fact_kind == "property":
            fact_key = ("property", attribution.entity_id, attribution.property_path)
        else:
            fact_key = ("relationship", attribution.relationship_id, None)
        grouped[fact_key][attribution.evidence_id] = attribution
    return {fact_key: list(records.values()) for fact_key, records in grouped.items()}


def _fact_confidence(fact_key: tuple[str, UUID, str | None], confidence) -> FactConfidence:
    fact_kind, target_id, property_path = fact_key
    if fact_kind == "property":
        return FactConfidence(
            confidence=confidence,
            fact_kind="property",
            entity_id=target_id,
            property_path=property_path,
        )
    return FactConfidence(
        confidence=confidence,
        fact_kind="relationship",
        relationship_id=target_id,
    )


def _fact_sort_key(fact_key: tuple[str, UUID, str | None]) -> tuple[str, str, str]:
    fact_kind, target_id, property_path = fact_key
    return fact_kind, str(target_id), property_path or ""


def _missing_evidence_finding(attributions: list[FactAttribution]) -> ValidationFinding:
    attribution = attributions[0]
    return ValidationFinding(
        code="missing_attributed_evidence",
        severity=FindingSeverity.ERROR,
        message=(
            "A fact attribution references evidence that is not present in this "
            "compilation input; no confidence was calculated."
        ),
        subject_type="fact_attribution",
        subject_id=attribution.entity_id or attribution.relationship_id,
        field_path=attribution.property_path,
        evidence_ids=[item.evidence_id for item in attributions],
        remediation_hint="Use evidence from the exact immutable artifact version.",
    )


__all__ = ["FactConfidenceAggregationResult", "aggregate_fact_confidences"]
