"""Tests for proposal versus canonical contracts."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from packages.domain.enums import EntityType, ExtractionMethod
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.proposals import EntityProposal, ExtractionResult, ProposalStatus
from packages.domain.scope import GraphScope
from packages.domain.validation import FindingSeverity, ValidationFinding

ARTIFACT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SCOPE = GraphScope(
    organization_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    project_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
)
CHECKSUM = "a" * 64


def evidence():
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_location=SourceLocation(line_start=1),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        observed_at=datetime.now(timezone.utc),
        confidence=0.9,
    )


def extraction_result(**overrides):
    values = {
        "artifact_id": ARTIFACT_ID,
        "artifact_version_id": ARTIFACT_VERSION_ID,
        "artifact_version_number": 1,
        "artifact_kind": "cisco_ios_running_config",
        "artifact_checksum": CHECKSUM,
        "scope": SCOPE,
        "extraction_method": ExtractionMethod.DETERMINISTIC_PARSER,
        "extractor_name": "cisco_ios_running_config_parser",
        "extractor_version": "1",
    }
    values.update(overrides)
    return ExtractionResult(**values)


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


def test_extraction_result_is_traceable_to_one_artifact_version_and_scope():
    proposal = EntityProposal(
        extraction_method=ExtractionMethod.OCR,
        extractor_version="1",
        evidence=[evidence()],
        entity_type=EntityType.DEVICE,
        display_name="router",
    )
    finding = ValidationFinding(
        code="unsupported_command",
        severity=FindingSeverity.INFO,
        message="Ignored an unsupported command.",
        subject_type="artifact_version",
    )

    result = extraction_result(entity_proposals=[proposal], findings=[finding])

    assert result.artifact_id == ARTIFACT_ID
    assert result.artifact_version_id == ARTIFACT_VERSION_ID
    assert result.artifact_version_number == 1
    assert result.artifact_checksum == CHECKSUM
    assert result.scope == SCOPE
    assert result.entity_proposals == [proposal]
    assert result.findings == [finding]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("artifact_kind", "   "),
        ("extractor_name", "   "),
        ("extractor_version", "   "),
        ("artifact_checksum", "not-a-sha256"),
        ("artifact_version_number", 0),
    ],
)
def test_extraction_result_rejects_invalid_traceability_metadata(field_name, value):
    with pytest.raises(ValidationError):
        extraction_result(**{field_name: value})


def test_extraction_result_requires_exact_artifact_traceability_metadata():
    values = extraction_result().model_dump()
    values.pop("artifact_version_id")

    with pytest.raises(ValidationError):
        ExtractionResult(**values)
