"""Convert parsed Cisco IOS claims into evidence-backed proposal-stage contracts."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from packages.artifacts.contracts import ArtifactKind
from packages.domain.confidence import confidence_score_for_method
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.proposals import (
    AttributeProposal,
    EntityProposal,
    ExtractionResult,
    RelationshipProposal,
)
from packages.domain.validation import FindingSeverity, ValidationFinding
from packages.extraction.cisco_ios.models import (
    CiscoIosLine,
    CiscoIosParseResult,
    HostnameClaim,
    InterfaceAccessVlanClaim,
    InterfaceAdminStateClaim,
    InterfaceClaim,
    InterfaceDescriptionClaim,
    InterfaceIpv4AddressClaim,
    VlanClaim,
    VlanNameClaim,
)
from packages.ingestion.models import ExtractionInput

EXTRACTOR_NAME = "cisco_ios_running_config_parser"
EXTRACTOR_VERSION = "1"
_DETERMINISTIC_CONFIDENCE = 0.95


class CiscoIosProposalBuilder:
    """Build proposals from one parsed Cisco config without canonical graph mutation."""

    def build(
        self,
        *,
        extraction_input: ExtractionInput,
        parsed: CiscoIosParseResult,
    ) -> ExtractionResult:
        """Return one typed proposal batch for the exact immutable source artifact version."""
        if extraction_input.artifact_kind is not ArtifactKind.CISCO_IOS_RUNNING_CONFIG:
            raise ValueError(
                "Cisco IOS proposal builder requires a Cisco IOS running-config input."
            )

        entity_proposals: list[EntityProposal] = []
        attribute_proposals: list[AttributeProposal] = []
        relationship_proposals: list[RelationshipProposal] = []
        findings, evidence_records = self._build_findings(parsed, extraction_input)

        hostname_claims = tuple(
            claim for claim in parsed.claims if isinstance(claim, HostnameClaim)
        )
        interface_claims = tuple(
            claim for claim in parsed.claims if isinstance(claim, InterfaceClaim)
        )
        vlan_claims = tuple(claim for claim in parsed.claims if isinstance(claim, VlanClaim))
        ip_claims = tuple(
            claim for claim in parsed.claims if isinstance(claim, InterfaceIpv4AddressClaim)
        )

        device_proposal = self._build_source_device(
            hostname_claims, extraction_input, entity_proposals, attribute_proposals, findings
        )
        if device_proposal is None and not hostname_claims and interface_claims:
            findings.append(
                ValidationFinding(
                    code="source_device_missing",
                    severity=FindingSeverity.WARNING,
                    message=(
                        "No reliable hostname claim is available for Device ownership proposals."
                    ),
                    subject_type="artifact_version",
                    field_path="properties.hostname",
                )
            )
        interfaces_by_line = self._build_interfaces(
            interface_claims, extraction_input, entity_proposals, attribute_proposals
        )
        vlans_by_id = self._build_vlans(
            vlan_claims, extraction_input, entity_proposals, attribute_proposals
        )
        self._add_access_vlan_entities(
            parsed.claims,
            vlans_by_id,
            extraction_input,
            entity_proposals,
            attribute_proposals,
        )
        ips_by_line = self._build_ips(
            ip_claims, extraction_input, entity_proposals, attribute_proposals
        )
        self._build_networks(ip_claims, extraction_input, entity_proposals, attribute_proposals)

        self._build_interface_attributes(
            parsed.claims, interfaces_by_line, extraction_input, attribute_proposals
        )
        self._build_vlan_name_attributes(
            parsed.claims, vlans_by_id, extraction_input, attribute_proposals
        )
        self._build_relationships(
            device_proposal,
            interface_claims,
            ip_claims,
            parsed.claims,
            interfaces_by_line,
            ips_by_line,
            vlans_by_id,
            extraction_input,
            relationship_proposals,
        )

        # Network proposal references are intentionally not relationships in this first contract.

        return ExtractionResult(
            artifact_id=extraction_input.artifact_id,
            artifact_version_id=extraction_input.artifact_version_id,
            artifact_version_number=extraction_input.version_number,
            artifact_kind=extraction_input.artifact_kind.value,
            artifact_checksum=extraction_input.sha256_checksum,
            scope=extraction_input.scope,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_name=EXTRACTOR_NAME,
            extractor_version=EXTRACTOR_VERSION,
            entity_proposals=entity_proposals,
            attribute_proposals=attribute_proposals,
            relationship_proposals=relationship_proposals,
            findings=findings,
            evidence_records=evidence_records,
        )

    def _build_source_device(
        self,
        hostname_claims: tuple[HostnameClaim, ...],
        extraction_input: ExtractionInput,
        entity_proposals: list[EntityProposal],
        attribute_proposals: list[AttributeProposal],
        findings: list[ValidationFinding],
    ) -> EntityProposal | None:
        if len(hostname_claims) != 1:
            if hostname_claims:
                findings.append(
                    ValidationFinding(
                        code="ambiguous_source_device_hostname",
                        severity=FindingSeverity.ERROR,
                        message=(
                            "Multiple hostname claims prevent a reliable source Device proposal."
                        ),
                        subject_type="artifact_version",
                        field_path="properties.hostname",
                    )
                )
            return None
        claim = hostname_claims[0]
        proposal = self._entity_proposal(
            entity_type=EntityType.DEVICE,
            display_name=claim.hostname,
            line=claim.line,
            extraction_input=extraction_input,
        )
        entity_proposals.append(proposal)
        attribute_proposals.append(
            self._attribute_proposal(
                subject_proposal_id=proposal.proposal_id,
                field_path="properties.hostname",
                value=claim.hostname,
                line=claim.line,
                extraction_input=extraction_input,
            )
        )
        return proposal

    def _build_interfaces(
        self,
        claims: tuple[InterfaceClaim, ...],
        extraction_input: ExtractionInput,
        entity_proposals: list[EntityProposal],
        attribute_proposals: list[AttributeProposal],
    ) -> dict[int, EntityProposal]:
        proposals: dict[int, EntityProposal] = {}
        for claim in claims:
            proposal = self._entity_proposal(
                entity_type=EntityType.INTERFACE,
                display_name=claim.interface_name,
                line=claim.line,
                extraction_input=extraction_input,
            )
            entity_proposals.append(proposal)
            proposals[claim.line.number] = proposal
            attribute_proposals.extend(
                (
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.interface_name",
                        value=claim.interface_name,
                        line=claim.line,
                        extraction_input=extraction_input,
                    ),
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.interface_type",
                        value=claim.interface_type,
                        line=claim.line,
                        extraction_input=extraction_input,
                    ),
                )
            )
        return proposals

    def _build_vlans(
        self,
        claims: tuple[VlanClaim, ...],
        extraction_input: ExtractionInput,
        entity_proposals: list[EntityProposal],
        attribute_proposals: list[AttributeProposal],
    ) -> dict[int, EntityProposal]:
        proposals: dict[int, EntityProposal] = {}
        for claim in claims:
            if claim.vlan_id in proposals:
                continue
            proposal = self._vlan_proposal(claim.vlan_id, claim.line, extraction_input)
            entity_proposals.append(proposal)
            attribute_proposals.append(
                self._attribute_proposal(
                    subject_proposal_id=proposal.proposal_id,
                    field_path="properties.vlan_id",
                    value=claim.vlan_id,
                    line=claim.line,
                    extraction_input=extraction_input,
                )
            )
            proposals[claim.vlan_id] = proposal
        return proposals

    def _add_access_vlan_entities(
        self,
        claims: Iterable[object],
        vlans_by_id: dict[int, EntityProposal],
        extraction_input: ExtractionInput,
        entity_proposals: list[EntityProposal],
        attribute_proposals: list[AttributeProposal],
    ) -> None:
        for claim in claims:
            if not isinstance(claim, InterfaceAccessVlanClaim) or claim.vlan_id in vlans_by_id:
                continue
            proposal = self._vlan_proposal(claim.vlan_id, claim.line, extraction_input)
            entity_proposals.append(proposal)
            attribute_proposals.append(
                self._attribute_proposal(
                    subject_proposal_id=proposal.proposal_id,
                    field_path="properties.vlan_id",
                    value=claim.vlan_id,
                    line=claim.line,
                    extraction_input=extraction_input,
                )
            )
            vlans_by_id[claim.vlan_id] = proposal

    def _build_ips(
        self,
        claims: tuple[InterfaceIpv4AddressClaim, ...],
        extraction_input: ExtractionInput,
        entity_proposals: list[EntityProposal],
        attribute_proposals: list[AttributeProposal],
    ) -> dict[int, EntityProposal]:
        proposals: dict[int, EntityProposal] = {}
        for claim in claims:
            proposal = self._entity_proposal(
                entity_type=EntityType.IP,
                display_name=claim.address,
                line=claim.line,
                extraction_input=extraction_input,
                section=f"interface {claim.interface_name}",
            )
            entity_proposals.append(proposal)
            proposals[claim.line.number] = proposal
            attribute_proposals.extend(
                (
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.address",
                        value=claim.address,
                        line=claim.line,
                        extraction_input=extraction_input,
                        section=f"interface {claim.interface_name}",
                    ),
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.address_family",
                        value="ipv4",
                        line=claim.line,
                        extraction_input=extraction_input,
                        section=f"interface {claim.interface_name}",
                    ),
                )
            )
        return proposals

    def _build_networks(
        self,
        claims: tuple[InterfaceIpv4AddressClaim, ...],
        extraction_input: ExtractionInput,
        entity_proposals: list[EntityProposal],
        attribute_proposals: list[AttributeProposal],
    ) -> dict[int, EntityProposal]:
        proposals: dict[int, EntityProposal] = {}
        for claim in claims:
            proposal = self._entity_proposal(
                entity_type=EntityType.NETWORK,
                display_name=claim.network_cidr,
                line=claim.line,
                extraction_input=extraction_input,
                section=f"interface {claim.interface_name}",
            )
            entity_proposals.append(proposal)
            proposals[claim.line.number] = proposal
            attribute_proposals.extend(
                (
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.cidr",
                        value=claim.network_cidr,
                        line=claim.line,
                        extraction_input=extraction_input,
                        section=f"interface {claim.interface_name}",
                    ),
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.address_family",
                        value="ipv4",
                        line=claim.line,
                        extraction_input=extraction_input,
                        section=f"interface {claim.interface_name}",
                    ),
                    self._attribute_proposal(
                        subject_proposal_id=proposal.proposal_id,
                        field_path="properties.network_type",
                        value="interface_subnet",
                        line=claim.line,
                        extraction_input=extraction_input,
                        section=f"interface {claim.interface_name}",
                    ),
                )
            )
        return proposals

    def _build_interface_attributes(
        self,
        claims: Iterable[object],
        interfaces_by_line: dict[int, EntityProposal],
        extraction_input: ExtractionInput,
        attribute_proposals: list[AttributeProposal],
    ) -> None:
        for claim in claims:
            if isinstance(claim, InterfaceDescriptionClaim):
                field_path, value = "properties.description", claim.description
            elif isinstance(claim, InterfaceAdminStateClaim):
                field_path, value = "properties.admin_status", claim.admin_status
            else:
                continue
            proposal = interfaces_by_line.get(claim.interface_line_number)
            if proposal is None:
                continue
            attribute_proposals.append(
                self._attribute_proposal(
                    subject_proposal_id=proposal.proposal_id,
                    field_path=field_path,
                    value=value,
                    line=claim.line,
                    extraction_input=extraction_input,
                    section=f"interface {claim.interface_name}",
                )
            )

    def _build_vlan_name_attributes(
        self,
        claims: Iterable[object],
        vlans_by_id: dict[int, EntityProposal],
        extraction_input: ExtractionInput,
        attribute_proposals: list[AttributeProposal],
    ) -> None:
        for claim in claims:
            if not isinstance(claim, VlanNameClaim):
                continue
            proposal = vlans_by_id.get(claim.vlan_id)
            if proposal is None:
                continue
            attribute_proposals.append(
                self._attribute_proposal(
                    subject_proposal_id=proposal.proposal_id,
                    field_path="properties.vlan_name",
                    value=claim.vlan_name,
                    line=claim.line,
                    extraction_input=extraction_input,
                    section=f"vlan {claim.vlan_id}",
                )
            )

    def _build_relationships(
        self,
        device_proposal: EntityProposal | None,
        interface_claims: tuple[InterfaceClaim, ...],
        ip_claims: tuple[InterfaceIpv4AddressClaim, ...],
        claims: Iterable[object],
        interfaces_by_line: dict[int, EntityProposal],
        ips_by_line: dict[int, EntityProposal],
        vlans_by_id: dict[int, EntityProposal],
        extraction_input: ExtractionInput,
        relationship_proposals: list[RelationshipProposal],
    ) -> None:
        if device_proposal is not None:
            for claim in interface_claims:
                interface = interfaces_by_line[claim.line.number]
                relationship_proposals.append(
                    self._relationship_proposal(
                        relationship_type=RelationshipType.HAS_INTERFACE,
                        source_proposal_id=device_proposal.proposal_id,
                        target_proposal_id=interface.proposal_id,
                        line=claim.line,
                        extraction_input=extraction_input,
                        section=f"interface {claim.interface_name}",
                    )
                )
        for claim in ip_claims:
            interface = interfaces_by_line.get(claim.interface_line_number)
            ip = ips_by_line[claim.line.number]
            if interface is None:
                continue
            relationship_proposals.append(
                self._relationship_proposal(
                    relationship_type=RelationshipType.ATTACHED_TO,
                    source_proposal_id=ip.proposal_id,
                    target_proposal_id=interface.proposal_id,
                    line=claim.line,
                    extraction_input=extraction_input,
                    section=f"interface {claim.interface_name}",
                )
            )
        for claim in claims:
            if not isinstance(claim, InterfaceAccessVlanClaim):
                continue
            interface = interfaces_by_line.get(claim.interface_line_number)
            vlan = vlans_by_id.get(claim.vlan_id)
            if interface is None or vlan is None:
                continue
            relationship_proposals.append(
                self._relationship_proposal(
                    relationship_type=RelationshipType.MEMBER_OF,
                    source_proposal_id=interface.proposal_id,
                    target_proposal_id=vlan.proposal_id,
                    line=claim.line,
                    extraction_input=extraction_input,
                    section=f"interface {claim.interface_name}",
                )
            )

    def _entity_proposal(
        self,
        *,
        entity_type: EntityType,
        display_name: str,
        line: CiscoIosLine,
        extraction_input: ExtractionInput,
        section: str | None = None,
    ) -> EntityProposal:
        return EntityProposal(
            entity_type=entity_type,
            display_name=display_name,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version=EXTRACTOR_VERSION,
            evidence=[self._evidence(line, display_name, extraction_input, section)],
        )

    def _vlan_proposal(
        self, vlan_id: int, line: CiscoIosLine, extraction_input: ExtractionInput
    ) -> EntityProposal:
        return self._entity_proposal(
            entity_type=EntityType.VLAN,
            display_name=f"VLAN {vlan_id}",
            line=line,
            extraction_input=extraction_input,
            section=f"vlan {vlan_id}",
        )

    def _attribute_proposal(
        self,
        *,
        subject_proposal_id: UUID,
        field_path: str,
        value: object,
        line: CiscoIosLine,
        extraction_input: ExtractionInput,
        section: str | None = None,
    ) -> AttributeProposal:
        return AttributeProposal(
            subject_proposal_id=subject_proposal_id,
            field_path=field_path,
            proposed_value=value,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version=EXTRACTOR_VERSION,
            evidence=[self._evidence(line, str(value), extraction_input, section)],
        )

    def _relationship_proposal(
        self,
        *,
        relationship_type: RelationshipType,
        source_proposal_id: UUID,
        target_proposal_id: UUID,
        line: CiscoIosLine,
        extraction_input: ExtractionInput,
        section: str | None = None,
    ) -> RelationshipProposal:
        return RelationshipProposal(
            relationship_type=relationship_type,
            source_proposal_id=source_proposal_id,
            target_proposal_id=target_proposal_id,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version=EXTRACTOR_VERSION,
            evidence=[self._evidence(line, relationship_type.value, extraction_input, section)],
        )

    @staticmethod
    def _evidence(
        line: CiscoIosLine,
        extracted_value: str,
        extraction_input: ExtractionInput,
        section: str | None,
    ) -> Evidence:
        return Evidence(
            source_artifact_id=extraction_input.artifact_id,
            source_artifact_version=str(extraction_input.version_number),
            source_artifact_checksum=extraction_input.sha256_checksum,
            source_location=SourceLocation(
                artifact_type=extraction_input.artifact_kind.value,
                line_start=line.number,
                line_end=line.number,
                section=section,
            ),
            evidence_reference=(
                f"artifact://{extraction_input.artifact_id}/versions/"
                f"{extraction_input.version_number}#line={line.number}"
            ),
            extracted_value=extracted_value,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version=EXTRACTOR_VERSION,
            confidence=confidence_score_for_method(ExtractionMethod.DETERMINISTIC_PARSER),
        )

    def _build_findings(
        self, parsed: CiscoIosParseResult, extraction_input: ExtractionInput
    ) -> tuple[list[ValidationFinding], list[Evidence]]:
        findings: list[ValidationFinding] = []
        evidence_records: list[Evidence] = []
        for parsed_finding in parsed.findings:
            evidence = self._evidence(
                parsed_finding.line,
                parsed_finding.code,
                extraction_input,
                section=None,
            )
            evidence_records.append(evidence)
            findings.append(
                ValidationFinding(
                    code=parsed_finding.code,
                    severity=FindingSeverity.ERROR,
                    message=parsed_finding.message,
                    subject_type="artifact_version",
                    field_path=parsed_finding.field_path,
                    evidence_ids=[evidence.id],
                )
            )
        return findings, evidence_records
