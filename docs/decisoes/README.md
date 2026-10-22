# Decisões arquiteturais (ADRs)

Cada arquivo registra uma decisão curta: contexto, decisão, alternativas e
consequências. Status possíveis: `aceita`, `substituída`.

| ADR | Decisão |
|---|---|
| [0001](0001-uv-como-gerenciador.md) | uv como único gerenciador de dependências |
| [0002](0002-api-e-worker-separados.md) | API e worker em processos separados, um worker suportado |
| [0003](0003-async-e-transacoes-curtas.md) | asyncio, SQLAlchemy assíncrono e transações curtas em volta da rede |
| [0004](0004-lentidao-nao-abre-incidente.md) | Resposta lenta não abre incidente |
| [0005](0005-ssrf-conectar-no-ip-validado.md) | SSRF: validar e conectar no mesmo IP; sem redirecionamentos |
| [0006](0006-pausa-e-arquivamento.md) | Pausar/arquivar encerra o incidente aberto como `closed` |
| [0007](0007-outbox-e-entrega-pelo-menos-uma-vez.md) | Outbox e entrega "pelo menos uma vez" |
| [0008](0008-autenticacao-por-sessao.md) | Sessão em banco, cookie HttpOnly e CSRF por token |
| [0009](0009-mypy.md) | mypy como verificador de tipos |
| [0010](0010-dashboard-server-side.md) | Dashboard renderizado no servidor, gráfico em SVG |
| [0011](0011-metricas-e-percentil.md) | Métricas por checks e p95 nearest-rank |
