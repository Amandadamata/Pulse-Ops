# Operação e solução de problemas

## Subir, parar e atualizar

```bash
cp .env.example .env            # troque POSTGRES_PASSWORD
docker compose up -d --build --wait
docker compose run --rm api pulseops create-admin --username amanda
docker compose ps               # db, api e worker "healthy"; migrate "exited (0)"
docker compose down             # para tudo e mantém o volume do banco
```

- **Migrações** rodam no serviço `migrate` a cada `up`; api e worker só sobem
  depois que ele termina com sucesso.
- **Atualizar** para uma versão nova: `git pull` e `docker compose up -d --build
  --wait`. O worker termina os checks em andamento ao receber `SIGTERM`.
- **Um só worker.** Não use `--scale worker=2`: o segundo processo encerra com
  "outro worker já está rodando neste banco" (advisory lock do PostgreSQL).

## Variáveis de configuração

Todas com prefixo `PULSEOPS_`, lidas do ambiente ou do `.env`.

| Variável | Padrão | Uso |
|---|---|---|
| `DATABASE_URL` | montada pelo Compose | URL do PostgreSQL (`postgresql+psycopg://...`) |
| `PORT` | `8000` | Porta publicada em `127.0.0.1` (só no Compose) |
| `COOKIE_SECURE` | `false` | Use `true` atrás de HTTPS |
| `SESSION_TTL_MINUTES` | `480` | Duração da sessão |
| `DISPLAY_TIMEZONE` | `America/Sao_Paulo` | Fuso usado na interface; o banco guarda UTC |
| `ALLOWED_PORTS` | `80,443,8080,8443` | Portas permitidas para monitores e webhooks |
| `WORKER_CONCURRENCY` | `20` | Checks simultâneos |
| `WORKER_TICK_SECONDS` | `1.0` | Intervalo do laço do worker quando não há fila |
| `WORKER_STALE_AFTER_SECONDS` | `30` | Heartbeat mais antigo que isto = worker parado |
| `HEARTBEAT_INTERVAL_SECONDS` | `5` | Intervalo do heartbeat e da manutenção |
| `WEBHOOK_TIMEOUT_SECONDS` | `5` | Prazo de cada envio |
| `WEBHOOK_MAX_ATTEMPTS` | `6` | Tentativas antes de falha permanente |
| `WEBHOOK_BACKOFF_BASE_SECONDS` / `WEBHOOK_BACKOFF_MAX_SECONDS` | `5` / `300` | Espera `min(base * 2^(n-1), teto)` |
| `CHECK_RETENTION_DAYS` | `30` | Checks mais antigos são apagados (incidentes ficam) |
| `LOG_LEVEL` | `INFO` | Nível dos logs |
| `DEMO_MODE`, `DEMO_ALLOWED_HOSTS` | `false`, vazio | Só para o laboratório (`compose.demo.yaml`) |

Para build atrás de proxy TLS corporativo: `PULSEOPS_EXTRA_CA_FILE=/caminho/ca.pem`
(passado como secret de build, não fica na imagem).

## Saúde do próprio PulseOps

| Sinal | Onde ver |
|---|---|
| API viva | `GET /health/live` → 200 sem tocar no banco |
| API pronta | `GET /health/ready` → 200 se o banco responde em até 2 s; 503 caso contrário |
| Worker vivo | Painel: aviso "Worker sem sinal desde ..." e contador "desatualizados"; API: `GET /api/v1/summary` → `worker_alive` |
| Monitor com dados velhos | Último check mais antigo que `2 × intervalo + timeout + 30 s` aparece como "desatualizado" |

O PulseOps não avisa quando ele mesmo cai (está na mesma máquina dos dados). Para
isso, aponte outro serviço externo para `/health/ready`.

## Logs

Uma linha JSON por evento, com `ts`, `level`, `logger`, `msg` e, quando há
contexto, `monitor_id`, `run_key`, `incident_id`, `delivery_id`, `event_id`.
Query strings, credenciais em URL e campos como `password`, `token` e
`authorization` são mascarados antes de gravar.

```bash
docker compose logs -f worker | grep '"level": "WARNING"'
docker compose logs worker | grep '"monitor_id": 7'
```

O log de acesso do uvicorn também passa pelo mesmo formatador (query mascarada).
O healthcheck do Compose gera uma linha de acesso a cada 3 s em `/health/ready`.

## Backup e restauração

```bash
docker compose exec -T db pg_dump -U pulseops -Fc pulseops > pulseops.dump
docker compose exec -T db pg_restore -U pulseops -d pulseops --clean < pulseops.dump
```

Não há backup automático no projeto.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Todos os monitores "desatualizados" e aviso "Worker sem sinal" | Worker parado ou sem acesso ao banco | `docker compose ps worker`; `docker compose logs worker` (procure "erro no laço do worker") |
| Worker sai com "outro worker já está rodando neste banco" | Segunda instância rodando | Pare a outra (`docker ps`); só um worker é suportado |
| `/health/ready` com 503 | Banco fora do ar ou lento | `docker compose ps db`; espaço em disco do volume |
| Cadastro recusado com "endereço privado", "loopback" ou "porta não permitida" | Política SSRF, de propósito | Monitores só alcançam endereços públicos nas portas de `ALLOWED_PORTS`. Não há opção para liberar a rede interna fora do modo demonstração |
| Check com "falha de DNS: nome não resolvido" | DNS do container ou nome errado | `docker compose exec worker python -c "import socket; print(socket.getaddrinfo('exemplo.com', 443))"` |
| Alertas "pendentes" crescendo | Destino fora do ar ou lento | Página Notificações mostra cada tentativa e o erro; depois de `WEBHOOK_MAX_ATTEMPTS` a entrega vira "falhou" |
| Alerta recebido duas vezes | Entrega "pelo menos uma vez" (processo caiu depois do envio) | Deduplicar no receptor pelo header `X-PulseOps-Event-Id` |
| Checks começando até ~1 s depois do horário previsto | Granularidade do tick do worker | Esperado; reduza `WORKER_TICK_SECONDS` se precisar |
| Lacuna nas métricas depois de uma parada | Retomada sem avalanche: o período perdido vira `coverage_gaps` | Esperado; a lacuna aparece como período sem dados |
| Login esquecido | Senha não pode ser recuperada (Argon2) | Crie outro usuário com `pulseops create-admin --username novo` e apague o antigo no banco |
| Build falha com erro de certificado ou 429 do Docker Hub | Proxy TLS ou limite de downloads | Use `PULSEOPS_EXTRA_CA_FILE`; para o 429, espere ou use um espelho e marque a imagem com o nome oficial |
