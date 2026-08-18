"""Build evidence-backed proposal contracts from direct CDP neighbor claims."""

from __future__ import annotations

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
from packages.extraction.cdp.models import CdpLine, CdpNeighborRecord, CdpParseResult
from packages.ingestion.models import ExtractionInput

EXTRACTOR_NAME = "cisco_cdp_neighbors_detail_parser"
EXTRACTOR_VERSION = "1"


class CdpNeighborsDetailProposalBuilder:
    """Build candidates from CDP without treating neighbor claims as resolved identity."""

    def build(
        self, *, extraction_input: ExtractionInput, parsed: CdpParseResult
    ) -> ExtractionResult:
        """Return direct-source proposals and structured findings for each CDP record."""
        if extraction_input.artifact_kind is not ArtifactKind.CDP_NEIGHBORS_DETAIL:
            raise ValueError("CDP proposal builder requires a CDP neighbor-detail input.")

        entities: list[EntityProposal] = []
        attributes: list[AttributeProposal] = []
        relationships: list[RelationshipProposal] = []
        findings: list[ValidationFinding] = []
        evidence_records: list[Evidence] = []

        for finding in parsed.findings:
            evidence = self._evidence(finding.line, finding.code, extraction_input)
            evidence_records.append(evidence)
            findings.append(
                ValidationFinding(
                    code=finding.code,
                    severity=FindingSeverity.ERROR,
                    message=finding.message,
                    subject_type="artifact_version",
                    field_path=finding.field_path,
                    evidence_ids=[evidence.id],
                )
            )
        for record in parsed.records:
            self._build_record(
                record,
                extraction_input,
                entities,
                attributes,
                relationships,
                findings,
                evidence_records,
            )

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
            entity_proposals=entities,
            attribute_proposals=attributes,
            relationship_proposals=relationships,
            findings=findings,
            evidence_records=evidence_records,
        )

    def _build_record(
        self,
        record: CdpNeighborRecord,
        extraction_input: ExtractionInput,
        entities: list[EntityProposal],
        attributes: list[AttributeProposal],
        relationships: list[RelationshipProposal],
        findings: list[ValidationFinding],
        evidence_records: list[Evidence],
    ) -> None:
        if record.device_id is None:
            self._missing_finding(
                "cdp_neighbor_device_id_missing",
                "CDP neighbor record has no direct Device ID claim.",
                record,
                extraction_input,
                findings,
                evidence_records,
            )
            return
        device_name, device_line = record.device_id
        remote_device = self._entity(EntityType.DEVICE, device_name, device_line, extraction_input)
        entities.append(remote_device)
        attributes.append(
            self._attribute(
                remote_device.proposal_id,
                "properties.hostname",
                device_name,
                device_line,
                extraction_input,
            )
        )
        for field_path, claim in (
            ("properties.platform", record.platform),
            ("properties.capabilities", record.capabilities),
            ("properties.management_ip", record.management_address),
        ):
            if claim is not None:
                value, line = claim
                attributes.append(
                    self._attribute(
                        remote_device.proposal_id,
                        field_path,
                        value,
                        line,
                        extraction_input,
                    )
                )

        if record.local_interface is None or record.remote_interface is None:
            self._missing_finding(
                "cdp_connection_endpoint_missing",
                "CDP neighbor record lacks a direct local or remote interface claim.",
                record,
                extraction_input,
                findings,
                evidence_records,
            )
            return
        local_name, connection_line = record.local_interface
        remote_name, _ = record.remote_interface
        local_interface = self._entity(
            EntityType.INTERFACE, local_name, connection_line, extraction_input
        )
        remote_interface = self._entity(
            EntityType.INTERFACE, remote_name, connection_line, extraction_input
        )
        entities.extend((local_interface, remote_interface))
        attributes.extend(
            (
                self._attribute(
                    local_interface.proposal_id,
                    "properties.interface_name",
                    local_name,
                    connection_line,
                    extraction_input,
                ),
                self._attribute(
                    remote_interface.proposal_id,
                    "properties.interface_name",
                    remote_name,
                    connection_line,
                    extraction_input,
                ),
            )
        )
        relationships.append(
            RelationshipProposal(
                relationship_type=RelationshipType.CONNECTED_TO,
                source_proposal_id=local_interface.proposal_id,
                target_proposal_id=remote_interface.proposal_id,
                extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
                extractor_version=EXTRACTOR_VERSION,
                evidence=[
                    self._evidence(connection_line, "CONNECTED_TO", extraction_input),
                    self._evidence(device_line, device_name, extraction_input),
                ],
            )
        )

    def _missing_finding(
        self,
        code: str,
        message: str,
        record: CdpNeighborRecord,
        extraction_input: ExtractionInput,
        findings: list[ValidationFinding],
        evidence_records: list[Evidence],
    ) -> None:
        line = next(
            (claim[1] for claim in (record.device_id, record.local_interface) if claim),
            None,
        )
        if line is None:
            return
        evidence = self._evidence(line, code, extraction_input)
        evidence_records.append(evidence)
        findings.append(
            ValidationFinding(
                code=code,
                severity=FindingSeverity.WARNING,
                message=message,
                subject_type="artifact_version",
                evidence_ids=[evidence.id],
            )
        )

    def _entity(
        self,
        entity_type: EntityType,
        display_name: str,
        line: CdpLine,
        extraction_input: ExtractionInput,
    ) -> EntityProposal:
        return EntityProposal(
            entity_type=entity_type,
            display_name=display_name,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version=EXTRACTOR_VERSION,
            evidence=[self._evidence(line, display_name, extraction_input)],
        )

    def _attribute(
        self,
        subject_proposal_id: UUID,
        field_path: str,
        value: str,
        line: CdpLine,
        extraction_input: ExtractionInput,
    ) -> AttributeProposal:
        return AttributeProposal(
            subject_proposal_id=subject_proposal_id,
            field_path=field_path,
            proposed_value=value,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_version=EXTRACTOR_VERSION,
            evidence=[self._evidence(line, value, extraction_input)],
        )

    @staticmethod
    def _evidence(
        line: CdpLine, extracted_value: str, extraction_input: ExtractionInput
    ) -> Evidence:
        return Evidence(
            source_artifact_id=extraction_input.artifact_id,
            source_artifact_version=str(extraction_input.version_number),
            source_artifact_checksum=extraction_input.sha256_checksum,
            source_location=SourceLocation(
                artifact_type=extraction_input.artifact_kind.value,
                line_start=line.number,
                line_end=line.number,
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
