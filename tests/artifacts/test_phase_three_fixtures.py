"""Real-file checks for every supported deterministic-ingestion artifact kind."""

from pathlib import Path

import pytest

from packages.artifacts import ArtifactFileValidator, ArtifactKind


@pytest.mark.parametrize(
    "filename, content_type, expected_kind",
    [
        ("edge-router-01-running-config.cfg", "text/plain", ArtifactKind.CISCO_IOS_RUNNING_CONFIG),
        ("switch-01-cdp-neighbors.txt", "text/plain", ArtifactKind.CDP_NEIGHBORS_DETAIL),
        ("switch-01-lldp-neighbors.txt", "text/plain", ArtifactKind.LLDP_NEIGHBORS_DETAIL),
        ("inventory.json", "application/json", ArtifactKind.JSON),
        ("inventory.yaml", "application/yaml", ArtifactKind.YAML),
        ("inventory.csv", "text/csv", ArtifactKind.CSV),
        ("operator-notes.txt", "text/plain", ArtifactKind.TEXT),
    ],
)
def test_sanitized_fixture_is_classified_as_its_supported_artifact_kind(
    filename: str, content_type: str, expected_kind: ArtifactKind
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "artifacts" / filename
    validator = ArtifactFileValidator(maximum_size_bytes=1_024)

    assert validator.validate_file(
        filename=filename,
        content_type=content_type,
        path=fixture,
        size_bytes=fixture.stat().st_size,
    ) is expected_kind
