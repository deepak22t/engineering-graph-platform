# Phase 4 Cisco IOS running-config grammar

## Purpose

This is the exact first deterministic extraction contract. It turns one artifact
classified as `cisco_ios_running_config` into **proposals only**. It does not
create canonical entities, resolve identities, deduplicate across artifacts,
write Neo4j, or infer topology.

The parser must implement only this document. A Cisco IOS configuration is a
large language; unsupported syntax is not permission to guess.

## Input and output boundary

Input is exactly one `ExtractionInput` plus `VerifiedArtifactText` produced by
the internal content reader. The reader has already verified the artifact
version's SHA-256 checksum and valid UTF-8 decoding.

Output is one `ExtractionResult` with:

- the same artifact, version, checksum, scope, extractor name and version;
- `EntityProposal`, `AttributeProposal`, and `RelationshipProposal` records;
- one precise `Evidence` record per proposed property or relationship; and
- structured `ValidationFinding` records for malformed supported commands.

The parser must not receive a client filename, storage key, canonical ID,
proposal ID, confidence level, or database/Neo4j client.

## Line and block rules

- Preserve original one-based line numbers, including blank lines and comments.
- Treat `!`, a blank line, `end`, or any non-indented top-level command as the
  end of the current `interface` or `vlan` block.
- A supported subcommand is valid only while its matching block is current.
- Leading spaces or tabs are allowed before supported subcommands. The command
  words themselves must be complete; abbreviations such as `int` or `desc` are
  unsupported.
- Command tokens are case-sensitive for this first parser: only the normal IOS
  lower-case spellings below are accepted. Normalization is Phase 5 work.
- Unknown commands create no proposal. They may produce one informational
  finding, but never an error solely because the command is unsupported.

## Supported grammar and exact proposal mapping

| Syntax (anchored to the entire logical line) | Required context | Proposed output | Evidence | Invalid form |
| --- | --- | --- | --- | --- |
| `hostname <hostname>` | top level | one `DEVICE` proposal; `properties.hostname` attribute proposal | the hostname line | error finding; no device claim |
| `interface <interface-name>` | top level | one `INTERFACE` proposal and `properties.interface_name` + `properties.interface_type` attribute proposals | the interface line | error finding; no interface claim |
| `description <text>` | current interface | `properties.description` attribute proposal | the description line | error finding; no description claim |
| `ip address <ipv4> <netmask>` | current interface | `IP` and `NETWORK` proposals; IP address/address-family, network CIDR/address-family/network-type attributes; `IP -> INTERFACE` `ATTACHED_TO` proposal | the IP-address line | error finding; no IP, network, or attachment claim |
| `switchport access vlan <vlan-id>` | current interface | `VLAN` proposal when no source-local VLAN reference exists; `properties.vlan_id` attribute; `INTERFACE -> VLAN` `MEMBER_OF` proposal | the switchport line | error finding; no membership claim |
| `vlan <vlan-id>` | top level | one source-local `VLAN` proposal and `properties.vlan_id` attribute | the VLAN line | error finding; no VLAN claim |
| `name <text>` | current VLAN | `properties.vlan_name` attribute proposal | the VLAN-name line | error finding; no VLAN-name claim |
| `shutdown` | current interface | `properties.admin_status = down` attribute proposal | the shutdown line | no special fallback |
| `no shutdown` | current interface | `properties.admin_status = up` attribute proposal | the no-shutdown line | no special fallback |

### Exact value restrictions

- `<hostname>` and `<interface-name>` are one non-whitespace token. Interface
  names must begin with an alphabetic type prefix followed by a non-empty
  non-whitespace suffix, for example `GigabitEthernet0/1` or `Port-channel1`.
  The prefix becomes the proposed `interface_type`; the whole token becomes
  the proposed `interface_name`.
- `<text>` must contain at least one non-whitespace character after trimming
  outer whitespace. Quoted text has no special parsing in this first version.
- `<ipv4>` must be a valid IPv4 address and `<netmask>` a valid IPv4 netmask.
  `dhcp`, `negotiated`, `unnumbered`, `secondary`, IPv6, and extra tokens are
  out of scope. The network is the IPv4 network obtained from the address and
  netmask; it must be canonical.
- `<vlan-id>` must be base-10 digits only and be in the inclusive range
  `1..4094`. Values such as `0`, `4095`, `0010x`, ranges, and comma lists are
  invalid for this parser.

## Relationship contract

Only direct source facts create relationships:

```text
DEVICE    -> INTERFACE : HAS_INTERFACE
IP        -> INTERFACE : ATTACHED_TO
INTERFACE -> VLAN      : MEMBER_OF
```

`HAS_INTERFACE` is emitted only when a reliable hostname/device proposal and
an interface proposal both exist in this artifact. A config without a hostname
may still return interface proposals and a structured finding, but it must not
invent a source device association.

A running configuration does **not** prove physical adjacency. It must never
emit `CONNECTED_TO`; CDP and LLDP detail parsers are responsible for later
candidate topology connections.

A source-local VLAN reference is only a way to link facts inside this one
extraction result. It is not canonical identity resolution and must not merge
claims from other artifact versions or scopes.

## Evidence, metadata, and confidence

Every emitted property and relationship receives separate evidence with:

```text
source_artifact_id
source_artifact_version and checksum
line_start = line_end = exact source line
section = current interface or VLAN block when applicable
extracted_value
extraction_method = deterministic_parser
extractor version
recorded_at
confidence candidate from the shared deterministic policy
```

`observed_at` is left unset unless the source itself supplies an observation
time. Upload time must not be represented as source observation time.

The parser emits one proposal per explicit claim. If the same source has two
contradictory commands, it retains both proposals and their evidence; it does
not silently overwrite the earlier claim. Phase 5 handles normalization,
conflict detection, resolution, and canonical commit.

## Findings and out-of-scope syntax

Malformed syntax for a supported command produces a `ValidationFinding` with:

```text
severity = error
subject_type = artifact_version
field_path = the relevant command/property
line-level evidence ID when source evidence was constructed
```

Unsupported syntax is ignored or reported as `info`; it creates no engineering
fact. The following are explicitly deferred:

```text
route maps, VRFs, ACLs/firewall policies, NAT, routing protocols,
port channels, stack/VSS, interface ranges, abbreviations, nested modes,
IPv6, DHCP/unnumbered/secondary addresses, trunk VLAN lists, and all
commands not listed above.
```

## Acceptance examples for the parser tests in Step 5

The existing sanitized fixture must produce:

```text
hostname edge-router-01
interface GigabitEthernet0/1
 description Uplink to distribution switch
 ip address 192.0.2.1 255.255.255.252
 no shutdown
```

Expected facts are one device proposal, one interface proposal, one IP
proposal, one `192.0.2.0/30` network proposal, `HAS_INTERFACE`,
`ATTACHED_TO`, and separate line-level evidence for hostname, interface,
description, IP attachment, and administrative state. No `CONNECTED_TO` fact
is expected.

Before adding more Cisco syntax, update this document, add the corresponding
parser tests, and verify the typed domain property and relationship contracts.