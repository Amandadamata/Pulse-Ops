"""Plugin do pytest que grava o SQL de verdade emitido pelo SQLAlchemy.

Uso (a partir da raiz, com o banco de testes no ar):
    PYTHONPATH=study uv run pytest -p captura_sql -q tests/integration

Cada consulta de interesse (CONSULTAS) é procurada entre os comandos que os testes
executaram; o primeiro que contém todos os fragmentos é salvo em study/sql/<nome>.sql.
O guia inclui esses arquivos com a diretiva @@sql, então o SQL mostrado é o que o
PostgreSQL recebeu, não uma reconstrução manual.
"""

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

DESTINO = Path(__file__).resolve().parent / "sql"
CONSULTAS: dict[str, tuple[str, ...]] = {
    "reservar-monitores": ("FROM monitors", "FOR UPDATE SKIP LOCKED"),
    "inserir-check": ("INSERT INTO checks", "ON CONFLICT"),
    "travar-monitor": ("FROM monitors", "WHERE monitors.id =", "FOR UPDATE"),
    "incidente-aberto": ("FROM incidents", "incidents.status =", "FOR UPDATE"),
    "historico-cursor": ("FROM checks", "(checks.started_at, checks.id) <"),
    "metricas-contagem": ("count(*)", "GROUP BY checks.outcome"),
    "metricas-latencia": ("percentile_disc",),
    "reservar-entregas": (
        "FROM deliveries JOIN alert_events",
        "FOR UPDATE OF deliveries SKIP LOCKED",
    ),
    "gravar-entrega": ("UPDATE deliveries SET", "deliveries.attempt_count ="),
    "retencao": ("DELETE FROM checks",),
    "lock-worker": ("pg_try_advisory_lock",),
}
_vistos: list[str] = []


@event.listens_for(Engine, "before_cursor_execute")
def _guardar(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
    if statement not in _vistos:
        _vistos.append(statement)


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    DESTINO.mkdir(exist_ok=True)
    faltando = []
    for nome, fragmentos in CONSULTAS.items():
        achado = next((s for s in _vistos if all(f in s for f in fragmentos)), None)
        if achado is None:
            faltando.append(nome)
            continue
        (DESTINO / f"{nome}.sql").write_text(achado.strip() + "\n", encoding="utf-8")
    print(f"\ncaptura_sql: {len(CONSULTAS) - len(faltando)} consultas salvas em {DESTINO}")
    if faltando:
        print("captura_sql: não encontradas:", ", ".join(faltando))
