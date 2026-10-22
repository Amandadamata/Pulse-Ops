# Parte E — Fundamentos de Python aplicados

Cada seção explica um conceito e mostra **onde ele aparece no PulseOps e por quê**.
Quando um conceito é citado só para comparação, isso está dito.

## Tipos

Todo valor em Python tem um tipo: `int` (inteiro), `float` (número com casas
decimais), `str` (texto), `bool` (`True`/`False`), `None` (ausência de valor),
`datetime` (data e hora). No PulseOps:

- `interval_seconds` é `int`; `worker_tick_seconds` é `float`, porque pode ser 0,5 s.
- Datas são sempre `datetime` **com fuso** (*timezone-aware*), em UTC. Um
  `datetime` sem fuso é ambíguo ("10h de onde?"); a API recusa datas assim
  (`_require_aware` em `web/api.py`) e o banco usa `timestamptz`.
- `None` aparece onde algo pode não existir: `Monitor.next_run_at` é `None` quando
  o monitor está pausado; `Check.status_code` é `None` quando não houve resposta.

**Enum** é um tipo com um conjunto fechado de valores. `Outcome` herda de
`StrEnum`, então cada membro também é uma `str` e pode ser gravado direto no banco:

@@trecho src/pulseops/domain/outcomes.py 6-28

`Outcome.TIMEOUT == "timeout"` é verdadeiro. As `@property` (`is_failure`,
`is_success`, `label`) colocam o conhecimento sobre cada resultado junto do tipo,
em vez de espalhar `if outcome in (...)` pelo código.

## Coleções

| Coleção | Característica | Onde aparece |
|---|---|---|
| `list` | ordenada, mutável, aceita repetidos | `ClaimedRun`s reservados em `claim_due_runs`; checks de uma página |
| `tuple` | ordenada, imutável | pares `(host, porta)` da lista do laboratório; `ANSWERED = ("healthy", "slow")` em `charts.py` |
| `dict` | pares chave → valor | `_LABELS` em `outcomes.py`; `payload` do webhook; contagem `by_outcome` nas métricas |
| `set` | sem ordem, sem repetidos, busca rápida | `Worker._inflight`, as tarefas em andamento |
| `frozenset` | `set` imutável | `_FAILURES` em `outcomes.py`; `UNSAFE_METHODS` em `web/deps.py`; portas permitidas |

Por que `frozenset` para `_FAILURES`? Porque o conjunto de falhas é uma constante:
imutável, ninguém o altera por engano, e `x in conjunto` é rápido.

**Compreensões** criam coleções a partir de outras numa linha. Exemplo de
`config.py`: `frozenset(int(p) for p in self.allowed_ports.split(",") if p.strip())`
transforma `"80,443"` em `frozenset({80, 443})`, ignorando pedaços vazios. A
correção do bug B2 trocou `dict(resultado)` por uma compreensão
`{status: count for status, count in rows}` (parte G).

## Funções e argumentos

- **Argumentos só por nome.** O `*` na assinatura obriga a nomear o que vem
  depois: `claim_due_runs(sessions, *, now, limit)` só pode ser chamada como
  `claim_due_runs(sessions, now=..., limit=...)`. Em funções com vários valores
  do mesmo tipo (dois `datetime`, dois `int`), isso evita trocar a ordem sem
  perceber. O PulseOps usa esse padrão em quase todos os serviços.
- **Valores padrão**: `create_monitor(..., resolver: Resolver | None = None)`.
- **`**fields`** junta argumentos nomeados num `dict`: `log_context(monitor_id=1,
  run_key="...")` em `logs.py`.
- **Funções como valores**: em `web/api.py`, `operations = {"pause":
  monitor_service.pause_monitor, ...}` guarda funções num dicionário e escolhe qual
  chamar pelo nome da ação.

## Imports e módulos

Cada arquivo `.py` é um **módulo**; cada pasta com `__init__.py` é um **pacote**.
`from pulseops.domain.health import HealthTracker` busca a classe no arquivo
`src/pulseops/domain/health.py`. O projeto usa o layout `src/`: o código fica em
`src/pulseops/` e só é importável depois de instalado (`uv sync` instala o próprio
projeto). Isso evita importar sem querer arquivos soltos da pasta atual.

Os imports seguem uma direção: `web` e `worker` importam `services`; `services`
importa `domain`, `db` e `security`; `domain` não importa nada do projeto. Essa
direção é o que torna o domínio testável sem banco.

## Classes e instâncias

Uma **classe** é um molde; uma **instância** é um objeto criado a partir dele.
`HealthTracker(Thresholds(3, 2))` cria uma instância que guarda os limiares em
`self._thresholds`. O `self` é a própria instância, passado automaticamente.

**Dataclasses** geram `__init__`, comparação e representação a partir das
anotações. `@dataclass(frozen=True)` torna a instância imutável:

@@trecho src/pulseops/domain/health.py 46-62

`TrackerState` é imutável de propósito: o `HealthTracker` nunca altera o estado
recebido; ele devolve um estado novo com `dataclasses.replace(...)`. Assim fica
impossível um teste "contaminar" o estado de outro, e a função é fácil de
entender: entra estado e observação, sai decisão.

## Encapsulamento e composição

**Encapsulamento** é esconder os detalhes atrás de uma interface pequena. O
`HealthTracker` expõe só `apply(state, observation)`; as regras ficam em métodos
privados (`_on_failure`, `_on_success`, com `_` indicando "uso interno"). Quem
chama não precisa saber como a contagem funciona.

**Composição** é montar um objeto a partir de outros, em vez de herdar.
Exemplos:

- `HealthTracker` **tem** um `Thresholds`.
- `Worker` **tem** um `Checker`, um `Notifier`, um `Clock` e uma fábrica de
  sessões, recebidos no construtor.
- `GuardedNetworkBackend` **tem** uma `DestinationPolicy`, um `Resolver` e o
  backend de rede real, a quem repassa a conexão depois de validar.

A alternativa seria herança, por exemplo um `WorkerDeTeste(Worker)` que
sobrescrevesse o método de fazer requisição. Com composição, o teste só entrega
outro `Checker` ao mesmo `Worker`. Nada de herança foi necessário no código de
domínio; ela aparece só onde a biblioteca exige (`Base(DeclarativeBase)` no
SQLAlchemy, `BaseModel` no Pydantic, `BaseSettings`).

## Protocolos (interfaces)

Um `Protocol` descreve **o que** um objeto precisa ter, sem dizer de qual classe
ele vem. Qualquer classe com os mesmos métodos serve (é a "tipagem estrutural",
verificada pelo mypy).

@@trecho src/pulseops/clock.py 8-23

Protocolos usados no PulseOps:

| Protocolo | Implementação real | Dublê nos testes |
|---|---|---|
| `Clock` (`clock.py`) | `SystemClock` | `FakeClock`: tempo parado que o teste avança |
| `Checker` (`checks/checker.py`) | `HttpChecker` | `HttpChecker` com `httpx.MockTransport` (`ScriptedTarget`) |
| `Notifier` (`notifications/webhook.py`) | `WebhookNotifier` | `RecordingNotifier`, que só anota o que receberia |
| `Resolver` (`security/transport.py`) | `SystemResolver` | `FakeResolver`, com respostas DNS fixas |

`SystemClock` nem menciona `Clock`: ele simplesmente tem `now()` e `monotonic()`.

## Exceções

Uma **exceção** interrompe o fluxo normal e sobe pela pilha de chamadas até
alguém tratá-la com `try/except`.

- **Exceções próprias** (`services/errors.py`): `NotFoundError`, `ConflictError`,
  `ValidationFailedError`. Os serviços as levantam sem saber de HTTP; as rotas as
  traduzem em 404, 409 e 422.
- **`raise ... from exc`** preserva a causa original. Em
  `security/transport.py`, um `OSError` do DNS vira `httpcore.ConnectError` com a
  causa encadeada, e o verificador consegue olhar a cadeia para separar falha de
  DNS de falha TLS (`checker.py`, `_classify_connect_error`).
- **Barreira final**: em `Worker._run_one`, um `except Exception` em volta do
  verificador transforma qualquer erro inesperado em `INTERNAL_ERROR`, que não
  conta como falha do alvo. Sem isso, um bug do PulseOps derrubaria a tarefa e
  ninguém saberia.
- **Exceções de bibliotecas** que precisaram de cuidado viraram bugs reais: B4
  (`UnicodeEncodeError` no Argon2) e B5 (`ZoneInfoNotFoundError` herda de `KeyError`,
  que o Pydantic não converte em erro de validação).

## Context managers

Um *context manager* executa algo na entrada e garante algo na saída, mesmo se
houver exceção, com `with` (ou `async with`).

| Onde | O que garante |
|---|---|
| `async with sessions.begin() as session:` | `COMMIT` se o bloco terminar bem, `ROLLBACK` se houver exceção, e devolve a conexão |
| `async with asyncio.timeout(target.timeout_seconds):` (`checker.py`) | Cancela a requisição inteira se passar do prazo |
| `with log_context(monitor_id=..., run_key=...):` (`logs.py`) | Todo log dentro do bloco ganha esses campos; ao sair, o contexto anterior volta |
| `async with app.router.lifespan_context(app):` (testes) | Executa a inicialização e o encerramento da aplicação |

`log_context` é um context manager **escrito no projeto**, com `@contextmanager`:

@@trecho src/pulseops/logs.py 35-43

O `try/finally` é o que garante a restauração. `ContextVar` faz o contexto valer
só para a tarefa `asyncio` atual: dois checks rodando ao mesmo tempo não misturam
o `monitor_id` um do outro.

## Tipagem

Anotações como `def apply(self, state: TrackerState, obs: Observation) -> Decision`
não mudam a execução, mas permitem que o **mypy** confira o código antes de rodar
(modo estrito, ADR 0009). O que o projeto usa:

- `X | None` para valores opcionais.
- `list[int]`, `dict[str, Any]`, `frozenset[tuple[str, int]]`.
- `Mapped[int]` nas entidades do SQLAlchemy 2.x, que liga o tipo Python à coluna.
- `Annotated[AsyncSession, Depends(get_db)]` em `web/deps.py`: o tipo e, junto, a
  instrução para o FastAPI de como obter o valor.
- `Protocol`, visto acima.
- `TypeVar` em `scripts/demo_flow.py` (`wait_for` devolve o mesmo tipo que a
  função testada devolve).

## async/await

Um programa que faz rede passa a maior parte do tempo **esperando**. Com
`asyncio`, uma única thread alterna entre várias tarefas: quando uma diz
`await` (vou esperar a rede), outra pode andar.

- `async def` define uma **corrotina**; chamá-la não executa nada até alguém
  fazer `await` nela ou transformá-la em tarefa.
- `await algo()` pausa a corrotina atual até `algo` terminar.
- `asyncio.create_task(coro)` põe a corrotina para rodar "em paralelo" com as
  outras. O worker cria uma tarefa por check (`runner.py`, `_dispatch`).
- `asyncio.gather(*tarefas)` espera várias de uma vez (as entregas de um lote).
- `asyncio.Event` é um sinal: uma tarefa espera (`await evento.wait()`) até outra
  chamar `evento.set()`. O worker usa um para parar (`stop`) e outro para saber
  que uma vaga abriu (`_slot_freed`).

**Regra de ouro:** nada que bloqueie pode rodar dentro de uma corrotina. Um
`time.sleep(5)` ou uma consulta síncrona ao banco travaria **todas** as tarefas.
Por isso o projeto usa o driver assíncrono do PostgreSQL, o `httpx.AsyncClient` e
`loop.getaddrinfo` (que roda a resolução de DNS em outra thread) em vez de
`socket.getaddrinfo` direto.

## Concorrência e seus limites

Concorrência não é ilimitada: cada check aberto usa uma conexão de rede, memória
e, na gravação, uma conexão do banco. O worker nunca tem mais que
`worker_concurrency` (padrão 20) checks em andamento: `_dispatch` reserva no banco
só o número de vagas livres. O pool do banco tem 10 conexões (`db/session.py`),
compartilhadas por todas as tarefas: se mais tarefas quiserem gravar ao mesmo
tempo, esperam na fila do pool.

Outro limite: **uma `AsyncSession` nunca é compartilhada entre tarefas**. A sessão
guarda o estado de uma transação; duas tarefas usando a mesma sessão misturariam
comandos de transações diferentes. Cada função de `services/processing.py` abre a
própria sessão com `async with sessions.begin()`.

O que asyncio **não** dá: paralelismo de CPU. Tudo roda numa thread; se o trabalho
fosse cálculo pesado, seria preciso processos. Para o PulseOps, que espera rede,
asyncio é suficiente (*só para comparação*: threads e `multiprocessing` não são
usados).

## Injeção de dependências

Injetar uma dependência é **receber de fora** aquilo de que uma peça precisa, em
vez de criá-lo dentro dela. Dois estilos aparecem:

1. **Pelo construtor ou por parâmetro.** `Worker(sessions=..., checker=...,
   notifier=..., clock=..., settings=...)`; `create_app(settings, sessions=...,
   clock=..., resolver=...)`. Em produção, `worker/__main__.py` passa os objetos
   reais; nos testes, `tests/support_db.make_worker` passa dublês.
2. **Pelo FastAPI (`Depends`).** Em `web/deps.py`, `Db = Annotated[AsyncSession,
   Depends(get_db)]` diz: "para obter este parâmetro, chame `get_db`". Uma rota que
   declara `db: Db` recebe uma sessão nova por requisição, fechada no fim.
   `ApiAuth` encadeia: para autenticar, precisa da sessão do banco e do estado da
   aplicação, e o FastAPI resolve a cadeia sozinho.

O ganho prático: os testes controlam o tempo (`FakeClock`), a rede
(`ScriptedTarget`, `FakeResolver`) e os alertas (`RecordingNotifier`) sem mudar uma
linha do código de produção.
