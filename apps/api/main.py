from contextlib import asynccontextmanager

import asyncpg
import miniopy_async
import uvicorn
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from neo4j import AsyncGraphDatabase

from apps.api.artifacts import router as artifact_router
from apps.api.dependencies import artifact_service_lifespan
from packages.common.config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with artifact_service_lifespan(app, settings):
        yield


app = FastAPI(
    title=settings.app_name,
    description="Engineering Graph Platform API",
    version="0.1.0",
    contact={
        "name": "Engineering Graph Platform",
        "url": "https://engineering-graph-platform.com",
        "email": "engineering-graph-platform@example.com",
    },
    license={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    terms_of_service="https://engineering-graph-platform.com/terms",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.include_router(artifact_router)


@app.get("/")
def root():
    return {"message": "Engineering Graph Platform API is running"}


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    health_status = {
        "status": "healthy",
        "postgres": "unknown",
        "neo4j": "unknown",
        "minio": "unknown",
    }

    try:
        conn = await asyncpg.connect(settings.postgres_uri)
        await conn.execute("SELECT 1")
        await conn.close()
        health_status["postgres"] = "connected"
    except Exception as error:
        health_status["postgres"] = f"error: {error}"
        health_status["status"] = "unhealthy"

    try:
        async with AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            encrypted=False,
        ) as driver:
            await driver.verify_connectivity()
        health_status["neo4j"] = "connected"
    except Exception as error:
        health_status["neo4j"] = f"error: {error}"
        health_status["status"] = "unhealthy"

    try:
        client = miniopy_async.Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False,
        )
        await client.list_buckets()
        health_status["minio"] = "connected"
    except Exception as error:
        health_status["minio"] = f"error: {error}"
        health_status["status"] = "unhealthy"

    if health_status["status"] == "unhealthy":
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=health_status)

    return health_status


if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)
