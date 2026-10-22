# ADR 0002 — API e worker em processos separados, um worker suportado

Status: aceita (2026-10-22)

## Contexto
Verificações periódicas e entrega de alertas são trabalho contínuo. A
especificação proíbe agendar dentro de cada worker do servidor web e usar
`BackgroundTasks` para trabalho durável.

## Decisão
- Processo `api`: `uvicorn pulseops.web.app:create_app --factory`.
- Processo `worker`: `python -m pulseops.worker`, com três laços assíncronos:
  verificações, entregas e manutenção (heartbeat, checks interrompidos,
  retenção).
- Mesma imagem Docker, comandos diferentes.
- **Apenas um worker é suportado.** Ao iniciar, o worker pega um *advisory
  lock* de sessão do PostgreSQL (`pg_try_advisory_lock`). Se outro worker já o
  tiver, o segundo encerra com erro. Isso evita o problema de instância
  duplicada citado na pesquisa (uptime-kuma#3255).
- Mesmo assim, o banco protege contra sobreposição: índice único parcial de
  check `running` por monitor, `run_key` único e um incidente aberto por
  monitor. A proteção não depende da memória do processo.

## Alternativas
- Celery/Redis: resolveria filas distribuídas, mas o volume e o requisito de
  um operador não justificam outro serviço (proibido pela especificação sem
  justificativa).
- APScheduler dentro da API: rodaria duplicado com vários workers do Uvicorn.

## Consequências
- Escala limitada ao que um processo `asyncio` aguenta (ver ensaio de carga em
  `docs/operacao.md`).
- O lock é liberado automaticamente quando a conexão do worker cai.
