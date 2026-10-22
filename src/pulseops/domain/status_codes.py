"""Interpretação da lista de status HTTP aceitos, por exemplo "200-299,301"."""

from dataclasses import dataclass

MAX_SPEC_LENGTH = 100


@dataclass(frozen=True)
class AcceptedStatusCodes:
    ranges: tuple[tuple[int, int], ...]

    def __contains__(self, code: object) -> bool:
        return isinstance(code, int) and any(low <= code <= high for low, high in self.ranges)

    def __str__(self) -> str:
        return ",".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in self.ranges)


def parse_status_codes(spec: str) -> AcceptedStatusCodes:
    """Converte o texto em faixas. Levanta ValueError com mensagem para o operador."""
    spec = spec.replace(" ", "")
    if not spec:
        raise ValueError("informe pelo menos um status, por exemplo 200-299")
    if len(spec) > MAX_SPEC_LENGTH:
        raise ValueError(f"no máximo {MAX_SPEC_LENGTH} caracteres")

    ranges: list[tuple[int, int]] = []
    for part in spec.split(","):
        low_text, sep, high_text = part.partition("-")
        if not low_text.isdigit() or (sep and not high_text.isdigit()):
            raise ValueError(f"trecho inválido: {part!r}")
        low = int(low_text)
        high = int(high_text) if sep else low
        if not (100 <= low <= 599 and 100 <= high <= 599):
            raise ValueError(f"status fora de 100–599: {part!r}")
        if low > high:
            raise ValueError(f"faixa invertida: {part!r}")
        ranges.append((low, high))
    return AcceptedStatusCodes(tuple(sorted(ranges)))
