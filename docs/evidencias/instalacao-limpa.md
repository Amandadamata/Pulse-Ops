# Instalação limpa

Executada em 2026-10-22, seguindo a seção "Início rápido" do `README.md`, a partir
de um clone novo do commit final.

## Ponto de partida

- Commit: `b737a56bfc6e8c478c2c4821e9e5eed88aa0d7ae`.
- Antes de começar: `docker compose ... down -v` apagou o volume `pulseops_pgdata`
  e `docker rmi pulseops:local` apagou a imagem. Não havia volume nem imagem do
  PulseOps na máquina.
- **O que não foi limpo:** o cache de build do Docker (BuildKit). Por isso o build
  levou poucos segundos; numa máquina nova ele baixa as dependências e demora mais.
- Docker 29.9.1, Compose 5.6.0, Linux 6.18 x86_64.

## Passos e saídas

```text
$ git clone <repositório> pulseops && cd pulseops
$ git rev-parse HEAD
b737a56bfc6e8c478c2c4821e9e5eed88aa0d7ae

$ cp .env.example .env            # POSTGRES_PASSWORD trocada por uma senha local
$ PULSEOPS_EXTRA_CA_FILE=docker/local-ca.pem docker compose up -d --build --wait
 Container pulseops-db-1 Healthy
 Container pulseops-migrate-1 Exited
 Container pulseops-worker-1 Started
 Container pulseops-api-1 Healthy
(código 0, 24,6 s)

$ docker compose run --rm -T api pulseops create-admin --username amanda --password-stdin
operador 'amanda' criado

$ curl -s http://127.0.0.1:8000/health/ready
{"status":"ok","database":"ok","worker":{"alive":true,"last_seen_at":"2026-10-22T05:03:13.217137+00:00"}}
```

Login pelo formulário e cadastro de um monitor pela API (com `curl` e o cookie de
sessão):

```text
POST /login                         -> HTTP 303 para /
POST /api/v1/monitors (https://example.com/, intervalo 30 s) -> HTTP 201, id 1, health "no_data"
GET  /api/v1/monitors/1/checks?limit=1
  outcome "connection_error", explanation "falha de DNS: nome não resolvido", duration_ms 29
GET  /api/v1/summary
  {"total":1,"by_health":{"degraded":1},"stale":0,"open_incidents":0,
   "pending_deliveries":0,"failed_deliveries":0,"worker_alive":true, ...}

$ docker compose ps
api     Up 30 seconds (healthy)
db      Up 35 seconds (healthy)
worker  Up 30 seconds
```

Conferência do endurecimento do contêiner:

```text
$ docker inspect pulseops-api-1
user=pulseops readonly=true capdrop=[ALL] secopt=[no-new-privileges:true]
ports={"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":"8000"}]}
$ docker inspect pulseops-db-1
ports={}                      # banco sem porta publicada
$ docker exec pulseops-api-1 id
uid=10001(pulseops) gid=999(pulseops) groups=999(pulseops)
```

Em seguida, no mesmo clone, `scripts/demo.sh` concluiu os 11 passos:
"Demonstração concluída: os 11 passos foram verificados." (código 0).

## Diferenças em relação ao README, e por quê

- **`PULSEOPS_EXTRA_CA_FILE`:** este ambiente sai para a internet por um proxy TLS
  próprio. Sem o certificado dele, o build não consegue baixar o `uv` e as
  dependências. Numa máquina comum, a variável não é necessária.
- **`--password-stdin` e `-T`:** o README usa a forma interativa, que pede a senha
  no terminal. Aqui não há terminal interativo, então a senha foi passada pela
  entrada padrão. O comando e o resultado são os mesmos.
- **O monitor ficou degradado, não saudável:** este ambiente não tem DNS público,
  então `example.com` não resolve. É o comportamento correto (a falha é classificada
  e explicada), mas significa que esta instalação **não** demonstrou um site real
  respondendo. Os checks saudáveis foram demonstrados com o alvo do laboratório.

## Referências da documentação

Depois de criar esta página e `docs/evidencias/verificacao.md`:

```text
$ uv run python scripts/conferir_referencias.py
416 referências conferidas, 0 problemas
(código 0)
```
