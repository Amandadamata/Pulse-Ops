# PulseOps — instruções para retomar o trabalho

- Especificação completa (não editar): `docs/especificacao.md`
- Estado e pendências por etapa: `docs/progresso.md`
- Requisitos com códigos (RF03.4 etc.): `docs/requisitos.md`

Regras de honestidade da especificação valem para tudo: só afirmar o que foi
executado, nada de bugs/métricas inventados, roadmap não é funcionalidade.

## Comandos

```bash
uv sync                                   # instalar dependências (inclui dev)
docker run -d --name pulseops-testdb -e POSTGRES_USER=pulseops \
  -e POSTGRES_PASSWORD=pulseops -p 127.0.0.1:5433:5432 postgres:16-alpine
uv run pytest                             # testes (o banco pulseops_test é recriado a cada execução)
uv run pytest --cov                       # cobertura; metas em docs/estrategia-de-testes.md
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/conferir_referencias.py   # testes e arquivos citados nos docs existem
docker compose up -d --build --wait       # API + worker + banco
scripts/demo.sh                           # laboratório de falhas (perfil demo, 11 passos)
scripts/ensaio_carga.sh                   # ensaio de carga (com a demo no ar)
```

Neste ambiente de desenvolvimento, o build da imagem precisou de
`PULSEOPS_EXTRA_CA_FILE=./docker/local-ca.pem` (proxy TLS; arquivo fora do Git).
