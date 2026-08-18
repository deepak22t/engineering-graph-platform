"""Synchronous Phase 4 extraction orchestration."""

from uuid import UUID

from packages.artifacts.contracts import ArtifactKind, ArtifactStatus
from packages.artifacts.persistence import ArtifactRepository
from packages.domain.proposals import ExtractionResult
from packages.extraction.cdp.parser import CdpNeighborsDetailParser
from packages.extraction.cdp.proposals import CdpNeighborsDetailProposalBuilder
from packages.extraction.cisco_ios.parser import CiscoIosRunningConfigParser
from packages.extraction.cisco_ios.proposals import CiscoIosProposalBuilder
from packages.extraction.errors import UnsupportedExtractionKindError
from packages.extraction.lldp.parser import LldpNeighborsDetailParser
from packages.extraction.lldp.proposals import LldpNeighborsDetailProposalBuilder
from packages.extraction.reader import ArtifactContentReader
from packages.ingestion.service import IngestionService

_SUPPORTED_DETERMINISTIC_KINDS = frozenset(
    {
        ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        ArtifactKind.CDP_NEIGHBORS_DETAIL,
        ArtifactKind.LLDP_NEIGHBORS_DETAIL,
    }
)


class ExtractionService:
    """Run one deterministic extraction without any canonical graph write."""

    def __init__(
        self,
        *,
        repository: ArtifactRepository,
        ingestion_service: IngestionService,
        content_reader: ArtifactContentReader,
    ) -> None:
        self._repository = repository
        self._ingestion_service = ingestion_service
        self._content_reader = content_reader

    async def extract(self, artifact_id: UUID, version_number: int) -> ExtractionResult:
        """Return proposals, marking the source version's synchronous outcome."""
        extraction_input = await self._ingestion_service.prepare_extraction(
            artifact_id, version_number
        )
        await self._repository.update_version_status(
            artifact_id, version_number, ArtifactStatus.PROCESSING
        )
        try:
            if extraction_input.artifact_kind not in _SUPPORTED_DETERMINISTIC_KINDS:
                raise UnsupportedExtractionKindError(extraction_input.artifact_kind.value)
            source = await self._content_reader.read_verified_text(extraction_input)
            if extraction_input.artifact_kind is ArtifactKind.CISCO_IOS_RUNNING_CONFIG:
                parsed = CiscoIosRunningConfigParser().parse(source.text)
                result = CiscoIosProposalBuilder().build(
                    extraction_input=extraction_input, parsed=parsed
                )
            elif extraction_input.artifact_kind is ArtifactKind.CDP_NEIGHBORS_DETAIL:
                parsed = CdpNeighborsDetailParser().parse(source.text)
                result = CdpNeighborsDetailProposalBuilder().build(
                    extraction_input=extraction_input, parsed=parsed
                )
            elif extraction_input.artifact_kind is ArtifactKind.LLDP_NEIGHBORS_DETAIL:
                parsed = LldpNeighborsDetailParser().parse(source.text)
                result = LldpNeighborsDetailProposalBuilder().build(
                    extraction_input=extraction_input, parsed=parsed
                )

        except Exception:
            await self._repository.update_version_status(
                artifact_id, version_number, ArtifactStatus.FAILED
            )
            raise
        await self._repository.update_version_status(
            artifact_id, version_number, ArtifactStatus.PROCESSED
        )
        return result
