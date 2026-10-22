# Verificação local

Executado em 2026-10-22 sobre o commit `52ecb09` (código idêntico ao do commit final
`b737a56`; a diferença entre os dois é só texto do README). Ambiente: Linux 6.18
x86_64, Python 3.12 pelo `uv`, PostgreSQL 16 em contêiner na porta 5433.

Os comandos são os mesmos do CI (`.github/workflows/ci.yml`). Isto **não** é uma
execução do CI no GitHub: o repositório ainda não foi publicado.

## Lint, formatação e tipos

```text
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
132 files already formatted

$ uv run mypy
Success: no issues found in 48 source files
```

## Migrações num banco vazio

```text
$ uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, esquema inicial
INFO  [alembic.runtime.migration] Running downgrade 0001 -> , esquema inicial
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, esquema inicial
```

(Código de saída 0. Banco `pulseops_ci_check`, criado vazio para isso e apagado
depois.)

## Testes com cobertura

```text
$ uv run pytest --cov --cov-report=term --cov-fail-under=90
251 passed, 74 warnings in 49.95s
TOTAL   2348 statements, 102 missing, 372 branches, 33 partial   95%

$ uv run coverage report --include='src/pulseops/domain/*' --fail-under=95
TOTAL   98%
$ uv run coverage report --include='src/pulseops/security/*' --fail-under=95
TOTAL   97%
```

Os 74 avisos são todos o mesmo: `SADeprecationWarning: The Result.tuples() method is
deprecated`, vindo de `src/pulseops/services/queries.py` (linhas 119 e 329). Não
afetam o resultado; a troca está proposta como exercício (J14 do guia de estudo).

Cobertura por arquivo, só os que ficaram abaixo de 90%:

| Arquivo | Cobertura | Por quê |
|---|---|---|
| `src/pulseops/worker/__main__.py` | 44% | ponto de entrada do processo; exercitado pela demonstração e pelo job `docker` do CI, não pelos testes |
| `src/pulseops/logs.py` | 80% | ramos de formatação de exceção não exercitados |
| `src/pulseops/cli.py` | 83% | caminhos de erro de leitura da senha |
| `src/pulseops/web/templating.py` | 83% | rótulos para valores desconhecidos |
| `src/pulseops/web/app.py` | 84% | página de erro 503 de banco (a versão JSON é testada) |

## Auditoria de dependências

```text
$ uv export --frozen --no-emit-project --no-hashes -o requirements-audit.txt
$ uvx pip-audit==2.9.0 -r requirements-audit.txt --disable-pip --no-deps
No known vulnerabilities found
```

Os dois avisos que o `pip-audit` imprime antes (sobre `--no-deps` e *hashes*) são
recomendações gerais da ferramenta, não vulnerabilidades.

## Workflow do CI

```text
$ uvx --from actionlint-py==1.7.7.23 actionlint .github/workflows/ci.yml
(nenhuma saída; código 0)
```

## Referências da documentação

```text
$ uv run python scripts/conferir_referencias.py
```

Resultado: 416 referências conferidas, 0 problemas (código 0). Antes de esta página e a da instalação limpa existirem, o script apontava exatamente as 4 citações a elas.

## Demonstração

`scripts/demo.sh` concluiu os 11 passos duas vezes: no repositório de trabalho e
no clone limpo (ver `docs/evidencias/instalacao-limpa.md`).
