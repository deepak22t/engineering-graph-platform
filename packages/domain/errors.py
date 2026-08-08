"""Domain-level error vocabulary independent of transports and persistence."""


class DomainError(ValueError):
    """Base error for violated canonical-domain invariants."""


class InvalidIdentityError(DomainError):
    pass


class InvalidEntityPropertiesError(DomainError):
    pass


class InvalidRelationshipError(DomainError):
    pass


class InvalidEvidenceError(DomainError):
    pass


class ConfidenceInvariantError(DomainError):
    pass


class ConflictDetectedError(DomainError):
    pass
