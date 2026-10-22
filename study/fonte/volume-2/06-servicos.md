# D6 — Serviços: os casos de uso

`src/pulseops/services/` é a camada que junta domínio e banco. Cada função recebe
uma sessão (ou a fábrica de sessões) e executa um caso de uso: criar monitor,
gravar resultado, abrir incidente, reservar entregas. As rotas da API e o worker só
chamam essas funções.

Duas formas aparecem e é importante distingui-las:

- funções que recebem **`session: AsyncSession`** trabalham **dentro** de uma
  transação aberta por quem chama (as rotas e o próprio `processing.py`);
- funções que recebem **`sessions: SessionFactory`** abrem e fecham a própria
  transação curta (as do worker: `claim_due_runs`, `record_result`...).

## `src/pulseops/services/errors.py`

**Finalidade.** Três exceções de caso de uso, independentes de HTTP.

@@arquivo src/pulseops/services/errors.py

- `NotFoundError` (6–7): o recurso não existe; as rotas devolvem 404.
- `ConflictError` (10–11): a operação não combina com o estado (pausar um monitor
  já pausado); as rotas devolvem 409.
- `ValidationFailedError` (14–17): carrega a lista de `FieldError`. A linha 16
  monta uma mensagem legível para logs; a 17 guarda a lista para a API devolver
  422 com os campos e o formulário mostrar cada erro ao lado do campo.

**Relações.** Levantadas em `services/monitors.py`; traduzidas em `web/api.py`
(`_http_error`) e `web/pages.py`. **Testes.** `test_invalid_configuration_is_rejected`,
`test_pause_resume_and_conflicts`.

## `src/pulseops/services/auth.py`

**Finalidade.** Operadora, login e sessões (RF08, ADR 0008).

**Dados.** Nome e senha (texto, do formulário); token de sessão (texto aleatório
de 43 caracteres, vai para o cookie); hash SHA-256 do token (vai para o banco).
**Relações.** Usa `security/passwords.py` e os modelos `Operator`,
`OperatorSession`; chamado por `cli.py`, `web/pages.py` (login e logout) e
`web/deps.py` (cada requisição). **Testes.** `tests/integration/test_auth.py` (16
funções, 26 casos) e `tests/integration/test_cli.py`.

@@trecho src/pulseops/services/auth.py 15-38

- Linhas 15–16: SHA-256 em hexadecimal. Para tokens aleatórios longos, um hash
  rápido basta (não há o que adivinhar); Argon2 é para senhas, que são curtas e
  previsíveis.
- Linhas 19–30: cria a operadora. `strip()` remove espaços nas pontas; o tamanho é
  conferido (3 a 50); um nome repetido levanta `ValueError` (linha 26). `flush()`
  manda o `INSERT` sem confirmar a transação, para gerar o `id`.
- Linhas 33–38: login (volume 1, parte G). Devolve a operadora ou `None`, nunca
  diz qual dos dois (usuário ou senha) estava errado.

@@trecho src/pulseops/services/auth.py 41-86

- Linhas 41–45: o que o login devolve para a rota: o token (para o cookie), o token
  CSRF (para os formulários) e a validade.
- Linhas 48–65: `secrets.token_urlsafe(32)` gera 32 bytes aleatórios do gerador
  criptográfico do sistema, em base64 seguro para URL. O banco guarda o hash (linha
  56). A linha 64 aproveita para apagar sessões vencidas de todo mundo.
- Linhas 68–80: carrega a sessão pelo hash do cookie, só se não estiver vencida
  (linha 76), junto com a operadora. Devolve uma tupla ou `None`.
- Linhas 83–86: logout apaga a linha da sessão. O cookie antigo deixa de valer
  imediatamente (`test_logout_invalidates_session`).

**Falhas possíveis.** Nenhuma exceção no caminho normal; erro de banco sobe para a
rota (erro 500).

## `src/pulseops/services/monitors.py`

**Finalidade.** Cadastro de monitores e o ciclo de vida: criar, editar, pausar,
retomar, arquivar e "verificar agora" (RF01).

**Dados.** `MonitorConfig` vindo da API ou do formulário; o horário atual; a política
de destinos. Grava em `monitors`, `health_changes` e, via `incidents`, em
`incident_events`. **Relações.** Chamado por `web/api.py` e `web/pages.py`; usa
`domain/monitor_rules.py`, `security/transport.py` e `services/incidents.py`.
**Testes.** `tests/integration/test_api_monitors.py`,
`test_edit_and_lifecycle_actions_through_forms`,
`test_pause_closes_open_incident_and_resume_starts_clean`,
`test_config_change_resets_counters_and_keeps_incident`.

@@trecho src/pulseops/services/monitors.py 19-44

`_validate` junta três validações e levanta **uma** exceção com todos os erros:

- Linha 28: regras de campo (`domain/monitor_rules.py`).
- Linhas 29–33: só valida o destino (SSRF) se a URL passou nas regras de tamanho;
  o erro vira um `FieldError` da URL.
- Linhas 35–41: nome repetido, sem diferenciar maiúsculas, entre não arquivados. Na
  edição, o próprio monitor é excluído da busca (`exclude_id`).

@@trecho src/pulseops/services/monitors.py 47-83

- Linhas 56–58: valida antes de qualquer gravação.
- Linhas 59–61: `asdict` transforma o `MonitorConfig` em dicionário; nome e URL são
  limpos de espaços.
- Linhas 62–75: `Monitor(**values, ...)` passa o dicionário como argumentos nomeados
  e completa o estado inicial: ativo, sem dados, contadores zerados, versão 1 e
  primeira verificação imediata (linha 72).
- Linhas 77–82: o `flush` dispara o índice único de nome. Se outra requisição
  cadastrou o mesmo nome **entre** a conferência da linha 41 e agora, o banco recusa,
  e o erro vira a mesma mensagem de validação. É a "corrida" que o índice resolve.

@@trecho src/pulseops/services/monitors.py 86-105

- Linhas 86–90: busca por id, opcionalmente com trava (`FOR UPDATE`); se não existe,
  `NotFoundError`.
- Linhas 93–105: o caminho inverso de `create_monitor`: monta a configuração a
  partir do monitor gravado (usado para comparar na edição e para preencher o
  formulário).

@@trecho src/pulseops/services/monitors.py 108-150

- Linha 118: trava o monitor durante a edição (serializa com o worker).
- Linhas 119–120: arquivado não se edita.
- Linhas 130–134: compara antes e depois e lista os campos de `CHECK_FIELDS` que
  mudaram.
- Linhas 135–137: `setattr` aplica cada campo. É genérico de propósito: um campo
  novo em `MonitorConfig` passa a ser gravado sem mudar esta função.
- Linhas 139–147: se mudou algo que afeta a contagem, incrementa a versão, zera os
  contadores e registra o evento no incidente aberto, se houver (RF03.5). Essas
  quatro linhas repetem o que `_reset_counters` (linhas 171–177) faz; poderiam
  chamá-la.
- Linhas 148–149: mudou o intervalo de um monitor ativo: verifica já, em vez de
  esperar o agendamento antigo.

@@trecho src/pulseops/services/monitors.py 153-177

- Linhas 153–168: muda a saúde **e registra** a mudança em `health_changes`, sem
  check associado (foi a operadora, não um check). Se a saúde não muda, só
  atualiza o motivo (linha 168).
- Linhas 171–177: zera a contagem e incrementa a versão. O comentário explica o
  bug B6.

@@trecho src/pulseops/services/monitors.py 180-236

As quatro ações seguem o mesmo padrão: travar o monitor, conferir o estado
(`ConflictError` se não combina), alterar e registrar.

- Pausar (180–191): encerra o incidente aberto como `closed` (ADR 0006), tira o
  agendamento (`next_run_at = None`), zera a contagem e marca "pausado".
- Retomar (194–209): agenda para agora e volta para "sem dados". O monitor recomeça
  limpo: um incidente anterior não é reaberto.
- Arquivar (212–225): igual a pausar, mais a data de arquivamento. Nada é apagado
  (RF01.8).
- Verificar agora (228–236): antecipa o agendamento e marca o próximo check como
  manual. Não executa nada na rota (volume 1, H7).

**Falhas possíveis.** `NotFoundError`, `ConflictError` e `ValidationFailedError`,
traduzidas pelas rotas. Erro de banco sobe como erro 500.

## `src/pulseops/services/incidents.py`

**Finalidade.** Todas as mudanças em incidentes: abrir, registrar nova falha,
resolver, encerrar pela operadora e registrar mudança de configuração. Cada uma
grava eventos na linha do tempo e, quando é uma transição, o alerta.

**Dados.** Monitor e check já carregados na transação de quem chama. **Relações.**
Chamado por `services/processing.py` (regras do worker) e `services/monitors.py`
(ações da operadora); chama `services/alerts.py`. **Testes.**
`tests/integration/test_incident_lifecycle.py` (nove testes),
`test_incident_list_detail_and_timeline`, `test_outbox_event_is_atomic_with_incident`.

@@trecho src/pulseops/services/incidents.py 1-35

- Linha 1: a docstring é a regra do arquivo: **nunca** abre transação; sempre
  roda dentro da de quem chama.
- Linhas 13–16: garante que o check está concluído e devolve resultado e fim. A
  checagem existe também para o mypy: as colunas são `| None`.
- Linhas 19–27: o "retrato" da configuração vigente, guardado em cada evento.
- Linhas 30–35: busca o incidente aberto **travando-o** (`FOR UPDATE`).

@@trecho src/pulseops/services/incidents.py 38-94

- Linhas 48–62: cria o incidente com início (primeira falha), confirmação (este
  check), retrato dos limiares e o último resultado.
- Linha 64: `flush` gera o `id`; o comentário lembra que é aqui que o índice único
  de "um aberto por monitor" é verificado.
- Linhas 66–85: dois eventos de uma vez (`add_all`): "primeira falha" com o horário
  do início e "aberto" com o motivo e o status HTTP.
- Linhas 86–93: o alerta `incident.opened`, na mesma transação.

@@trecho src/pulseops/services/incidents.py 97-145

- Linhas 97–117: nova falha com incidente aberto. Atualiza contagem e último check.
  Só cria um evento se o **tipo** de falha mudou (de timeout para 500, por exemplo):
  a linha do tempo não ganha uma linha por check. Teste:
  `test_error_type_change_is_recorded_on_timeline`. O parâmetro `monitor` não é usado
  dentro da função; está na assinatura por simetria com as outras.
- Linhas 120–145: resolução por recuperação: status `resolved`, fim, motivo,
  evento e alerta `incident.resolved`.

@@trecho src/pulseops/services/incidents.py 148-201

- Linhas 148–181: encerramento pela operadora (pausa ou arquivamento). O status é
  `closed`, diferente de `resolved`: o texto deixa claro que **não** houve
  recuperação observada. Também gera alerta (`incident.closed`).
- Linhas 184–201: mudança de configuração com incidente aberto: um evento
  `config_changed` com os campos alterados e o novo limiar de recuperação. Não gera
  alerta (não é transição de estado).

**Falhas possíveis.** Um segundo incidente aberto violaria o índice único:
`IntegrityError` e rollback de tudo (o check fica `running` até a manutenção). Não
há caso conhecido que leve a isso, porque o monitor está travado.

## `src/pulseops/services/alerts.py`

**Finalidade.** O outbox de alertas: criação do evento e das entregas, reserva das
entregas vencidas e gravação do resultado de cada tentativa (RF06, ADR 0007).

**Dados.** Incidente e monitor (para montar o payload); configurações de
tentativas e espera; `SendResult` do notificador. **Relações.** Chamado por
`services/incidents.py` (criação) e `worker/runner.py` (reserva e gravação);
`SendResult` e `is_permanent_status` são usados por `notifications/webhook.py`.
**Testes.** `tests/integration/test_delivery.py` (13 funções, 17 casos).

@@trecho src/pulseops/services/alerts.py 22-89

- Linhas 22–23: a chave estável: `incident:42:opened`. `removeprefix` tira o
  `incident.` do tipo.
- Linhas 40–62: o payload. A URL do monitor vai **mascarada** (linha 48). As datas
  em ISO 8601 com fuso.
- Linhas 63–72: grava o evento e faz `flush` para ter o `id`.
- Linhas 74–88: uma entrega `pending` por destino **ativo**, para tentar já
  (`next_attempt_at=now`). Sem destino, o evento fica gravado sem entregas.

@@trecho src/pulseops/services/alerts.py 92-99

Espera exponencial com teto e classificação de status permanentes (volume 1, parte
G). `2 ** (attempt - 1)` é potência: 1, 2, 4, 8...

@@trecho src/pulseops/services/alerts.py 102-143

- Linhas 102–108: o que o worker precisa para enviar, copiado para um objeto
  simples (não do ORM), porque o envio acontece **depois** do commit.
- Linhas 116–127: busca as entregas vencidas com o evento e o destino (`JOIN`),
  travando só as entregas e pulando as já travadas (SQL na parte F do volume 1).
  Inclui `sending` com prazo vencido: reserva abandonada.
- Linhas 129–133: marca como `sending`, soma a tentativa e põe o fim da reserva em
  `next_attempt_at`.

@@trecho src/pulseops/services/alerts.py 146-204

- Linhas 146–152: o resultado do envio.
- Linhas 166–174: decide o desfecho **antes** de abrir a transação: sucesso vira
  `delivered`; erro permanente ou última tentativa vira `failed`; o resto volta a
  `pending`.
- Linhas 176–187: grava a tentativa.
- Linhas 188–193: valores a alterar; `pending` ganha o próximo horário com espera
  exponencial.
- Linhas 194–203: o `UPDATE` condicional (controle otimista; parte F do volume 1).
  Se a condição não bate, nenhuma linha muda, e a tentativa fica registrada só no
  histórico.

**Falhas possíveis.** Banco fora do ar durante a gravação: a exceção sobe para o
worker, a entrega fica `sending` e volta à fila quando a reserva vence (pode
duplicar, RF06.8).

## `src/pulseops/services/processing.py`

**Finalidade.** O ciclo de um check no banco: reservar, gravar o resultado e
aplicar as regras; também a manutenção (checks abandonados e retenção).

**Dados.** O horário atual (do relógio do worker); `CheckObservation` do
verificador; colunas do monitor. **Relações.** Chamado só por `worker/runner.py`;
usa `domain/health.py`, `services/incidents.py`. **Testes.**
`tests/integration/test_consistency.py`, `test_incident_lifecycle.py`,
`test_retention.py`, `test_first_slice.py`.

@@trecho src/pulseops/services/processing.py 33-47

- Linha 34: folga de 30 s além do timeout antes de considerar um check `running`
  como abandonado.
- Linhas 37–43: a execução reservada, como objeto simples (imutável), entregue à
  tarefa do check.
- Linhas 46–47: o `run_key`, com o horário em ISO e milissegundos.

@@trecho src/pulseops/services/processing.py 50-77

- Linhas 58–59: sem vagas, nem consulta o banco.
- Linha 60: o `NOT EXISTS` de check em andamento, montado como expressão reutilizável.
- Linhas 61–70: a consulta com `FOR UPDATE SKIP LOCKED` (SQL na parte F).
- Linhas 72–77: reserva cada monitor; `_reserve` pode devolver `None` (execução já
  existente).

@@trecho src/pulseops/services/processing.py 80-136

- Linhas 81–82: proteção para o mypy (a consulta já garante que não é nulo).
- Linhas 85–86: lê e limpa o pedido de "verificar agora".
- Linhas 88–103: retomada sem avalanche (CB4). Se o atraso passou de um intervalo,
  registra a lacuna, loga um aviso e agenda para agora.
- Linhas 105–119: o `INSERT ... ON CONFLICT DO NOTHING RETURNING id`.
- Linha 120: o próximo agendamento: agendado + intervalo, mas nunca menos de 1 s no
  futuro.
- Linhas 121–123: execução já existente: não devolve nada.
- Linhas 124–136: a execução reservada, com o alvo já interpretado.

@@trecho src/pulseops/services/processing.py 139-178

- Linha 146: `log_context` acrescenta monitor e `run_key` a todos os logs do bloco.
- Linhas 149–153: trava monitor e check; se o check já não está `running`, foi
  gravado antes: devolve `False` (reprocessamento).
- Linhas 155–162: conclui o check com os dados observados (explicação cortada em 300
  caracteres, o tamanho da coluna).
- Linhas 164–167: monitor pausado ou com outra versão: o check fica no histórico,
  mas não decide nada.
- Linha 169: `flush` grava o check antes de aplicar as regras (os eventos apontam
  para ele).

@@trecho src/pulseops/services/processing.py 181-236

- Linhas 184–195: monta o estado da regra a partir das colunas do monitor e da
  existência de incidente aberto, e aplica `HealthTracker`.
- Linhas 197–200: grava os contadores novos.
- Linhas 202–220: executa a ação decidida. Os `and open_incident is not None` são
  defesas: a regra só pede `UPDATE`/`RESOLVE` quando há incidente.
- Linhas 222–223: o motivo da saúde só muda se **não** for erro interno: um erro do
  PulseOps não apaga a explicação anterior.
- Linhas 224–236: se a saúde mudou, atualiza e registra em `health_changes`, com o
  check que causou. Teste: `test_every_health_change_is_explained`.

@@trecho src/pulseops/services/processing.py 239-279

- Linhas 239–264: checks abandonados viram `internal_error`. Linha 248 trava só os
  checks (`of=Check`) e pula os já travados. Linha 253: só os que passaram do
  timeout mais a folga. Não mexe em contadores: não é falha do alvo.
- Linhas 267–279: retenção em lotes (parte F). `getattr(result, "rowcount", 0)`
  lê o número de linhas apagadas de forma segura para a tipagem.

**Falhas possíveis.** Banco indisponível em qualquer função: exceção para o worker,
que registra e tenta de novo com espera crescente. Nenhum resultado é contado pela
metade (transação).

## `src/pulseops/services/queries.py`

**Finalidade.** Todas as consultas de leitura: lista de monitores, resumo do painel,
histórico paginado, incidentes, alertas, métricas e série do gráfico.

**Dados.** Parâmetros de janela e paginação vindos das rotas (já validados);
devolve objetos do ORM ou *dataclasses* de visualização. **Relações.** Chamado por
`web/api.py` e `web/pages.py`. **Testes.** `tests/integration/test_api_history.py`,
`test_metrics.py`, `test_dashboard.py`, `test_stopped_worker_makes_data_stale`.

@@trecho src/pulseops/services/queries.py 27-58

- Linhas 27–29: tamanho máximo e padrão de página; folga de 30 s para "desatualizado".
- Linhas 35–37: o cursor: `"data|id"` em base64 seguro para URL, sem o `=` final.
- Linhas 40–50: o caminho inverso. Repõe o `=` (linha 42), decodifica, separa,
  exige data com fuso (linhas 45–46) e transforma qualquer erro em
  `ValueError("cursor inválido")`, que a rota devolve como 422.
- Linhas 53–56: uma página genérica: itens e o cursor da próxima (ou `None`).
  `Page[T]` usa a sintaxe de genéricos do Python 3.12.

@@trecho src/pulseops/services/queries.py 61-122

- Linhas 61–73: estado do worker: o heartbeat mais recente, a idade em segundos e se
  está dentro do limite.
- Linhas 76–85: "desatualizado" (volume 1, H21). Monitor não ativo nunca está
  desatualizado. Sem check ainda, usa a data da última alteração.
- Linhas 90–94: lista ordenada por nome sem diferenciar maiúsculas.
- Linhas 97–122: o resumo do painel: contagem por saúde (os desatualizados à parte,
  porque a saúde deles não é confiável), incidentes abertos e entregas pendentes e
  falhas. A linha 119 é a que corrigiu o bug B2.

@@trecho src/pulseops/services/queries.py 128-185

- Linhas 128–151: histórico. Limita o tamanho da página (linha 139), filtra por
  janela e resultado, aplica o cursor (linhas 147–149) e pede `limit + 1` linhas.
- Linhas 154–177: incidentes com o monitor (`JOIN`). O filtro `closed` da interface
  significa "encerrados", isto é, resolvidos **ou** fechados (linha 164).
- Linhas 180–185: se veio mais que o limite, corta e gera o cursor do último item.

@@trecho src/pulseops/services/queries.py 188-275

- Linhas 188–206: *dataclasses* de visualização (entrega com destino e tentativas;
  evento com entregas; detalhe do incidente).
- Linhas 209–235: detalhe do incidente: o incidente com o monitor, os eventos em
  ordem e os alertas.
- Linhas 238–247: os alertas mais recentes.
- Linhas 250–275: monta as visões com **três** consultas no total (eventos,
  entregas, tentativas), em vez de uma consulta por entrega (o problema "N+1"). A
  linha 264 usa `or [0]` porque `IN ()` vazio não é SQL válido. As linhas 268–274
  agrupam em dicionários com `setdefault`.

@@trecho src/pulseops/services/queries.py 278-313

- Linhas 278–290: as últimas mudanças de saúde de um monitor.
- Linha 295: `RESPONSE_OUTCOMES`, os resultados que têm tempo de resposta HTTP:
  saudável, lento e status inesperado. É a base da latência média, do p95 e, desde
  a correção do bug B10, também do resumo do gráfico.
- Linhas 298–313: o resultado das métricas, com `None` onde não há base.

@@trecho src/pulseops/services/queries.py 316-421

- Linhas 320–325: a janela como tupla de condições, reutilizada nas consultas.
- Linhas 326–331: contagem por resultado (`GROUP BY`; SQL na parte F).
- Linhas 332–334: `N` exclui erros internos; disponíveis são saudáveis mais lentos.
- Linhas 336–346: contagem, média e p95 numa consulta só.
- Linhas 348–359: incidentes que **se sobrepõem** à janela (começaram antes do fim e
  não terminaram antes do início) e a soma das durações recortadas.
- Linhas 361–377: último check e lacunas que se sobrepõem à janela.
- Linhas 403–421: a série do gráfico: os 300 checks mais recentes da janela (sem
  erros internos), invertidos para ordem cronológica. `r[1] or 0` cobre duração
  nula.

**Falhas possíveis.** Cursor inválido: `ValueError`, 422 na API. Janela muito
grande: consultas mais lentas, mas limitadas pelos índices e pelo `limit`.
