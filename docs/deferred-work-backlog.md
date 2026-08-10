# Deferred Work Backlog

This document is the single register for work deliberately **not** implemented
in the current Engineering Graph Platform scope. It prevents a deferred feature
from being forgotten or being added without its required contracts and tests.

It is a backlog, not a commitment to build every item immediately. A later
phase or a specific user requirement must select an item before implementation
starts.

## Current baseline

Phase 4 currently supports deterministic, proposal-only extraction for:

- Cisco IOS running configuration (the documented subset only);
- Cisco CDP neighbor-detail output; and
- Cisco LLDP neighbor-detail output.

The output is evidence-backed proposals. It does not create canonical graph
facts or write to Neo4j.

## Rules for every backlog item

Before starting an item:

1. Confirm that its prerequisite phase is complete.
2. Define the accepted source grammar or source schema.
3. Update the relevant typed property, identity, relationship, and evidence
   contracts when required.
4. Add sanitized fixtures and valid, invalid, ambiguous, and regression tests.
5. Keep extractor output proposal-only. Semantic validation and canonical commit
   remain Phase 5 responsibilities.
6. Update this register: mark the item implemented, split it, or add a newly
   discovered deferred item.

## A. Deterministic Cisco IOS running-config expansion

The current supported grammar is intentionally small. Its exact supported
commands are maintained in
[Phase 4 Cisco IOS grammar](phase4-cisco-ios-running-config-grammar.md).

| ID | Deferred capability | Do not do until | Notes |
| --- | --- | --- | --- |
| CISCO-01 | IPv6 addresses and networks | Typed IPv6 proposal/property mapping is specified | Never treat an IPv6 address as the current IPv4 command. |
| CISCO-02 | Static and dynamic routes, OSPF, EIGRP, BGP, and other routing protocols | Route grammar, route properties, and relationship semantics are selected | Parse one protocol/subset at a time. |
| CISCO-03 | VRFs | Scope/VRF semantics are defined | Do not silently merge same CIDR across VRFs. |
| CISCO-04 | ACLs and firewall policies | Firewall-policy proposal contract and policy identity are specified | Do not convert configuration text directly to canonical policy facts. |
| CISCO-05 | NAT | NAT proposal and relationship design are specified | Preserve inside/outside context and evidence. |
| CISCO-06 | Trunk VLAN lists, port channels, stack/VSS, and interface ranges | Exact grammar and cardinality rules are specified | Do not expand ranges by guesswork. |
| CISCO-07 | DHCP, unnumbered, secondary addresses, and other address variants | Per-variant IP semantics are specified | Keep unsupported variants as findings or ignored syntax. |
| CISCO-08 | Cisco abbreviations, nested modes, and remaining commands | A deterministic grammar for each construct is approved | Unsupported syntax never creates an inferred fact. |

## B. Additional deterministic artifact schemas

| ID | Deferred capability | Do not do until | Notes |
| --- | --- | --- | --- |
| FORMAT-01 | JSON extraction | A source-specific JSON schema is defined | Arbitrary keys are not engineering facts. |
| FORMAT-02 | YAML extraction | A source-specific YAML schema is defined | Same rule as JSON. |
| FORMAT-03 | CSV extraction | Header meanings, row identity, and validation rules are defined | Do not infer meaning from a column name alone. |
| FORMAT-04 | Generic TXT extraction | A named text format and deterministic grammar are defined | Plain prose remains unsupported. |
| FORMAT-05 | Additional network vendor/configuration formats | One vendor format and its deterministic grammar are chosen | Add one representative format at a time. |

## C. Unstructured document and AI-assisted extraction

| ID | Deferred capability | Do not do until | Notes |
| --- | --- | --- | --- |
| AI-01 | PDF text extraction | A supported PDF source contract and page-level evidence policy are defined | Use deterministic text extraction before AI where possible. |
| AI-02 | OCR for scanned PDFs/images | OCR quality policy, page/box evidence, and confidence policy are defined | OCR output is a proposal, never a canonical write. |
| AI-03 | VLM diagram extraction | Diagram entity/connection proposal contract and bounding-box evidence are defined | Diagram links are candidates requiring later validation. |
| AI-04 | LLM extraction for unstructured engineering text | Prompt/model versioning, evidence policy, evaluation fixtures, and review policy are defined | LLM output is proposal-only and lower-trust unless policy says otherwise. |

## D. Semantic compilation and canonical commit

These are the next core capabilities after deterministic extraction, primarily
Phase 5 work.

| ID | Deferred capability | Do not do until | Notes |
| --- | --- | --- | --- |
| GRAPH-01 | Proposal schema validation and normalization | Phase 4 proposal outputs are stable | Reuse shared normalization functions. |
| GRAPH-02 | Typed identity resolution | Identity policy and scope rules are applied | Resolve candidates; do not identify by display name alone. |
| GRAPH-03 | Relationship validation and duplicate/cardinality checks | Endpoint identities are resolved | Apply the Phase 1 relationship specifications. |
| GRAPH-04 | Evidence/confidence aggregation | Competing evidence can be compared | Use the shared confidence policy. |
| GRAPH-05 | Conflict detection and human review decisions | Candidate claims are validated | Never overwrite an old claim silently. |
| GRAPH-06 | Canonical graph commit / Neo4j persistence | All prior semantic checks succeed | Extractors must never perform this step. |

## E. Platform improvements intentionally deferred

| ID | Deferred capability | Do not do until | Notes |
| --- | --- | --- | --- |
| PLATFORM-01 | Login, RBAC, and tenant authorization | Product authorization requirements are selected | Scope-aware identity already exists; authorization does not. |
| PLATFORM-02 | Configurable confidence thresholds and auto-commit policy | Review/commit workflow is implemented | Do not introduce parser-specific thresholds. |
| PLATFORM-03 | Human correction actor/review references | Review UI/workflow exists | Corrections must remain traceable. |
| PLATFORM-04 | Inferred-fact input IDs and rule-version tracking | Inference rules are implemented | Preserve source facts and rule version. |
| PLATFORM-05 | Public artifact download endpoint | A concrete internal/user need exists and access rules are defined | Internal storage retrieval is sufficient today. |

## Status updates

When an item is implemented, replace its row with:

```text
Status: implemented
Implemented in: phase/step/commit
Tests: paths or command
Decision: short explanation of the selected grammar/schema
```

Do not remove completed items: keeping the history explains why the supported
scope looks the way it does.