"""Tests for proposal versus canonical contracts."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.proposals import EntityProposal, ExtractionResult, ProposalStatus


def evidence():
    return Evidence(
        source_artifact_id=uuid.uuid4(),
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        observed_at=datetime.now(timezone.utc),
        confidence=0.9,
    )


def test_proposal_id_is_separate_from_canonical_identity_and_requires_evidence():
    proposal = EntityProposal(
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence()],
        entity_type=EntityType.DEVICE,
        display_name="router-01",
    )
    assert proposal.proposal_id != uuid.uuid4()
    assert proposal.status == ProposalStatus.PENDING
    with pytest.raises(ValidationError):
        EntityProposal(
            extraction_method=ExtractionMethod.LLM,
            extractor_version="1",
            evidence=[],
            entity_type=EntityType.DEVICE,
            display_name="router",
        )


def test_extraction_result_contains_only_proposals():
    proposal = EntityProposal(
        extraction_method=ExtractionMethod.OCR,
        extractor_version="1",
        evidence=[evidence()],
        entity_type=EntityType.DEVICE,
        display_name="router",
    )
    result = ExtractionResult(
        extraction_method=ExtractionMethod.OCR, extractor_version="1", entity_proposals=[proposal]
    )
    assert result.entity_proposals == [proposal]
