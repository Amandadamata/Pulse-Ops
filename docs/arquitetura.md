# Arquitetura e modelo de dados

## Processos

```mermaid
flowchart LR
    browser[Navegador da operadora] -->|HTML, formulários, /api/v1| api
    subgraph compose[Docker Compose]
        api[api<br/>uvicorn + FastAPI<br/>dashboard e API JSON]
        worker[worker<br/>python -m pulseops.worker]
        db[(PostgreSQL 16)]
        migrate[migrate<br/>alembic upgrade head]
    end
    api -->|SQLAlchemy async| db
    worker -->|transações curtas| db
    migrate --> db
    worker -->|checks HTTP com política SSRF| alvos[APIs monitoradas]
    worker -->|POST de webhook| destinos[Destinos de alerta]
```

- **api** atende o dashboard (Jinja2) e a API JSON em `/api/v1`. Não executa
  nenhum trabalho periódico (ADR 0002). Publica a porta só em `127.0.0.1`.
- **worker** roda três laços `asyncio` independentes: checks, entregas de alertas
  e manutenção (heartbeat, checks abandonados, retenção). Um advisory lock do
  PostgreSQL garante que só um worker fica ativo; um segundo processo sai com erro.
- **migrate** aplica as migrações antes de api e worker subirem.
- **db** não publica porta no Compose padrão.

A mesma imagem atende api, worker, migrate e, no perfil `demo`, o laboratório.

## Ciclo de uma verificação

```mermaid
sequenceDiagram
    participant W as worker (laço de checks)
    participant DB as PostgreSQL
    participant T as alvo HTTP
    W->>DB: transação 1: SELECT monitores vencidos FOR UPDATE SKIP LOCKED<br/>INSERT check 'running' (run_key único), avança next_run_at
    DB-->>W: execuções reservadas
    W->>T: requisição HTTP (sem transação aberta)
    T-->>W: status, tempo ou erro
    W->>DB: transação 2: trava o monitor, grava o resultado,<br/>aplica HealthTracker, incidente, eventos, outbox
```

1. **Reserva** (`services/processing.py::claim_due_runs`): transação curta. O
   índice único parcial `uq_checks_one_running_per_monitor` impede dois checks em
   andamento para o mesmo monitor; `run_key = monitor_id:scheduled_at` é único e
   torna o reprocessamento da mesma execução inofensivo.
2. **Requisição** (`checks/checker.py::HttpChecker`): nenhuma transação aberta. O
   cliente HTTPX usa `GuardedNetworkBackend`, que resolve o nome, valida todos os
   IPs e conecta no IP validado (ADR 0005).
3. **Gravação** (`record_result`): uma transação grava resultado, contadores,
   saúde, mudança de estado, incidente, eventos da linha do tempo, evento de alerta
   e entregas. Ou tudo, ou nada. Se o monitor foi pausado, editado ou arquivado
   durante a requisição (`config_version` diferente), o resultado entra no
   histórico sem efeito no domínio.

Se o processo morrer entre 1 e 3, o check fica `running`. A manutenção o marca
como `internal_error` depois de `timeout + 30 s`; erro interno não conta como
falha do alvo.

**Retomada sem avalanche:** se um monitor está atrasado mais de um intervalo, a
próxima execução é agendada para agora e o período perdido vira uma linha em
`coverage_gaps`, exibida como lacuna nas métricas.

**Vazão:** o laço reserva até `worker_concurrency` execuções. Se preencheu todas
as vagas, volta assim que uma vaga abre; se não havia mais nada vencido, espera o
tick de 1 s (bug B8 e `docs/evidencias/ensaio-de-carga.md`).

## Organização do código

| Pasta | Responsabilidade |
|---|---|
| `domain/` | Regras puras, sem banco nem HTTP: `HealthTracker` (RF03), validação de configuração, códigos de status, fórmulas de métricas |
| `security/` | Política de destinos (SSRF), transporte protegido, hash de senha |
| `checks/` | Cliente de verificação (`Checker` Protocol e `HttpChecker`) |
| `notifications/` | Envio de webhook (`Notifier` Protocol e `WebhookNotifier`) |
| `services/` | Casos de uso que combinam domínio e persistência (monitores, processamento, incidentes, alertas, autenticação, consultas) |
| `db/` | Modelos SQLAlchemy 2.x e sessão |
| `worker/` | Laços do worker e ponto de entrada com o advisory lock |
| `web/` | Rotas da API e das páginas, schemas Pydantic, templates e estáticos |
| `lab/` (raiz) | Alvo e receptor controláveis do laboratório |

**Onde há classes e por quê.** `HealthTracker` encapsula a regra de transição e
recebe `Thresholds` por composição; `HttpChecker`, `WebhookNotifier` e
`SystemClock` implementam `Protocol`s (`Checker`, `Notifier`, `Clock`), o que
permite trocar transporte, notificador e relógio nos testes (`ScriptedTarget`,
`RecordingNotifier`, `FakeClock`). `Worker` guarda o estado dos laços (tarefas em
andamento, última retenção).

**Onde funções simples bastaram.** Casos de uso em `services/` são funções que
recebem a sessão: não guardam estado entre chamadas, e uma classe só repassaria
argumentos. O mesmo vale para `backoff_delay`, `nearest_rank` e `parse_status_codes`.

## Modelo de dados

```mermaid
erDiagram
    operators ||--o{ operator_sessions : "tem"
    monitors ||--o{ checks : "gera"
    monitors ||--o{ incidents : "tem"
    monitors ||--o{ health_changes : "registra"
    monitors ||--o{ coverage_gaps : "registra"
    incidents ||--o{ incident_events : "linha do tempo"
    incidents ||--o{ alert_events : "gera"
    alert_events ||--o{ deliveries : "uma por destino"
    alert_destinations ||--o{ deliveries : "recebe"
    deliveries ||--o{ delivery_attempts : "tentativas"
    checks |o--o{ incident_events : "referência opcional"
    checks |o--o{ health_changes : "referência opcional"
    checks |o--o{ incidents : "último check"

    operators {
        int id PK
        string username UK
        string password_hash
        timestamptz created_at
    }
    operator_sessions {
        string token_hash PK
        int operator_id FK
        string csrf_token
        timestamptz expires_at
    }
    monitors {
        int id PK
        string name "único entre não arquivados (lower)"
        string url
        string method "GET ou HEAD"
        int interval_seconds
        int timeout_seconds
        string accepted_status_codes
        int latency_threshold_ms
        int failure_threshold
        int recovery_threshold
        string state "active, paused, archived"
        string health "no_data, healthy, degraded, down, paused"
        string health_reason
        int consecutive_failures
        int consecutive_successes
        int config_version
        timestamptz next_run_at
        timestamptz archived_at
    }
    checks {
        bigint id PK
        int monitor_id FK
        string run_key UK
        string trigger "scheduled, manual"
        string status "running, completed"
        timestamptz scheduled_at
        timestamptz started_at
        int duration_ms
        int status_code
        string outcome
        string explanation
    }
    incidents {
        int id PK
        int monitor_id FK
        string status "open, resolved, closed"
        timestamptz started_at
        timestamptz confirmed_at
        timestamptz ended_at
        string opening_reason
        string resolution_explanation
        int failure_count
        bigint last_check_id FK
    }
    incident_events {
        int id PK
        int incident_id FK
        string kind
        timestamptz occurred_at
        jsonb details
        bigint check_id FK
    }
    health_changes {
        int id PK
        int monitor_id FK
        string from_health
        string to_health
        string reason
        bigint check_id FK
    }
    coverage_gaps {
        int id PK
        int monitor_id FK
        timestamptz gap_start
        timestamptz gap_end
        string reason
    }
    alert_destinations {
        int id PK
        string name UK
        string url
        bool enabled
    }
    alert_events {
        int id PK
        string event_key UK
        string kind
        int incident_id FK
        int monitor_id FK
        jsonb payload
    }
    deliveries {
        int id PK
        int event_id FK
        int destination_id FK
        string status
        int attempt_count
        timestamptz next_attempt_at
    }
    delivery_attempts {
        int id PK
        int delivery_id FK
        int attempt_number
        int status_code
        string result
        string error
    }
    worker_heartbeats {
        string worker_id PK
        string hostname
        int pid
        timestamptz last_seen_at
    }
```

Todas as datas são `timestamptz` e gravadas em UTC; a interface converte para
`PULSEOPS_DISPLAY_TIMEZONE`.

### Restrições que o banco garante

| Restrição | O que impede |
|---|---|
| `uq_incidents_one_open_per_monitor` (único parcial, `status = 'open'`) | Dois incidentes abertos para o mesmo monitor (CB2) |
| `uq_checks_one_running_per_monitor` (único parcial, `status = 'running'`) | Checks sobrepostos, inclusive "verificar agora" (CB3) |
| `checks.run_key` único | Gravar duas vezes a mesma execução agendada (CB1) |
| `uq_monitors_active_name` (único parcial em `lower(name)`) | Dois monitores ativos ou pausados com o mesmo nome |
| `alert_events.event_key` único (`incident:{id}:{opened,resolved,closed}`) | Evento de alerta duplicado para a mesma transição |
| `uq_deliveries_event_destination` | Duas entregas do mesmo evento para o mesmo destino |
| `uq_delivery_attempts_number` | Duas tentativas com o mesmo número |
| CHECKs de faixa em `monitors` (intervalo, timeout < intervalo, limiares, latência) | Configuração inválida mesmo que a validação da aplicação falhe |
| `(status = 'open') = (ended_at IS NULL)` em `incidents` | Incidente aberto com fim, ou encerrado sem fim |
| `(state = 'archived') = (archived_at IS NOT NULL)` | Arquivamento sem data |
| FKs `ON DELETE RESTRICT` para monitores e incidentes | Apagar monitor ou incidente com histórico (arquivar é o caminho) |
| FKs `ON DELETE SET NULL` para `check_id` | A retenção apaga checks sem perder incidentes, eventos e mudanças de estado |

### Índices e a consulta que cada um atende

| Índice | Consulta |
|---|---|
| `ix_monitors_due` (`next_run_at`, parcial `state = 'active'`) | Reserva do worker: monitores ativos vencidos |
| `ix_checks_monitor_history` (`monitor_id, started_at, id`) | Histórico paginado por cursor e janelas de métricas por monitor |
| `ix_checks_started_at` | Retenção: apagar checks mais antigos que N dias |
| `ix_incidents_confirmed` (`confirmed_at, id`) | Lista geral de incidentes, mais recentes primeiro |
| `ix_incidents_monitor` (`monitor_id, confirmed_at`) | Incidentes de um monitor e contagem na janela de métricas |
| `ix_incident_events_timeline` (`incident_id, occurred_at, id`) | Linha do tempo de um incidente |
| `ix_health_changes_monitor` (`monitor_id, changed_at, id`) | Mudanças de estado na página do monitor |
| `ix_coverage_gaps_monitor` (`monitor_id, gap_start`) | Lacunas na janela de métricas |
| `ix_alert_events_created`, `ix_alert_events_incident` | Página de notificações e alertas de um incidente |
| `ix_deliveries_due` (`next_attempt_at`, parcial `pending`/`sending`) | Reserva do entregador |
| `ix_*_check` (em `incidents`, `incident_events`, `health_changes`) | `SET NULL` rápido quando a retenção apaga checks |

### Retenção, preservação e arquivamento

- **Checks** são apagados depois de `PULSEOPS_CHECK_RETENTION_DAYS` (30 por padrão),
  uma vez por hora, pela manutenção do worker. Referências a eles viram nulas.
- **Incidentes, eventos, mudanças de estado, lacunas e alertas** não são apagados:
  são a evidência do que aconteceu e continuam legíveis depois da retenção (as
  explicações são texto copiado no momento do fato, não junções com o check).
- **Arquivar** um monitor não apaga nada: fecha um incidente aberto com status
  `closed`, para de agendar e libera o nome para um novo monitor. O histórico
  continua consultável (ADR 0006).
