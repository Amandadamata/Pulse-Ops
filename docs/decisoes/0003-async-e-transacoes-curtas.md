# ADR 0003 — asyncio, SQLAlchemy assíncrono e transações curtas

Status: aceita (2026-10-22)

## Contexto
O worker passa a maior parte do tempo esperando rede. Várias verificações
precisam acontecer em paralelo sem uma thread por monitor.

## Decisão
- `asyncio` no worker e na API. HTTPX `AsyncClient` criado uma vez por
  processo (um para checks, outro para webhooks) e fechado no encerramento.
- SQLAlchemy 2.x assíncrono com o driver **psycopg 3** (o mesmo driver serve ao
  Alembic, que roda de forma síncrona).
- Concorrência limitada a `PULSEOPS_WORKER_CONCURRENCY` (padrão 20) checks em
  andamento. *Revisão na implementação:* em vez de `asyncio.Semaphore`, o laço
  reserva no banco só o número de vagas livres, para não marcar como `running`
  checks que ainda iriam esperar na fila do semáforo. Veja também o bug B8.
- Uma `AsyncSession` por unidade de trabalho; nenhuma sessão é compartilhada
  entre tarefas.
- Sequência de um check: (1) transação curta que reserva a execução e grava o
  check como `running`; (2) requisição HTTP sem transação aberta; (3)
  transação curta que grava o resultado e aplica as regras de domínio.

## Alternativas
- Código síncrono com threads: mais simples de ler linha a linha, mas cada
  verificação lenta prende uma thread e a sessão precisaria do mesmo cuidado.

## Consequências
- Exige atenção a I/O síncrono dentro de corrotinas (por exemplo, a resolução
  DNS usa `loop.getaddrinfo`, que roda em thread do executor).
- Uma falha entre (2) e (3) deixa um check `running`; o laço de manutenção o
  marca como `internal_error` depois do prazo (RF03.8).
