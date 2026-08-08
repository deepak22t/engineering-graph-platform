"""Tests for validation findings and conflict review contracts."""

import uuid

import pytest
from pydantic import ValidationError

from packages.domain.conflicts import CompetingClaim, Conflict, ConflictType, ReviewDecision
from packages.domain.validation import FindingSeverity, ValidationFinding


def claim(value):
    return CompetingClaim(value=value, evidence_ids=[uuid.uuid4()], source_method="parser")


def test_structured_validation_finding_supports_safe_parser_output():
    finding = ValidationFinding(
        code="invalid_ip",
        severity=FindingSeverity.ERROR,
        message="Invalid IP",
        subject_type="proposal",
        proposal_id=uuid.uuid4(),
        field_path="properties.address",
        remediation_hint="Provide a host IP.",
    )
    assert finding.severity == FindingSeverity.ERROR


def test_conflicts_retain_competing_claims_without_resolution():
    conflict = Conflict(
        subject_type="device",
        subject_id=uuid.uuid4(),
        field_path="properties.serial_number",
        competing_claims=[claim("A"), claim("B")],
        conflict_type=ConflictType.PROPERTY,
    )
    assert conflict.status.value == "open"
    assert len(conflict.competing_claims) == 2


def test_review_correction_requires_explicit_value():
    with pytest.raises(ValidationError):
        ReviewDecision(decision="correct", reviewer_id=uuid.uuid4(), reason="wrong")
    assert (
        ReviewDecision(
            decision="correct", reviewer_id=uuid.uuid4(), corrected_value="100", reason="verified"
        ).corrected_value
        == "100"
    )
