"""Executable package-boundary tests for the pure domain layer."""

import ast
from pathlib import Path

from packages.domain.errors import (
    ConfidenceInvariantError,
    ConflictDetectedError,
    InvalidEntityPropertiesError,
    InvalidEvidenceError,
    InvalidIdentityError,
    InvalidRelationshipError,
)

FORBIDDEN_ROOTS = {"fastapi", "neo4j", "asyncpg", "sqlalchemy", "psycopg", "httpx"}
DOMAIN_ROOT = Path("packages/domain")


def test_domain_has_transport_and_persistence_independent_error_vocabulary():
    for error in (
        InvalidIdentityError,
        InvalidEntityPropertiesError,
        InvalidRelationshipError,
        InvalidEvidenceError,
        ConfidenceInvariantError,
        ConflictDetectedError,
    ):
        assert issubclass(error, ValueError)


def test_domain_imports_no_api_or_database_integrations():
    violations = []
    for path in DOMAIN_ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            module = None
            if isinstance(node, ast.Import):
                module = node.names[0].name
            if isinstance(node, ast.ImportFrom):
                module = node.module
            if module and module.split(".")[0] in FORBIDDEN_ROOTS:
                violations.append((path, module))
    assert not violations


def test_schema_entity_request_uses_domain_factory():
    source = Path("packages/schemas/domain/entity_schema.py").read_text(encoding="utf-8")
    assert "def to_entity" in source and "entity_class(" in source
