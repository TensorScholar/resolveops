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


class IntegrationContractError(ResolveOpsError):
    """An external system could not satisfy a required ResolveOps data contract."""


class ExternalDependencyError(ResolveOpsError):
    """An external integration was unavailable or could not be queried safely."""
