# Requisitos e critérios de aceitação

Este documento transforma a especificação (`docs/especificacao.md`) em regras
verificáveis. Cada critério recebe um código (`RF03.4`, por exemplo) usado na
[matriz de rastreabilidade](matriz-de-rastreabilidade.md) para apontar o código
e o teste correspondentes.

> **Cenário fictício.** O PulseOps é um projeto pessoal de estudo. O cenário
> abaixo foi criado como requisito de exercício; não existe uma equipe, cliente
> ou empresa real por trás dele.

## Cenário (fictício)

Uma pequena equipe mantém APIs usadas por uma aplicação. Hoje descobre
problemas quando alguém reclama. Ela precisa acompanhar disponibilidade e
lentidão, consultar evidências dos incidentes e receber alertas sem ser
inundada por notificações repetidas.

## Escopo

Dentro:

- Monitores HTTP/HTTPS (GET ou HEAD) cadastrados por um único operador.
- Um worker que executa as verificações e entrega alertas por webhook.
- Incidentes abertos e encerrados por limiares consecutivos.
- Dashboard server-side (Jinja2) e API JSON, ambos autenticados.
- Laboratório local (perfil `demo` do Compose) para reproduzir falhas.

Fora (não implementado; alguns itens aparecem no roadmap do README):

- Outros tipos de monitor (TCP, ping, DNS, palavra-chave no corpo).
- Vários operadores, cadastro público, recuperação de senha, OAuth.
- Headers de autenticação para os alvos.
- Canais de alerta além de webhook genérico (e-mail, Slack etc.).
- Status page pública.
- Mais de um worker em paralelo.

## Glossário

| Termo | Significado no PulseOps |
|---|---|
| Monitor | Configuração de um endpoint a verificar. |
| Check (verificação) | Uma execução agendada de um monitor e seu resultado. |
| Identidade da execução (`run_key`) | Texto `"{monitor_id}:{scheduled_at ISO-8601 UTC}"`, único no banco. |
| Resultado (`outcome`) | Categoria do check: `healthy`, `slow`, `unexpected_status`, `timeout`, `connection_error`, `tls_error`, `blocked`, `internal_error`. |
| Falha do alvo | Resultado que indica que o serviço não respondeu como esperado (ver RF03.1). |
| Incidente | Período em que um monitor foi considerado indisponível, confirmado por limiar. |
| Evento de alerta | Linha persistida (outbox) que representa uma transição de incidente a notificar. |
| Entrega | Tentativa(s) de enviar um evento a um destino de webhook. |

## RF01 — Cadastro de monitores

Campos: `id`, `name`, `description` (opcional), `url`, `method` (`GET`/`HEAD`),
`interval_seconds`, `timeout_seconds`, `accepted_status_codes`,
`latency_threshold_ms`, `failure_threshold`, `recovery_threshold`,
`created_at`, `updated_at`, `state` (`active`, `paused`, `archived`).

Limites (modo normal; o modo demonstração muda apenas o mínimo do intervalo):

| Campo | Mínimo | Máximo | Padrão |
|---|---|---|---|
| `interval_seconds` | 30 (demo: 2) | 86400 | 60 |
| `timeout_seconds` | 1 | 30 | 5 |
| `latency_threshold_ms` | 50 | `timeout_seconds × 1000` | 1000 |
| `failure_threshold` | 1 | 10 | 3 |
| `recovery_threshold` | 1 | 10 | 2 |
| `name` | 1 caractere | 100 caracteres | — |
| `description` | — | 500 caracteres | vazio |
| `url` | — | 2048 caracteres | — |
| `accepted_status_codes` | — | 100 caracteres, códigos 100–599 | `200-299` |

Critérios:

- **RF01.1** Criar, listar, consultar, editar, pausar, retomar e arquivar
  monitores pela API e pelo dashboard.
- **RF01.2** Valores fora dos limites são rejeitados com mensagem que nomeia o
  campo (API responde 422).
- **RF01.3** `timeout_seconds` deve ser **menor** que `interval_seconds`.
- **RF01.4** `latency_threshold_ms` deve ser **menor ou igual** a
  `timeout_seconds × 1000`.
- **RF01.5** `accepted_status_codes` aceita lista de códigos e faixas
  (`200-299,301`). Faixas invertidas, códigos fora de 100–599 ou texto inválido
  são rejeitados.
- **RF01.6** A URL passa pela política de destino (ver `modelo-de-ameacas.md`)
  no cadastro e na edição.
- **RF01.7** Nomes são únicos entre monitores não arquivados (sem diferenciar
  maiúsculas). O banco garante isso com índice único parcial.
- **RF01.8** Arquivar não apaga nada: checks, incidentes e eventos continuam
  consultáveis. Monitor arquivado não pode ser editado nem retomado.
- **RF01.9** Pausar ou arquivar um monitor com incidente aberto **encerra o
  incidente com status `closed`** e motivo `monitor_paused` ou
  `monitor_archived`, e gera o evento de alerta `incident.closed`. O incidente
  não é marcado como "recuperado", porque nenhuma recuperação foi observada.
  Decisão registrada na [ADR 0006](decisoes/0006-pausa-e-arquivamento.md).

## RF02 — Verificações

- **RF02.1** Cada check grava: monitor, `run_key`, `scheduled_at` (previsto),
  `started_at` e `finished_at` (observados, UTC), `duration_ms` (medido com
  relógio monotônico), `status_code` quando houver resposta, `outcome`,
  `explanation` curta e `config_version` vigente.
- **RF02.2** Classificação, nesta ordem de precedência:

  | Situação | `outcome` |
  |---|---|
  | Destino recusado pela política de rede no momento da conexão | `blocked` |
  | Prazo total (`timeout_seconds`) estourado | `timeout` |
  | Erro de certificado/handshake TLS | `tls_error` |
  | Falha de DNS, conexão recusada, rede inalcançável | `connection_error` |
  | Resposta com status fora de `accepted_status_codes` | `unexpected_status` |
  | Status aceito e duração > `latency_threshold_ms` | `slow` |
  | Status aceito e duração ≤ `latency_threshold_ms` | `healthy` |
  | Exceção do próprio PulseOps, ou execução interrompida antes de gravar | `internal_error` |

- **RF02.3** `internal_error` **não conta como falha do alvo**: não altera
  contadores, saúde nem incidentes.
- **RF02.4** O corpo da resposta não é lido nem armazenado. A duração é medida
  até o recebimento dos cabeçalhos de resposta (inclui DNS, conexão e TLS).
- **RF02.5** Verificação TLS sempre habilitada; não existe opção para
  desabilitá-la.
- **RF02.6** Redirecionamentos não são seguidos. Um 3xx é avaliado como
  qualquer outro status (aceito só se estiver em `accepted_status_codes`).
- **RF02.7** A explicação não contém query string, credenciais nem corpo de
  resposta. Exemplo: `"Timeout: sem resposta em 5 s."`

## RF03 — Estados e incidentes

### Dois eixos separados

- Estado operacional (`monitors.state`): `active`, `paused`, `archived`.
- Saúde (`monitors.health`): `no_data`, `healthy`, `degraded`, `down`,
  `paused`.
- Condição derivada **dados desatualizados** (`stale`), calculada na leitura:
  monitor ativo cujo último check concluído é mais antigo que
  `2 × interval + timeout + 30 s`, **ou** heartbeat do worker mais antigo que
  `PULSEOPS_WORKER_STALE_AFTER_SECONDS` (padrão 30 s). Quando `stale`, a
  interface mostra "Dados desatualizados" no lugar da cor de saúde.

### Definições formais

- **RF03.1 Falha.** São falhas do alvo: `unexpected_status`, `timeout`,
  `connection_error`, `tls_error`, `blocked`. Não são falhas: `healthy`,
  `slow`, `internal_error`.
- **RF03.2 Lentidão.** `slow` **não** conta como falha para abrir incidente: o
  serviço respondeu com status aceito. Ela deixa a saúde em `degraded` e conta
  como **sucesso** para os contadores e para a recuperação. Motivo: o cenário
  pede separar lentidão de indisponibilidade; alertar por lentidão fica no
  roadmap ([ADR 0004](decisoes/0004-lentidao-nao-abre-incidente.md)).
- **RF03.3 Limiares consecutivos.** O monitor guarda `consecutive_failures` e
  `consecutive_successes`. Falha: `failures += 1`, `successes = 0`. Sucesso
  (`healthy` ou `slow`): `successes += 1`, `failures = 0`. `internal_error`:
  nada muda.
- **RF03.4 Reinício de contadores.** Os contadores voltam a zero (a) quando o
  resultado muda de lado (falha ↔ sucesso), (b) quando o monitor é pausado,
  retomado ou arquivado, (c) quando a configuração de verificação muda
  (RF03.5).
- **RF03.5 Alteração de configuração.** Mudar `url`, `method`,
  `accepted_status_codes`, `timeout_seconds`, `latency_threshold_ms`,
  `failure_threshold` ou `recovery_threshold` incrementa `config_version` e
  zera os contadores. Mudar só `name`, `description` ou `interval_seconds` não
  zera. Um incidente aberto continua aberto; a recuperação passa a exigir o novo
  `recovery_threshold` e o evento `config_changed` é registrado na linha do
  tempo do incidente. Resultados de checks iniciados com uma `config_version`
  antiga são gravados mas **não alteram** contadores nem incidentes.
- **RF03.6 Início, confirmação e fim.**
  - Primeira falha observada: quando `consecutive_failures` passa de 0 para 1,
    o instante do check é guardado em `monitors.first_failure_at`.
  - Confirmação (abertura): quando `consecutive_failures` atinge
    `failure_threshold` e não há incidente aberto, cria-se o incidente com
    `started_at = first_failure_at` e `confirmed_at = instante do check atual`.
  - Fim por recuperação: com incidente aberto, quando `consecutive_successes`
    atinge `recovery_threshold`, o incidente recebe `status = resolved`,
    `ended_at = instante do check atual`.
  - Fim por ação do operador: ver RF01.9 (`status = closed`).
- **RF03.7 Primeira falha ≠ confirmação.** `started_at` (primeira falha) é
  anterior ou igual a `confirmed_at`. A duração observada do incidente é
  `ended_at − started_at`.
- **RF03.8 Reinício do worker.** Contadores, saúde e incidente aberto ficam no
  banco, não na memória; após reinício o worker continua de onde parou. Checks
  que estavam `running` quando o processo morreu são marcados como
  `internal_error` ("execução interrompida") depois de `timeout + 30 s`, sem
  afetar contadores. Execuções perdidas não são recuperadas: ver RF04/consistência.
- **RF03.9 Saúde.** Calculada após cada check do monitor ativo:
  - incidente aberto → `down`;
  - senão, último resultado é falha (abaixo do limiar) → `degraded`;
  - senão, último resultado `slow` → `degraded`;
  - senão, `healthy`.
  Pausado/arquivado → `paused`. Recém-criado ou recém-retomado → `no_data`.
- **RF03.10 Explicação de cada mudança.** Toda mudança de saúde grava uma linha
  em `health_changes` com estado anterior, novo, check que causou e frase
  explicativa. Exemplo: `"Incidente confirmado após 3 falhas consecutivas;
  último resultado: timeout (sem resposta em 5 s)."`
- **RF03.11 Unicidade.** O banco impede mais de um incidente `open` por monitor
  (índice único parcial `WHERE status = 'open'`).
- **RF03.12 Retrato da decisão.** Incidente e eventos guardam
  `failure_threshold`, `recovery_threshold`, `timeout_seconds` e
  `latency_threshold_ms` vigentes no momento, além do último resultado. Mudanças
  posteriores no monitor não alteram esses valores.

### Exemplo obrigatório (vira teste)

Limiar de abertura 3, recuperação 2:

1. falha, falha, sucesso → nenhum incidente, contadores `failures=0, successes=1`.
2. falha, falha, falha → exatamente um incidente `open`.
3. mais duas falhas → o mesmo incidente; `failure_count = 5`.
4. um sucesso → incidente continua aberto.
5. segundo sucesso → incidente `resolved`.

## RF04 — Histórico

- **RF04.1** Checks paginados por cursor, ordem `(started_at DESC, id DESC)`.
  `limit` padrão 50, máximo 200.
- **RF04.2** Filtros: período `[from, to)` em UTC e `outcome`.
- **RF04.3** Incidentes abertos e encerrados, filtráveis por status, com o
  mesmo esquema de paginação (`confirmed_at DESC, id DESC`).
- **RF04.4** Linha do tempo do incidente: eventos em ordem `(occurred_at, id)`
  com motivo de abertura e de encerramento.
- **RF04.5** Notificações: eventos de alerta, estado de cada entrega e cada
  tentativa (instante, duração, status HTTP, erro).
- **RF04.6** Parâmetros de paginação fora dos limites → 422.

## RF05 — Métricas

Janela `[início, fim)`, padrão: últimas 24 h. Base: checks concluídos cujo
`started_at` está na janela.

| Métrica | Fórmula | Sem base válida |
|---|---|---|
| Checks avaliados `N` | checks na janela com `outcome ≠ internal_error` | 0 |
| Erros internos | checks `internal_error` na janela (fora de `N`) | 0 |
| % de checks disponíveis | `(healthy + slow) / N` | N/A se `N = 0` |
| % de checks saudáveis | `healthy / N` | N/A se `N = 0` |
| Latência média | média de `duration_ms` de checks com resposta HTTP (`healthy`, `slow`, `unexpected_status`) | N/A se nenhum |
| Latência p95 | **nearest-rank**: ordenar as `n` durações, `p95 = valor na posição ⌈0,95 × n⌉` (1-indexado) | N/A se `n = 0` |
| Incidentes | incidentes que se sobrepõem à janela (`started_at < fim` e (`ended_at` nulo ou `ended_at > início`)) | 0 |
| Duração observada | soma de `min(fim, ended_at ou agora) − max(início, started_at)` | 0 |
| Último check | maior `finished_at` | "Sem dados" |
| Lacunas | períodos registrados em `coverage_gaps` que se sobrepõem à janela | lista vazia |

Regras:

- **RF05.1** A proporção de checks disponíveis **não** é chamada de
  "disponibilidade temporal". A interface diz "checks disponíveis".
- **RF05.2** Timeouts entram em `N` como falha e **não** entram na latência
  (a duração de um timeout só mostra o prazo, não o tempo do serviço).
- **RF05.3** `slow` conta como disponível e não saudável.
- **RF05.4** Períodos pausados não geram checks: não contam como
  indisponibilidade nem como disponibilidade.
- **RF05.5** Com `n < 20`, o p95 nearest-rank é o maior valor da amostra; a
  interface mostra o tamanho da amostra ao lado do p95.
- **RF05.6** Tudo é armazenado em UTC (`timestamptz`). O dashboard converte
  explicitamente para o fuso de `PULSEOPS_DISPLAY_TIMEZONE` (padrão
  `America/Sao_Paulo`) e mostra o fuso.
- **RF05.7** Fim da janela é exclusivo: um check exatamente em `fim` fica fora;
  exatamente em `início` fica dentro.

## RF06 — Alertas

- **RF06.1** Abertura, recuperação e encerramento por operador criam um evento
  em `alert_events` **na mesma transação** da mudança do incidente, com chave
  estável `incident:{id}:{opened|resolved|closed}` (única).
- **RF06.2** Para cada destino de webhook ativo, cria-se uma linha em
  `deliveries` na mesma transação.
- **RF06.3** O entregador roda em tarefa separada do agendador de checks. Falha
  ou lentidão do webhook não atrasa nem impede verificações.
- **RF06.4** Cada envio tem timeout (`PULSEOPS_WEBHOOK_TIMEOUT_SECONDS`, padrão
  5 s), é registrado em `delivery_attempts` e envia o header
  `X-PulseOps-Event-Id`.
- **RF06.5** Retentativas: no máximo `PULSEOPS_WEBHOOK_MAX_ATTEMPTS` (padrão 6).
  Espera antes da tentativa `k+1`: `min(base × 2^(k−1), teto)`, base 5 s e
  teto 300 s (no modo demo, 1 s e 5 s).
- **RF06.6** Falha permanente: tentativas esgotadas, resposta 4xx (exceto 408 e
  429) ou destino recusado pela política de rede → `status = failed`.
- **RF06.7** Repetições de falha não geram novos eventos: só transições geram.
- **RF06.8** Entrega "pelo menos uma vez": se o processo cair depois do envio e
  antes de registrar o sucesso, o mesmo evento pode ser reenviado. O receptor
  deve deduplicar pelo `event_id`. O receptor do laboratório faz isso.
- **RF06.9** URLs de webhook passam pela mesma política SSRF dos monitores, no
  cadastro e no envio.

## RF07 — Dashboard

- **RF07.1** Telas: resumo de estados, lista de monitores, formulário de
  criação/edição, detalhe com gráfico de latência (SVG gerado no servidor a
  partir dos checks reais), histórico de checks, incidentes com linha do tempo,
  notificações, destinos de webhook.
- **RF07.2** Faixa visível "Modo demonstração" quando `PULSEOPS_DEMO_MODE=true`.
- **RF07.3** Estados: vazio (sem monitores), sem dados (monitor sem checks),
  dados desatualizados, erro (falha ao consultar o banco mostra página de erro
  sem detalhes internos), carregando (atualização automática do resumo).
- **RF07.4** Acessibilidade: todo estado tem rótulo de texto; foco visível;
  contraste mínimo 4,5:1 nos textos; tudo operável por teclado.
- **RF07.5** Nenhum dado sintético no dashboard. O laboratório gera tráfego
  real contra serviços locais, identificado como demonstração.

## RF08 — Acesso

- **RF08.1** Um operador criado por CLI (`pulseops create-admin`); senha com
  hash Argon2id (`argon2-cffi`).
- **RF08.2** Login cria sessão no banco; o cookie `pulseops_session` é
  `HttpOnly`, `SameSite=Lax`, `Secure` quando `PULSEOPS_COOKIE_SECURE=true`.
  O banco guarda apenas o hash SHA-256 do token.
- **RF08.3** Sessão expira em `PULSEOPS_SESSION_TTL_MINUTES` (padrão 480).
  Logout apaga a sessão.
- **RF08.4** Todas as rotas do dashboard e da API exigem sessão, exceto login,
  `/health/live`, `/health/ready` e estáticos. Sem sessão: API → 401,
  páginas → redirecionamento para o login.
- **RF08.5** CSRF: toda operação que altera estado (POST/PUT/PATCH/DELETE)
  exige token. Formulários enviam campo `csrf_token`; a API JSON envia header
  `X-CSRF-Token`. O token do login usa cookie de dupla submissão.
- **RF08.6** Nenhum token administrativo no JavaScript servido.

## RF09 — Saúde do próprio PulseOps

- **RF09.1** `GET /health/live` → 200 sem tocar no banco.
- **RF09.2** `GET /health/ready` → 200 se `SELECT 1` responde em até 2 s;
  senão 503. Informa a idade do heartbeat do worker (não reprova a prontidão
  da API por causa do worker).
- **RF09.3** Worker grava heartbeat a cada 5 s em `worker_heartbeats`.
- **RF09.4** Logs em JSON com `monitor_id`, `run_key`, `incident_id` quando
  houver; segredos e query strings mascarados.
- **RF09.5** Worker parado → todos os monitores ativos aparecem como "dados
  desatualizados" e o resumo mostra "Worker sem sinal há N s".
- **RF09.6** Limitação documentada: se o PulseOps inteiro cair, ele não consegue
  avisar. É preciso uma observação externa (por exemplo, outro serviço
  consultando `/health/ready`).

## Consistência e banco

- **CB1** Processar um resultado é uma transação: check, contadores, saúde,
  mudança de saúde, incidente, evento do incidente, evento de alerta e
  entregas. Falhou qualquer parte → rollback de tudo.
- **CB2** Reserva da execução em transação curta → requisição HTTP sem
  transação aberta → gravação do resultado em transação curta.
- **CB3** No máximo um check `running` por monitor (índice único parcial) e
  `run_key` único. Gravar duas vezes o resultado da mesma execução não duplica
  nada: a segunda gravação é ignorada.
- **CB4** Retomada sem avalanche: se o próximo horário previsto estiver mais de
  um intervalo no passado, o worker agenda para "agora" e grava a lacuna em
  `coverage_gaps` (motivo `scheduler_behind`).
- **CB5** "Verificar agora" apenas antecipa `next_run_at`; usa a mesma reserva e
  o mesmo controle de sobreposição. O check manual (`trigger = manual`) conta
  em métricas e incidentes como qualquer outro.
- **CB6** Retenção: checks concluídos com mais de
  `PULSEOPS_CHECK_RETENTION_DAYS` (padrão 30) são apagados pelo worker em
  lotes. Incidentes, eventos, mudanças de saúde e alertas não são apagados
  (guardam o retrato necessário; a referência ao check vira nula).
- **CB7** Um segundo worker não inicia enquanto o primeiro estiver rodando
  (advisory lock do PostgreSQL).

## Plano curto de implementação

1. Base: dependências travadas, configuração, modelos, migração, Compose, API
   mínima e primeiro teste de integração.
2. Fatia: cadastro → worker → check gravado → consulta pela API.
3. Domínio: máquina de estados, incidentes, contadores, consistência, reinício.
4. Alertas: outbox, entregador, receptor com deduplicação.
5. Interface e métricas: autenticação, páginas, gráfico, estados.
6. Revisão: segurança, retenção, logs, carga, instalação limpa.
7. GitHub e PDF.
