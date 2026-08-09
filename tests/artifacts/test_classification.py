"""Tests for conservative Cisco topology artifact classification."""

from pathlib import Path

import pytest

from packages.artifacts import ArtifactClassifier, ArtifactKind


@pytest.mark.parametrize(
    "text, expected_kind",
    [
        (
            "version 15.2\nhostname router-01\ninterface GigabitEthernet0/1\n",
            ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        ),
        (
            "Device ID: switch-01\nInterface: Gi0/1\nPort ID (outgoing port): Gi1/0/24\n",
            ArtifactKind.CDP_NEIGHBORS_DETAIL,
        ),
        (
            "Local Intf: Gi0/1\nChassis id: 0011.2233.4455\nPort id: Gi1/0/24\n",
            ArtifactKind.LLDP_NEIGHBORS_DETAIL,
        ),
    ],
)
def test_classifier_returns_only_one_approved_artifact_kind(text: str, expected_kind: ArtifactKind):
    assert ArtifactClassifier.classify_text(text) is expected_kind


@pytest.mark.parametrize(
    "text",
    [
        "ordinary text",
        "Device ID: switch-01\nInterface: Gi0/1\n",
        "Local Intf: Gi0/1\nPort id: Gi1/0/24\n",
        (
            "version 15.2\n"
            "hostname router-01\n"
            "interface Gi0/1\n"
            "Device ID: switch-01\n"
            "Interface: Gi0/1\n"
            "Port ID: Gi1/0/24\n"
        ),
    ],
)
def test_classifier_rejects_unknown_partial_or_ambiguous_text(text: str):
    with pytest.raises(ValueError):
        ArtifactClassifier.classify_text(text)


def test_classifier_rejects_non_text_input():
    with pytest.raises(ValueError, match="must be a string"):
        ArtifactClassifier.classify_text(b"not text")  # type: ignore[arg-type]


def test_classifier_classifies_temporary_file_without_text_loading(tmp_path):
    artifact_file = tmp_path / "router.cfg"
    artifact_file.write_text("version 17\nhostname router-01\ninterface Gi0/1\n")

    assert ArtifactClassifier.classify_file(artifact_file) == ArtifactKind.CISCO_IOS_RUNNING_CONFIG


def test_sanitized_cisco_config_fixture_is_classified_as_running_config():
    fixture = (
        Path(__file__).parents[1] / "fixtures" / "artifacts" / "edge-router-01-running-config.cfg"
    )

    assert ArtifactClassifier.classify_file(fixture) is ArtifactKind.CISCO_IOS_RUNNING_CONFIG
