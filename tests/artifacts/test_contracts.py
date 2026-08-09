"""Tests for the minimal Phase 2 Artifact Service contract."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from packages.artifacts import ArtifactKind, ArtifactScope, ArtifactStatus


def test_first_vertical_artifact_kinds_are_explicit_and_limited():
    assert [kind.value for kind in ArtifactKind] == [
        "cisco_ios_running_config",
        "cdp_neighbors_detail",
        "lldp_neighbors_detail",
    ]


def test_artifact_lifecycle_statuses_match_the_phase_2_contract():
    assert [status.value for status in ArtifactStatus] == [
        "uploaded",
        "processing",
        "processed",
        "failed",
    ]


def test_artifact_scope_requires_all_cisco_upload_context():
    scope = ArtifactScope(
        organization_id=UUID(int=1),
        project_id=UUID(int=2),
        environment=" Prod ",
        site_id=UUID(int=3),
    )
    assert scope.environment == "prod"
    assert scope.site_id == UUID(int=3)

    with pytest.raises(ValidationError):
        ArtifactScope(
            organization_id=UUID(int=1),
            project_id=UUID(int=2),
            environment="prod",
        )


def test_artifact_scope_rejects_invalid_uuid_and_blank_environment():
    with pytest.raises(ValidationError):
        ArtifactScope(
            organization_id="not-a-uuid",
            project_id=UUID(int=2),
            environment="prod",
            site_id=UUID(int=3),
        )
    with pytest.raises(ValidationError):
        ArtifactScope(
            organization_id=UUID(int=1),
            project_id=UUID(int=2),
            environment="   ",
            site_id=UUID(int=3),
        )
