"""Cisco LLDP neighbor-detail deterministic extraction support."""

from packages.extraction.lldp.parser import LldpNeighborsDetailParser
from packages.extraction.lldp.proposals import LldpNeighborsDetailProposalBuilder

__all__ = ["LldpNeighborsDetailParser", "LldpNeighborsDetailProposalBuilder"]
