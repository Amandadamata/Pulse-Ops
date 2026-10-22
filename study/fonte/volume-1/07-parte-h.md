# Parte H — Perguntas de entrevista

São 34 perguntas específicas sobre o PulseOps. As 15 primeiras são as obrigatórias
da especificação, na mesma ordem. Cada uma tem:

- **Resposta curta**: o que dizer em 20 a 40 segundos;
- **Explicação**: o raciocínio, para você entender e não decorar;
- **Onde ver**: arquivo, trecho ou teste para mostrar ou reler;
- **Aprofundamento provável**: a pergunta que costuma vir depois, com uma pista;
- **Limite honesto**: até onde você pode afirmar com segurança.

Uma regra geral para todas: o projeto foi escrito com o Claude Code a partir da sua
especificação (README, seção "Como este projeto foi feito"). Diga isso se
perguntarem, e responda sobre o código como alguém que o estudou e consegue
explicá-lo, não como quem o digitou linha por linha.

## H1. Por que FastAPI?

**Resposta curta.** A especificação pedia uma API JSON e um painel no mesmo
processo, com validação de entrada forte e código assíncrono. O FastAPI dá as três
coisas: rotas assíncronas, validação com Pydantic a partir dos tipos e injeção de
dependências pelo `Depends`.

**Explicação.** O worker e a API compartilham os mesmos serviços assíncronos
(`services/*.py`, com `AsyncSession`). Um framework síncrono obrigaria a duplicar
o acesso a banco ou a rodar código assíncrono dentro de threads. O Pydantic faz a
validação de formato (`web/schemas.py`, por exemplo `extra="forbid"` recusa campos
desconhecidos) e devolve 422 com a lista de erros. As dependências (`Db`, `State`,
`ApiAuth` em `web/deps.py`) deixam as rotas curtas e trocáveis nos testes.

**Onde ver.** `src/pulseops/web/api.py`, `src/pulseops/web/deps.py`,
`src/pulseops/web/schemas.py`; teste `test_unknown_fields_and_methods_rejected`.

**Aprofundamento provável.** "E Django?" Pista: Django traz ORM, admin e
autenticação prontos, mas o ORM dele é outro (a especificação pedia SQLAlchemy e
Alembic) e o suporte assíncrono no acesso a banco é mais recente. Para um serviço
pequeno de API, FastAPI + SQLAlchemy é uma combinação comum nas vagas pesquisadas.

**Limite honesto.** A escolha da stack veio da especificação, não de uma
comparação feita por você em produção. Não diga que o FastAPI é "mais rápido" sem
ter medido.

## H2. Onde há orientação a objetos?

**Resposta curta.** Em quatro formas: classes com estado e comportamento (`Worker`,
`HttpChecker`, `WebhookNotifier`, `HealthTracker`); herança onde uma biblioteca
exige (`GuardedNetworkBackend` herda de `httpcore.AsyncNetworkBackend`, os modelos
herdam de `Base`); protocolos (`Clock`, `Checker`, `Notifier`, `Resolver`); e
objetos de valor imutáveis com `@dataclass(frozen=True)` (`ClaimedRun`,
`Thresholds`, `Decision`).

**Explicação.** `Worker` guarda as vagas em andamento (`_inflight`) e expõe
operações (`dispatch_checks`, `run`). `HealthTracker` encapsula a regra de saúde:
recebe o estado anterior e uma observação e devolve uma `Decision`, sem efeito
colateral. Herança é usada pouco e só quando a biblioteca pede um tipo base.
O resto é composição.

**Onde ver.** `src/pulseops/worker/runner.py` (linhas 33–54),
`src/pulseops/domain/health.py`, `src/pulseops/security/transport.py` (linha 33),
`src/pulseops/clock.py`.

**Aprofundamento provável.** "O que é um Protocol?" Pista: é tipagem estrutural.
Qualquer classe com o método `now()` e `monotonic()` serve como `Clock`, sem herdar
de nada. É o que permite passar o `FakeClock` nos testes.

**Limite honesto.** Não há padrões elaborados (fábricas abstratas, repositórios
genéricos). Não diga que o projeto "aplica todos os princípios SOLID".

## H3. Por que composição?

**Resposta curta.** O `Worker` não cria o verificador, o notificador nem o relógio:
recebe prontos no construtor. Assim, cada peça pode ser trocada (nos testes, por
dublês) e testada separadamente.

**Explicação.** Com herança, um `Worker` que precisasse de outro tipo de
verificador viraria uma subclasse nova. Com composição, basta passar outro objeto
que siga o protocolo `Checker`. Os testes passam um `HttpChecker` com
`httpx.MockTransport` e um `FakeClock`. A montagem real fica num lugar só:
`src/pulseops/worker/__main__.py`.

**Onde ver.** `src/pulseops/worker/runner.py` linhas 34–48;
`src/pulseops/worker/__main__.py` (montagem); `tests/support.py` (`ScriptedTarget`).

**Aprofundamento provável.** "Isso é injeção de dependências?" Pista: sim, feita à
mão, pelo construtor. Na API, o FastAPI faz o mesmo com `Depends`.

**Limite honesto.** Não há contêiner de injeção de dependências. É composição
simples, o que é adequado ao tamanho do projeto.

## H4. O que acontece quando o worker reinicia?

**Resposta curta.** Nada se perde, porque o estado mora no banco. Ao subir, o worker
pega o advisory lock, volta a reservar execuções vencidas, marca como
`internal_error` os checks que ficaram `running` e registra uma **lacuna de
cobertura** se ficou mais de um intervalo sem verificar. Um incidente aberto
continua aberto e a contagem segue.

**Explicação.** Os contadores (`consecutive_failures`...) ficam na tabela
`monitors`, não na memória. `mark_abandoned_runs` resolve os checks interrompidos
sem contar falha do alvo (não foi o alvo que falhou, foi o worker). Em `_reserve`,
se `now - scheduled_at > interval`, o PulseOps não tenta "recuperar" todos os
checks perdidos (seria uma avalanche): grava um `CoverageGap` e agenda para agora.
Entregas que estavam `sending` voltam a ser elegíveis quando a reserva vence.

**Onde ver.** `src/pulseops/services/processing.py` linhas 88–103 e 239–264;
testes `test_restart_with_open_incident_continues_and_records_gap` e
`test_interrupted_run_becomes_internal_error_not_failure`.

**Aprofundamento provável.** "E se dois workers subirem?" Pista: H16 e o
`pg_try_advisory_lock`; o segundo sai com código 1 (`test_second_worker_is_refused`).

**Limite honesto.** Reinício foi testado com relógio simulado e na demonstração com
Docker. Não houve teste com o processo morto à força (`kill -9`) no meio de uma
gravação, embora a transação garanta que ela não fique pela metade.

## H5. Como impedir incidentes duplicados?

**Resposta curta.** Em duas camadas: a regra só manda **abrir** quando não há
incidente aberto (senão manda **atualizar**), e o banco tem um índice único parcial
que proíbe um segundo incidente `open` para o mesmo monitor.

**Explicação.** `record_result` trava o monitor (`FOR UPDATE`) e lê o incidente
aberto também com `FOR UPDATE`, então duas gravações simultâneas do mesmo monitor
acontecem uma depois da outra. Mesmo que um bug escapasse disso, o índice
`uq_incidents_one_open_per_monitor` faria o `INSERT` falhar, a transação inteira
seria desfeita e nenhum alerta duplicado sairia.

**Onde ver.** `src/pulseops/db/models.py` linhas 182–188;
`src/pulseops/services/processing.py` linhas 149 e 184; testes
`test_database_rejects_second_open_incident` e
`test_mandatory_example_more_failures_update_the_same_incident`.

**Aprofundamento provável.** "E alerta duplicado?" Pista: `alert_events.event_key`
é único (`incident:{id}:opened`), e há uma entrega por par (evento, destino).

**Limite honesto.** "Sem duplicatas nos cenários testados" é o que dá para afirmar.
Não houve teste de carga concorrente com vários processos gravando ao mesmo tempo,
porque o projeto só admite um worker.

## H6. Por que uma sessão SQLAlchemy não deve ser compartilhada entre tarefas?

**Resposta curta.** Uma `AsyncSession` representa **uma** conversa com o banco,
em uma conexão e uma transação. Ela não é segura para uso simultâneo: duas tarefas
`asyncio` usando a mesma sessão misturariam comandos na mesma transação e o
SQLAlchemy levanta erro. Cada unidade de trabalho abre a sua.

**Explicação.** No worker, cada check roda numa tarefa própria
(`asyncio.create_task(self._run_one(run))`), e `claim_due_runs` e `record_result`
recebem a **fábrica** de sessões (`SessionFactory`), não uma sessão. Cada chamada
faz `async with sessions.begin() as session:`, com começo e fim claros. Além da
segurança, isso mantém as transações curtas: se uma tarefa segurasse a sessão
durante a requisição HTTP, seguraria travas.

**Onde ver.** `src/pulseops/worker/runner.py` linhas 67–75 e 102–122;
`src/pulseops/services/processing.py` (todas as funções recebem
`sessions: SessionFactory`); `src/pulseops/db/session.py`.

**Aprofundamento provável.** "E na API?" Pista: `get_db` abre uma sessão por
requisição HTTP, e uma requisição é tratada por uma tarefa só.

**Limite honesto.** O PulseOps nunca tentou compartilhar sessões, então você não
viu o erro na prática. Fale do motivo, não de uma experiência.

## H7. Por que não executar tudo na rota?

**Resposta curta.** Porque checks são periódicos e alertas precisam de
retentativas: isso precisa continuar mesmo sem ninguém acessar a API. A rota só
grava a intenção (por exemplo, "verificar agora" põe `check_requested = true`), e
o worker faz o trabalho.

**Explicação.** Se a rota fizesse a requisição HTTP ao alvo, a resposta da API
demoraria até o timeout do alvo (30 s). Se fizesse com `BackgroundTasks` do
FastAPI, o trabalho morreria com o processo e não teria retentativa (a
especificação proíbe isso para trabalho durável). Separar também isola falhas: um
alvo lento não deixa o painel lento.

**Onde ver.** `src/pulseops/services/monitors.py` (`request_check_now`, linhas
228–236); `docs/decisoes/0002-api-e-worker-separados.md`; teste
`test_check_now_marks_next_check_as_manual`.

**Aprofundamento provável.** "Como a API sabe que o worker está vivo?" Pista: H21,
heartbeat.

**Limite honesto.** A API e o worker compartilham o banco; não há fila de
mensagens. Para este volume, o banco como fila é suficiente, e você pode dizer por
quê (H14).

## H8. Como funciona a transação?

**Resposta curta.** `async with sessions.begin() as session:` abre a transação;
se o bloco termina normalmente, faz `COMMIT`; se uma exceção escapa, faz
`ROLLBACK`. Tudo que está dentro vale junto ou não vale.

**Explicação.** O exemplo central é `record_result`: concluir o check, atualizar os
contadores, abrir o incidente, gravar a mudança de saúde e criar o alerta e as
entregas acontecem numa transação só. Se o banco cair no meio, nada fica pela
metade, e o check continua `running` até a manutenção marcá-lo como interrompido.
A requisição HTTP fica **fora** de qualquer transação (ADR 0003).

**Onde ver.** Parte F deste guia; `src/pulseops/services/processing.py` linhas
139–178; testes `test_outbox_event_is_atomic_with_incident` e
`test_database_failure_while_recording_does_not_count_as_target_failure`.

**Aprofundamento provável.** "Qual nível de isolamento?" Pista: o padrão do
PostgreSQL, *Read Committed*. O PulseOps não depende de um nível mais forte porque
trava explicitamente as linhas que disputa (`FOR UPDATE`).

**Limite honesto.** O isolamento não foi alterado nem testado em outros níveis.

## H9. Qual a diferença entre lentidão e falha?

**Resposta curta.** Lento é quando o alvo respondeu com um status aceito, mas acima
do limite de latência. Falha é quando não respondeu certo: timeout, erro de conexão,
erro TLS ou status fora da lista. Lento deixa o monitor **degradado**, mas não
conta para abrir incidente; falha conta.

**Explicação.** Se lentidão abrisse incidente, um pico de carga geraria alertas de
"fora do ar" para um serviço no ar. O PulseOps também conta uma resposta lenta como
**sucesso** para a recuperação: um serviço que voltou, mas lento, está disponível.
O timeout é falha porque, para quem usa, "não respondeu".

**Onde ver.** `src/pulseops/domain/outcomes.py`;
`docs/decisoes/0004-lentidao-nao-abre-incidente.md`; testes
`test_slow_is_degraded_but_not_a_failure` e
`test_slow_response_counts_towards_recovery`.

**Aprofundamento provável.** "Como mede o tempo?" Pista: com o relógio
**monotônico** (`clock.monotonic()`), que não volta para trás quando o relógio do
sistema é ajustado.

**Limite honesto.** O tempo medido inclui DNS, conexão e TLS, porque é o que o
usuário sente. Não é só o tempo de processamento do servidor.

## H10. Como calcular métricas sem dados?

**Resposta curta.** Mostrando "N/A", nunca 0% nem 100%. Sem checks na janela, a
proporção não tem denominador; inventar um número seria mentir.

**Explicação.** `ratio(part, total)` devolve `None` quando `total <= 0`, e o painel
mostra `None` como "N/A". O denominador também é escolhido com cuidado: checks
`internal_error` (falha do próprio PulseOps) saem da conta, porque não dizem nada
sobre o alvo. Latência média e p95 usam só checks que receberam resposta HTTP
(`healthy`, `slow` e `unexpected_status`); timeout e erro de conexão ficam fora. Lacunas de
cobertura aparecem ao lado das métricas.

**Onde ver.** `src/pulseops/domain/metrics.py` linhas 22–26;
`src/pulseops/services/queries.py` (`monitor_metrics`); testes
`test_no_data_returns_na_not_zero_or_hundred` e
`test_paused_period_produces_no_samples`.

**Aprofundamento provável.** "Disponibilidade de 99,9% com 3 checks?" Pista: o
painel mostra o número de amostras junto da proporção; poucas amostras não
sustentam conclusão nenhuma.

**Limite honesto.** As métricas são proporções de **checks**, não de tempo. Um
intervalo de 60 s não vê uma queda de 20 s entre dois checks.

## H11. O que ocorre se o webhook cair?

**Resposta curta.** As verificações continuam normalmente. A entrega falha, é
registrada como tentativa e volta para a fila com espera exponencial, até dar certo
ou atingir o máximo de tentativas.

**Explicação.** Alertas são entregues por outro laço do worker
(`run_deliveries_once`), em tarefas separadas, com timeout próprio. Um destino
lento ou fora do ar não ocupa as vagas dos checks. Cada tentativa vira uma linha em
`delivery_attempts`, visível no painel de notificações. Os passos 9, 10 e 11 da
demonstração mostram exatamente isso: receptor fora, checks continuando, e a
entrega acontecendo quando o receptor volta.

**Onde ver.** `src/pulseops/worker/runner.py` linhas 126–159;
`src/pulseops/services/alerts.py`; testes `test_slow_webhook_does_not_block_checks`
e `test_retries_with_capped_exponential_backoff`.

**Aprofundamento provável.** "E se ficar fora para sempre?" Pista: depois de
`webhook_max_attempts` (6 por padrão) a entrega fica `failed`, e isso aparece no
painel. Não há segundo canal de alerta.

**Limite honesto.** Não existe alerta sobre "o alerta falhou". A operadora só vê
olhando o painel.

## H12. Por que a entrega pode se repetir?

**Resposta curta.** Porque a garantia é "pelo menos uma vez". Se o worker morrer
depois de o destino receber o POST e antes de gravar o sucesso, a reserva vence e
o envio é feito de novo. O `event_id` estável permite ao destino descartar a
repetição.

**Explicação.** Não há transação que englobe o banco do PulseOps e o servidor do
destino. Um dos dois lados sempre pode falhar entre "enviei" e "anotei que enviei".
Escolher "no máximo uma vez" perderia alertas; escolher "pelo menos uma vez" e
deduplicar no destino é o padrão usado por serviços de webhook.

**Onde ver.** `src/pulseops/services/alerts.py` linhas 111–143 (reserva com
lease); `lab/receiver.py` (deduplicação no receptor do laboratório); teste
`test_expired_lease_is_retried_which_may_duplicate`; RF06.8 em
`docs/requisitos.md`.

**Aprofundamento provável.** "Como evitar que uma gravação atrasada sobrescreva uma
tentativa nova?" Pista: o `UPDATE` só vale se `status = 'sending'` e
`attempt_count` for o da própria tentativa (parte F).

**Limite honesto.** A deduplicação depende do destino. O PulseOps não pode
garanti-la sozinho.

## H13. Como o projeto trata SSRF?

**Resposta curta.** Valida o texto da URL no cadastro (esquema, porta, credenciais,
formas estranhas de IP) e, principalmente, valida o IP **na hora de cada conexão**,
conectando no mesmo IP validado. Isso fecha a porta do DNS rebinding.
Redirecionamentos não são seguidos e o proxy do ambiente é ignorado.

**Explicação.** Ver a parte G. O ponto que costuma impressionar é o
`GuardedNetworkBackend`: o HTTPX chama `connect_tcp(host, porta)`, o PulseOps
resolve o nome, recusa se **qualquer** IP for proibido e conecta no IP. O header
`Host` e o SNI continuam com o nome original, então HTTPS funciona.

**Onde ver.** `src/pulseops/security/url_policy.py`,
`src/pulseops/security/transport.py`; testes
`test_rebinding_is_checked_at_connect_time`,
`test_mixed_public_and_private_answers_are_refused`, `test_blocked_urls`.

**Aprofundamento provável.** "E se o HTTPX mudar por dentro?" Pista: o projeto troca
o pool interno (`transport._pool`), um detalhe interno da versão 0.28. O teste
`test_connects_to_validated_ip_and_keeps_host_header` quebra se isso mudar; está no
modelo de ameaças.

**Limite honesto.** A proteção está na aplicação. Não há firewall de saída
configurado pelo projeto, que seria a segunda barreira numa instalação séria.

## H14. Qual a limitação de escala?

**Resposta curta.** Um worker por banco, com até 20 checks simultâneos por padrão
e tick de 1 s. Foi medido: 200 monitores a cada 10 s numa máquina de 4 CPUs, com
99,5% dos checks esperados feitos e atraso mediano de 0,64 s.

**Explicação.** O advisory lock impede um segundo worker de propósito: assim não é
preciso coordenar quem verifica o quê. Para escalar, seria preciso permitir vários
workers (a reserva com `SKIP LOCKED` já está pronta para isso, mas o heartbeat, a
manutenção e a retenção supõem um só) e, mais tarde, particionar a tabela `checks`
por data.

**Onde ver.** `docs/evidencias/ensaio-de-carga.md`;
`src/pulseops/worker/__main__.py` linhas 24–32; ADR 0002.

**Aprofundamento provável.** "Qual seria o gargalo primeiro?" Pista: com alvos
lentos, as vagas de concorrência (cada check ocupa uma vaga até o timeout). Com
muitos monitores, o volume de linhas em `checks`.

**Limite honesto.** Não houve teste com mais de 200 monitores nem com alvos
reais na internet (o ensaio usou o alvo do laboratório). Não fale em
"milhares de monitores".

## H15. O que você mudaria numa versão comercial?

**Resposta curta.** Vários workers com alta disponibilidade, contas e papéis,
limite de tentativas de login, assinatura HMAC nos webhooks, mais canais de alerta
(e-mail, Slack), autenticação nos alvos, verificações de várias regiões e um
firewall de saída.

**Explicação.** Cada item vem de uma limitação documentada (parte G). A ordem que
você pode defender: primeiro segurança (limite de login, HMAC), porque são riscos
já identificados; depois disponibilidade (vários workers), porque hoje uma queda da
máquina silencia tudo; por último funcionalidades.

**Onde ver.** README, seção de limitações; `docs/modelo-de-ameacas.md`, seção
"Limitações remanescentes".

**Aprofundamento provável.** "Como você monitoraria o próprio monitor?" Pista: um
*dead man's switch* externo (o modelo passivo do Healthchecks): o PulseOps manda
um sinal periódico para fora, e o silêncio vira alerta.

**Limite honesto.** Nada disso está implementado. É roadmap, e deve ser dito como
roadmap.

## H16. Por que API e worker em processos separados?

**Resposta curta.** Para que um não derrube o outro. Se o painel estiver sob
carga, os checks continuam; se o worker travar, o painel mostra "worker sem sinal".
Cada processo pode ser reiniciado sozinho.

**Explicação.** No `compose.yaml` são dois serviços com a mesma imagem e comandos
diferentes. A comunicação é só pelo banco. Por isso a API consegue mostrar que o
worker parou: ela lê o último heartbeat.

**Onde ver.** `compose.yaml`; `docs/decisoes/0002-api-e-worker-separados.md`;
teste `test_stopped_worker_makes_data_stale`.

**Aprofundamento provável.** "Por que não Celery?" Pista: Celery exige um broker
(Redis ou RabbitMQ), mais uma peça para operar. Para um worker e agendamento
simples, o banco como fila resolve.

**Limite honesto.** Separar processos não dá alta disponibilidade: os dois rodam
na mesma máquina.

## H17. Por que async e não threads?

**Resposta curta.** O trabalho do worker é quase todo **espera** (rede e banco).
Com `asyncio`, uma thread só alterna entre centenas de esperas sem o custo de criar
uma thread para cada uma.

**Explicação.** Cada check é uma corrotina que passa quase todo o tempo em `await`
(conexão, resposta, gravação). O event loop executa outra enquanto isso. O limite
de simultaneidade é explícito: no máximo `worker_concurrency` tarefas em
`_inflight`. A resolução DNS (`getaddrinfo`), que é bloqueante, vai para uma thread
do próprio loop (`loop.getaddrinfo`).

**Onde ver.** `src/pulseops/worker/runner.py`; `src/pulseops/security/transport.py`
linhas 25–30; ADR 0003.

**Aprofundamento provável.** "O que acontece se alguém escrever código bloqueante
numa corrotina?" Pista: trava o loop inteiro, todos os checks param. Por isso o
corpo da resposta não é lido e nada pesado roda no laço.

**Limite honesto.** Async não ajuda trabalho de CPU. O PulseOps não tem esse tipo de
trabalho, então não houve necessidade de processos extras.

## H18. Como o worker sabe o que verificar e quando?

**Resposta curta.** Cada monitor tem `next_run_at`. A cada tick, o worker reserva
os monitores ativos com `next_run_at <= agora` e sem check em andamento, grava o
check como `running` e avança `next_run_at` em um intervalo.

**Explicação.** O agendamento fica no banco, não num temporizador em memória. Por
isso sobrevive a reinícios. O índice parcial `ix_monitors_due` torna a consulta
barata. O novo `next_run_at` é calculado a partir do horário **agendado**, não do
horário em que o check terminou, para o ritmo não "escorregar".

**Onde ver.** `src/pulseops/services/processing.py` linhas 50–136; parte F, "Reservar
monitores vencidos"; teste `test_scheduled_time_and_observed_time_are_both_recorded`.

**Aprofundamento provável.** "E se o check demorar mais que o intervalo?" Pista:
não pode, por constraint (`timeout_seconds < interval_seconds`), e a reserva pula
monitores com check em andamento.

**Limite honesto.** A precisão é de cerca de 1 s (o tick).

## H19. O que é o run_key?

**Resposta curta.** A identidade de uma execução agendada:
`"{monitor_id}:{horário agendado}"`. É única no banco, então a mesma execução não
vira dois checks, mesmo que seja reservada duas vezes.

**Explicação.** O `INSERT ... ON CONFLICT (run_key) DO NOTHING RETURNING id`
insere ou não faz nada; se não inseriu, não volta id, e o worker não executa. É uma
forma de **idempotência**: repetir a operação dá o mesmo resultado que fazê-la uma
vez.

**Onde ver.** `src/pulseops/services/processing.py` linhas 46–47 e 105–123; teste
`test_same_run_identity_cannot_be_reserved_twice`.

**Aprofundamento provável.** "E gravar o resultado duas vezes?" Pista:
`record_result` só grava se o check ainda está `running`; a segunda chamada
devolve `False` (`test_reprocessed_result_is_ignored`).

**Limite honesto.** Dois cliques em "verificar agora" antes de o worker reservar
viram um único check, porque cada clique só antecipa `next_run_at`. Isso evita
fila de checks manuais, mas não foi pedido explicitamente pela especificação.

## H20. Como impedir que um check comece antes do anterior terminar?

**Resposta curta.** A reserva pula monitores que já têm um check `running`, e o
banco tem um índice único parcial que proíbe dois checks `running` no mesmo
monitor.

**Explicação.** É o mesmo padrão de H5 aplicado aos checks. O "verificar agora"
também passa por esse controle: se houver um check em andamento, o manual espera
ele terminar (CB5).

**Onde ver.** `src/pulseops/db/models.py` linhas 147–153; testes
`test_overlapping_check_is_not_started` e `test_database_rejects_second_running_check`.

**Aprofundamento provável.** "Por que as duas coisas?" Pista: a consulta evita o
trabalho; o índice garante a regra mesmo se a consulta tiver um bug.

**Limite honesto.** Nada a ressalvar além do que já foi dito: é garantido pelo
banco.

## H21. Como o painel mostra que o worker parou?

**Resposta curta.** O worker grava um heartbeat periódico. Se o último for mais
antigo que o limite, o painel mostra "Worker sem sinal" e marca todos os monitores
ativos como **desatualizados**. Um monitor também fica desatualizado se o último
check for velho demais, mesmo com o worker vivo.

**Explicação.** Sem isso, um worker parado deixaria o painel congelado em "saudável",
o pior tipo de erro para um monitor. O limite por monitor é
`2 × intervalo + timeout + folga`.

**Onde ver.** `src/pulseops/services/queries.py` linhas 68–87 (`worker_status`,
`is_stale`); `src/pulseops/worker/runner.py` linhas 163–176; testes
`test_stopped_worker_makes_data_stale` e
`test_old_last_check_is_stale_even_with_worker_alive`.

**Aprofundamento provável.** "E se o banco cair?" Pista: a API responde 503 em
`/health/ready`, e o painel não carrega
(`test_ready_returns_503_when_database_is_down`).

**Limite honesto.** Ninguém é **avisado** de que o worker parou; só quem abre o
painel vê.

## H22. Como testar tempo sem `sleep`?

**Resposta curta.** O código recebe um `Clock` e os testes passam um `FakeClock`,
que só anda quando o teste manda. "Esperar 3 intervalos" vira
`clock.advance(...)`.

**Explicação.** Testes com `sleep` são lentos e instáveis (passam ou falham
dependendo da carga da máquina). Com o relógio injetado, os 251 testes rodam em
menos de um minuto e dão sempre o mesmo resultado. A lentidão do alvo simulado
também é feita avançando o relógio.

**Onde ver.** `src/pulseops/clock.py`; `tests/support.py` linhas 15–30.

**Aprofundamento provável.** "Algum teste usa tempo real?" Pista: o teste do B8
(`test_dispatcher_refills_freed_slots_without_waiting_a_tick`) mede com tempo
real, porque o bug era justamente de espera.

**Limite honesto.** O relógio falso não pega problemas de fuso ou de ajuste de
relógio do sistema; para isso há os testes de fuso horário e o uso do relógio
monotônico.

## H23. Por que PostgreSQL de verdade nos testes?

**Resposta curta.** Porque as garantias mais importantes estão no banco: `SKIP
LOCKED`, advisory lock, índices parciais, `percentile_disc`, `JSONB`. O SQLite não
tem a maioria disso; um teste nele não provaria nada.

**Explicação.** Ver a tabela da parte G. O custo é precisar do container
`pulseops-testdb`; o CI sobe o PostgreSQL 16 como serviço.

**Onde ver.** `tests/conftest.py`; `.github/workflows/ci.yml`.

**Aprofundamento provável.** "Como isolar os testes?" Pista: `TRUNCATE` de todas as
tabelas antes de cada teste.

**Limite honesto.** Os testes não rodam em paralelo (`pytest -n`), porque
compartilham o mesmo banco.

## H24. Como a senha é guardada?

**Resposta curta.** Como hash Argon2id, com os parâmetros padrão da biblioteca
argon2-cffi. A senha em si nunca é gravada.

**Explicação.** Argon2id é lento e usa bastante memória de propósito, o que torna
caro testar muitas senhas mesmo com GPU. A conferência roda até para usuário
inexistente, para não revelar pelo tempo quais usuários existem. O bug B4 mostrou
que um hash corrompido podia levantar uma exceção inesperada; agora ela é tratada
como "senha não confere".

**Onde ver.** `src/pulseops/security/passwords.py`;
`src/pulseops/services/auth.py` linhas 33–38; testes de `tests/unit/test_passwords.py`.

**Aprofundamento provável.** "E se os parâmetros ficarem fracos com o tempo?" Pista:
o argon2-cffi oferece `check_needs_rehash`; o PulseOps **não** usa. Seria uma
melhoria.

**Limite honesto.** Não há limite de tentativas de login.

## H25. Como funciona a proteção contra CSRF?

**Resposta curta.** Toda ação que altera dados exige um token secreto da sessão,
no formulário ou no header `X-CSRF-Token`. Um site de terceiros consegue fazer o
navegador enviar o cookie, mas não consegue ler o token.

**Explicação.** Somado a isso, o cookie de sessão é `SameSite=Lax`. O login também tem
token próprio, num cookie separado, para impedir um "login forçado" na conta do
atacante. A comparação é em tempo constante (`hmac.compare_digest`).

**Onde ver.** `src/pulseops/web/deps.py` linhas 80–95; testes
`test_api_mutation_requires_csrf_header`, `test_form_action_requires_csrf_field`,
`test_login_form_requires_its_csrf_cookie`.

**Aprofundamento provável.** "Se já há SameSite, por que o token?" Pista: defesa
em profundidade; navegadores antigos e alguns cenários (subdomínios) não respeitam
`SameSite` igual.

**Limite honesto.** Não foi feito um teste com navegador e um site malicioso de
verdade; os testes enviam as requisições diretamente.

## H26. Como o p95 é calculado?

**Resposta curta.** Pelo método *nearest-rank*: ordena as latências e pega a da
posição `ceil(0,95 × n)`. No banco, `percentile_disc(0.95)`, que dá o mesmo valor.

**Explicação.** Existem vários métodos de percentil (alguns interpolam entre dois
valores). O *nearest-rank* sempre devolve uma latência que realmente aconteceu. Um
teste compara o SQL com a função Python para tamanhos de 1 a 137 amostras.

**Onde ver.** `src/pulseops/domain/metrics.py` linhas 8–19;
`docs/decisoes/0011-metricas-e-percentil.md`; teste
`test_sql_percentile_matches_nearest_rank`.

**Aprofundamento provável.** "Com 10 amostras, o p95 é o quê?" Pista:
`ceil(9,5) = 10`, o maior valor. Com poucas amostras, o p95 é o máximo.

**Limite honesto.** Nada além do método documentado.

## H27. Por que paginação por cursor?

**Resposta curta.** Porque o histórico cresce enquanto a pessoa navega. Com
`OFFSET`, itens novos empurram os antigos e há repetição; com o cursor
`(started_at, id)`, a próxima página começa exatamente depois do último item visto.

**Explicação.** Ver a parte F. O `id` entra como desempate porque dois checks podem
ter o mesmo `started_at`.

**Onde ver.** `src/pulseops/services/queries.py` (`encode_cursor`, `list_checks`);
teste `test_cursor_pagination_is_stable_and_complete`.

**Aprofundamento provável.** "Dá para pular para a página 50?" Pista: não; cursor
só anda para a frente. É uma troca consciente.

**Limite honesto.** Nada a ressalvar.

## H28. O que acontece se a configuração mudar durante um check?

**Resposta curta.** O resultado fica no histórico, mas não decide nada. Cada check
guarda o `config_version` da reserva; se o monitor tiver outra versão quando o
resultado chega, o efeito é descartado.

**Explicação.** Editar, pausar, retomar e arquivar incrementam a versão e zeram os
contadores. O bug B6 era a pausa e a retomada não incrementarem a versão.

**Onde ver.** `src/pulseops/services/processing.py` linhas 164–167;
`src/pulseops/services/monitors.py` linhas 171–177; testes
`test_result_of_run_started_before_config_change_does_not_count` e
`test_config_change_resets_counters_and_keeps_incident`.

**Aprofundamento provável.** "E o incidente aberto?" Pista: continua aberto e ganha
um evento `config_changed` na linha do tempo.

**Limite honesto.** O nome `config_version` hoje significa "versão da contagem";
está documentado em RF03.5.

## H29. Qual foi o bug mais interessante?

**Resposta curta.** O B8: com mais checks vencidos que vagas, o worker dormia o
tick inteiro mesmo com vagas abrindo, e a vazão ficava em cerca de 20 checks por
segundo. Nenhum teste funcional pegou; o ensaio de carga mostrou atraso mediano de
7,8 s.

**Explicação.** A correção: depois de preencher todas as vagas pedidas, o laço
espera um **evento** de "vaga liberada", com o tick como limite. A primeira
tentativa de correção estava errada (usava o número de tarefas em andamento); a
condição certa é "reservei menos do que pedi". Depois da correção, a mediana caiu
para 0,64 s.

**Onde ver.** `docs/registro-de-bugs.md` (B8); `src/pulseops/worker/runner.py`
linhas 77–90; `docs/evidencias/ensaio-de-carga-antes-B8.md` e
`docs/evidencias/ensaio-de-carga.md`.

**Aprofundamento provável.** "Como você teria achado sem o ensaio?" Pista: talvez
não acharia; essa é a lição.

**Limite honesto.** O ensaio é local. Não diga "otimizei a performance em produção".

## H30. Como as migrações são validadas?

**Resposta curta.** Um teste aplica a migração num banco vazio e compara o
resultado com os modelos (`compare_metadata`); outro faz `downgrade` até o fim e
`upgrade` de novo. O CI repete o ciclo.

**Explicação.** Ver a parte F. O bug B1 (coluna no modelo e não na migração) foi
pego por esse teste.

**Onde ver.** `tests/integration/test_migrations.py`; `.github/workflows/ci.yml`.

**Aprofundamento provável.** "Como renomear uma coluna sem parar o sistema?" Pista:
em etapas (criar a nova, copiar, passar a usar, remover a antiga). O projeto não
passou por isso.

**Limite honesto.** Há uma migração só. Evolução de esquema com dados não foi
exercitada.

## H31. O que é o padrão outbox?

**Resposta curta.** Gravar a intenção de enviar uma mensagem **na mesma transação**
da mudança que a causou, e enviar depois por um processo separado. Assim a
mensagem nunca se perde e nunca é enviada para uma mudança que foi desfeita.

**Explicação.** Ver a parte G. No PulseOps, `enqueue_incident_alert` é chamada
dentro da transação de `record_result` e não faz commit sozinha (o comentário diz
"quem chama decide").

**Onde ver.** `src/pulseops/services/alerts.py` linhas 26–89;
`docs/decisoes/0007-outbox-e-entrega-pelo-menos-uma-vez.md`; teste
`test_outbox_event_is_atomic_with_incident`.

**Aprofundamento provável.** "E sem destino cadastrado?" Pista: o evento é gravado
mesmo assim, sem entregas (`test_without_destination_event_is_still_recorded`).

**Limite honesto.** Nada a ressalvar além da duplicidade (H12).

## H32. Como os logs evitam vazar segredos?

**Resposta curta.** Os logs são JSON, e antes de escrever cada campo o formatador
mascara chaves sensíveis (senha, token, cookie...) e tira de URLs a *query string*
e as credenciais.

**Explicação.** Uma URL monitorada pode ter `?api_key=...`. O payload do webhook
também leva a URL mascarada. As explicações gravadas nos checks nunca contêm a URL
(`test_explanation_never_contains_url_or_query`).

**Onde ver.** `src/pulseops/logs.py` linhas 14–32; testes de
`tests/unit/test_logging.py`.

**Aprofundamento provável.** "E o caminho da URL?" Pista: o caminho fica; se houver
segredo no caminho (`/token/abc`), ele aparece. É uma limitação.

**Limite honesto.** A máscara funciona por padrões; um segredo num formato
inesperado pode passar.

## H33. Como o CI está configurado?

**Resposta curta.** GitHub Actions com dois jobs: `qualidade` (ruff, mypy,
migrações para cima e para baixo, pytest com cobertura mínima, conferência de
referências dos documentos e auditoria de dependências) e `docker` (constrói a
imagem e roda a demonstração inteira). O token do workflow só tem permissão de
leitura.

**Explicação.** `permissions: contents: read` segue o princípio do menor
privilégio: se uma dependência maliciosa rodasse no CI, não conseguiria escrever no
repositório. O job `docker` prova que a instalação pelo Compose funciona do zero a
cada push.

**Onde ver.** `.github/workflows/ci.yml`.

**Aprofundamento provável.** "As actions estão fixadas por hash?" Pista: não, por
versão (`@v4`, `@v6`). Fixar por hash do commit seria mais seguro.

**Limite honesto.** Só afirme que o CI passa com o link de uma execução verde no
GitHub. Sem isso, diga que ele foi validado localmente com `actionlint`.

## H34. Qual foi o papel da IA no projeto?

**Resposta curta.** O código, os testes e a documentação foram produzidos com o
Claude Code a partir de uma especificação que eu escrevi, com requisitos, regras
de honestidade e critérios de aceitação. Eu estudei o código com este material e
consigo explicar as decisões.

**Explicação.** Ser direta sobre isso evita constrangimento depois. O que a
entrevistadora quer saber é se você entende o que está no repositório: mostre isso
explicando uma decisão (outbox, SSRF, transações curtas) e respondendo os
aprofundamentos.

**Onde ver.** README, seção "Como este projeto foi feito".

**Aprofundamento provável.** "Então o que você fez?" Pista: a especificação, a
revisão, o estudo, a decisão de publicar, e o que você conseguir mostrar na hora,
como alterar uma regra e atualizar os testes (exercícios da parte J).

**Limite honesto.** Não diga que escreveu o código sozinha.
