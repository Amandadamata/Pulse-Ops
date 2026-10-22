# Registro de bugs

Apenas bugs **observados** durante o desenvolvimento, na ordem em que apareceram.
Riscos que ainda não aconteceram ficam no [modelo de ameaças](modelo-de-ameacas.md)
(seção "Limitações remanescentes") e em `docs/operacao.md`.

## B1 — Migração sem a coluna `monitors.check_requested`

- **Sintoma:** `tests/integration/test_migrations.py::test_upgrade_on_empty_database_creates_all_tables`
  falhou; o Alembic detectou "added column 'monitors.check_requested'" ao comparar
  o banco migrado com os modelos.
- **Como reproduzir:** acrescentar uma coluna em `src/pulseops/db/models.py` sem
  gerar migração e rodar `uv run pytest tests/integration/test_migrations.py`.
- **Causa:** a coluna foi criada no modelo depois da geração da migração inicial.
- **Correção:** migração inicial regenerada (o projeto ainda não tinha sido
  publicado, então não havia banco real a migrar).
- **Teste de regressão:** o próprio teste, que compara modelos e migração com
  `alembic.autogenerate.compare_metadata`.
- **Limitação remanescente:** depois de publicado, mudanças de esquema precisam
  de uma migração nova, nunca de edição da inicial.

## B2 — `dict()` sobre resultado do SQLAlchemy levantava `TypeError`

- **Sintoma:** `tests/integration/test_first_slice.py` falhou na preparação
  (login): ao abrir a página inicial, `services/queries.py::summary` levantou
  `TypeError: 'ChunkedIteratorResult' object is not subscriptable`.
- **Como reproduzir:** na versão anterior, `dict((await session.execute(select(Delivery.status, func.count())...)).tuples())`.
- **Causa:** o objeto de resultado tem um método `keys()`. O `dict()` do Python
  trata qualquer objeto com `keys()` como um mapeamento e tenta `objeto[chave]`,
  em vez de iterar pares.
- **Correção:** montar o dicionário com compreensão:
  `{status: count for status, count in rows.tuples()}`.
- **Teste de regressão:** `tests/integration/test_first_slice.py` (o login abre o
  painel, que chama `summary`) e `tests/integration/test_dashboard.py`.
- **Limitação remanescente:** nenhuma conhecida.

## B3 — `Jinja2Templates(autoescape=True)` não existe na versão instalada do Starlette

- **Sintoma:** a aplicação não importava:
  `TypeError: Jinja2Templates.__init__() got an unexpected keyword argument 'autoescape'`.
- **Como reproduzir:** `uv run python -c "from pulseops.web.app import create_app"`
  com a versão anterior de `web/templating.py`.
- **Causa:** o Starlette 1.x removeu a passagem de opções do Jinja pelo
  construtor; é preciso criar o `jinja2.Environment` e entregá-lo pronto.
- **Correção:** `Environment(loader=..., autoescape=True)` passado como `env=`.
- **Teste de regressão:** `tests/integration/test_dashboard.py::test_monitor_name_is_escaped`
  confirma que o autoescape está ligado.
- **Limitação remanescente:** nenhuma conhecida.

## B4 — `verify_password` levantava exceção com hash corrompido contendo acentos

- **Sintoma:** `tests/unit/test_passwords.py::test_missing_user_never_verifies`
  falhou com `UnicodeEncodeError: 'ascii' codec can't encode character`.
- **Como reproduzir:** `verify_password("não é um hash", "x")` na versão anterior.
- **Causa:** o argon2-cffi codifica o hash em ASCII antes de interpretá-lo; um
  texto com acentos falha nessa etapa, antes de chegar a `InvalidHashError`, que
  era a única exceção de formato tratada.
- **Correção:** `security/passwords.py` também trata `ValueError` (da qual
  `UnicodeEncodeError` herda) como "senha não confere". Um hash corrompido no banco
  nunca derruba o login com erro 500.
- **Teste de regressão:** `tests/unit/test_passwords.py::test_missing_user_never_verifies`.
- **Limitação remanescente:** nenhuma conhecida.

## B5 — Fuso horário inexistente não virava erro de configuração legível

- **Sintoma:** `tests/unit/test_config.py::test_unknown_timezone_is_rejected`
  esperava `ValidationError` e recebeu `ZoneInfoNotFoundError`.
- **Como reproduzir:** `Settings(display_timezone="Marte/Olympus")` na versão anterior.
- **Causa:** `ZoneInfoNotFoundError` herda de `KeyError`; o Pydantic só converte
  `ValueError` e `AssertionError` levantados em validadores.
- **Correção:** o validador `_known_timezone` em `config.py` captura o erro e
  levanta `ValueError("fuso horário desconhecido: ...")`.
- **Teste de regressão:** `tests/unit/test_config.py::test_unknown_timezone_is_rejected`.
- **Limitação remanescente:** nenhuma conhecida.

## B6 — Check em andamento durante pausa e retomada contava para a nova contagem

- **Sintoma:** encontrado ao escrever o roteiro da demonstração, que pausa e retoma
  o monitor para recomeçar do zero. Um check iniciado antes da pausa e terminado
  depois da retomada ainda somava falhas.
- **Como reproduzir:** reservar a execução, pausar, retomar e só então gravar um
  resultado de erro com `failure_threshold=1`: o monitor ficava com
  `consecutive_failures == 1` (o teste novo falhou com `assert 1 == 0`).
- **Causa:** `record_result` descartava o efeito apenas se o monitor não estivesse
  ativo ou se a `config_version` tivesse mudado; pausar e retomar não mudava a versão.
- **Correção:** `_reset_counters` em `services/monitors.py` (usado por pausar,
  retomar e arquivar) incrementa `config_version`.
- **Teste de regressão:** `tests/integration/test_incident_lifecycle.py::test_result_of_run_started_before_pause_and_resume_does_not_count`.
- **Limitação remanescente:** o nome `config_version` agora significa "versão da
  contagem", não só da configuração; está documentado em RF03.5.

## B7 — Erro 500 ao cadastrar destino de webhook com nome repetido pelo formulário

- **Sintoma:** o teste novo `test_destination_form_validates_and_toggles` recebeu
  `MissingGreenlet: greenlet_spawn has not been called` em vez da página com o erro
  "já existe um destino com este nome".
- **Como reproduzir:** na versão anterior, cadastrar pelo formulário de
  `/notifications` dois destinos com o mesmo nome.
- **Causa:** depois do `IntegrityError`, a rota faz `rollback()`, o que expira todos
  os objetos da sessão do banco, inclusive a sessão do operador guardada em
  `AuthContext`. Ao montar a página, o template leu `csrf_token`; o SQLAlchemy
  tentou recarregar o objeto com I/O síncrono fora do contexto assíncrono.
- **Correção:** `AuthContext` (`web/deps.py`) passou a guardar só valores simples
  (`operator_id`, `username`, `csrf_token`) copiados no início da requisição.
- **Teste de regressão:** `tests/integration/test_dashboard.py::test_destination_form_validates_and_toggles`.
- **Limitação remanescente:** nenhuma conhecida. Outras rotas que fazem rollback não
  leem objetos do ORM depois dele.

## B8 — Worker atrasava os checks quando havia mais checks vencidos que vagas

- **Sintoma:** no ensaio de carga (200 monitores a cada 10 s, concorrência 20), o
  atraso entre o horário previsto e o início do check teve mediana de 7,8 s e p95 de
  9,7 s, e só 93% dos checks esperados foram feitos
  (`docs/evidencias/ensaio-de-carga-antes-B8.md`).
- **Como reproduzir:** `tests/integration/test_consistency.py::test_dispatcher_refills_freed_slots_without_waiting_a_tick`
  (2 vagas, 6 monitores vencidos, tick de 2 s) falha na versão anterior por tempo esgotado.
- **Causa:** o laço de checks reservava no máximo `worker_concurrency` execuções e
  dormia o tick inteiro (1 s) mesmo quando todas as vagas tinham sido preenchidas e
  ainda havia fila. A vazão ficava limitada a cerca de 20 checks por segundo, embora
  cada check levasse uns 40 ms.
- **Correção:** `worker/runner.py`: quando a reserva preenche todas as vagas pedidas,
  o laço espera só até uma vaga abrir (evento sinalizado ao fim de cada check), com
  o tick como limite. Sem fila, continua esperando o tick.
- **Teste de regressão:** o teste citado acima, mais o ensaio repetido
  (`docs/evidencias/ensaio-de-carga.md`: mediana de 0,64 s e 99,5% dos checks).
- **Limitação remanescente:** granularidade de 1 s do tick; documentada em `operacao.md`.
