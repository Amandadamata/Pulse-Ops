# Registro de bugs

Apenas bugs **observados** durante o desenvolvimento, na ordem em que apareceram.
Riscos que ainda não aconteceram ficam no [modelo de ameaças](modelo-de-ameacas.md)
(seção "Limitações remanescentes") e em `docs/operacao.md`.

## B1 — Migração sem a coluna `monitors.check_requested`

- **Sintoma:** `tests/integration/test_migrations.py::test_upgrade_on_empty_database_creates_all_tables`
  falhou; o Alembic detectou "added column 'monitors.check_requested'" ao comparar
  o banco migrado com os modelos.
- **Como reproduzir:** acrescentar uma coluna em `src/pulseops/db/models.py` sem
  gerar migração e rodar `uv run pytest tests/integration/test_migrations.py`.
- **Causa:** a coluna foi criada no modelo depois da geração da migração inicial.
- **Correção:** migração inicial regenerada (o projeto ainda não tinha sido
  publicado, então não havia banco real a migrar).
- **Teste de regressão:** o próprio teste, que compara modelos e migração com
  `alembic.autogenerate.compare_metadata`.
- **Limitação remanescente:** depois de publicado, mudanças de esquema precisam
  de uma migração nova, nunca de edição da inicial.

## B2 — `dict()` sobre resultado do SQLAlchemy levantava `TypeError`

- **Sintoma:** `tests/integration/test_first_slice.py` falhou na preparação
  (login): ao abrir a página inicial, `services/queries.py::summary` levantou
  `TypeError: 'ChunkedIteratorResult' object is not subscriptable`.
- **Como reproduzir:** na versão anterior, `dict((await session.execute(select(Delivery.status, func.count())...)).tuples())`.
- **Causa:** o objeto de resultado tem um método `keys()`. O `dict()` do Python
  trata qualquer objeto com `keys()` como um mapeamento e tenta `objeto[chave]`,
  em vez de iterar pares.
- **Correção:** montar o dicionário com compreensão:
  `{status: count for status, count in rows.tuples()}`.
- **Teste de regressão:** `tests/integration/test_first_slice.py` (o login abre o
  painel, que chama `summary`) e `tests/integration/test_dashboard.py`.
- **Limitação remanescente:** nenhuma conhecida.

## B3 — `Jinja2Templates(autoescape=True)` não existe na versão instalada do Starlette

- **Sintoma:** a aplicação não importava:
  `TypeError: Jinja2Templates.__init__() got an unexpected keyword argument 'autoescape'`.
- **Como reproduzir:** `uv run python -c "from pulseops.web.app import create_app"`
  com a versão anterior de `web/templating.py`.
- **Causa:** o Starlette 1.x removeu a passagem de opções do Jinja pelo
  construtor; é preciso criar o `jinja2.Environment` e entregá-lo pronto.
- **Correção:** `Environment(loader=..., autoescape=True)` passado como `env=`.
- **Teste de regressão:** `tests/integration/test_dashboard.py::test_monitor_name_is_escaped`
  confirma que o autoescape está ligado.
- **Limitação remanescente:** nenhuma conhecida.
