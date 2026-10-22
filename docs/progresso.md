# Progresso

Arquivo atualizado ao final de cada etapa. Datas em UTC.

## Situação atual

Etapa atual: **2 — Base executável** (iniciada em 2026-10-22).

## Ambiente de desenvolvimento usado

- Container Linux x86_64, 4 CPUs, 15 GiB de RAM, Python 3.12/3.13, uv 0.11.32.
- Docker 29.9.1 e Compose v5.6.0. O daemon precisou ser iniciado manualmente
  (`dockerd`). O Docker Hub respondeu `429 Too Many Requests`; as imagens base
  foram baixadas de `mirror.gcr.io/library/...` e marcadas localmente com os
  nomes oficiais (`python:3.12-slim`, `postgres:16-alpine`). Os arquivos do
  projeto usam os nomes oficiais.

## Etapas

### Etapa 1 — Refinamento
Entregue: `docs/especificacao.md`, `docs/pesquisa-de-mercado.md`,
`docs/requisitos.md`, `docs/decisoes/` (11 ADRs), `docs/modelo-de-ameacas.md`,
este arquivo e `CLAUDE.md`.
Como verifiquei: leitura das páginas de vagas, READMEs e issues em 2026-10-22
(detalhes e limitações no próprio documento de pesquisa); `ls docs docs/decisoes`.
Falta: matriz de competências com caminhos reais (feita na Etapa 8).
Bloqueios: API do GitHub e HTML das issues inacessíveis (403 do proxy); estado
das issues ficou "não confirmado".
