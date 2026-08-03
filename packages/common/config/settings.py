from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Engineering Graph Platform"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    postgres_host: str
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_port: int = 5432

    neo4j_host: str
    neo4j_user: str
    neo4j_password: str
    neo4j_port: int = 7687

    minio_host: str
    minio_root_user: str
    minio_root_password: str
    minio_port: int = 9000

    @computed_field
    @property
    def postgres_uri(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def neo4j_uri(self) -> str:
        return f"bolt://{self.neo4j_host}:{self.neo4j_port}"

    @computed_field
    @property
    def minio_endpoint(self) -> str:
        return f"{self.minio_host}:{self.minio_port}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
