"""Build evidence-backed proposal contracts from direct LLDP neighbor claims."""

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
from packages.extraction.lldp.models import LldpLine, LldpNeighborRecord, LldpParseResult
from packages.ingestion.models import ExtractionInput

EXTRACTOR_NAME = "cisco_lldp_neighbors_detail_parser"
EXTRACTOR_VERSION = "1"


class LldpNeighborsDetailProposalBuilder:
    """Build LLDP candidates without equating a chassis ID to a system name."""

    def build(
        self, *, extraction_input: ExtractionInput, parsed: LldpParseResult
    ) -> ExtractionResult:
        """Return proposal-only output with exact field-level evidence."""
        if extraction_input.artifact_kind is not ArtifactKind.LLDP_NEIGHBORS_DETAIL:
            raise ValueError("LLDP proposal builder requires an LLDP neighbor-detail input.")
        entities: list[EntityProposal] = []
        attributes: list[AttributeProposal] = []
        relationships: list[RelationshipProposal] = []
        findings: list[ValidationFinding] = []
        evidence_records: list[Evidence] = []
        for parsed_finding in parsed.findings:
            evidence = self._evidence(parsed_finding.line, parsed_finding.code, extraction_input)
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
        record: LldpNeighborRecord,
        extraction_input: ExtractionInput,
        entities: list[EntityProposal],
        attributes: list[AttributeProposal],
        relationships: list[RelationshipProposal],
        findings: list[ValidationFinding],
        evidence_records: list[Evidence],
    ) -> None:
        identifier = record.system_name or record.chassis_id
        if identifier is None:
            self._missing_finding(
                "lldp_neighbor_identifier_missing",
                "LLDP neighbor record has no direct system name or chassis ID claim.",
                record,
                extraction_input,
                findings,
                evidence_records,
            )
            return
        name, identifier_line = identifier
        remote_device = self._entity(EntityType.DEVICE, name, identifier_line, extraction_input)
        entities.append(remote_device)
        for field_path, claim in (
            ("properties.hostname", record.system_name),
            ("properties.chassis_id", record.chassis_id),
            ("properties.platform", record.platform),
            ("properties.capabilities", record.capabilities),
            ("properties.management_ip", record.management_address),
        ):
            if claim is not None:
                value, line = claim
                attributes.append(
                    self._attribute(
                        remote_device.proposal_id, field_path, value, line, extraction_input
                    )
                )
        if record.local_interface is None or record.remote_port is None:
            self._missing_finding(
                "lldp_connection_endpoint_missing",
                "LLDP neighbor record lacks a direct local interface or remote port claim.",
                record,
                extraction_input,
                findings,
                evidence_records,
            )
            return
        local_name, connection_line = record.local_interface
        remote_name, remote_line = record.remote_port
        local = self._entity(EntityType.INTERFACE, local_name, connection_line, extraction_input)
        remote = self._entity(EntityType.INTERFACE, remote_name, remote_line, extraction_input)
        entities.extend((local, remote))
        attributes.extend(
            (
                self._attribute(
                    local.proposal_id,
                    "properties.interface_name",
                    local_name,
                    connection_line,
                    extraction_input,
                ),
                self._attribute(
                    remote.proposal_id,
                    "properties.interface_name",
                    remote_name,
                    remote_line,
                    extraction_input,
                ),
            )
        )
        relationships.append(
            RelationshipProposal(
                relationship_type=RelationshipType.CONNECTED_TO,
                source_proposal_id=local.proposal_id,
                target_proposal_id=remote.proposal_id,
                extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
                extractor_version=EXTRACTOR_VERSION,
                evidence=[
                    self._evidence(connection_line, "CONNECTED_TO", extraction_input),
                    self._evidence(remote_line, "CONNECTED_TO", extraction_input),
                    self._evidence(identifier_line, name, extraction_input),
                ],
            )
        )

    def _missing_finding(
        self,
        code: str,
        message: str,
        record: LldpNeighborRecord,
        extraction_input: ExtractionInput,
        findings: list[ValidationFinding],
        evidence_records: list[Evidence],
    ) -> None:
        line = next(
            (
                claim[1]
                for claim in (record.system_name, record.chassis_id, record.local_interface)
                if claim
            ),
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
        line: LldpLine,
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
        line: LldpLine,
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
        line: LldpLine, extracted_value: str, extraction_input: ExtractionInput
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
