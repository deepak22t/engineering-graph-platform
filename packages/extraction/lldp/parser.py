"""Deterministic parser for the supported Cisco ``show lldp neighbors detail`` subset."""

from __future__ import annotations

import ipaddress
import re

from packages.extraction.lldp.models import (
    LldpLine,
    LldpNeighborRecord,
    LldpParseFinding,
    LldpParseResult,
)

_SEPARATOR = re.compile(r"^-{5,}\s*$")
_FIELD = re.compile(r"^(?P<name>[^:]+):\s*(?P<value>\S(?:.*\S)?)\s*$", re.IGNORECASE)
_FIELDS = {
    "local intf": "local_interface",
    "local interface": "local_interface",
    "chassis id": "chassis_id",
    "system name": "system_name",
    "port id": "remote_port",
    "port description": "remote_port",
    "system description": "platform",
    "system capabilities": "capabilities",
}


class LldpNeighborsDetailParser:
    """Parse only explicit LLDP values and retain chassis and system-name separately."""

    def parse(self, text: str) -> LldpParseResult:
        """Return independent records and source-located validation findings."""
        records: list[LldpNeighborRecord] = []
        findings: list[LldpParseFinding] = []
        current: dict[str, tuple[str, LldpLine]] = {}
        in_management_addresses = False

        def finish_record() -> None:
            nonlocal in_management_addresses
            if current:
                records.append(LldpNeighborRecord(**current))
                current.clear()
            in_management_addresses = False

        for number, raw in enumerate(text.splitlines(), start=1):
            line = LldpLine(number=number, raw=raw, content=raw.strip())
            if _SEPARATOR.fullmatch(line.content):
                finish_record()
                continue
            if not line.content:
                continue
            if line.content.casefold() == "management addresses:":
                in_management_addresses = True
                continue
            if in_management_addresses and (match := _FIELD.fullmatch(line.content)):
                if match.group("name").casefold() in {"ip", "ip address", "management address"}:
                    self._parse_management_address(match.group("value"), line, current, findings)
                    continue
            if match := _FIELD.fullmatch(line.content):
                field = _FIELDS.get(match.group("name").casefold())
                if field is not None:
                    if field == "chassis_id" and "chassis_id" in current:
                        finish_record()
                    current[field] = (match.group("value"), line)
                    in_management_addresses = False
                    continue
            in_management_addresses = False
        finish_record()
        return LldpParseResult(records=tuple(records), findings=tuple(findings))

    @staticmethod
    def _parse_management_address(
        value: str,
        line: LldpLine,
        current: dict[str, tuple[str, LldpLine]],
        findings: list[LldpParseFinding],
    ) -> None:
        try:
            current["management_address"] = (str(ipaddress.ip_address(value)), line)
        except ValueError:
            findings.append(
                LldpParseFinding(
                    code="invalid_lldp_management_address",
                    message="LLDP management address must be a valid IPv4 or IPv6 address.",
                    line=line,
                    field_path="properties.management_ip",
                )
            )
