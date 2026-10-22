# ADR 0001 — uv como único gerenciador de dependências

Status: aceita (2026-10-22)

## Contexto
A especificação pede dependências fixadas com arquivo de lock e um único fluxo
em README, Dockerfile e CI.

## Decisão
Usar **uv**. `pyproject.toml` declara as dependências; `uv.lock` fixa versões
exatas com hashes. Todos os comandos usam `uv sync` e `uv run`. O Dockerfile
instala com `uv sync --frozen --no-dev`; o CI usa `uv sync --frozen`.

## Alternativas
- Poetry: também tem lock, mas é mais lento e a instalação dentro do Docker
  exige mais passos.
- `pip` + `requirements.txt` com `pip-tools`: funciona, mas são duas
  ferramentas para o mesmo papel.

## Consequências
- Quem clona o projeto precisa instalar o uv (um binário) ou usar só Docker.
- `--frozen` falha se o lock estiver desatualizado, o que evita instalar
  versões diferentes das testadas.
