"""Line-aware intermediate contracts for Cisco LLDP neighbor-detail output."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LldpLine:
    """One original LLDP output line and its one-based source position."""

    number: int
    raw: str
    content: str


@dataclass(frozen=True, slots=True)
class LldpNeighborRecord:
    """Explicit LLDP claims from one neighbor record; no identity is resolved here."""

    local_interface: tuple[str, LldpLine] | None = None
    chassis_id: tuple[str, LldpLine] | None = None
    system_name: tuple[str, LldpLine] | None = None
    remote_port: tuple[str, LldpLine] | None = None
    platform: tuple[str, LldpLine] | None = None
    capabilities: tuple[str, LldpLine] | None = None
    management_address: tuple[str, LldpLine] | None = None


@dataclass(frozen=True, slots=True)
class LldpParseFinding:
    """A safe LLDP parser finding with exact source position."""

    code: str
    message: str
    line: LldpLine
    field_path: str


@dataclass(frozen=True, slots=True)
class LldpParseResult:
    """Independent LLDP records and findings, never graph write objects."""

    records: tuple[LldpNeighborRecord, ...]
    findings: tuple[LldpParseFinding, ...]
