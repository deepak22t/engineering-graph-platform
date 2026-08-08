# Engineering Graph Platform

The Engineering Graph Platform builds an evidence-backed canonical graph from
engineering artifacts and exposes it through an API and interactive diagrams.

## Prerequisites

- Python 3.11 or later
- Docker with Docker Compose

## Local development

1. Create local configuration from the safe template.

   ```powershell
   Copy-Item .env.example .env
   ```

   Use strong, local-only values in `.env`. Do not commit this file.

2. Create and activate a virtual environment.

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the application and development dependencies. `pyproject.toml` is
   the single source of truth for dependencies.

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -e ".[dev]"
   ```

4. Start PostgreSQL, Neo4j, and MinIO.

   ```powershell
   docker compose --env-file .env -f infrastructure/compose/docker-compose.yml up -d
   ```

   If your Docker installation provides the legacy command instead, use:

   ```powershell
   docker-compose --env-file .env -f infrastructure/compose/docker-compose.yml up -d
   ```

5. Run the API.

   ```powershell
   uvicorn apps.api.main:app --reload
   ```

6. Verify the local baseline.

   ```powershell
   pytest
   ruff check .
   ```

The API health endpoint is available at `http://127.0.0.1:8000/health` and
interactive API documentation at `http://127.0.0.1:8000/docs`.

## Security

- Never place GitHub tokens, database passwords, or other credentials in this
  repository, documentation, source code, or shell history.
- Use GitHub CLI authentication, SSH keys, or your operating system's Git
  credential manager for GitHub access.
- `.env` is intentionally ignored by Git. Keep `.env.example` free of real
  credentials.
