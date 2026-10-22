# Parte C — Arquitetura

## Os processos

@@diagrama processos

O PulseOps roda como **dois processos Python** que não conversam diretamente: os
dois leem e gravam no mesmo PostgreSQL.

- **api**: o servidor web (uvicorn + FastAPI). Responde ao navegador e à API JSON.
  Nunca faz checks nem envia webhooks.
- **worker**: um programa que fica em laço. Ele reserva checks vencidos, faz as
  requisições, grava os resultados, entrega alertas e faz manutenção.

Por que separar? Se o agendador rodasse dentro do servidor web, cada processo do
uvicorn teria o próprio agendador, e os checks rodariam em dobro. Um servidor web
também pode ser reiniciado a qualquer momento; um laço preso nele morreria junto
(ADR 0002). Como a fila de trabalho mora no banco (`monitors.next_run_at` e a
tabela `deliveries`), a API só precisa gravar e o worker só precisa ler.

## Responsabilidade de cada pasta e arquivo

### Raiz do repositório

| Arquivo | Responsabilidade |
|---|---|
| `pyproject.toml` | Metadados do pacote, dependências, configuração de Ruff, mypy, pytest e cobertura |
| `uv.lock` | Versões exatas de todas as dependências (gerado pelo uv) |
| `Dockerfile` | Receita da imagem usada por api, worker, migrate e laboratório |
| `.dockerignore` | O que não entra no contexto de build da imagem |
| `compose.yaml` | Serviços do ambiente normal: db, migrate, api, worker |
| `compose.demo.yaml` | Acréscimos do laboratório: modo demo, alvo, receptor e roteiro |
| `alembic.ini` | Configuração do Alembic (onde estão as migrações) |
| `.env.example` | Modelo de variáveis de ambiente, sem segredos reais |
| `docker/no-extra-ca.pem` | Arquivo vazio usado quando não há certificado extra no build |
| `.github/workflows/ci.yml` | Integração contínua no GitHub Actions |
| `README.md`, `LICENSE`, `CLAUDE.md` | Apresentação, licença MIT, instruções para retomar o trabalho |

### `src/pulseops/` — a aplicação

| Arquivo | Responsabilidade |
|---|---|
| `config.py` | `Settings`: lê as variáveis `PULSEOPS_*` e valida |
| `clock.py` | `Clock` (protocolo) e `SystemClock`: a fonte de "agora" substituível nos testes |
| `logs.py` | Logs em JSON com contexto e mascaramento de dados sensíveis |
| `cli.py` | Comando `pulseops create-admin` |
| `domain/outcomes.py` | `Outcome`: os oito resultados possíveis de um check |
| `domain/status_codes.py` | Interpreta `"200-299,301"` e responde se um status é aceito |
| `domain/monitor_rules.py` | `MonitorConfig` e `validate_config`: limites e regras combinadas |
| `domain/health.py` | `HealthTracker`: a regra de saúde e de incidentes (o coração do projeto) |
| `domain/metrics.py` | Fórmulas puras: nearest-rank, razão segura, duração recortada pela janela |
| `security/url_policy.py` | `DestinationPolicy`: quais URLs e IPs são permitidos |
| `security/transport.py` | Cliente HTTPX que resolve, valida e conecta no IP validado |
| `security/passwords.py` | Hash e verificação de senha com Argon2id |
| `checks/checker.py` | `HttpChecker`: faz um check e classifica o resultado |
| `notifications/webhook.py` | `WebhookNotifier`: envia um evento por POST |
| `db/models.py` | As 13 tabelas como classes do SQLAlchemy |
| `db/session.py` | Criação da conexão (engine) e da fábrica de sessões |
| `services/errors.py` | Exceções dos casos de uso (não encontrado, conflito, validação) |
| `services/monitors.py` | Criar, editar, pausar, retomar, arquivar, verificar agora |
| `services/processing.py` | Reservar execuções, gravar resultados, manutenção |
| `services/incidents.py` | Abrir, atualizar, resolver e encerrar incidentes |
| `services/alerts.py` | Outbox: criar eventos e entregas, reservar, registrar tentativas |
| `services/auth.py` | Operadores e sessões de login |
| `services/queries.py` | Consultas de leitura: listas, resumo, histórico, métricas |
| `worker/runner.py` | `Worker`: os três laços (checks, entregas, manutenção) |
| `worker/__main__.py` | Ponto de entrada do worker: trava única, sinais, clientes HTTP |
| `web/app.py` | `create_app`: monta o FastAPI, middlewares e tratamento de erros |
| `web/deps.py` | Dependências injetadas nas rotas: estado, sessão do banco, autenticação |
| `web/schemas.py` | Modelos Pydantic de entrada e saída da API |
| `web/api.py` | Rotas JSON em `/api/v1` |
| `web/pages.py` | Rotas das páginas HTML e login/logout |
| `web/health.py` | `/health/live` e `/health/ready` |
| `web/templating.py` | Ambiente Jinja2 com autoescape e filtros de formatação |
| `web/charts.py` | Monta o gráfico de latência em SVG |
| `web/templates/*.html` | As páginas |
| `web/static/style.css`, `app.js` | Estilo e o único JavaScript (atualiza o resumo) |

### Laboratório, scripts e testes

| Caminho | Responsabilidade |
|---|---|
| `lab/target.py` | Alvo controlável: saudável, lento, erro 500, timeout |
| `lab/receiver.py` | Receptor de webhooks com deduplicação e modo indisponível |
| `scripts/demo.sh`, `scripts/demo_flow.py` | Sobem o laboratório e executam os 11 passos |
| `scripts/ensaio_carga.sh`, `scripts/ensaio_carga.py` | Ensaio de carga local |
| `scripts/conferir_referencias.py` | Confere se testes citados na documentação existem |
| `scripts/capturar_telas.mjs` | Gera as capturas de tela (opcional, usa Node) |
| `migrations/env.py`, `migrations/versions/0001_esquema_inicial.py` | Configuração do Alembic e a migração |
| `tests/unit/` | Testes sem banco |
| `tests/integration/` | Testes com PostgreSQL real |
| `tests/conftest.py`, `tests/support.py`, `tests/support_db.py` | Fixtures e dublês compartilhados |

## Rota, schema, entidade e serviço

Esses quatro nomes aparecem o tempo todo. Usando o cadastro de monitor como
exemplo:

| Peça | O que é | Exemplo no PulseOps | Sabe de HTTP? | Sabe de banco? |
|---|---|---|---|---|
| **Rota** | Função ligada a um método e caminho HTTP; recebe a requisição e devolve a resposta | `create_monitor` em `web/api.py`, ligada a `POST /api/v1/monitors` | sim | só repassa a sessão |
| **Schema** | Classe Pydantic que descreve o formato de entrada ou saída e valida tipos | `MonitorIn` e `MonitorOut` em `web/schemas.py` | descreve o JSON | não |
| **Entidade** (modelo) | Classe SQLAlchemy que corresponde a uma tabela | `Monitor` em `db/models.py` | não | sim |
| **Serviço** (caso de uso) | Função que executa a regra de negócio, usando entidades e regras de domínio | `create_monitor` em `services/monitors.py` | não | sim |

E uma quinta peça, a **regra de domínio**: código puro, sem HTTP nem banco, como
`validate_config` e `HealthTracker`. É a parte mais fácil de testar.

Por que não colocar tudo na rota? Porque a mesma regra é usada por caminhos
diferentes: o cadastro pela API JSON (`web/api.py`) e pelo formulário HTML
(`web/pages.py`) chamam o **mesmo** `services/monitors.create_monitor`. Se a regra
estivesse dentro da rota, existiriam duas cópias, e um dia elas divergiriam.

## Caminho de uma requisição

@@diagrama requisicao

1. O navegador envia `POST /api/v1/monitors` com o cookie de sessão, o cabeçalho
   `X-CSRF-Token` e o JSON.
2. O middleware de `web/app.py` envolve tudo: no fim, acrescenta cabeçalhos de
   segurança (CSP, `X-Frame-Options`...).
3. O FastAPI resolve as **dependências** declaradas na assinatura da rota
   (`db: Db, state: State, _: ApiAuth`): abre uma sessão do banco, carrega a sessão
   de login pelo hash do cookie e confere o token CSRF. Sem sessão, 401; sem CSRF
   válido, 403.
4. O Pydantic converte o JSON em `MonitorIn`. Campo desconhecido ou tipo errado
   gera 422 antes de a rota rodar.
5. A rota chama o serviço, que valida as regras combinadas, aplica a política
   SSRF, confere nome repetido e faz `INSERT` (com `flush`, ainda sem confirmar).
6. A rota faz `commit` e devolve `MonitorOut` com status 201.
7. Erros de regra viram respostas HTTP: `ValidationFailedError` → 422,
   `NotFoundError` → 404, `ConflictError` → 409.

## Caminho de uma verificação

@@diagrama verificacao

1. O laço de checks do worker (`Worker._check_loop`) calcula as vagas livres
   (`worker_concurrency` menos os checks em andamento).
2. `claim_due_runs` abre uma transação curta: seleciona monitores ativos com
   `next_run_at` vencido e sem check em andamento, travando as linhas
   (`FOR UPDATE SKIP LOCKED`). Para cada um, insere um check `running` com
   `run_key = "<id>:<horário previsto>"` e avança `next_run_at` em um intervalo.
   Confirma e libera as travas.
3. Para cada execução reservada, o worker cria uma tarefa `asyncio` que chama
   `HttpChecker.check`. A requisição acontece **sem transação aberta**: um alvo
   que demora 30 s não segura nada no banco.
4. O transporte protegido resolve o nome, valida todos os IPs e conecta no IP
   validado. O verificador mede o tempo, lê só o status (nunca o corpo) e
   classifica o resultado em um `Outcome` com uma explicação curta.
5. `record_result` abre a segunda transação: trava o monitor, grava o resultado no
   check e, se o monitor continua ativo e com a mesma `config_version`, chama
   `_apply_domain`.
6. `_apply_domain` monta o estado atual (`TrackerState`), pergunta ao
   `HealthTracker` o que fazer e aplica a decisão: contadores, saúde, mudança de
   estado com motivo e, se for o caso, incidente e alerta. Tudo na mesma
   transação: ou tudo é gravado, ou nada.
7. Quando a tarefa termina, ela libera a vaga e acorda o laço, que reserva a
   próxima execução se houver fila (correção do bug B8).

## Caminho de um incidente

@@diagrama incidente

- **Abertura** (`services/incidents.open_incident`): cria o incidente com
  `started_at` = primeira falha e `confirmed_at` = check atual, copia os limiares
  vigentes, grava dois eventos na linha do tempo (`first_failure` e `opened`) e
  enfileira o alerta `incident.opened`. O `flush` força o banco a conferir o
  índice único parcial: se já houvesse um incidente aberto, a transação inteira
  falharia.
- **Atualização** (`record_failure_on_open_incident`): falhas seguintes só somam
  `failure_count` e trocam o último check. Se o **tipo** de falha mudar (de timeout
  para erro 500, por exemplo), entra um evento `error_changed`. Nenhum alerta novo.
- **Recuperação** (`resolve_incident`): status `resolved`, `ended_at`, motivo,
  evento `resolved` e alerta `incident.resolved`.
- **Encerramento pelo operador** (`close_incident_by_operator`): pausar ou
  arquivar com incidente aberto encerra como `closed`, com motivo explícito de que
  não houve recuperação observada, e alerta `incident.closed` (ADR 0006).
- **Mudança de configuração** (`record_config_change`): o incidente continua
  aberto; a linha do tempo registra o que mudou e quantos sucessos passam a ser
  exigidos.

## Caminho de uma notificação

@@diagrama notificacao

1. Na mesma transação que muda o incidente, `enqueue_incident_alert` grava o
   evento em `alert_events` (com `event_key` único, por exemplo
   `incident:12:opened`) e uma linha em `deliveries` para cada destino ativo.
   Esse é o padrão **outbox**: o alerta não é enviado agora, ele é registrado.
2. O laço de entregas, independente do laço de checks, chama
   `claim_due_deliveries`: pega entregas `pending` vencidas (ou `sending` cuja
   reserva expirou), marca como `sending` e empurra `next_attempt_at` para frente
   (uma "reserva com prazo").
3. `WebhookNotifier.send` faz o POST com o cabeçalho `X-PulseOps-Event-Id`, com
   timeout próprio e a mesma política SSRF dos checks.
4. `record_delivery_result` grava a tentativa e decide: 2xx → `delivered`; 4xx
   (exceto 408 e 429) → `failed` (não adianta repetir); outros erros → `pending`
   com espera `min(base × 2^(n−1), teto)`; tentativas esgotadas → `failed`.
5. Se o worker cair depois de enviar e antes de gravar, a reserva expira e a
   entrega é tentada de novo. Por isso a entrega é "pelo menos uma vez" e o
   receptor deve ignorar ids repetidos.

## Por que nenhuma fila externa

Não há Redis, Celery nem Kafka. A "fila" de checks é a coluna `next_run_at` com o
índice `ix_monitors_due`; a de alertas é a tabela `deliveries` com o índice
`ix_deliveries_due`. Para um worker e algumas centenas de monitores, o PostgreSQL
dá conta (o ensaio de carga mediu 200 monitores a cada 10 s) e as garantias de
consistência ficam em um só lugar. Uma fila externa entraria se houvesse muitos
workers ou volume muito maior, e isso exigiria medir antes (parte H, pergunta
sobre escala).
