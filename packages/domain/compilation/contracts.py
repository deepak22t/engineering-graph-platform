"""Immutable input and output contracts for pure semantic compilation."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from packages.domain.confidence import Confidence
from packages.domain.conflicts import Conflict, ConflictStatus
from packages.domain.entities import CanonicalEntityPayload
from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import FactAttribution
from packages.domain.immutability import deep_freeze
from packages.domain.proposals import ExtractionResult
from packages.domain.relationships import Relationship
from packages.domain.scope import GraphScope
from packages.domain.validation import FindingSeverity, ValidationFinding


class CanonicalSnapshot(BaseModel):
    """Read-only same-scope canonical state supplied to semantic compilation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: GraphScope
    entities: tuple[CanonicalEntityPayload, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    fact_attributions: tuple[FactAttribution, ...] = ()

    @model_validator(mode="after")
    def require_entities_in_snapshot_scope(self) -> "CanonicalSnapshot":
        out_of_scope = [entity.id for entity in self.entities if entity.scope != self.scope]
        if out_of_scope:
            raise ValueError("Canonical snapshot entities must all use its scope.")
        entity_ids = [entity.id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("Canonical snapshot must not contain duplicate entity IDs.")
        return self


class CompilationInput(BaseModel):
    """One extraction batch and the immutable canonical state used to compile it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    extraction_result: ExtractionResult
    canonical_snapshot: CanonicalSnapshot

    @model_validator(mode="after")
    def require_matching_scope(self) -> "CompilationInput":
        if self.extraction_result.scope != self.canonical_snapshot.scope:
            raise ValueError("Extraction result and canonical snapshot scopes must match.")
        return self


class FactConfidence(BaseModel):
    """Confidence attached to exactly one compiled property or relationship fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence: Confidence
    fact_kind: Literal["property", "relationship"]
    entity_id: UUID | None = None
    property_path: str | None = None
    relationship_id: UUID | None = None

    @model_validator(mode="after")
    def require_exact_fact_target(self) -> "FactConfidence":
        property_target = self.entity_id is not None and self.property_path is not None
        relationship_target = self.relationship_id is not None
        if self.fact_kind == "property" and property_target and not relationship_target:
            return self
        if self.fact_kind == "relationship" and relationship_target and not property_target:
            return self
        raise ValueError("Fact confidence must point to exactly one declared fact.")


class TypedPropertyFact(BaseModel):
    """One validated canonical property value before persistence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: UUID
    entity_type: EntityType
    field_path: str = Field(pattern=r"^properties\.[A-Za-z_][A-Za-z0-9_]*$")
    value: Any
    source_attribute_proposal_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("value", mode="after")
    @classmethod
    def freeze_value(cls, value: Any) -> Any:
        return deep_freeze(value)


class CompilationResult(BaseModel):
    """Pure semantic-compilation output; never a persistence or graph-write request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    artifact_id: UUID
    artifact_version_id: UUID
    artifact_version_number: int = Field(ge=1)
    artifact_kind: str = Field(min_length=1, max_length=128)
    artifact_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: GraphScope
    extraction_method: ExtractionMethod
    extractor_name: str = Field(min_length=1, max_length=255)
    extractor_version: str = Field(min_length=1, max_length=255)
    canonical_entity_candidates: tuple[CanonicalEntityPayload, ...] = ()
    matched_entity_ids: tuple[UUID, ...] = ()
    typed_property_facts: tuple[TypedPropertyFact, ...] = ()
    canonical_relationship_candidates: tuple[Relationship, ...] = ()
    fact_attributions: tuple[FactAttribution, ...] = ()
    fact_confidences: tuple[FactConfidence, ...] = ()
    findings: tuple[ValidationFinding, ...] = ()
    conflicts: tuple[Conflict, ...] = ()

    @computed_field
    @property
    def review_required(self) -> bool:
        """Return whether unresolved conflicts block affected canonical output."""
        return any(conflict.status is ConflictStatus.OPEN for conflict in self.conflicts)

    @computed_field
    @property
    def fact_support_complete(self) -> bool:
        """Return whether every emitted fact has attribution and one confidence."""
        attribution_keys = {
            _attribution_key(attribution) for attribution in self.fact_attributions
        }
        confidence_keys = [
            _confidence_key(confidence) for confidence in self.fact_confidences
        ]
        required_keys = {
            ("property", fact.entity_id, fact.field_path)
            for fact in self.typed_property_facts
        } | {
            ("relationship", relationship.id, None)
            for relationship in self.canonical_relationship_candidates
        }
        return (
            required_keys == attribution_keys == set(confidence_keys)
            and all(confidence_keys.count(key) == 1 for key in required_keys)
        )

    @computed_field
    @property
    def candidate_references_complete(self) -> bool:
        """Return whether every emitted fact/edge targets an emitted entity reference."""
        new_ids = [entity.id for entity in self.canonical_entity_candidates]
        matched_ids = list(self.matched_entity_ids)
        available_ids = set(new_ids) | set(matched_ids)
        property_keys = [
            (fact.entity_id, fact.field_path) for fact in self.typed_property_facts
        ]
        return (
            len(new_ids) == len(set(new_ids))
            and len(matched_ids) == len(set(matched_ids))
            and set(new_ids).isdisjoint(matched_ids)
            and len(property_keys) == len(set(property_keys))
            and all(fact.entity_id in available_ids for fact in self.typed_property_facts)
            and all(
                relationship.source_id in available_ids
                and relationship.target_id in available_ids
                for relationship in self.canonical_relationship_candidates
            )
        )

    @computed_field
    @property
    def canonical_ready(self) -> bool:
        """Return whether the result is complete and has no blocking issue."""
        return (
            self.fact_support_complete
            and self.candidate_references_complete
            and not self.review_required
            and not any(
                finding.severity is FindingSeverity.ERROR for finding in self.findings
            )
        )

    @classmethod
    def from_input(cls, compilation_input: CompilationInput) -> "CompilationResult":
        """Create an empty result with immutable traceability copied from its input."""
        result = compilation_input.extraction_result
        return cls(
            artifact_id=result.artifact_id,
            artifact_version_id=result.artifact_version_id,
            artifact_version_number=result.artifact_version_number,
            artifact_kind=result.artifact_kind,
            artifact_checksum=result.artifact_checksum,
            scope=result.scope,
            extraction_method=result.extraction_method,
            extractor_name=result.extractor_name,
            extractor_version=result.extractor_version,
        )


def _attribution_key(attribution: FactAttribution) -> tuple[str, UUID, str | None]:
    if attribution.fact_kind == "property":
        assert attribution.entity_id is not None
        return "property", attribution.entity_id, attribution.property_path
    assert attribution.relationship_id is not None
    return "relationship", attribution.relationship_id, None


def _confidence_key(confidence: FactConfidence) -> tuple[str, UUID, str | None]:
    if confidence.fact_kind == "property":
        assert confidence.entity_id is not None
        return "property", confidence.entity_id, confidence.property_path
    assert confidence.relationship_id is not None
    return "relationship", confidence.relationship_id, None


__all__ = [
    "CanonicalSnapshot",
    "CompilationInput",
    "CompilationResult",
    "FactConfidence",
    "TypedPropertyFact",
]
