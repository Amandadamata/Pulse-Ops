# D3 — Persistência: modelos, sessão e migrações

A parte F do volume 1 explica os conceitos (chaves, constraints, índices,
transações) e mostra o SQL gerado. Aqui o foco é cada linha dos arquivos.

## `src/pulseops/db/models.py`

**Finalidade.** Declara as 13 tabelas como classes do SQLAlchemy, com tipos,
chaves, constraints e índices.

**Dados.** Cada classe corresponde a uma tabela; cada atributo `Mapped[...]` a uma
coluna. Datas são sempre `timestamptz` (com fuso). **Relações.** Importado por
todos os serviços, pelo worker, pelos testes e por `migrations/env.py` (que usa
`Base.metadata` para comparar com o banco). **Testes.**
`test_upgrade_on_empty_database_creates_all_tables` (modelos = migração),
`test_database_rejects_second_running_check`,
`test_database_rejects_second_open_incident`,
`test_duplicate_name_is_rejected_case_insensitive`.

@@trecho src/pulseops/db/models.py 1-42

- Linhas 1–6: a docstring diz o porquê do arquivo: o banco garante o que a
  aplicação promete, mesmo com bug no Python.
- Linhas 11–27: imports. `JSONB` (linha 26) é um tipo específico do PostgreSQL;
  `DeclarativeBase`, `Mapped` e `mapped_column` são o estilo tipado do
  SQLAlchemy 2.x.
- Linhas 30–36: **convenção de nomes**. Sem ela, o PostgreSQL inventaria nomes
  como `checks_monitor_id_fkey`. Com ela, toda constraint tem nome previsível
  (`ck_monitors_state`, `fk_checks_monitor_id_monitors`), o que facilita
  migrações futuras e mensagens de erro.
- Linha 38: um apelido para `DateTime(timezone=True)`, usado em todas as colunas
  de data.
- Linhas 41–42: a classe base de todos os modelos, com a convenção aplicada.

@@trecho src/pulseops/db/models.py 45-62

- `Operator` (linhas 45–51): `id` inteiro gerado pelo banco
  (`primary_key=True`); `username` único com até 50 caracteres; `password_hash`
  em `Text` (o hash Argon2 tem cerca de 100 caracteres).
- `OperatorSession` (linhas 54–62): a chave primária é o **hash** do token
  (linha 58, 64 caracteres hexadecimais do SHA-256). `ondelete="CASCADE"` (linha
  59) apaga as sessões junto com a operadora. `expires_at` tem índice (linha 62)
  porque o login apaga as sessões vencidas.

Os padrões dessas duas classes se repetem em todas: `Mapped[tipo]` define o tipo
Python e se aceita nulo (`| None`); `mapped_column(...)` define o tipo SQL e
extras. Daqui em diante só o que é novo é comentado.

@@trecho src/pulseops/db/models.py 65-100

As constraints de `monitors`. Volume 1, parte F, explica as linhas 68–86 uma a uma
e os dois índices:

- Linhas 88–93: índice **único parcial** sobre `lower(name)`, só para monitores
  não arquivados. `func.lower(text("name"))` gera a expressão SQL `lower(name)`.
- Linhas 95–99: índice parcial para o agendador.

@@trecho src/pulseops/db/models.py 102-129

As colunas de `monitors`, em três grupos:

- Linhas 102–112, **configuração**: o que a operadora define. `accepted_status_codes`
  é texto (`"200-299"`), interpretado por `domain/status_codes.py`.
- Linhas 114–121, **estado calculado**: `state` (ciclo de vida: ativo, pausado,
  arquivado), `health` (saúde calculada), `health_reason` (o porquê, em texto),
  contadores, início da sequência de falhas e `config_version` (versão da
  contagem; bug B6).
- Linhas 123–129, **agendamento e auditoria**: `next_run_at` (quando verificar;
  nulo se pausado ou arquivado), `check_requested` ("verificar agora"),
  `last_check_at`, datas de criação, alteração e arquivamento.

`default=...` é o valor que o SQLAlchemy põe se o código não informar. O código
de `services/monitors.py` informa tudo explicitamente, então os padrões são uma
rede de segurança.

@@trecho src/pulseops/db/models.py 132-173

`checks`, um registro por verificação:

- Linhas 143–146: a constraint mais interessante: um check `running` **não tem**
  resultado nem fim; um `completed` **tem** os dois. O banco não aceita um estado
  intermediário.
- Linhas 148–157: os três índices (volume 1, parte F).
- Linha 160: `BigInteger`, porque esta tabela cresce sem parar.
- Linha 161: `RESTRICT`: um monitor com checks não pode ser apagado.
- Linhas 162–163: `run_key` único (identidade da execução).
- Linhas 166–167: versão da contagem na reserva e o horário **agendado**
  (diferente do `started_at`, o horário real).
- Linhas 169–173: preenchidos na conclusão. `explanation` tem no máximo 300
  caracteres; `services/processing.py` corta o texto antes de gravar.

@@trecho src/pulseops/db/models.py 176-215

`incidents`:

- Linha 180: `(status = 'open') = (ended_at IS NULL)`: aberto se e somente se não
  tem fim.
- Linha 181: o início não pode ser depois da confirmação.
- Linhas 183–188: um incidente aberto por monitor (RF03.11).
- Linhas 202–206: **retrato** da configuração no momento da abertura (RF03.12). Se
  a operadora mudar o limiar depois, o incidente continua dizendo com qual limiar
  foi aberto.
- Linhas 207–212: motivos de abertura e de resolução, número de falhas, último
  resultado e última explicação.
- Linhas 213–215: o último check, com `SET NULL` (a retenção pode apagá-lo).

@@trecho src/pulseops/db/models.py 218-272

Três tabelas de "fatos derivados", no mesmo padrão (id `BigInteger`, chave para o
pai, data, texto e, quando faz sentido, o check que causou):

- `incident_events` (218–238): a linha do tempo do incidente. `kind` tem seis
  valores possíveis (linha 222); `details` é `JSONB` com o retrato da configuração
  (linha 235). `default=dict` (sem parênteses) passa a **função** `dict`, que cria
  um dicionário novo a cada linha. Passar `{}` faria todas as linhas
  compartilharem o mesmo objeto.
- `health_changes` (241–256): de qual saúde para qual, quando e por quê.
- `coverage_gaps` (259–272): períodos sem checks, com início antes do fim
  (constraint da linha 264).

@@trecho src/pulseops/db/models.py 275-306

- `alert_destinations` (275–283): destinos de webhook, nome único, ativo ou não.
- `alert_events` (286–306): o evento do outbox. `event_key` único (linha 301) é o
  `event_id` enviado ao destino. `payload` é o JSON exato que será enviado,
  montado uma vez na criação.

@@trecho src/pulseops/db/models.py 309-364

- `deliveries` (309–335): uma entrega por par (evento, destino), garantida pela
  `UniqueConstraint` da linha 312. A linha 330 explica o duplo uso de
  `next_attempt_at`: para `pending`, quando tentar; para `sending`, até quando vale
  a reserva.
- `delivery_attempts` (338–354): uma linha por tentativa, com número único por
  entrega (linha 341).
- `worker_heartbeats` (357–364): chave primária textual (`hostname:pid`) e o último
  sinal de vida.

**Falhas possíveis.** Uma gravação que viole qualquer constraint levanta
`IntegrityError` e a transação inteira é desfeita. Na criação de monitor e de
destino, esse erro vira uma mensagem para a operadora (nome repetido); nos outros
casos, indica bug e aparece como erro 500 ou como log de erro do worker.

## `src/pulseops/db/session.py`

**Finalidade.** Cria o *engine* (o gerenciador do pool de conexões) e a fábrica de
sessões.

@@arquivo src/pulseops/db/session.py

- Linhas 3–8: os tipos assíncronos do SQLAlchemy.
- Linha 10: `SessionFactory` é um apelido de tipo, usado nas assinaturas dos
  serviços.
- Linhas 13–19: `pool_pre_ping` testa a conexão antes de usar;
  `connect_timeout: 5` faz uma conexão com banco inacessível falhar em 5 s, em vez
  de esperar indefinidamente.
- Linhas 22–24: `expire_on_commit=False` (volume 1, parte F).

**Dados.** A URL do banco (texto da configuração). **Relações.** Usado por
`web/app.py`, `worker/__main__.py`, `cli.py` e `tests/conftest.py`. **Falhas.** URL
inválida levanta erro na criação; banco fora do ar só aparece na primeira
consulta. **Testes.** Indiretamente, todos os de integração;
`test_ready_returns_503_when_database_is_down` cobre o banco inacessível.

## `alembic.ini`

**Finalidade.** Configuração do Alembic: onde estão as migrações e como logar.

@@trecho alembic.ini 1-20

- Linha 2: `%(here)s` é a pasta do próprio arquivo; as migrações ficam em
  `migrations/`.
- Linha 3: modelo do nome dos arquivos novos: `0001_esquema_inicial.py`.
- Linha 4: acrescenta a raiz ao caminho de import, para `migrations/env.py`
  conseguir importar `pulseops`.
- Linha 5: separa os caminhos da linha 4 conforme o sistema operacional (`:` no
  Linux, `;` no Windows); é a forma atual recomendada pelo Alembic.
- Linha 6: o comentário avisa que **não** há URL de banco aqui (ela seria um
  segredo num arquivo versionado); vem do ambiente.
- Linhas 8–20 e o resto do arquivo: configuração padrão de logging do Alembic
  (nível WARNING para o SQLAlchemy, INFO para o Alembic, saída em `stderr`).

## `migrations/env.py`

**Finalidade.** Script que o Alembic executa a cada comando: descobre a URL, abre a
conexão e roda as migrações.

@@arquivo migrations/env.py

- Linhas 13–15: usa as mesmas classes de configuração e de modelos da aplicação.
- Linhas 17–19: aplica o logging do `alembic.ini`.
- Linha 21: `target_metadata` é o que o `--autogenerate` compara com o banco.
- Linhas 24–26: a URL vem primeiro de `config.attributes` (os testes passam a URL
  do banco de teste assim; `tests/conftest.py`, `alembic_config`), senão de
  `PULSEOPS_DATABASE_URL`.
- Linhas 29–32: modo *offline*: gera o SQL como texto, sem conectar
  (`alembic upgrade head --sql`).
- Linhas 35–41: modo normal. Um engine **síncrono** com `NullPool` (sem pool,
  porque é um comando de uma vez), uma transação, e as migrações dentro dela. No
  PostgreSQL, até `CREATE TABLE` é transacional: se a migração falhar no meio,
  nada fica criado pela metade.

**Testes.** `tests/integration/test_migrations.py` e o passo de migrações do CI.

## `migrations/script.py.mako`

**Finalidade.** Modelo (template Mako) usado pelo `alembic revision` para criar
arquivos de migração novos.

@@arquivo migrations/script.py.mako

`${...}` são marcadores que o Alembic preenche: mensagem, identificador da revisão,
revisão anterior, data e os comandos gerados. O modelo foi ajustado para usar
anotações de tipo (linhas 14–17), porque o mypy está em modo estrito.

## `migrations/versions/0001_esquema_inicial.py` (explicado por padrão)

**Finalidade.** Cria todas as tabelas, constraints e índices (`upgrade`) e remove
tudo na ordem inversa (`downgrade`).

O arquivo foi **gerado** por `alembic revision --autogenerate` a partir dos
modelos, e por isso não é explicado linha a linha (ver exclusões). Ele tem 468
linhas, mas usa só cinco padrões. Um exemplo de cada:

@@trecho migrations/versions/0001_esquema_inicial.py 14-18

**Identificação.** `revision` é o id desta migração; `down_revision = None` diz que
é a primeira. Uma próxima migração teria `down_revision = "0001"`.

@@trecho migrations/versions/0001_esquema_inicial.py 125-158

**Criar tabela** (`op.create_table`). Cada `sa.Column` traz nome, tipo e se aceita
nulo. Depois vêm as constraints com os nomes da convenção (`op.f(...)` marca o
nome como "já final", para o Alembic não aplicar a convenção de novo). O mesmo
padrão se repete nas 13 tabelas, nas linhas 21–31, 32–92, 107–115, 116–124,
125–158, 170–185, 189–203, 207–229, 237–278, 291–318, 321–347, 355–386 e 394–416.

@@trecho migrations/versions/0001_esquema_inicial.py 159-169

**Criar índice** (`op.create_index`), comum ou **parcial**
(`postgresql_where`). O índice sobre `lower(name)` (linhas 100–106) usa
`sa.literal_column` porque é uma expressão, não uma coluna.

@@trecho migrations/versions/0001_esquema_inicial.py 419-426

**Desfazer** (`downgrade`). Remove índices e tabelas na ordem inversa da criação:
uma tabela só pode ser apagada depois das que apontam para ela.

**Como se sabe que está certo.** `test_upgrade_on_empty_database_creates_all_tables`
aplica a migração e compara com os modelos: qualquer diferença (coluna faltando,
índice diferente) faz o teste falhar. Foi assim que o bug B1 apareceu.
