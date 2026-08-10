"""Line-aware intermediate contracts for Cisco CDP neighbor-detail output."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CdpLine:
    """One original CDP output line and its one-based source position."""

    number: int
    raw: str
    content: str


@dataclass(frozen=True, slots=True)
class CdpNeighborRecord:
    """Explicit claims from one CDP neighbor record; absent fields remain absent."""

    device_id: tuple[str, CdpLine] | None = None
    local_interface: tuple[str, CdpLine] | None = None
    remote_interface: tuple[str, CdpLine] | None = None
    platform: tuple[str, CdpLine] | None = None
    capabilities: tuple[str, CdpLine] | None = None
    management_address: tuple[str, CdpLine] | None = None


@dataclass(frozen=True, slots=True)
class CdpParseFinding:
    """A parser finding with the exact source line that caused it."""

    code: str
    message: str
    line: CdpLine
    field_path: str


@dataclass(frozen=True, slots=True)
class CdpParseResult:
    """Independent CDP records and parse findings; never canonical graph facts."""

    records: tuple[CdpNeighborRecord, ...]
    findings: tuple[CdpParseFinding, ...]
