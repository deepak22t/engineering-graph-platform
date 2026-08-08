import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    """Verify that the root endpoint is operational."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Engineering Graph Platform API is running"}


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Verify health endpoint checks PostgreSQL, Neo4j, and MinIO connectivity."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

        # Must return 200 OK when services are running
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["postgres"] == "connected"
        assert data["neo4j"] == "connected"
        assert data["minio"] == "connected"
