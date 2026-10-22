# Parte F — Banco de dados e SQL

O PostgreSQL é a peça que dá confiança ao PulseOps. Ele guarda o histórico, e
também **garante regras**: algumas promessas do sistema ("um incidente aberto por
monitor", "um check em andamento por monitor") não dependem só do código Python
estar certo.

## Modelo relacional

Um banco **relacional** organiza dados em **tabelas**. Cada **linha** é um registro
e cada **coluna** tem um tipo (`integer`, `varchar`, `timestamptz`...). Tabelas se
ligam por valores: a coluna `checks.monitor_id` guarda o `id` do monitor ao qual o
check pertence.

O diagrama abaixo mostra as 13 tabelas e como se relacionam (é o mesmo diagrama
de `docs/arquitetura.md`, com os atributos expandidos lá).

@@diagrama er

Leitura do diagrama, pelos grupos:

| Grupo | Tabelas | Papel |
|---|---|---|
| Acesso | `operators`, `operator_sessions` | quem pode entrar e as sessões abertas |
| Configuração | `monitors`, `alert_destinations` | o que verificar e para onde avisar |
| Fatos observados | `checks`, `coverage_gaps` | cada verificação feita e os períodos sem verificação |
| Decisões | `health_changes`, `incidents`, `incident_events` | o que o sistema concluiu a partir dos fatos, com o motivo |
| Alertas | `alert_events`, `deliveries`, `delivery_attempts` | outbox: o evento, a entrega por destino e cada tentativa |
| Processo | `worker_heartbeats` | último sinal de vida do worker |

A separação entre **fatos** e **decisões** é proposital. Um check é algo que
aconteceu e não muda depois de concluído. Uma mudança de saúde é uma conclusão
tirada de vários checks, e guarda o motivo em texto. Assim, dá para auditar
qualquer decisão voltando aos fatos que a geraram.

## Chaves primárias e estrangeiras

- **Chave primária** (*primary key*, PK): identifica cada linha de forma única. Em
  quase todas as tabelas é uma coluna `id` numerada pelo próprio banco. Duas
  exceções: `operator_sessions` usa o `token_hash` (o hash do cookie, que já é
  único) e `worker_heartbeats` usa o `worker_id`.
- **Chave estrangeira** (*foreign key*, FK): diz que o valor de uma coluna precisa
  existir em outra tabela. `checks.monitor_id` só aceita `id` de monitores que
  existem. O banco recusa um check "órfão".

O `ondelete` da FK diz o que acontece quando a linha apontada é apagada:

@@trecho src/pulseops/db/models.py 160-163

| Regra | Onde | Por quê |
|---|---|---|
| `RESTRICT` | `checks.monitor_id`, `incidents.monitor_id`, entregas... | monitores nunca são apagados, só arquivados; se alguém tentar apagar um monitor com histórico, o banco recusa |
| `CASCADE` | `operator_sessions.operator_id` | sessões não têm sentido sem a operadora |
| `SET NULL` | `incidents.last_check_id`, `incident_events.check_id`, `health_changes.check_id` | a retenção apaga checks antigos, mas incidentes ficam para sempre; a referência vira nula em vez de impedir a limpeza |

## Constraints: o banco como segunda linha de defesa

Uma **constraint** (restrição) é uma regra que o banco verifica em toda gravação.
Se a regra é violada, o comando inteiro falha. O PulseOps usa três tipos.

**CHECK** — condição sobre os valores da própria linha:

@@trecho src/pulseops/db/models.py 67-86

Linha a linha do que importa aqui:

- 68–72: listas fechadas de valores. `state` só pode ser `active`, `paused` ou
  `archived`. Um erro de digitação no código (`"actve"`) é recusado pelo banco.
- 75: o intervalo fica entre 2 s e 1 dia. O mínimo de 30 s do modo normal é
  conferido na aplicação (o comentário das linhas 73–74 explica: o modo demonstração
  aceita 2 s).
- 77: o timeout precisa ser menor que o intervalo, senão um check ainda estaria
  rodando quando o próximo começasse.
- 78–80: o limite de lentidão fica entre 50 ms e o timeout. Um limite maior que o
  timeout nunca seria alcançado.
- 86: `(state = 'archived') = (archived_at IS NOT NULL)` compara dois booleanos: a
  data de arquivamento existe **se e somente se** o monitor está arquivado.

**UNIQUE** — nenhum par de linhas pode repetir o valor. Exemplos: `checks.run_key`,
`alert_events.event_key` e o par (`event_id`, `destination_id`) em `deliveries`.

**Índice único parcial** — único só entre as linhas que satisfazem uma condição.
É a ferramenta mais importante do esquema:

@@trecho src/pulseops/db/models.py 147-153

`WHERE status = 'running'` faz o índice conter só os checks em andamento. Como ele
é `unique` por `monitor_id`, **no máximo um check em andamento por monitor**.
Checks concluídos ficam fora do índice, então um monitor pode ter milhares deles.

O mesmo padrão aparece em outros dois lugares:

| Índice | Garante | Requisito |
|---|---|---|
| `uq_checks_one_running_per_monitor` | um check em andamento por monitor | CB3 |
| `uq_incidents_one_open_per_monitor` | um incidente aberto por monitor | RF03.11 |
| `uq_monitors_active_name` | nome único (sem diferenciar maiúsculas) entre monitores não arquivados | RF01.7 |

O último usa `lower(name)` dentro do índice. "API Pagamentos" e "api pagamentos"
viram o mesmo valor e colidem. Um monitor arquivado sai do índice, então o nome
dele pode ser reutilizado.

**Por que repetir no banco o que o código já faz?** O código confere antes de
gravar, mas entre a conferência e a gravação outra transação pode ter gravado a
mesma coisa (a "corrida" da seção de concorrência). Só o banco vê todas as
transações. Os testes `test_database_rejects_second_running_check` e
`test_database_rejects_second_open_incident` (em
`tests/integration/test_consistency.py`) tentam inserir a segunda linha
diretamente, sem passar pelo código, e conferem que o PostgreSQL recusa.

## Índices

Um **índice** é uma estrutura auxiliar (no PostgreSQL, por padrão, uma árvore B)
que permite achar linhas sem ler a tabela inteira, como o índice remissivo de um
livro. Custa espaço e deixa as gravações um pouco mais lentas, então cada índice
precisa de uma consulta que o justifique.

| Índice | Colunas | Consulta que atende |
|---|---|---|
| `ix_monitors_due` (parcial, `state = 'active'`) | `next_run_at` | o agendador: "monitores ativos com execução vencida" |
| `ix_checks_monitor_history` | `monitor_id, started_at, id` | histórico de um monitor, paginado |
| `ix_checks_started_at` | `started_at` | retenção: checks antigos de todos os monitores |
| `ix_incidents_confirmed` | `confirmed_at, id` | lista geral de incidentes |
| `ix_deliveries_due` (parcial, pendentes) | `next_attempt_at` | o entregador: "entregas vencidas" |
| `ix_incidents_last_check` e similares | colunas com `SET NULL` | ao apagar um check, o banco precisa achar quem aponta para ele |

A ordem das colunas num índice composto importa. `(monitor_id, started_at, id)`
serve para "checks **deste** monitor, ordenados por data", porque primeiro filtra
pelo monitor e depois já encontra as linhas na ordem certa. Não serviria para
"checks de todos os monitores de ontem"; para isso existe `ix_checks_started_at`.

O último grupo é um detalhe fácil de esquecer: o PostgreSQL **não** cria índice
sozinho nas colunas de chave estrangeira. Sem `ix_incidents_last_check`, apagar
5000 checks na retenção faria o banco varrer a tabela de incidentes 5000 vezes
para aplicar o `SET NULL`.

## ORM: tabelas como classes Python

Um **ORM** (*Object-Relational Mapper*) liga classes Python a tabelas. O PulseOps
usa o SQLAlchemy 2.x no estilo com anotações de tipo:

@@trecho src/pulseops/db/models.py 132-135

@@trecho src/pulseops/db/models.py 160-173

- `class Check(Base)`: cada instância é uma linha da tabela `checks`.
- `Mapped[int]`: o tipo que o Python (e o mypy) enxerga.
- `mapped_column(...)`: detalhes da coluna no banco. `Mapped[int | None]` vira uma
  coluna que aceita `NULL`; `Mapped[int]` vira `NOT NULL`.
- `BigInteger` nos ids de tabelas que crescem sem parar (checks, eventos): um
  `integer` comum acaba em cerca de 2,1 bilhões.

A conexão e a fábrica de sessões ficam em `src/pulseops/db/session.py`:

@@trecho src/pulseops/db/session.py 13-24

- `pool_size`: quantas conexões o processo mantém abertas para reaproveitar.
- `pool_pre_ping=True`: antes de usar uma conexão do pool, confere se ela ainda
  está viva. Sem isso, depois de o banco reiniciar, a primeira consulta falharia.
- `expire_on_commit=False`: depois do `commit`, os objetos continuam legíveis sem
  ir ao banco de novo. O worker lê `monitor.id` depois de fechar a transação, então
  isso evita consultas extras (e erros em código assíncrono).

**O que o ORM não faz por você:** ele não decide quando a transação começa e
termina, nem quais linhas travar. Essas decisões estão escritas explicitamente no
código (próximas seções).

## O SQL que realmente roda

Os trechos de SQL a seguir **não foram escritos à mão**. O script
`study/captura_sql.py` é um plugin do pytest que escuta todos os comandos
enviados ao PostgreSQL durante os testes de integração e salva os de interesse.
A única mudança feita no texto é de espaçamento: quebras de linha antes de
palavras como `FROM` e `WHERE`.

Os marcadores `%(nome)s` são **parâmetros**: o valor vai separado do comando, e o
banco nunca o interpreta como SQL. É isso que torna o PulseOps imune a injeção de
SQL nesses pontos, e é testado em `test_sql_injection_attempts_are_plain_data`
(em `tests/integration/test_dashboard.py`). O `::VARCHAR` depois de cada
parâmetro é um *cast* (conversão de tipo) que o SQLAlchemy acrescenta.

### Reservar monitores vencidos

Código Python (`src/pulseops/services/processing.py`):

@@trecho src/pulseops/services/processing.py 60-70

SQL gerado:

@@sql reservar-monitores

Parte por parte:

- `WHERE monitors.state = ... AND monitors.next_run_at <= ...`: ativos e com a
  próxima execução no passado (ou agora).
- `NOT (EXISTS (SELECT * FROM checks WHERE ... status = 'running'))`: pula
  monitores que já têm um check em andamento. `EXISTS` responde "há pelo menos
  uma linha?" e para na primeira que encontrar.
- `ORDER BY monitors.next_run_at, monitors.id`: os mais atrasados primeiro; o `id`
  desempata para a ordem ser sempre a mesma.
- `LIMIT`: no máximo o número de vagas livres do worker.
- `FOR UPDATE SKIP LOCKED`: trava as linhas escolhidas até o fim da transação e
  **pula** as que outra transação já travou. Explicação completa na seção de
  concorrência.

### Gravar o check como "em andamento", sem duplicar

@@trecho src/pulseops/services/processing.py 105-123

@@sql inserir-check

- `ON CONFLICT (run_key) DO NOTHING`: se já existe um check com essa identidade, o
  banco não insere e não dá erro.
- `RETURNING checks.id`: devolve o id criado. Se nada foi inserido, não volta
  nenhuma linha, o Python recebe `None` (linha 121) e entende que essa execução já
  existia.

O `run_key` é `"{monitor_id}:{horário agendado}"` (linha 46–47 do mesmo arquivo).
A mesma execução agendada tem sempre o mesmo `run_key`, então reprocessá-la não
cria um segundo check. Teste: `test_same_run_identity_cannot_be_reserved_twice`.

### Histórico paginado por cursor

@@sql historico-cursor

`(checks.started_at, checks.id) < (..., ...)` compara **pares**: primeiro pela
data; se empatar, pelo id. É a "paginação por cursor" (*keyset pagination*): o
cursor que a API devolve é o par do último item da página, codificado em base64
(`encode_cursor` em `src/pulseops/services/queries.py`). A próxima página começa
logo depois dele.

Por que não `OFFSET`? Com `OFFSET 50`, o banco precisa ler e descartar 50 linhas, e
se um check novo chegar entre uma página e outra, todo mundo "anda" uma posição: um
item aparece duas vezes. Com o cursor, a posição é definida pelo próprio dado. O
`LIMIT` pede um item a mais que o tamanho da página só para saber se há próxima
página. Teste: `test_cursor_pagination_is_stable_and_complete`.

### Métricas

@@sql metricas-contagem

`GROUP BY checks.outcome` junta as linhas por resultado e `count(*)` conta cada
grupo. O resultado tem uma linha por tipo de resultado (`healthy`, `timeout`...).
A janela é `started_at >= início AND started_at < fim`: fechada no começo e aberta
no fim, para que janelas vizinhas não contem o mesmo check duas vezes.

@@sql metricas-latencia

`percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_ms)` ordena as durações e
devolve o primeiro valor cuja posição acumulada chega a 95%. É o método
*nearest-rank* (ADR 0011). O filtro `outcome IN (...)` deixa de fora timeouts e
erros de conexão, que não têm duração de resposta. O teste
`test_sql_percentile_matches_nearest_rank` compara o resultado do SQL com a função
Python `nearest_rank` de `src/pulseops/domain/metrics.py`.

### Retenção

@@trecho src/pulseops/services/processing.py 267-279

@@sql retencao

Apaga em **lotes** de até 5000 checks concluídos mais antigos que o prazo. Um
`DELETE` de milhões de linhas numa transação só seguraria travas por muito tempo.
O `RETURNING checks.id` não está no código Python: foi o SQLAlchemy que o
acrescentou, porque um `delete()` do ORM sincroniza os objetos já carregados na
sessão. Incidentes não são apagados, e as referências a checks apagados viram
`NULL` (o `SET NULL` visto antes). Teste:
`test_old_checks_are_purged_and_incidents_kept`.

## Transações, commit e rollback

Uma **transação** é um grupo de comandos que o banco trata como uma unidade: ou
**todos** valem (`COMMIT`), ou **nenhum** vale (`ROLLBACK`). Isso é o "A" de ACID
(*atomicidade*). As outras letras: **C**onsistência (constraints valem no fim de
toda transação), **I**solamento (transações simultâneas não veem o trabalho pela
metade umas das outras) e **D**urabilidade (o que foi confirmado sobrevive a uma
queda).

No PulseOps, o padrão é `async with sessions.begin() as session:`.

@@trecho src/pulseops/services/processing.py 139-153

- Entrar no bloco abre a transação.
- Sair do bloco normalmente faz `COMMIT`.
- Sair por exceção faz `ROLLBACK` e deixa a exceção seguir.

`record_result` é o melhor exemplo de por que isso importa. Dentro de uma única
transação ele: marca o check como concluído, atualiza os contadores do monitor,
talvez abre ou resolve um incidente, grava a mudança de saúde **e** cria o evento
de alerta com as entregas. Se o banco cair no meio, nada disso fica pela metade:
não existe "incidente aberto sem alerta" nem "alerta sem incidente". Testes:
`test_outbox_event_is_atomic_with_incident` (em `tests/integration/test_delivery.py`)
e `test_database_failure_while_recording_does_not_count_as_target_failure`.

**Transações curtas (ADR 0003).** O ciclo de um check usa **duas** transações, com
a requisição HTTP entre elas e fora de ambas:

1. `claim_due_runs`: reserva e grava o check `running`. Commit.
2. Requisição HTTP ao alvo (até `timeout_seconds`), sem transação aberta.
3. `record_result`: grava o resultado e aplica as regras. Commit.

Se a requisição ficasse dentro da transação, cada check lento seguraria uma
conexão e travas por até 30 segundos. Com 100 monitores lentos, o pool de conexões
acabaria. O preço da separação é tratar o caso em que o worker cai entre os
passos 1 e 3: o check fica `running` para sempre. `mark_abandoned_runs` (linhas
239–264 de `processing.py`) encontra esses checks e os marca como
`internal_error`, que **não** conta como falha do alvo.

Na API, a sessão é aberta por requisição (`get_db` em
`src/pulseops/web/deps.py`) e as rotas que alteram dados chamam `commit()`
explicitamente. O que não foi confirmado é desfeito quando a sessão fecha.

## Migrações com Alembic

O esquema do banco evolui junto com o código. Uma **migração** é um arquivo Python
com duas funções: `upgrade()` (aplica a mudança) e `downgrade()` (desfaz). O
Alembic anota na tabela `alembic_version` qual foi a última aplicada.

O PulseOps tem uma migração só, `migrations/versions/0001_esquema_inicial.py`.
Ela foi **gerada automaticamente** pelo Alembic (`alembic revision
--autogenerate`), comparando os modelos com um banco vazio, e depois revisada. Por
isso o volume 2 a explica por padrão, e não linha a linha.

Dois testes cuidam dela (`tests/integration/test_migrations.py`):

- `test_upgrade_on_empty_database_creates_all_tables`: aplica a migração num banco
  vazio e usa `compare_metadata` para conferir que o resultado é **idêntico** aos
  modelos. Se alguém mudar um modelo e esquecer a migração, o teste falha.
- `test_downgrade_and_upgrade_again`: desfaz tudo (sobra só `alembic_version`) e
  aplica de novo.

O CI repete o ciclo `upgrade` → `downgrade` → `upgrade` contra um PostgreSQL de
verdade.

**Limite honesto:** com uma migração só, o projeto nunca passou por uma
**alteração** de esquema com dados existentes (renomear coluna, preencher coluna
nova). Esse é o caso difícil de migrações, e não está exercitado aqui.

## Concorrência

Concorrência é quando duas coisas acontecem "ao mesmo tempo" e disputam os mesmos
dados. No PulseOps, há três fontes:

- o worker roda até `PULSEOPS_WORKER_CONCURRENCY` checks em paralelo (20 por padrão);
- a API e o worker alteram o mesmo monitor (a operadora pausa enquanto um check
  roda);
- alguém pode, por engano, iniciar um segundo worker.

### Travas de linha: `FOR UPDATE`

`SELECT ... FOR UPDATE` trava as linhas lidas até o fim da transação. Outra
transação que tente travar a mesma linha **espera**.

@@sql travar-monitor

Esse comando sai de `session.get(Monitor, run.monitor_id, with_for_update=True)`
na linha 149 de `processing.py`. Ele serializa `record_result` com a pausa feita
pela API, que também trava o monitor (`get_monitor(..., lock=True)` em
`services/monitors.py`). Uma das duas termina primeiro; a outra vê o resultado.

### Pular o que está ocupado: `SKIP LOCKED`

Com `SKIP LOCKED`, em vez de esperar, a consulta **pula** linhas travadas. É o
padrão de "fila no banco": dois consumidores pegam itens diferentes, sem brigar.
O teste `test_concurrent_claims_never_take_the_same_monitor` dispara reservas em
paralelo e confere que nenhum monitor é reservado duas vezes.

### A versão da configuração

Travar não resolve tudo. Considere: o check começa às 10:00:00 com timeout de 5 s;
às 10:00:02 a operadora muda o limite de falhas; às 10:00:05 o check termina. O
resultado foi medido com a configuração **antiga**. Deve contar?

O PulseOps responde "não": cada check guarda o `config_version` do momento da
reserva, e `record_result` só aplica as regras se ele ainda for igual ao do
monitor (linhas 164–167 de `processing.py`). Edição, pausa, retomada e
arquivamento incrementam a versão. O bug B6 (registro de bugs) era justamente a
pausa e a retomada **não** incrementarem: um check iniciado antes da pausa contava
depois da retomada. Testes: `test_result_of_run_started_before_config_change_does_not_count`
e `test_result_of_run_started_before_pause_and_resume_does_not_count` (em
`tests/integration/test_incident_lifecycle.py`).

### Um worker só: advisory lock

@@trecho src/pulseops/worker/__main__.py 24-32

Um **advisory lock** é uma trava sem tabela: um número que só uma conexão por vez
pode segurar. O worker tenta pegá-lo ao iniciar com
`pg_try_advisory_lock`, que responde na hora (`true` ou `false`) em vez de esperar.
Se outro worker já o tem, este registra o erro e sai com código 1. O lock é
**de sessão**: dura enquanto a conexão estiver aberta, e o PostgreSQL o libera
sozinho se o processo morrer. Teste: `test_second_worker_is_refused`.

### Entregas: reserva com prazo

@@sql reservar-entregas

`FOR UPDATE OF deliveries SKIP LOCKED` trava só as linhas de `deliveries`, não as
do evento e do destino que vieram no `JOIN`. A reserva muda o status para
`sending` e põe em `next_attempt_at` o fim do prazo de reserva (*lease*). Se o
worker morrer durante o envio, a reserva vence e outra rodada pega a entrega de
novo. Isso pode gerar **entrega duplicada** (o destino recebeu, mas o worker morreu
antes de gravar), e por isso cada evento leva um `event_id` estável para o destino
descartar repetições (RF06.8).

@@sql gravar-entrega

A gravação do resultado só altera a linha se ela ainda estiver `sending` **com o
mesmo número de tentativa**. Se a reserva venceu e outra tentativa já começou, esta
gravação atrasada não sobrescreve o estado mais novo. É uma forma de **controle
otimista**: em vez de travar antes, confere na hora de gravar.

## Resumo da parte F

| Garantia | Mecanismo | Onde |
|---|---|---|
| Um check em andamento por monitor | índice único parcial + `NOT EXISTS` na reserva | `models.py`, `processing.py` |
| Um incidente aberto por monitor | índice único parcial | `models.py` |
| Execução não duplicada | `run_key` único + `ON CONFLICT DO NOTHING` | `processing.py` |
| Incidente e alerta juntos ou nada | uma transação em `record_result` | `processing.py`, `alerts.py` |
| Resultado velho não decide | `config_version` | `processing.py`, `monitors.py` |
| Um worker por banco | advisory lock de sessão | `worker/__main__.py` |
| Entrega retomada após queda | lease em `next_attempt_at` | `alerts.py` |
| Histórico estável | paginação por cursor `(started_at, id)` | `queries.py` |
