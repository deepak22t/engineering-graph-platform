"""Tests for safe Cisco topology artifact file validation."""

import pytest

from packages.artifacts import ArtifactFileValidator


@pytest.fixture
def validator() -> ArtifactFileValidator:
    return ArtifactFileValidator(maximum_size_bytes=1_024)


@pytest.mark.parametrize(
    "filename, content",
    [
        (
            "router-01",
            b"version 15.2\nhostname router-01\ninterface GigabitEthernet0/1\n",
        ),
        (
            "router-01.cfg",
            b"version 15.2\nhostname router-01\ninterface GigabitEthernet0/1\n",
        ),
        (
            "router-01-cdp.txt",
            (
                b"Device ID: switch-01\n"
                b"Interface: GigabitEthernet0/1\n"
                b"Port ID (outgoing port): Gi1/0/24\n"
            ),
        ),
        (
            "switch-01-lldp.conf",
            b"Local Intf: Gi0/1\nChassis id: 0011.2233.4455\nPort id: Gi1/0/24\n",
        ),
    ],
)
def test_validator_accepts_only_recognized_cisco_text_artifacts(
    validator: ArtifactFileValidator, filename: str, content: bytes
):
    validator.validate(filename=filename, content_type="text/plain", content=content)


@pytest.mark.parametrize(
    "filename, content_type, content",
    [
        ("", "text/plain", b"hostname router-01\ninterface Gi0/1\n"),
        ("../router.cfg", "text/plain", b"hostname router-01\ninterface Gi0/1\n"),
        ("router.pdf", "text/plain", b"hostname router-01\ninterface Gi0/1\n"),
        ("router.txt", "application/pdf", b"hostname router-01\ninterface Gi0/1\n"),
        ("router.txt", "text/plain", b""),
        ("router.txt", "text/plain", b"%PDF-1.7"),
        ("router.txt", "text/plain", b"\x89PNG\r\n\x1a\n"),
        ("router.txt", "text/plain", b"\xff\xd8\xff"),
        ("router.txt", "text/plain", b"Rar!\x1a\x07"),
        ("router.txt", "text/plain", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        ("router.txt", "text/plain", b"AC1027"),
        ("router.txt", "text/plain", b"PK\x03\x04"),
        ("router.txt", "text/plain", b"MZ"),
        ("router.txt", "text/plain", b"\xff\xfe"),
        ("router.txt", "text/plain", b"hostname r\x00\ninterface Gi0/1\n"),
    ],
)
def test_validator_rejects_unsafe_or_unsupported_files(
    validator: ArtifactFileValidator, filename: str, content_type: str, content: bytes
):
    with pytest.raises(ValueError):
        validator.validate(filename=filename, content_type=content_type, content=content)


def test_validator_uses_configured_maximum_size():
    validator = ArtifactFileValidator(maximum_size_bytes=10)
    content = b"hostname router-01\ninterface Gi0/1\n"
    with pytest.raises(ValueError, match="configured maximum size"):
        validator.validate(filename="router.txt", content_type="text/plain", content=content)


def test_validator_rejects_invalid_maximum_size():
    with pytest.raises(ValueError, match="maximum_size_bytes"):
        ArtifactFileValidator(maximum_size_bytes=0)


def test_file_validation_rejects_binary_disguised_as_text_file(tmp_path, validator):
    artifact_file = tmp_path / "router.txt"
    artifact_file.write_bytes(b"%PDF-1.7")

    with pytest.raises(ValueError, match="binary"):
        validator.validate_file(
            filename="router.txt",
            content_type="text/plain",
            path=artifact_file,
            size_bytes=artifact_file.stat().st_size,
        )


def test_validator_accepts_cnf_extension_for_valid_cisco_text(validator):
    artifact_kind = validator.validate(
        filename="router.cnf",
        content_type="text/plain",
        content=b"version 15.2\nhostname router-01\ninterface GigabitEthernet0/1\n",
    )

    assert artifact_kind.value == "cisco_ios_running_config"


def test_validator_rejects_generic_binary_mime_even_when_contents_are_text(validator):
    with pytest.raises(ValueError, match="text-like"):
        validator.validate(
            filename="router.cnf",
            content_type="application/octet-stream",
            content=b"version 15.2\nhostname router-01\ninterface GigabitEthernet0/1\n",
        )


@pytest.mark.parametrize(
    "filename, content_type, content, expected_kind",
    [
        ("inventory.json", "application/json", b'{"devices": []}', "json"),
        ("inventory.yaml", "application/yaml", b"devices: []\n", "yaml"),
        ("inventory.csv", "text/csv", b"hostname,role\nrouter-01,router\n", "csv"),
        ("notes.txt", "text/plain", b"operator notes\n", "text"),
    ],
)
def test_validator_accepts_explicit_phase_three_text_formats(
    validator, filename: str, content_type: str, content: bytes, expected_kind: str
):
    artifact_kind = validator.validate(
        filename=filename, content_type=content_type, content=content
    )

    assert artifact_kind.value == expected_kind
