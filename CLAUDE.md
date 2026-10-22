# PulseOps — instruções para retomar o trabalho

- Especificação completa (não editar): `docs/especificacao.md`
- Estado e pendências por etapa: `docs/progresso.md`
- Requisitos com códigos (RF03.4 etc.): `docs/requisitos.md`

Regras de honestidade da especificação valem para tudo: só afirmar o que foi
executado, nada de bugs/métricas inventados, roadmap não é funcionalidade.

## Comandos

```bash
uv sync                                   # instalar dependências (inclui dev)
docker compose up -d db                   # banco para desenvolvimento
uv run alembic upgrade head               # migrações
uv run pytest                             # testes (precisa de PostgreSQL; ver docs/estrategia-de-testes.md)
uv run ruff check . && uv run ruff format --check .
uv run mypy
docker compose up --build                 # API + worker + banco
./scripts/demo.sh                         # laboratório de falhas (perfil demo)
```
