"""Proposal-stage contracts that isolate extractors from canonical graph writes."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.domain.entities import CanonicalEntity
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence
from packages.domain.relationships import Relationship
from packages.domain.scope import GraphScope
from packages.domain.validation import ValidationFinding


class ProposalStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ProposalBase(BaseModel):
    """Extractor output only; never a graph-persistence contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    proposal_id: UUID = Field(default_factory=uuid4)
    extraction_method: ExtractionMethod
    extractor_version: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EntityProposal(ProposalBase):
    entity_type: EntityType
    display_name: str = Field(min_length=1)
    proposed_properties: dict[str, Any] = Field(default_factory=dict)


class RelationshipProposal(ProposalBase):
    relationship_type: RelationshipType
    source_proposal_id: UUID | None = None
    source_canonical_id: UUID | None = None
    target_proposal_id: UUID | None = None
    target_canonical_id: UUID | None = None
    proposed_attributes: dict[str, Any] = Field(default_factory=dict)


class AttributeProposal(ProposalBase):
    subject_proposal_id: UUID | None = None
    subject_canonical_id: UUID | None = None
    field_path: str = Field(min_length=1)
    proposed_value: Any


class ExtractionResult(BaseModel):
    """Typed, immutable extraction output for one exact immutable artifact version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    artifact_version_id: UUID
    artifact_version_number: int = Field(ge=1)
    artifact_kind: str = Field(min_length=1, max_length=128)
    artifact_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    scope: GraphScope
    extraction_method: ExtractionMethod
    extractor_name: str = Field(min_length=1, max_length=255)
    extractor_version: str = Field(min_length=1, max_length=255)
    entity_proposals: list[EntityProposal] = Field(default_factory=list)
    relationship_proposals: list[RelationshipProposal] = Field(default_factory=list)
    attribute_proposals: list[AttributeProposal] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    evidence_records: list[Evidence] = Field(default_factory=list)

    @field_validator("artifact_kind", "extractor_name", "extractor_version")
    @classmethod
    def reject_blank_metadata(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("metadata value must not be blank.")
        return value


# Canonical aliases intentionally live beside proposal contracts, never inherit from them.
CanonicalRelationship = Relationship

__all__ = [
    "AttributeProposal",
    "CanonicalEntity",
    "CanonicalRelationship",
    "EntityProposal",
    "ExtractionResult",
    "ProposalStatus",
    "RelationshipProposal",
]
