"""Erros de caso de uso, traduzidos para HTTP pelas rotas."""

from pulseops.domain.monitor_rules import FieldError


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    """Operação incompatível com o estado atual (por exemplo, editar monitor arquivado)."""


class ValidationFailedError(Exception):
    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__("; ".join(f"{e.field}: {e.message}" for e in errors))
        self.errors = errors
