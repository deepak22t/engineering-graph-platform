"""Tests for exact relationship-level evidence attribution."""

from uuid import UUID, uuid4

from packages.domain.compilation import (
    CanonicalSnapshot,
    CompilationInput,
    EntityResolution,
    EntityResolutionResult,
    EntityResolutionStatus,
    TypedPropertyCandidate,
    aggregate_fact_confidences,
    associate_relationship_evidence,
    compile_relationship_candidates,
)
from packages.domain.entities.properties import DeviceProperties, InterfaceProperties
from packages.domain.enums import EntityType, ExtractionMethod, RelationshipType
from packages.domain.evidence import Evidence, SourceLocation
from packages.domain.identity import DeviceIdentity, InterfaceIdentity
from packages.domain.ids import generate_entity_id
from packages.domain.proposals import ExtractionResult, RelationshipProposal
from packages.domain.scope import GraphScope

ARTIFACT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ARTIFACT_VERSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SCOPE = GraphScope(
    organization_id=UUID("11111111-1111-1111-1111-111111111111"),
    project_id=UUID("22222222-2222-2222-2222-222222222222"),
    environment="production",
    site_id=UUID("33333333-3333-3333-3333-333333333333"),
)


def _evidence(line: int, *, checksum: str = "a" * 64) -> Evidence:
    return Evidence(
        source_artifact_id=ARTIFACT_ID,
        source_artifact_version="1",
        source_artifact_checksum=checksum,
        source_location=SourceLocation(line_start=line),
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        confidence=0.95,
    )


def _proposal(device_id: UUID, interface_id: UUID, evidence: Evidence) -> RelationshipProposal:
    return RelationshipProposal(
        relationship_type=RelationshipType.HAS_INTERFACE,
        source_proposal_id=device_id,
        target_proposal_id=interface_id,
        extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
        extractor_version="1",
        evidence=[evidence],
    )


def _input(proposals: list[RelationshipProposal]) -> CompilationInput:
    return CompilationInput(
        extraction_result=ExtractionResult(
            artifact_id=ARTIFACT_ID,
            artifact_version_id=ARTIFACT_VERSION_ID,
            artifact_version_number=1,
            artifact_kind="cisco_ios_running_config",
            artifact_checksum="a" * 64,
            scope=SCOPE,
            extraction_method=ExtractionMethod.DETERMINISTIC_PARSER,
            extractor_name="test-parser",
            extractor_version="1",
            relationship_proposals=proposals,
        ),
        canonical_snapshot=CanonicalSnapshot(scope=SCOPE),
    )


def _resolutions(device_id: UUID, interface_id: UUID) -> EntityResolutionResult:
    device_identity = DeviceIdentity(scope=SCOPE, hostname="router-01")
    interface_identity = InterfaceIdentity(
        scope=SCOPE,
        parent_device_identity=device_identity,
        interface_name="Gi0/1",
    )
    return EntityResolutionResult(
        resolutions=(
            EntityResolution(
                candidate=TypedPropertyCandidate(
                    entity_type=EntityType.DEVICE,
                    subject_proposal_id=device_id,
                    properties=DeviceProperties(hostname="router-01"),
                    attribute_proposal_ids=(uuid4(),),
                ),
                status=EntityResolutionStatus.NEW_CANDIDATE,
                identity=device_identity,
                canonical_entity_id=generate_entity_id(device_identity),
            ),
            EntityResolution(
                candidate=TypedPropertyCandidate(
                    entity_type=EntityType.INTERFACE,
                    subject_proposal_id=interface_id,
                    properties=InterfaceProperties(
                        interface_name="Gi0/1",
                        interface_type="ethernet",
                    ),
                    attribute_proposal_ids=(uuid4(),),
                ),
                status=EntityResolutionStatus.NEW_CANDIDATE,
                identity=interface_identity,
                canonical_entity_id=generate_entity_id(interface_identity),
            ),
        )
    )


def test_relationship_attribution_uses_only_its_exact_proposal_evidence() -> None:
    device_id, interface_id = uuid4(), uuid4()
    relation_evidence = _evidence(10)
    proposal = _proposal(device_id, interface_id, relation_evidence)
    compilation_input = _input([proposal])
    relationships = compile_relationship_candidates(
        compilation_input, _resolutions(device_id, interface_id)
    )

    output = associate_relationship_evidence(compilation_input, relationships)

    assert output.findings == ()
    assert len(output.fact_attributions) == 1
    attribution = output.fact_attributions[0]
    assert attribution.fact_kind == "relationship"
    assert attribution.relationship_id == relationships.candidates[0].id
    assert attribution.evidence_id == relation_evidence.id
    assert attribution.entity_id is None
    assert attribution.property_path is None


def test_equivalent_duplicate_claims_preserve_all_relationship_evidence() -> None:
    device_id, interface_id = uuid4(), uuid4()
    first_evidence, second_evidence = _evidence(10), _evidence(20)
    compilation_input = _input(
        [
            _proposal(device_id, interface_id, first_evidence),
            _proposal(device_id, interface_id, second_evidence),
        ]
    )
    relationships = compile_relationship_candidates(
        compilation_input, _resolutions(device_id, interface_id)
    )

    output = associate_relationship_evidence(compilation_input, relationships)

    assert len(relationships.candidates) == 1
    assert relationships.findings == ()
    assert {item.evidence_id for item in output.fact_attributions} == {
        first_evidence.id,
        second_evidence.id,
    }


def test_stale_relationship_evidence_does_not_create_attribution() -> None:
    device_id, interface_id = uuid4(), uuid4()
    proposal = _proposal(device_id, interface_id, _evidence(10, checksum="b" * 64))
    compilation_input = _input([proposal])
    relationships = compile_relationship_candidates(
        compilation_input, _resolutions(device_id, interface_id)
    )

    output = associate_relationship_evidence(compilation_input, relationships)

    assert output.fact_attributions == ()
    assert output.findings[-1].code == "unverifiable_relationship_evidence"


def test_compiled_relationship_gets_one_reproducible_shared_policy_confidence() -> None:
    device_id, interface_id = uuid4(), uuid4()
    relation_evidence = _evidence(10)
    compilation_input = _input([_proposal(device_id, interface_id, relation_evidence)])
    relationships = compile_relationship_candidates(
        compilation_input, _resolutions(device_id, interface_id)
    )
    evidence_result = associate_relationship_evidence(compilation_input, relationships)

    first = aggregate_fact_confidences(compilation_input, evidence_result)
    second = aggregate_fact_confidences(compilation_input, evidence_result)

    assert first == second
    assert first.findings == ()
    assert len(first.fact_confidences) == 1
    fact_confidence = first.fact_confidences[0]
    assert fact_confidence.fact_kind == "relationship"
    assert fact_confidence.relationship_id == relationships.candidates[0].id
    assert fact_confidence.confidence.score == 0.9025
    assert fact_confidence.confidence.level.value == "high"
    assert fact_confidence.confidence.method == "aggregate"
    assert fact_confidence.confidence.rationale == "agreeing evidence increased confidence"
    assert fact_confidence.confidence.auto_commit_eligible


def test_equivalent_relationship_claims_aggregate_to_one_confidence() -> None:
    device_id, interface_id = uuid4(), uuid4()
    first_evidence, second_evidence = _evidence(10), _evidence(20)
    compilation_input = _input(
        [
            _proposal(device_id, interface_id, first_evidence),
            _proposal(device_id, interface_id, second_evidence),
        ]
    )
    relationships = compile_relationship_candidates(
        compilation_input, _resolutions(device_id, interface_id)
    )
    evidence_result = associate_relationship_evidence(compilation_input, relationships)

    output = aggregate_fact_confidences(compilation_input, evidence_result)

    assert output.findings == ()
    assert len(relationships.candidates) == 1
    assert len(output.fact_confidences) == 1
    assert output.fact_confidences[0].confidence.score == 0.9525
    assert (
        output.fact_confidences[0].confidence.rationale
        == "agreeing evidence increased confidence"
    )
