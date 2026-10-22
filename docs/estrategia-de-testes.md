# Estratégia de testes

## O que cada camada verifica

| Camada | Onde | O que prova | Dependências substituídas |
|---|---|---|---|
| Unidade de domínio | `tests/unit/test_health.py`, `test_monitor_rules.py`, `test_status_codes.py`, `test_metrics_formulas.py` | A regra de saúde e incidentes (RF03), validação de configuração e fórmulas de métricas, sem banco | nenhuma: as funções são puras |
| Unidade de segurança | `tests/unit/test_url_policy.py`, `test_transport.py`, `test_passwords.py`, `test_logging.py`, `test_config.py` | Política SSRF, conexão no IP validado, hash de senha, redação de logs | resolvedor DNS (`FakeResolver`) e socket (`RecordingBackend`) |
| Unidade do verificador | `tests/unit/test_checker.py` | Classificação de cada resultado (lento, status, timeout, rede, TLS, bloqueado, erro interno) | transporte HTTP (`httpx.MockTransport` via `ScriptedTarget`) e relógio (`FakeClock`) |
| Integração com PostgreSQL | `tests/integration/` | Restrições do banco, transações, worker + persistência, outbox, API, páginas, métricas em SQL, migrações | só o alvo HTTP, o notificador e o relógio. **O banco é PostgreSQL 16 real**; SQLite não é usado |
| Laboratório | `scripts/demo.sh` | O sistema inteiro em containers, com rede de verdade, alvo e receptor controláveis | nada: processos reais |
| Carga local | `scripts/ensaio_carga.sh` | Vazão e atraso do worker e latência da API sob 200 monitores | nada; números valem só para a máquina registrada |
| Interface | `tests/integration/test_dashboard.py` + capturas em `docs/imagens/` | Fluxos principais, escape de conteúdo, estados vazio, sem dados e desatualizado | as capturas foram feitas com Chromium (Playwright) sobre a demo real |

## Princípios

- **Relógio controlável.** Tudo que depende de tempo recebe um `Clock`. Os testes
  usam `FakeClock` e avançam o tempo; não há `sleep` longo na suíte (a suíte inteira
  roda em uns 35 s, a maior parte em I/O com o banco).
- **Sem sites externos.** O resolvedor DNS e o transporte HTTP são substituídos
  por dublês. O único teste que usa o resolvedor do sistema consulta `localhost`,
  que vem do `/etc/hosts`.
- **Banco limpo por teste.** O fixture `sessions` faz `TRUNCATE ... RESTART
  IDENTITY CASCADE` antes de cada teste; o esquema é criado uma vez pelo Alembic
  (a mesma migração da produção) no começo da sessão.
- **Atacar os riscos, não repetir a suíte.** Os cenários foram escolhidos a partir
  dos riscos do sistema (ver `docs/modelo-de-ameacas.md` e as issues reais em
  `docs/pesquisa-de-mercado.md`): reprocessamento, sobreposição, reinício, banco
  fora do ar, webhook travado, rebinding de DNS.
- **Teste de regressão para cada bug real.** Os bugs B1 a B8 em
  `docs/registro-de-bugs.md` têm, cada um, o teste que falhava antes da correção.
  Para B6 e B8 o teste foi escrito primeiro e confirmado falhando com a correção
  removida (`git stash` do arquivo corrigido).
- **Nenhum `skip` ou `xfail`.** A suíte não tem testes pulados.

## Metas de cobertura

Cobertura de linhas e ramos, medida com `pytest-cov` e `concurrency = ["greenlet",
"thread"]` (sem isso, o código executado dentro do SQLAlchemy assíncrono aparece
como não coberto).

| Escopo | Meta | Medido em 2026-10-22 |
|---|---|---|
| `src/pulseops/domain/` (regras) | ≥ 95% | 98% |
| `src/pulseops/security/` | ≥ 95% | 97% |
| Pacote inteiro | ≥ 90% | 95% |

As metas são verificadas no CI (`--cov-fail-under=90` e `coverage report
--include=... --fail-under=95`). O ponto mais baixo é `worker/__main__.py` (44%):
o ponto de entrada do processo (sinais, advisory lock, criação dos clientes) é
exercitado pelo laboratório e pelo Compose, não pela suíte. O advisory lock em si
tem teste (`test_second_worker_is_refused`).

Cobertura alta não prova correção. Os testes mais importantes são os que verificam
valores exatos (contadores, motivos, `started_at` versus `confirmed_at`, número de
eventos e de tentativas), não os que só executam linhas.

## Como rodar

```bash
# Banco de testes (uma vez)
docker run -d --name pulseops-testdb -e POSTGRES_USER=pulseops \
  -e POSTGRES_PASSWORD=pulseops -p 127.0.0.1:5433:5432 postgres:16-alpine

uv run pytest                     # suíte completa
uv run pytest tests/unit          # só unidade (sem banco)
uv run pytest --cov               # com cobertura
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/conferir_referencias.py   # testes citados nos docs existem
scripts/demo.sh                   # laboratório (11 passos)
```

Por padrão os testes usam `postgresql+psycopg://pulseops:pulseops@127.0.0.1:5433/pulseops_test`
(mude com `PULSEOPS_TEST_DATABASE_URL`). **O banco dessa URL é apagado e recriado a
cada execução**, por isso nunca aponte a variável para um banco com dados.

## O que não é testado automaticamente

- Navegadores diferentes do Chromium e leitores de tela: a acessibilidade foi
  revisada no HTML (rótulos, foco, texto além da cor), não com tecnologia assistiva.
- Certificados TLS reais e redes reais: TLS é testado com erros simulados do
  HTTPX; o laboratório usa HTTP dentro da rede do Compose.
- Mais de um worker: não é suportado; o teste garante que o segundo é recusado.
- Escala além do ensaio registrado.
