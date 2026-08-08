"""Proposal-stage contracts that isolate extractors from canonical graph writes."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from packages.domain.entities import CanonicalEntity
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence
from packages.domain.relationships import Relationship


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
    """Batch result returned by a parser/OCR/VLM/LLM; contains proposals only."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    extraction_method: ExtractionMethod
    extractor_version: str
    entity_proposals: list[EntityProposal] = Field(default_factory=list)
    relationship_proposals: list[RelationshipProposal] = Field(default_factory=list)
    attribute_proposals: list[AttributeProposal] = Field(default_factory=list)


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
