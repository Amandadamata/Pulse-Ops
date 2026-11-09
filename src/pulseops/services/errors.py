"""Use case errors, translated to HTTP by the routes."""

from pulseops.domain.monitor_rules import FieldError


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    """Operation incompatible with the current state (for example, editing an archived monitor)."""


class ValidationFailedError(Exception):
    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__("; ".join(f"{e.field}: {e.message}" for e in errors))
        self.errors = errors
