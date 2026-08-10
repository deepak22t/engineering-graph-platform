"""Deterministic parser for the supported Cisco ``show cdp neighbors detail`` subset."""

from __future__ import annotations

import ipaddress
import re

from packages.extraction.cdp.models import (
    CdpLine,
    CdpNeighborRecord,
    CdpParseFinding,
    CdpParseResult,
)

_DEVICE_ID = re.compile(r"^Device ID:\s*(?P<value>\S(?:.*\S)?)\s*$", re.IGNORECASE)
_INTERFACE = re.compile(
    r"^Interface:\s*(?P<local>\S(?:.*?\S)?)\s*,\s*"
    r"Port ID \(outgoing port\):\s*(?P<remote>\S(?:.*\S)?)\s*$",
    re.IGNORECASE,
)
_PLATFORM = re.compile(
    r"^Platform:\s*(?P<platform>\S(?:.*?\S)?)\s*,\s*"
    r"Capabilities:\s*(?P<capabilities>\S(?:.*\S)?)\s*$",
    re.IGNORECASE,
)
_IP_ADDRESS = re.compile(r"^(?:IP|Management) address:\s*(?P<value>\S+)\s*$", re.IGNORECASE)
_SEPARATOR = re.compile(r"^-{5,}\s*$")


class CdpNeighborsDetailParser:
    """Parse direct CDP claims without resolving device or interface identity."""

    def parse(self, text: str) -> CdpParseResult:
        """Return independent records, preserving all source locations."""
        records: list[CdpNeighborRecord] = []
        findings: list[CdpParseFinding] = []
        current: dict[str, tuple[str, CdpLine]] = {}

        def finish_record() -> None:
            if current:
                records.append(CdpNeighborRecord(**current))
                current.clear()

        for number, raw in enumerate(text.splitlines(), start=1):
            line = CdpLine(number=number, raw=raw, content=raw.strip())
            if _SEPARATOR.fullmatch(line.content):
                finish_record()
                continue
            if not line.content:
                continue
            if match := _DEVICE_ID.fullmatch(line.content):
                if "device_id" in current:
                    finish_record()
                current["device_id"] = (match.group("value"), line)
                continue
            if match := _INTERFACE.fullmatch(line.content):
                current["local_interface"] = (match.group("local"), line)
                current["remote_interface"] = (match.group("remote"), line)
                continue
            if match := _PLATFORM.fullmatch(line.content):
                current["platform"] = (match.group("platform"), line)
                current["capabilities"] = (match.group("capabilities"), line)
                continue
            if match := _IP_ADDRESS.fullmatch(line.content):
                address = match.group("value")
                try:
                    current["management_address"] = (str(ipaddress.ip_address(address)), line)
                except ValueError:
                    findings.append(
                        CdpParseFinding(
                            code="invalid_cdp_management_address",
                            message="CDP management address must be a valid IPv4 or IPv6 address.",
                            line=line,
                            field_path="properties.management_ip",
                        )
                    )
        finish_record()
        return CdpParseResult(records=tuple(records), findings=tuple(findings))
