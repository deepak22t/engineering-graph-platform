"""Pure application of traceable human conflict-review decisions."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from packages.domain.conflicts import (
    CompetingClaim,
    Conflict,
    ConflictStatus,
    ReviewDecision,
)


class CorrectionCandidate(BaseModel):
    """Raw human correction that must re-enter semantic compilation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ReviewDecision
    subject_type: str
    subject_id: UUID | None = None
    field_path: str | None = None
    relationship: str | None = None
    corrected_value: str
    requires_recompilation: Literal[True] = True

    @model_validator(mode="after")
    def require_correction_decision(self) -> "CorrectionCandidate":
        if self.decision.decision != "correct":
            raise ValueError("A correction candidate requires a correct decision.")
        if self.decision.corrected_value != self.corrected_value:
            raise ValueError("Correction candidate value must match its review decision.")
        return self


class ReviewDecisionResult(BaseModel):
    """Immutable review outcome retaining both source conflict and decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    original_conflict: Conflict
    reviewed_conflict: Conflict
    decision: ReviewDecision
    selected_claim: CompetingClaim | None = None
    remaining_claims: tuple[CompetingClaim, ...] = ()
    excluded_claims: tuple[CompetingClaim, ...] = ()
    correction_candidate: CorrectionCandidate | None = None

    @model_validator(mode="after")
    def require_traceable_conflict_identity(self) -> "ReviewDecisionResult":
        if self.original_conflict.id != self.reviewed_conflict.id:
            raise ValueError("Review result conflicts must retain the same conflict ID.")
        if self.decision.conflict_id != self.original_conflict.id:
            raise ValueError("Review result decision must reference its original conflict.")
        if (
            self.correction_candidate is not None
            and self.correction_candidate.decision != self.decision
        ):
            raise ValueError("Correction candidate must retain the applied review decision.")
        return self

    @computed_field
    @property
    def conflict_resolved(self) -> bool:
        return self.reviewed_conflict.status is ConflictStatus.RESOLVED

    @computed_field
    @property
    def revalidation_required(self) -> bool:
        return self.correction_candidate is not None


def apply_review_decision(
    conflict: Conflict,
    decision: ReviewDecision,
) -> ReviewDecisionResult:
    """Apply one decision without mutating claims or creating canonical state."""

    if conflict.status is not ConflictStatus.OPEN:
        raise ValueError("Only an open conflict can receive a review decision.")
    if decision.conflict_id != conflict.id:
        raise ValueError("Review decision conflict_id does not match the conflict.")

    selected_claim = _selected_claim(conflict, decision.selected_claim_value)
    if decision.selected_claim_value is not None and selected_claim is None:
        raise ValueError("selected_claim_value is not a competing claim in this conflict.")

    if decision.decision == "accept":
        assert selected_claim is not None
        excluded = tuple(claim for claim in conflict.competing_claims if claim != selected_claim)
        return ReviewDecisionResult(
            original_conflict=conflict,
            reviewed_conflict=conflict.model_copy(
                update={"status": ConflictStatus.RESOLVED}
            ),
            decision=decision,
            selected_claim=selected_claim,
            remaining_claims=(selected_claim,),
            excluded_claims=excluded,
        )

    if decision.decision == "reject":
        assert selected_claim is not None
        remaining = tuple(
            claim for claim in conflict.competing_claims if claim != selected_claim
        )
        if len(remaining) < 2:
            reviewed = conflict.model_copy(update={"status": ConflictStatus.RESOLVED})
        else:
            reviewed = conflict.model_copy(update={"competing_claims": remaining})
        return ReviewDecisionResult(
            original_conflict=conflict,
            reviewed_conflict=reviewed,
            decision=decision,
            selected_claim=selected_claim,
            remaining_claims=remaining,
            excluded_claims=(selected_claim,),
        )

    assert decision.corrected_value is not None
    correction = CorrectionCandidate(
        decision=decision,
        subject_type=conflict.subject_type,
        subject_id=conflict.subject_id,
        field_path=conflict.field_path,
        relationship=conflict.relationship,
        corrected_value=decision.corrected_value,
    )
    return ReviewDecisionResult(
        original_conflict=conflict,
        reviewed_conflict=conflict,
        decision=decision,
        selected_claim=selected_claim,
        remaining_claims=conflict.competing_claims,
        correction_candidate=correction,
    )


def _selected_claim(
    conflict: Conflict,
    selected_value: str | None,
) -> CompetingClaim | None:
    if selected_value is None:
        return None
    return next(
        (claim for claim in conflict.competing_claims if claim.value == selected_value),
        None,
    )


__all__ = [
    "CorrectionCandidate",
    "ReviewDecisionResult",
    "apply_review_decision",
]
