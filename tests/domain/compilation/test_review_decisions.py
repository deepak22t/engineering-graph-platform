"""Tests for minimal traceable conflict-review decisions."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.domain.compilation import apply_review_decision
from packages.domain.conflicts import (
    CompetingClaim,
    Conflict,
    ConflictStatus,
    ConflictType,
    ReviewDecision,
)


def _claim(value: str) -> CompetingClaim:
    return CompetingClaim(
        value=value,
        evidence_ids=(uuid4(),),
        source_method="deterministic_parser",
    )


def _conflict(*values: str) -> Conflict:
    return Conflict(
        subject_type="canonical_entity",
        subject_id=uuid4(),
        field_path="properties.serial_number",
        competing_claims=tuple(_claim(value) for value in values),
        conflict_type=ConflictType.PROPERTY,
    )


def _decision(
    conflict: Conflict,
    action: str,
    *,
    selected: str | None = None,
    corrected: str | None = None,
) -> ReviewDecision:
    return ReviewDecision(
        conflict_id=conflict.id,
        decision=action,
        reviewer_id=uuid4(),
        selected_claim_value=selected,
        corrected_value=corrected,
        reason="  verified against source  ",
    )


def test_conflict_without_decision_remains_open() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')

    assert conflict.status is ConflictStatus.OPEN


def test_accept_selects_exact_claim_and_preserves_original_history() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')
    original_claims = conflict.competing_claims
    decision = _decision(conflict, "accept", selected='"abc123"')

    output = apply_review_decision(conflict, decision)

    assert output.conflict_resolved
    assert not output.revalidation_required
    assert output.selected_claim == original_claims[0]
    assert output.remaining_claims == (original_claims[0],)
    assert output.excluded_claims == (original_claims[1],)
    assert output.original_conflict is conflict
    assert conflict.status is ConflictStatus.OPEN
    assert conflict.competing_claims == original_claims
    assert output.reviewed_conflict.status is ConflictStatus.RESOLVED
    assert output.decision.reason == "verified against source"


def test_reject_excludes_selected_claim_without_erasing_it() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')
    rejected = conflict.competing_claims[1]
    decision = _decision(conflict, "reject", selected=rejected.value)

    output = apply_review_decision(conflict, decision)

    assert output.conflict_resolved
    assert output.selected_claim == rejected
    assert output.excluded_claims == (rejected,)
    assert output.remaining_claims == (conflict.competing_claims[0],)
    assert rejected in output.original_conflict.competing_claims
    assert len(output.original_conflict.competing_claims) == 2


def test_reject_keeps_conflict_open_when_two_competing_claims_remain() -> None:
    conflict = _conflict('"a"', '"b"', '"c"')
    decision = _decision(conflict, "reject", selected='"a"')

    output = apply_review_decision(conflict, decision)

    assert not output.conflict_resolved
    assert output.reviewed_conflict.status is ConflictStatus.OPEN
    assert [claim.value for claim in output.reviewed_conflict.competing_claims] == [
        '"b"',
        '"c"',
    ]
    assert [claim.value for claim in output.original_conflict.competing_claims] == [
        '"a"',
        '"b"',
        '"c"',
    ]


def test_correction_creates_only_a_recompilation_required_candidate() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')
    decision = _decision(conflict, "correct", corrected="  Correct-123  ")

    output = apply_review_decision(conflict, decision)

    assert not output.conflict_resolved
    assert output.revalidation_required
    correction = output.correction_candidate
    assert correction is not None
    assert correction.corrected_value == "  Correct-123  "
    assert correction.requires_recompilation is True
    assert correction.subject_id == conflict.subject_id
    assert correction.field_path == conflict.field_path
    assert correction.decision == decision
    assert output.reviewed_conflict is conflict


def test_decision_must_reference_conflict_and_an_existing_claim() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')
    wrong_conflict = _decision(conflict, "accept", selected='"abc123"').model_copy(
        update={"conflict_id": uuid4()}
    )
    unknown_claim = _decision(conflict, "reject", selected='"missing"')

    with pytest.raises(ValueError, match="conflict_id"):
        apply_review_decision(conflict, wrong_conflict)
    with pytest.raises(ValueError, match="not a competing claim"):
        apply_review_decision(conflict, unknown_claim)


def test_accept_and_reject_require_an_identified_claim() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')

    with pytest.raises(ValidationError, match="selected_claim_value"):
        _decision(conflict, "accept")
    with pytest.raises(ValidationError, match="selected_claim_value"):
        _decision(conflict, "reject")


def test_nested_conflict_evidence_history_is_immutable() -> None:
    conflict = _conflict('"abc123"', '"xyz789"')

    with pytest.raises(TypeError):
        conflict.competing_claims[0].evidence_ids[0] = uuid4()
    with pytest.raises(ValidationError):
        conflict.competing_claims = (_claim('"replacement"'), _claim('"other"'))
