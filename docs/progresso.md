# Progresso

Arquivo atualizado ao final de cada etapa. Datas em UTC.

## Situação atual

Etapa atual: **9 — Material de estudo** (Etapas 1 a 7 concluídas; Etapa 8 pronta localmente, publicação aguardando o repositório de destino).

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

### Etapa 2 — Base executável
Entregue: `pyproject.toml` + `uv.lock` (uv), configuração (`src/pulseops/config.py`),
modelos e migração inicial (`migrations/versions/0001_esquema_inicial.py`),
API mínima, `Dockerfile`, `compose.yaml`, `.env.example`, primeiros testes de
integração.
Como verifiquei: `docker compose up -d --wait` → db, api e worker saudáveis,
migrate saiu com sucesso; `curl /health/ready` → `{"status":"ok","database":"ok",...}`;
`uv run pytest tests/integration` → 3 passed (migração em banco vazio, ida e volta
da migração, fatia ponta a ponta) contra PostgreSQL 16 em container.
Falta: nada para o critério de saída.
Bloqueios: Docker Hub com limite de requisições (contornado com mirror.gcr.io);
build da imagem neste ambiente precisa do certificado do proxy TLS via
`PULSEOPS_EXTRA_CA_FILE` (secret de build opcional, vazio por padrão).

### Etapa 3 — Primeira fatia completa
Entregue: cadastro pela API → worker reserva e executa → check gravado →
consulta pela API (`tests/integration/test_first_slice.py`).
Como verifiquei: `uv run pytest tests/integration/test_first_slice.py` → passed.
Falta: —
Bloqueios: nenhum.

### Etapa 4 — Domínio
Entregue: `domain/health.py` (`HealthTracker`), `services/processing.py`,
`services/incidents.py`, retomada com lacunas, checks interrompidos,
advisory lock do worker; testes de domínio e de consistência.
Como verifiquei: `uv run pytest tests/unit/test_health.py tests/integration/test_incident_lifecycle.py tests/integration/test_consistency.py`
→ todos passando; exemplo obrigatório do RF03 coberto por quatro testes
`test_mandatory_example_*` e por `test_threshold_example_with_database`.
Falta: —
Bloqueios: nenhum.

### Etapa 5 — Alertas
Entregue: outbox (`alert_events`, `deliveries`, `delivery_attempts`), entregador em
laço separado, backoff com teto, falha permanente, receptor do laboratório com
deduplicação.
Como verifiquei: `uv run pytest tests/integration/test_delivery.py tests/unit/test_lab_receiver.py`
→ passando; `test_slow_webhook_does_not_block_checks` prova o isolamento.
Falta: —
Bloqueios: nenhum.

### Etapa 6 — Interface e métricas
Entregue: login com sessão e CSRF, painel, página do monitor com métricas e
gráfico SVG, incidentes, notificações, API de histórico e métricas.
Como verifiquei: 239 testes passando no fechamento da etapa (commit `b5c84be`);
capturas reais com Chromium (Playwright) em desktop e celular, revisadas
visualmente, em `docs/imagens/`. Bugs B4 e B5 encontrados e corrigidos.
Falta: —
Bloqueios: nenhum.

### Laboratório de falhas
Entregue: `compose.demo.yaml`, `scripts/demo.sh`, `scripts/demo_flow.py`.
Como verifiquei: duas execuções seguidas de `scripts/demo.sh` com os 11 passos
"ok" e código de saída 0 (a segunda reaproveitou os monitores); execução com
senha errada terminou com "FALHOU: login recusado (HTTP 401)" e código 1. Bug B6
encontrado ao escrever o roteiro.
Falta: —
Bloqueios: nenhum.

### Etapa 7 — Revisão
Entregue: revisão de segurança (modelo de ameaças com referências exatas aos
testes; teste de SQL injection; inspeção do container), cobertura com metas,
ensaio de carga, `docs/arquitetura.md`, `docs/estrategia-de-testes.md`,
`docs/operacao.md`, `docs/matriz-de-rastreabilidade.md`,
`scripts/conferir_referencias.py`. Bugs B7, B8 e B9 encontrados e corrigidos.
Como verifiquei: `pip-audit` sem vulnerabilidades conhecidas; cobertura 95%
(domínio 98%, segurança 97%); `docker inspect` mostrou usuário `pulseops`
(uid 10001), raiz somente leitura, `cap_drop ALL`, banco sem porta publicada;
ensaio de carga antes e depois do B8 em `docs/evidencias/`; instalação limpa a
partir de um clone novo, com volume e imagem apagados antes (ver
`docs/evidencias/instalacao-limpa.md`). Saídas registradas em
`docs/evidencias/verificacao.md`.
Falta: —
Bloqueios: o build da imagem neste ambiente precisa do certificado do proxy TLS
(`PULSEOPS_EXTRA_CA_FILE`); sem DNS público no ambiente, monitores para sites
reais terminam em "falha de DNS" (comportamento correto, mas não deu para
demonstrar um site real saudável aqui).

### Etapa 8 — GitHub
Entregue: `README.md`, `LICENSE` (MIT), `.github/workflows/ci.yml` com
`permissions: contents: read`, screenshots reais.
Como verifiquei: `actionlint` sem erros no workflow; o passo de migrações do CI
foi executado localmente (upgrade, downgrade e upgrade em banco novo).
Publicado em 2026-10-22 em <https://github.com/Amandadamata/Pulse-Ops> (push sem
force; o commit inicial criado pelo GitHub Desktop foi integrado por merge).
Primeira execução do CI verde nos dois jobs (qualidade e imagem Docker com o
laboratório): <https://github.com/Amandadamata/Pulse-Ops/actions/runs/39780395966>.
Falta: —
Bloqueios: nenhum. Aviso do GitHub: `actions/checkout@v4` e `astral-sh/setup-uv@v6`
ainda usam Node.js 20 e são executadas em Node.js 24; atualizar as versões quando
houver novas.

### Etapa 9 — Material de estudo
Entregue: `docs/estudo/pulseops-por-dentro-volume-1.pdf` (partes A, B, C, E a J e
gabarito; 79 páginas) e `docs/estudo/pulseops-por-dentro-volume-2.pdf` (parte D,
código explicado arquivo por arquivo; 151 páginas). Fontes editáveis em
`study/fonte/`; trechos de código copiados por `study/build.py` do commit
registrado em `study/commit-explicado.txt`; SQL real capturado dos testes por
`study/captura_sql.py`. Ao explicar `web/charts.py` apareceu o bug B10 (resumo do
gráfico e latência média com bases diferentes), corrigido com teste de regressão.
Como verifiquei: o build recusa gerar se o código mudou desde o commit explicado;
os exercícios dos níveis 2 a 4 foram executados numa cópia descartável; as
páginas dos dois PDFs foram renderizadas em imagem e revisadas.
Falta: —
Bloqueios: nenhum.
