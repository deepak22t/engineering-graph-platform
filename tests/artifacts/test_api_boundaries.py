"""Tests that HTTP adapters do not absorb Artifact Service responsibilities."""

import inspect
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.api import artifacts
from packages.artifacts import Artifact, ArtifactKind, ArtifactScope, ArtifactVersion


class FakeUploadService:
    def __init__(self) -> None:
        self.initial_call = None
        self.next_call = None

    async def upload_initial(self, **kwargs):
        self.initial_call = {**kwargs, "content": await collect_chunks(kwargs["chunks"])}
        return records(kwargs["scope"])

    async def upload_next(self, **kwargs):
        self.next_call = {**kwargs, "content": await collect_chunks(kwargs["chunks"])}
        return records(
            ArtifactScope(
                organization_id=UUID(int=1),
                project_id=UUID(int=2),
                environment="prod",
                site_id=UUID(int=3),
            )
        )


async def collect_chunks(chunks):
    return b"".join([chunk async for chunk in chunks])


def records(scope: ArtifactScope):
    artifact = Artifact(id=UUID(int=10), scope=scope)
    return artifact, ArtifactVersion(
        id=UUID(int=11),
        artifact_id=artifact.id,
        version_number=1,
        original_filename="router.cfg",
        artifact_kind=ArtifactKind.CISCO_IOS_RUNNING_CONFIG,
        content_type="text/plain",
        size_bytes=3,
        sha256_checksum="a" * 64,
        storage_key="artifacts/00000000-0000-0000-0000-00000000000a/versions/1/original",
    )


def test_artifact_routes_delegate_business_work_to_service():
    source = inspect.getsource(artifacts)

    for forbidden_name in (
        "asyncpg",
        "miniopy_async",
        "ArtifactClassifier",
        "ArtifactFileValidator",
        "ArtifactStreamProcessor",
        "sha256",
        ".execute(",
    ):
        assert forbidden_name not in source

    assert "service.upload_initial(" in source
    assert "service.upload_next(" in source


@pytest.mark.asyncio
async def test_create_artifact_route_only_adapts_http_request_to_service():
    app = FastAPI()
    service = FakeUploadService()
    app.state.artifact_upload_service = service
    app.include_router(artifacts.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/artifacts",
            data={
                "organization_id": str(UUID(int=1)),
                "project_id": str(UUID(int=2)),
                "environment": "prod",
                "site_id": str(UUID(int=3)),
            },
            files={"file": ("router.cfg", b"abc", "text/plain")},
        )

    assert response.status_code == 201
    assert service.initial_call["content"] == b"abc"
    assert service.initial_call["scope"].site_id == UUID(int=3)
    assert "storage_key" not in response.json()["version"]


@pytest.mark.asyncio
async def test_create_artifact_version_route_only_adapts_http_request_to_service():
    app = FastAPI()
    service = FakeUploadService()
    app.state.artifact_upload_service = service
    app.include_router(artifacts.router)
    artifact_id = UUID(int=10)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/artifacts/{artifact_id}/versions",
            files={"file": ("renamed-router.cfg", b"abc", "text/plain")},
        )

    assert response.status_code == 201
    assert service.next_call["artifact_id"] == artifact_id
    assert service.next_call["content"] == b"abc"


def test_artifact_upload_endpoints_declare_text_plain_file_parts():
    app = FastAPI()
    app.include_router(artifacts.router)
    schema = app.openapi()

    for path in ("/artifacts", "/artifacts/{artifact_id}/versions"):
        encoding = schema["paths"][path]["post"]["requestBody"]["content"]["multipart/form-data"][
            "encoding"
        ]
        assert encoding["file"]["contentType"] == "text/plain"
