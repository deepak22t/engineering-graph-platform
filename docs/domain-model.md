# Canonical Domain Model

## Purpose and scope

This document defines the language of the Engineering Graph Platform. It is the
contract that parsers, semantic compilation, graph persistence, validation, and
diagram views must share.

The canonical semantic graph is the source of truth. A diagram is a projection
of that graph, not a separate engineering model.

This is a Phase 1 contract. It defines meaning and invariants; it does not add
API routes, database storage, parser behavior, AI behavior, tenant
authorization, or service extraction.

## Common rules

Every canonical entity and relationship has:

- a stable canonical identifier;
- a type from the approved vocabulary below;
- an engineering scope, such as organization, project, environment, or site,
  when needed to distinguish otherwise similar assets;
- a human-readable display name separate from its identity;
- typed, normalized properties;
- lifecycle and observation timestamps; and
- evidence, provenance, and confidence whenever the fact originates from a
  source artifact, integration, AI-assisted extraction, inference, or a human
  correction.

Canonical facts are immutable observations. Later corrections or new
observations create a new version or supersede a fact; they do not silently
rewrite history.

The Phase 1 entity and relationship enumerations in `packages/domain/enums.py`
are the current vocabulary. New types require an explicit contract update,
implementation, and tests.

## Entity vocabulary

| Entity | Meaning | Minimum properties | Identity inputs | Validation and normalization |
| --- | --- | --- | --- | --- |
| `DEVICE` | A physical or virtual device that hosts, routes, switches, or protects workloads. | hostname, role/type; vendor, model, serial number, OS, and management IP when known. | Scoped serial number; otherwise scoped normalized hostname and site. | Hostname is non-empty and normalized; management IP is valid; serial and vendor values are preserved as source values when normalization is uncertain. |
| `COMPONENT` | A replaceable or logical part of a device or another component. | component type, name/slot; serial number when available. | Parent identity plus serial number or normalized slot/name. | Must have a valid parent through `PART_OF`; a component cannot be its own ancestor. |
| `INTERFACE` | A physical, virtual, or logical interface owned by a device. | interface name, interface type; MAC, MTU, speed, and administrative/operational state when known. | Owning device identity plus normalized interface name. | Interface names use a shared normalization rule; MAC is canonicalized; MTU and speed are positive when present. |
| `NETWORK` | An IP network, subnet, segment, or logical network boundary. | CIDR, network type; name when supplied. | Scope plus canonical CIDR. | CIDR must parse and be stored in canonical form; address family is derived from the CIDR. |
| `SITE` | A physical or logical location, such as a data centre, region, campus, rack, or cloud location. | canonical name/code, site type; address or region when known. | Organization plus canonical site code/name. | Site type is controlled; display names are not globally unique without organization scope. |
| `SERVICE` | An application or infrastructure service that may depend on or run on other assets. | service name, service type, environment; owner or application when known. | Scope plus normalized service name and application/namespace where required. | A service is not a device; runtime placement is modeled by `RUNS_ON`, not a free-text host field. |
| `CONTAINER` | A containerized workload or orchestrated workload instance. | workload/container name, image, namespace, runtime/cluster when known. | Runtime scope plus namespace and stable workload/container identifier. | Container identity must not rely only on an ephemeral display name. |
| `IP` | One IPv4 or IPv6 address. | canonical address, address family. | Network/scope plus canonical address. | Address must be a host IP, not a CIDR string; IPv4 and IPv6 are normalized by the standard IP parser. |
| `VLAN` | A Layer 2 VLAN or equivalent scoped segmentation construct. | numeric VLAN ID; name when known. | Scope/site/network plus VLAN ID. | VLAN ID must be an integer in the configured valid range; VLAN name is descriptive, not identity. |
| `ROUTE` | A routing-table assertion or route policy entry. | destination CIDR, next hop, protocol, metric when known. | Source device plus destination CIDR, next hop, and route-table context. | Destination and next hop must be valid IP/CIDR values; metric is non-negative when present. |
| `FIREWALL` | A firewall appliance, logical firewall, security group, or policy boundary. | name, firewall type; vendor/model or policy identifier when known. | Scoped appliance serial/name or stable policy identifier. | A firewall appliance and a firewall policy must be distinguished through a controlled subtype/property. |
| `CONNECTION` | A physical or logical connection represented as an engineering object when connection metadata itself matters. | connection type; medium, capacity, and state when known. | Normalized endpoints plus connection type and scope. | Use `CONNECTED_TO` for a simple adjacency; use `CONNECTION` only when the link has its own identity or attributes. |

## Relationship vocabulary

Relationships are directed canonical facts. The stored direction expresses the
meaning below, even where a view later renders a relationship without arrows.

| Relationship | Meaning and allowed direction | Core rules |
| --- | --- | --- |
| `HAS_INTERFACE` | `DEVICE -> INTERFACE` | A device may own many interfaces. An active interface has one current owning device. |
| `CONNECTED_TO` | `INTERFACE -> INTERFACE` | Represents direct adjacency. It is semantically symmetric: `A` connected to `B` and `B` connected to `A` are one connection fact, not duplicates. |
| `LOCATED_AT` | `DEVICE`, `SERVICE`, `FIREWALL`, or `CONTAINER` `-> SITE` | The target must be a site. The relationship represents location, not ownership. |
| `MEMBER_OF` | `INTERFACE -> VLAN`; other combinations require an explicit future contract. | VLAN membership must be scoped consistently with the interface and network context. |
| `RUNS_ON` | `SERVICE -> DEVICE` or `CONTAINER -> DEVICE` | Represents runtime placement. It does not imply ownership or a dependency. |
| `HOSTS` | `DEVICE -> SERVICE` or `DEVICE -> CONTAINER` | The inverse semantic of runtime placement for supported targets. A compiler must avoid independently creating contradictory duplicate facts. |
| `ROUTES_TO` | `ROUTE -> NETWORK` | A route targets a network. The route's source device is represented by a separate relationship or typed route property defined with the Route implementation. |
| `CONTROLS` | `FIREWALL -> CONNECTION`, `INTERFACE`, or `NETWORK` | Represents an enforced policy/control boundary, not mere topology. |
| `CONTAINS` | `SITE -> DEVICE`, `SITE -> FIREWALL`, `SITE -> NETWORK`, or `NETWORK -> NETWORK` | A parent contains a child. Network containment requires proper subnet containment and cannot form cycles. |
| `DEPENDS_ON` | `SERVICE -> SERVICE` | Represents an operational dependency. It is directional and cannot be self-referential. |
| `PART_OF` | `COMPONENT -> DEVICE` or `COMPONENT -> COMPONENT` | Represents physical/logical composition. It cannot form cycles. |
| `ATTACHED_TO` | `IP -> INTERFACE` or `VLAN -> NETWORK` | Represents address or segmentation attachment. The semantic compiler validates scope and prevents conflicting active attachment facts. |

No relationship type permits a source and target with the same canonical ID
unless a future contract explicitly permits that self-reference.

## Property, identity, and evidence boundaries

- A display name identifies an asset to a human; it is not sufficient canonical
  identity.
- Identity inputs are immutable. Operational properties may change in a later
  observation/version.
- Each entity type has typed properties. A generic attribute bag must not be
  the only validation boundary for canonical data.
- Every normalized value retains source evidence when source evidence exists.
- A source assertion, extraction proposal, and committed canonical fact are
  separate states. An extractor never writes directly to the canonical graph.
- Evidence records identify the artifact, precise source location, extraction
  method, extractor version, observation time, confidence, and reference to
  the raw supporting material.
- Conflicting claims are retained as conflicts for semantic compilation and
  review; they are not resolved by last-write-wins behavior.

## Canonical identity policy

Every canonical entity owns a typed `EntityIdentity` with an immutable scope,
identity version, and normalized natural-key fields. The platform derives the
entity ID internally as UUIDv5 from the entity type, identity version, scope,
and identity fields. Display names, arbitrary supplied UUIDs, and mutable
attributes never participate in identity.

The exact per-type keys live in `packages/domain/identity.py`. Identity changes
create a different canonical entity; they do not rewrite an existing identity.
## Required implementation sequence

1. Implement scoped, typed identity keys and ID generation.
2. Implement typed entity properties and shared normalization.
3. Implement executable relationship specifications and validation.
4. Implement fact-level evidence and confidence invariants.
5. Implement proposal, conflict, and review contracts.
6. Add tests for every rule in this document before adding parsers or graph
   persistence.

## Out of scope for this phase

The following are deliberately deferred:

- Artifact upload and checksums
- Parser, OCR, VLM, and LLM extraction
- Semantic compilation and graph writes
- Neo4j/PostgreSQL repositories
- API endpoints for entities and relationships
- User authentication, RBAC, and tenant authorization
- Diagram layout and rendering
- Integrations, background jobs, and service extraction

Those later modules must implement this contract rather than redefine it.
