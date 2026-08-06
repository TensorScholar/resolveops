"""Domain errors."""


class ResolveOpsError(Exception):
    """Base error."""


class NotFoundError(ResolveOpsError):
    """Requested entity does not exist."""


class InvalidTransitionError(ResolveOpsError):
    """Workflow transition is not valid."""


class PolicyDeniedError(ResolveOpsError):
    """An action was denied by policy."""


class IntegrityError(ResolveOpsError):
    """Stored evidence or audit data failed integrity validation."""
