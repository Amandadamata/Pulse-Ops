# ADR 0004 — Resposta lenta não abre incidente

Status: aceita (2026-10-22)

## Contexto
A especificação exige decidir se resposta lenta conta como falha.

## Decisão
`slow` é tratado como **sucesso para disponibilidade** e como **degradação de
saúde**:
- não incrementa `consecutive_failures`;
- incrementa `consecutive_successes` (pode recuperar um incidente);
- deixa a saúde em `degraded` com a explicação "resposta lenta: X ms (limite
  Y ms)";
- nas métricas, conta como disponível e não saudável.

## Alternativas
- Contar lentidão como falha: misturaria "o serviço está fora" com "o serviço
  está devagar" e geraria incidentes de indisponibilidade para um serviço que
  responde.
- Incidente de lentidão separado: útil, mas dobra a máquina de estados.
  Fica no roadmap.

## Consequências
- Lentidão persistente aparece no dashboard (saúde `degraded`, p95) mas não
  gera alerta. Isso está nas limitações do README.
