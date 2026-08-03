import uvicorn
from packages.common.config.settings import get_settings
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
import asyncpg
from neo4j import AsyncGraphDatabase
import miniopy_async
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Engineering Graph Platform API",
    version="0.1.0",
    contact={
        "name": "Engineering Graph Platform",
        "url": "https://engineering-graph-platform.com",
        "email": "engineering-graph-platform@example.com"
    },
    license={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    terms_of_service="https://engineering-graph-platform.com/terms",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)



@app.get("/")
def root():
    return {"message": "Engineering Graph Platform API is running"}


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    health_status = {
        "status": "healthy",
        "postgres": "unknown",
        "neo4j": "unknown",
        "minio": "unknown"
    }
    
    # 1. Test PostgreSQL Connection
    try:
        conn = await asyncpg.connect(settings.postgres_uri)
        await conn.execute("SELECT 1")
        await conn.close()
        health_status["postgres"] = "connected"
    except Exception as e:
        health_status["postgres"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # 2. Test Neo4j Connection
    try:
        async with AsyncGraphDatabase.driver(
            settings.neo4j_uri, 
            auth=(settings.neo4j_user, settings.neo4j_password),
            encrypted=False
        ) as driver:
            await driver.verify_connectivity()
            health_status["neo4j"] = "connected"
    except Exception as e:
        health_status["neo4j"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # 3. Test MinIO Connection
    try:
        client = miniopy_async.Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False
        )
        await client.list_buckets()
        health_status["minio"] = "connected"
    except Exception as e:
        health_status["minio"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    if health_status["status"] == "unhealthy":
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=health_status)
    
    return health_status

if __name__ == "__main__":
    uvicorn.run(app, host=settings.app_host, port=settings.app_port)