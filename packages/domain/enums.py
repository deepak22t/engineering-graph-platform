"""Canonical enumeration types for the Engineering Graph Platform.

All enums inherit from (str, Enum) so values serialise as plain strings in
JSON and Pydantic models. EntityType and RelationshipType values map directly
to Neo4j node labels and relationship types (Phase 6).
"""

from enum import Enum


class EntityType(str, Enum):
    """Node types in the canonical engineering graph."""

    DEVICE = "DEVICE"           # Physical or virtual machine (router, switch, server, VM)
    COMPONENT = "COMPONENT"     # Sub-part of a device (module, blade, card, slot)
    INTERFACE = "INTERFACE"     # Network interface on a device (eth0, Gi0/0, port)
    NETWORK = "NETWORK"         # IP network or subnet (192.168.1.0/24)
    SITE = "SITE"               # Physical or logical location (data centre, rack, region)
    SERVICE = "SERVICE"         # Running application or service (nginx, postgres)
    CONTAINER = "CONTAINER"     # Containerised workload (Docker container, Pod)
    IP = "IP"                   # Single IP address, static or floating
    VLAN = "VLAN"               # VLAN identified by numeric ID and optional name
    ROUTE = "ROUTE"             # Routing table entry (destination, next-hop, metric)
    FIREWALL = "FIREWALL"       # Firewall policy, ACL, or security group
    CONNECTION = "CONNECTION"   # Logical or physical link between interfaces or devices


class RelationshipType(str, Enum):
    """Edge types in the canonical engineering graph."""

    HAS_INTERFACE = "HAS_INTERFACE"   # Device      → Interface
    CONNECTED_TO = "CONNECTED_TO"     # Interface   → Interface (or Device → Device)
    LOCATED_AT = "LOCATED_AT"         # Device/Service → Site
    MEMBER_OF = "MEMBER_OF"           # Interface   → VLAN, Device → Network
    RUNS_ON = "RUNS_ON"               # Service/Container → Device
    HOSTS = "HOSTS"                   # Device      → Service/Container
    ROUTES_TO = "ROUTES_TO"           # Device      → Network (via Route)
    CONTROLS = "CONTROLS"             # Firewall    → Connection/Interface
    CONTAINS = "CONTAINS"             # Site        → Device, Network → Subnet
    DEPENDS_ON = "DEPENDS_ON"         # Service     → Service
    PART_OF = "PART_OF"               # Component   → Device
    ATTACHED_TO = "ATTACHED_TO"       # IP          → Interface, VLAN → Network


class ExtractionMethod(str, Enum):
    """How a graph fact was extracted from its source artifact."""

    DETERMINISTIC_PARSER = "deterministic_parser"   # Rule-based, fully reproducible (preferred)
    OCR = "ocr"                                     # Optical character recognition
    LLM = "llm"                                     # Large language model
    VLM = "vlm"                                     # Vision-language model (diagrams/images)
    HUMAN = "human"                                 # Entered or corrected by a human operator
    INFERRED = "inferred"                           # Derived from other confirmed facts


class ConfidenceLevel(str, Enum):
    """Qualitative confidence band derived from a numeric score (0.0–1.0).

    HIGH   ≥ 0.85 — eligible for controlled auto-commit (Phase 9)
    MEDIUM ≥ 0.60 — passes with a caution flag
    LOW    < 0.60 — routed to the human review queue (Phase 9)
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """Return the confidence band for a given numeric score."""
        if score >= 0.85:
            return cls.HIGH
        if score >= 0.60:
            return cls.MEDIUM
        return cls.LOW
