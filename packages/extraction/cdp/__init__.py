"""Cisco CDP neighbor-detail deterministic extraction support."""

from packages.extraction.cdp.parser import CdpNeighborsDetailParser
from packages.extraction.cdp.proposals import CdpNeighborsDetailProposalBuilder

__all__ = ["CdpNeighborsDetailParser", "CdpNeighborsDetailProposalBuilder"]
