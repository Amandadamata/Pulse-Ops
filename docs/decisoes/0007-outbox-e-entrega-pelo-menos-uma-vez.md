# ADR 0007 — Outbox e entrega "pelo menos uma vez"

Status: aceita (2026-10-22)

## Contexto
Alertas não podem se perder se o destino estiver fora (uptime-kuma#6046), nem
travar as verificações (uptime-kuma#4058).

## Decisão
- `alert_events`: um evento por transição de incidente, criado na mesma
  transação da mudança. Chave única `incident:{id}:{tipo}`.
- `deliveries`: uma linha por (evento, destino), também na mesma transação.
- `delivery_attempts`: uma linha por tentativa.
- O laço de entregas reserva entregas vencidas com `FOR UPDATE SKIP LOCKED`,
  marca `sending` com prazo de reserva (`lease_until`), faz o POST fora da
  transação e grava o resultado.
- Backoff exponencial com teto e número máximo de tentativas; 4xx (exceto 408 e
  429) é falha permanente.
- Se o worker morrer durante o envio, a reserva expira e a entrega é tentada
  de novo: o destino pode receber o mesmo evento duas vezes. Por isso o header
  `X-PulseOps-Event-Id` e o campo `event_id` no corpo.

## Alternativas
- Enviar direto no processamento do check: acopla a verificação ao destino.
- Fila externa (Redis, RabbitMQ): desnecessária para um worker.

## Consequências
- Sem garantia "exactly once". O receptor precisa deduplicar.
