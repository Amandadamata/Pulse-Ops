# Pesquisa de vagas e de projetos de referência

Pesquisa curta feita em **2026-10-22** para refinar a especificação antes da
implementação. Ela não é um estudo de mercado: serve para escolher o que o
PulseOps precisa demonstrar e quais armadilhas conhecidas de ferramentas
parecidas vale evitar.

## Como a pesquisa foi feita e limitações

- As páginas foram lidas com uma ferramenta de busca e leitura de páginas a
  partir do ambiente de desenvolvimento, em 2026-10-22.
- A API do GitHub e as páginas HTML das issues **não estavam acessíveis** neste
  ambiente (resposta 403 do proxy de rede). O conteúdo das issues foi lido por
  uma ferramenta de leitura de páginas que não mostrou o estado (aberta ou
  fechada) nem a data. Por isso a coluna "estado" das issues diz "não
  confirmado".
- O README do Gatus foi baixado diretamente (`raw.githubusercontent.com`), o que
  permitiu citar os nomes exatos das opções de alerta.
- Agregadores (Indeed) mostram apenas um resumo de cada vaga. Requisitos
  completos não foram confirmados nesses casos e estão marcados assim.
- Não houve contato com empresas. Nenhuma informação abaixo foi completada por
  suposição; o que não apareceu na página está como "não informado".

## Vagas consultadas

Data de consulta de todas as linhas: 2026-10-22.

| # | Empresa | Título | Senioridade | Modalidade | URL | Status | Requisitos obrigatórios | Diferenciais | Fonte |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Delfos Energy | Desenvolvedor Python Jr | Júnior | Remoto (Fortaleza, CE) | https://vagas.solides.com.br/vaga/891428 | encerrado ("Esta vaga não aceita mais candidaturas") | Superior completo em Computação/Engenharias; Python, SQLAlchemy, FastAPI ou Flask, Pydantic, SQL, modelagem relacional, Git, Docker e Docker Compose; noções de IA/ML; inglês avançado | Dagster/Airflow/Prefect; PostgreSQL ou TimescaleDB; Alembic, Pandas, Pytest; type hints; CI/CD; Kubernetes; testes unitários; padrões como repositórios e serviços | plataforma de candidatura (Sólides) |
| 2 | Delfos Energy | Desenvolvedor Python Jr | Júnior | Presencial (Fortaleza, CE) — **referência técnica, não remota** | https://vagas.solides.com.br/vaga/870939 | não confirmado (botão de candidatura visível, sem aviso explícito) | Graduação em Computação/ADS ou afins; Dagster/Airflow/Prefect; Python, SQLAlchemy, FastAPI ou Flask, Pydantic, SQL e modelagem; Git, Docker e Compose; IA/ML; inglês avançado | PostgreSQL/TimescaleDB; Alembic; Pandas; Pytest; type hints; CI/CD; Kubernetes; testes unitários; arquitetura (modelos, repositórios, serviços) | plataforma de candidatura (Sólides) |
| 3 | Delfos | Desenvolvedor Python Jr | Júnior | Remoto | https://remotar.com.br/job/156535/delfos/desenvolvedor-python-jr | encerrado ("Esta vaga foi encerrada") | Mesmo conteúdo da linha 1 (parece ser o mesmo anúncio replicado pelo agregador) | Mesmo conteúdo da linha 1 | agregador (Remotar) |
| 4 | byx | Desenvolvedor Backend Python JR | Júnior | Remoto ("100% Remoto") | https://remotar.com.br/job/166955/byx/desenvolvedor-backend-python-jr | não confirmado (sem aviso de encerramento; "última atualização: 19 de outubro de 2026") | Python e fundamentos; Django, FastAPI ou Flask; criar e consumir APIs REST; bancos relacionais (PostgreSQL ou MySQL) e SQL; orientação a objetos, estruturas de dados, testes unitários e de integração; Git, Linux e terminal | Redis, mensageria ou processamento assíncrono; Docker, CI/CD, AWS; microsserviços e eventos; observabilidade (logs e monitoramento) e segurança de APIs | agregador (Remotar, origem Inhire) |
| 5 | Squadra Digital | DEV BACKEND PYTHON JR | Júnior | Remoto | https://br.indeed.com/q-python-junior-vagas.html (card jk=54b582fbc94096b4) | não confirmado | Resumo cita Python, GenAI, Pandas, NumPy, Scikit-learn, LangChain — **adjacente** (perfil de IA/dados) | não informado | agregador (Indeed) |
| 6 | TIVIA TI | Desenvolvedor Python Junior | Júnior | não informado (Paraíso, SP) | https://br.indeed.com/q-python-junior-vagas.html (card jk=031f55b3b678d499) | não confirmado | Resumo cita automações em Python e APIs/serviços back-end com FastAPI ou outros frameworks (texto truncado) | não informado | agregador (Indeed) |
| 7 | BairesDev | Junior Python Backend Developer / R + D - Remote Work | Júnior | Remoto | https://br.indeed.com/q-python-junior-vagas.html (card jk=e584562a7bd71a63) | não confirmado | Resumo cita "1+ year of practical experience in Python and Django" (truncado) | não informado | agregador (Indeed) |

Observações:

- As linhas 1 e 3 provavelmente são o mesmo anúncio em duas plataformas. Foram
  mantidas separadas porque as URLs são diferentes, mas contam como uma vaga.
- Não foram encontradas vagas de **estágio** de back-end Python com conteúdo
  acessível na busca feita. Isso fica registrado como lacuna, sem inferir nada.
- Vagas de dados, ML e QA vistas na busca (por exemplo "Cientista de Dados
  Junior") foram descartadas por não serem back-end júnior.

### O que se repete nas vagas (base: linhas 1, 2, 4, 6 e 7)

| Requisito recorrente | Aparece em |
|---|---|
| Python | todas |
| FastAPI (ou Flask/Django) | 1, 2, 4, 6 |
| SQL e banco relacional / PostgreSQL | 1, 2, 4 |
| SQLAlchemy, Pydantic | 1, 2 |
| Docker e Docker Compose | 1, 2, 4 (diferencial) |
| Git | 1, 2, 4 |
| Testes unitários e de integração / Pytest | 4 (obrigatório), 1, 2 (diferencial) |
| Alembic, type hints, CI/CD | 1, 2 (diferenciais) |
| Orientação a objetos | 4 |
| Observabilidade (logs, monitoramento) e segurança de APIs | 4 (diferencial) |
| Processamento assíncrono | 4 (diferencial) |

Requisitos que o PulseOps **não** cobre e não deve fingir cobrir: IA/ML,
orquestração de dados (Airflow, Dagster), Kubernetes, AWS, Redis/mensageria,
inglês avançado.

## Matriz de competências

Versão da Etapa 1: **caminhos planejados**, ainda não existentes. Esta tabela
foi revisada com os caminhos reais ao final da implementação (Etapa 7, 2026-10-22). A matriz
completa requisito → código → teste ficará em
[`matriz-de-rastreabilidade.md`](matriz-de-rastreabilidade.md).

| Requisito da vaga | Funcionalidade do PulseOps | Arquivo/módulo | Teste ou demonstração |
|---|---|---|---|
| Python, fundamentos e OO | Máquina de estados de saúde e incidentes (classe com regra encapsulada) | `src/pulseops/domain/health.py` | `tests/unit/test_health.py` |
| FastAPI e APIs REST | API JSON de monitores, checks, incidentes e notificações | `src/pulseops/web/api.py`, `src/pulseops/web/schemas.py` | `tests/integration/test_api_monitors.py` |
| Pydantic | Contratos de entrada/saída e configuração | `src/pulseops/web/schemas.py`, `src/pulseops/config.py` | `tests/integration/test_api_monitors.py`, `tests/unit/test_config.py` |
| SQL, PostgreSQL, modelagem relacional | Tabelas com FKs, CHECKs e índice único parcial de incidente aberto | `src/pulseops/db/models.py`, `migrations/versions/` | `tests/integration/test_consistency.py::test_database_rejects_second_open_incident`, `test_database_rejects_second_running_check` |
| SQLAlchemy 2.x | ORM com `Mapped[...]` e `select()`, sessão por unidade de trabalho | `src/pulseops/db/`, `src/pulseops/services/` | `tests/integration/test_incident_lifecycle.py`, `tests/integration/test_consistency.py` |
| Alembic | Migração inicial aplicada em banco limpo | `migrations/` | `tests/integration/test_migrations.py`, CI |
| Testes unitários e de integração (Pytest) | Suíte com PostgreSQL real, relógio controlável e `httpx.MockTransport` | `tests/` | `uv run pytest` |
| Docker e Docker Compose | API, worker, banco e laboratório | `Dockerfile`, `compose.yaml` | `scripts/demo.sh` |
| Git e CI | Workflow com lint, tipos, testes, migrações e build | `.github/workflows/ci.yml` | workflow do repositório (ver README) |
| Type hints | mypy em modo estrito no pacote | `pyproject.toml` | `uv run mypy` |
| Processamento assíncrono | Worker com `asyncio`, limite de concorrência e cliente HTTP reutilizado | `src/pulseops/worker/` | `tests/integration/test_consistency.py::test_dispatcher_refills_freed_slots_without_waiting_a_tick`, `tests/integration/test_delivery.py::test_slow_webhook_does_not_block_checks` |
| Observabilidade | Logs JSON com contexto, heartbeat do worker, liveness/readiness | `src/pulseops/logs.py`, `src/pulseops/web/health.py` | `tests/integration/test_health_endpoints.py`, `tests/unit/test_logging.py` |
| Segurança de APIs | Sessão HttpOnly, CSRF, proteção SSRF | `src/pulseops/security/` | `tests/unit/test_url_policy.py`, `tests/integration/test_auth.py` |

## Projetos de referência

Comparação feita a partir dos READMEs públicos em 2026-10-22. Nenhum código ou
design desses projetos foi copiado para o PulseOps; eles serviram para entender
problemas comuns.

| Critério | Uptime Kuma | Gatus | Healthchecks |
|---|---|---|---|
| Licença | MIT | Apache-2.0 | BSD-3-Clause |
| Linguagem | JavaScript/TypeScript (Node.js, Vue 3) — inferido pelos arquivos | Go | Python (Django) |
| Escopo | Monitor ativo de vários tipos: HTTP(s), TCP, palavra-chave, JSON, WebSocket, ping, DNS, push, Docker | Monitor ativo configurado por arquivo, com status page, alertas e "incident support" | Monitor **passivo**: tarefas agendadas enviam pings; alerta quando um ping atrasa (period + grace time) |
| Execução local | `docker run` ou Compose, porta 3001 | Imagem Docker (README longo, configuração em YAML) | `manage.py runserver` ou imagens Docker |
| Documentação | README + wiki externa | README extenso com tabela de cada opção | README + docs do site |
| Incidentes | Status pages; "incidente" não aparece no README | Limiares de falha e de sucesso para disparar e resolver alertas; "announcements" para comunicação | Estados up/down/grace por check |
| Alertas | Muitos canais (90+ citados) | Muitos provedores; `failure-threshold` (padrão 3), `success-threshold` (padrão 2), `send-on-resolved` | 25+ integrações; processo separado `manage.py sendalerts` lê o banco e envia |
| Testes | Pasta `test/` visível; README não descreve a suíte | Pastas `test/` e `testdata/` | `manage.py test`, badge de CI e cobertura, `mypy.ini` |

O que isso ensinou para o PulseOps:

- **Gatus** usa exatamente a ideia de limiar de falhas consecutivas para abrir e
  limiar de sucessos para resolver. O PulseOps adota o mesmo conceito (é uma
  prática comum, não uma invenção) e o diferencial está em **guardar a
  explicação** da decisão com os valores vigentes.
- **Healthchecks** separa o envio de alertas em um processo que lê o banco
  (`sendalerts`). O PulseOps segue uma ideia parecida: alertas são linhas no
  banco processadas por um entregador independente das verificações.
- O escopo do Uptime Kuma é muito maior. O PulseOps fica só com HTTP/HTTPS
  porque a especificação prioriza "pequeno e completo".

## Issues de referência e inspirações

Estado de todas as issues: **não confirmado** (ver limitações). Os resumos
descrevem o que a página mostrava em 2026-10-22.

| Issue | Problema relatado | Decisão para o PulseOps | Cenário de teste |
|---|---|---|---|
| [uptime-kuma#4058](https://github.com/louislam/uptime-kuma/issues/4058) — "getaddrinfo ENOTFOUND causes monitors to freeze" | Monitores ficaram presos em "down" depois de falha de DNS. Comentários apontam que o envio de notificação (`sendNotification`) pode travar e bloquear o ciclo do monitor; o mantenedor sugeriu não aguardar o envio. | Verificação e envio de alerta são **laços separados** no worker. A verificação só grava um evento no banco; o envio acontece em outra tarefa, com timeout próprio. | Cenário 16: webhook lento/indisponível não impede novas verificações (`tests/integration/test_delivery.py::test_slow_webhook_does_not_block_checks`; passo 10 da demo). |
| [uptime-kuma#6046](https://github.com/louislam/uptime-kuma/issues/6046) — "Notification lost if service is temporarily unavailable" | Se o serviço de notificação estiver fora no momento do evento, a notificação se perde, sem nova tentativa. Mantenedor observou que repetir automaticamente em todo erro 500 pode gerar alarmes indesejados. | Padrão outbox: evento persistido na mesma transação da mudança de incidente, **retentativas limitadas com backoff e teto**, registro de cada tentativa, falha permanente explícita. | Cenário 17: receptor indisponível, depois restaurado, recebe o evento (`tests/integration/test_delivery.py`, passo 11 da demo). |
| [uptime-kuma#3255](https://github.com/louislam/uptime-kuma/issues/3255) — notificações chegando em dobro | Cada notificação chegava duas vezes; a causa indicada na conversa foi uma **segunda instância** rodando ao mesmo tempo. | (a) Apenas um worker suportado, garantido por *advisory lock* do PostgreSQL (um segundo worker não inicia). (b) Cada evento tem identidade estável (`X-PulseOps-Event-Id`) para o receptor deduplicar. (c) Entrega documentada como "pelo menos uma vez". | Teste de segundo worker recusado (`tests/integration/test_consistency.py::test_second_worker_is_refused`) e deduplicação no receptor do laboratório (`tests/unit/test_lab_receiver.py`). |

## Documentação oficial consultada

| Fonte | Uso no PulseOps |
|---|---|
| OWASP SSRF Prevention Cheat Sheet | Preferir allowlist; validar IP com biblioteca testada; "Domain allowlisting alone does not prevent DNS rebinding"; conectar só ao IP validado, sem nova resolução entre validar e conectar, mantendo Host/SNI; desabilitar redirecionamentos automáticos; bloquear 169.254.169.254, RFC1918, link-local, ULA e multicast. Ver `docs/modelo-de-ameacas.md`. |
| FastAPI, SQLAlchemy, HTTPX, Pytest | Consultadas pela documentação instalada e pelas assinaturas das versões travadas em `uv.lock` (por exemplo, `httpcore.AsyncConnectionPool(network_backend=...)`, usado para conectar no IP validado). |
