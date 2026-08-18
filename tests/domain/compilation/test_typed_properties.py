"""Tests for Phase 5 typed property candidate compilation."""

from uuid import UUID

from packages.domain.compilation import (
    NormalizationResult,
    NormalizationStatus,
    NormalizedAttributeClaim,
    compile_typed_property_candidates,
)
from packages.domain.entities.properties import DeviceProperties
from packages.domain.enums import EntityType

PROPOSAL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
EVIDENCE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SUBJECT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _claim(
    *,
    field_path: str,
    normalized_value: object,
    proposal_id: UUID = PROPOSAL_ID,
    status: NormalizationStatus = NormalizationStatus.NORMALIZED,
) -> NormalizedAttributeClaim:
    return NormalizedAttributeClaim(
        attribute_proposal_id=proposal_id,
        subject_proposal_id=SUBJECT_ID,
        entity_type=EntityType.DEVICE,
        field_path=field_path,
        raw_value=normalized_value,
        normalized_value=normalized_value,
        evidence_ids=(EVIDENCE_ID,),
        status=status,
    )


def test_complete_normalized_claims_become_existing_typed_properties() -> None:
    output = compile_typed_property_candidates(
        NormalizationResult(
            claims=(
                _claim(field_path="properties.hostname", normalized_value="router-01"),
                _claim(
                    field_path="properties.management_ip",
                    normalized_value="192.0.2.1",
                    proposal_id=UUID(int=2),
                ),
            )
        )
    )

    assert output.findings == ()
    assert len(output.candidates) == 1
    candidate = output.candidates[0]
    assert isinstance(candidate.properties, DeviceProperties)
    assert candidate.properties.hostname == "router-01"
    assert candidate.properties.management_ip == "192.0.2.1"
    assert candidate.attribute_proposal_ids == (PROPOSAL_ID, UUID(int=2))


def test_missing_required_property_does_not_create_a_candidate() -> None:
    interface_claim = NormalizedAttributeClaim(
        attribute_proposal_id=PROPOSAL_ID,
        subject_proposal_id=SUBJECT_ID,
        entity_type=EntityType.INTERFACE,
        field_path="properties.interface_name",
        raw_value="eth0",
        normalized_value="eth0",
        evidence_ids=(EVIDENCE_ID,),
        status=NormalizationStatus.NORMALIZED,
    )

    output = compile_typed_property_candidates(NormalizationResult(claims=(interface_claim,)))

    assert output.candidates == ()
    assert [finding.code for finding in output.findings] == [
        "incomplete_or_invalid_typed_properties"
    ]
    assert output.findings[0].field_path == "properties.interface_type"


def test_conflicting_normalized_property_values_remain_unresolved() -> None:
    output = compile_typed_property_candidates(
        NormalizationResult(
            claims=(
                _claim(field_path="properties.hostname", normalized_value="router-01"),
                _claim(
                    field_path="properties.hostname",
                    normalized_value="router-02",
                    proposal_id=UUID(int=3),
                ),
            )
        )
    )

    assert output.candidates == ()
    assert [finding.code for finding in output.findings] == [
        "conflicting_normalized_property_values"
    ]
    assert output.findings[0].field_path == "properties.hostname"


def test_rejected_and_noncanonical_claims_never_enter_typed_properties() -> None:
    output = compile_typed_property_candidates(
        NormalizationResult(
            claims=(
                _claim(
                    field_path="properties.hostname",
                    normalized_value="router-01",
                    status=NormalizationStatus.REJECTED,
                ),
                _claim(
                    field_path="properties.platform",
                    normalized_value=None,
                    proposal_id=UUID(int=4),
                    status=NormalizationStatus.NONCANONICAL,
                ),
            )
        )
    )

    assert output.candidates == ()
    assert output.findings == ()
