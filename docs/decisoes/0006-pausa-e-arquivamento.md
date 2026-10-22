# ADR 0006 — Pausar ou arquivar encerra o incidente aberto como `closed`

Status: aceita (2026-10-22)

## Contexto
A especificação pede uma decisão explícita para incidente aberto quando o
monitor é pausado ou arquivado.

## Decisão
- O incidente aberto é encerrado na mesma transação da pausa/arquivamento, com
  `status = closed`, `ended_at = agora` e `resolution_reason =
  monitor_paused` ou `monitor_archived`.
- É criado o evento de alerta `incident.closed`, para que quem recebeu a
  abertura saiba que o PulseOps parou de acompanhar.
- Contadores e `first_failure_at` são zerados; a saúde vira `paused`.
- Ao retomar, a saúde vira `no_data` e o monitor começa do zero. Se o serviço
  ainda estiver fora, um **novo** incidente será aberto após o limiar.

## Alternativas
- Manter o incidente aberto e congelado: a duração cresceria sem observação, e
  o painel mostraria "indisponível" para algo que ninguém está verificando.
- Marcar como `resolved`: seria afirmar uma recuperação que não foi observada.

## Consequências
- Métricas de duração contam só até o encerramento, que é o que foi observado.
