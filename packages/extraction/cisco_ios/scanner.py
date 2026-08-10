"""Line scanner for the intentionally small Cisco IOS extraction grammar."""

from collections.abc import Iterator

from packages.extraction.cisco_ios.models import CiscoIosLine


def scan_cisco_ios_lines(text: str) -> Iterator[CiscoIosLine]:
    """Yield original line numbers and text without altering non-comment source content."""
    for number, raw in enumerate(text.splitlines(), start=1):
        leading_content = raw.lstrip(" \t")
        content = leading_content.rstrip(" \t")
        yield CiscoIosLine(
            number=number,
            raw=raw,
            content=content,
            is_indented=len(leading_content) != len(raw),
        )


def is_block_terminator(line: CiscoIosLine) -> bool:
    """Return whether this line closes the current supported configuration submode."""
    return not line.content or line.content.startswith("!") or line.content == "end"
