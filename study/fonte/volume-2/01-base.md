# D1 — Base do pacote: versão, configuração, relógio, logs e linha de comando

## `src/pulseops/__init__.py`

**Finalidade.** Marca a pasta `src/pulseops` como pacote Python e define a versão.

@@arquivo src/pulseops/__init__.py

- Linha 1: *docstring* do módulo, a descrição curta que aparece em `help(pulseops)`.
- Linha 3: `__version__` é uma convenção da comunidade Python. É lida pelo worker
  para montar o `User-Agent` (`PulseOps/0.1.0`) e pela parte B do volume 1 para
  conferir a instalação.

**Dados.** Uma constante de texto. **Relações.** `worker/__main__.py`,
`web/app.py`. **Falhas.** Nenhuma. **Testes.** Indiretamente, por todos (o pacote
precisa importar).

Os outros `__init__.py` (`checks/`, `db/`, `domain/`...) são **vazios**: só existem
para que cada pasta seja um subpacote importável (`from pulseops.domain import
health`).

## `src/pulseops/config.py`

**Finalidade.** Lê toda a configuração das variáveis de ambiente `PULSEOPS_*` e
valida os valores na inicialização.

**Dados.** Texto vindo do ambiente do processo ou do arquivo `.env`, convertido
pelo Pydantic para `str`, `int`, `float` e `bool`. **Relações.** Instanciado em
`web/app.py`, `worker/__main__.py`, `cli.py` e `migrations/env.py`; os valores
viram parâmetros dos serviços. **Testes.** `tests/unit/test_config.py`
(`test_minimum_interval_depends_on_demo_mode`, `test_allowed_ports_parsing`,
`test_unknown_timezone_is_rejected`).

@@trecho src/pulseops/config.py 1-14

- Linha 3: `cached_property` calcula um atributo na primeira leitura e guarda o
  resultado (usado nas linhas 48–70).
- Linha 4: `ZoneInfo` representa um fuso horário da base IANA
  (`America/Sao_Paulo`).
- Linha 7: `BaseSettings` é a classe do pacote `pydantic-settings` que preenche os
  campos a partir do ambiente.
- Linha 10: `Settings` herda de `BaseSettings`: cada atributo anotado é uma
  variável de configuração.
- Linha 11: `env_prefix="PULSEOPS_"` faz o campo `database_url` ser lido de
  `PULSEOPS_DATABASE_URL`. `env_file=".env"` também lê o arquivo `.env`, se
  existir. `extra="ignore"` ignora variáveis desconhecidas (por exemplo
  `POSTGRES_PASSWORD`, que é do Compose) em vez de falhar.
- Linha 13: o valor padrão serve para desenvolvimento local; no Compose ele é
  sempre substituído. `postgresql+psycopg` diz ao SQLAlchemy para usar o driver
  psycopg 3.

@@trecho src/pulseops/config.py 16-35

Cada linha é um campo com tipo e padrão. `Field(default=..., ge=..., le=...)`
acrescenta limites: `ge` é "maior ou igual", `le` "menor ou igual", `gt` "maior
que". Um valor fora do limite impede o processo de iniciar, com uma mensagem que
diz qual variável está errada. Isso é melhor do que descobrir o erro horas depois.

| Linhas | Grupo | O que controlam |
|---|---|---|
| 16–19 | rede | modo demonstração, exceções do laboratório e portas permitidas (política SSRF) |
| 21–23 | painel | cookie só por HTTPS, duração da sessão (5 min a 7 dias, padrão 8 h) e fuso de exibição |
| 25–28 | worker | checks simultâneos, tick, quando o worker é considerado sem sinal, intervalo do heartbeat |
| 30–33 | webhooks | timeout, tentativas e espera exponencial |
| 35 | retenção | dias que os checks ficam guardados |

@@trecho src/pulseops/config.py 37-46

- Linhas 37–38: `@field_validator` registra uma função que valida um campo;
  `@classmethod` porque roda antes de a instância existir.
- Linhas 42–45: tenta criar o `ZoneInfo`. Se o fuso não existe, converte o erro
  para `ValueError`. O comentário explica por quê: `ZoneInfoNotFoundError` herda de
  `KeyError`, e o Pydantic só transforma `ValueError` e `AssertionError` em erro de
  validação. Era o bug **B5**.
- Linha 46: um validador precisa devolver o valor (que poderia ser transformado).

@@trecho src/pulseops/config.py 48-74

- Linhas 48–50: `timezone` devolve o objeto de fuso pronto, criado uma vez só.
- Linhas 52–54: transforma `"80,443,8080,8443"` em `frozenset({80, 443, 8080,
  8443})`. `frozenset` é um conjunto imutável; ler `porta in conjunto` é rápido.
  `if p.strip()` ignora vírgulas sobrando.
- Linhas 56–70: monta a lista de exceções do laboratório. Fora do modo demo,
  devolve vazio **mesmo que a variável esteja preenchida** (linha 59): a exceção
  nunca vaza para uma instalação normal. `rpartition(":")` divide pelo **último**
  `:`; `lab-target:8081` vira `("lab-target", 8081)`. Um item malformado levanta
  erro com a variável e o valor recebido (linha 68).
- Linhas 72–74: `@property` (sem cache, porque é barato) com o intervalo mínimo:
  2 s na demonstração, 30 s no modo normal.

**Falhas possíveis.** Variável com tipo errado (`PULSEOPS_WORKER_CONCURRENCY=abc`)
ou fora do limite: o Pydantic levanta `ValidationError` e o processo não sobe.
`PULSEOPS_ALLOWED_PORTS` com texto não numérico levanta `ValueError` na primeira
leitura de `allowed_port_set`.

## `src/pulseops/clock.py`

**Finalidade.** Define o relógio como uma dependência substituível. Nenhum código
do PulseOps chama `datetime.now()` diretamente.

@@arquivo src/pulseops/clock.py

- Linha 5: `Protocol` permite definir uma interface por **forma** (tipagem
  estrutural): qualquer classe com `now()` e `monotonic()` serve.
- Linhas 8–15: o protocolo. Os `...` (reticências) indicam corpo vazio; as
  docstrings dizem o contrato: `now()` em UTC e com fuso; `monotonic()` só para
  medir durações, porque nunca volta para trás (o relógio de parede pode ser
  ajustado pelo sistema e "voltar").
- Linhas 18–23: a implementação real. `datetime.now(UTC)` devolve um `datetime`
  com fuso. Um `datetime` **sem** fuso ("ingênuo") seria ambíguo; o PostgreSQL
  grava em `timestamptz`.

**Dados.** Saem `datetime` (UTC, com fuso) e `float` (segundos). **Relações.**
`SystemClock` é criado em `web/app.py` e `worker/__main__.py`; os testes usam
`FakeClock` (`tests/support.py`). **Falhas.** Nenhuma própria. **Testes.** Todos
os testes que usam `FakeClock` dependem deste contrato; o uso de `monotonic`
para medir a duração é testado em `tests/unit/test_checker.py`.

## `src/pulseops/logs.py`

**Finalidade.** Formata os logs como JSON, acrescenta contexto (monitor, execução)
e mascara segredos.

**Dados.** Recebe `logging.LogRecord` (mensagem, nível, campos extras). Produz uma
linha de texto JSON por evento, na saída padrão. **Relações.**
`configure_logging` é chamado por `web/app.py` e `worker/__main__.py`;
`log_context` é usado em `services/processing.py` e `worker/runner.py`;
`redact_text` também é usado em `services/alerts.py` (URL no payload do webhook).
**Testes.** `tests/unit/test_logging.py` (quatro testes: query e credenciais
mascaradas, campos sensíveis, contexto em todas as linhas, formato JSON).

@@trecho src/pulseops/logs.py 12-19

- Linha 12: `ContextVar` é uma variável cujo valor é **por tarefa assíncrona**.
  Dois checks rodando ao mesmo tempo têm cada um o seu contexto; um não vê o
  `monitor_id` do outro. Com uma variável global comum, eles se misturariam.
- Linha 14: palavras que, se aparecerem no **nome** de um campo, fazem o valor
  ser trocado por `[redacted]`.
- Linha 15: expressão regular que encontra uma URL seguida de `?query`. O grupo
  `(...)` captura a parte antes do `?`.
- Linha 16: encontra `http://usuario:senha@` no começo de uma URL.
- Linha 19: cria um `LogRecord` vazio só para descobrir quais atributos todo
  registro tem por padrão. O que não estiver nesse conjunto veio de `extra=` e deve
  ir para o JSON.

@@trecho src/pulseops/logs.py 22-43

- Linhas 22–24: troca credenciais por `[redacted]@` e a query por `?[redacted]`.
  `\1` repete o grupo capturado (o começo da URL).
- Linhas 27–32: decide pelo nome do campo primeiro; se não for sensível e for
  texto, ainda passa pela limpeza de URLs.
- Linhas 35–43: `log_context` é um *context manager* (`with log_context(...)`).
  Linha 38 lê o contexto atual; linha 39 grava um novo, juntando o antigo com os
  campos novos, e guarda o `token`; o `finally` (linha 42–43) restaura o anterior
  mesmo se houver exceção. Isso permite aninhar contextos.

@@trecho src/pulseops/logs.py 46-74

- Linhas 46–61: o formatador. Monta um dicionário com horário (em UTC, com
  milissegundos), nível, nome do logger e mensagem mascarada (linhas 48–53);
  acrescenta o contexto (54–55) e os campos extras (56–58); se houver exceção,
  acrescenta o *traceback* mascarado (59–60). `ensure_ascii=False` mantém os
  acentos legíveis; `default=str` converte o que o JSON não conhece (por exemplo
  `datetime`).
- Linhas 64–69: troca os *handlers* do logger raiz por um só, com o formatador
  JSON.
- Linhas 70–73: o uvicorn tem *handlers* próprios que imprimiriam a URL inteira.
  Removê-los e ligar `propagate` faz as linhas dele passarem pelo nosso
  formatador, que mascara a query.
- Linha 74: o HTTPX registra cada requisição em INFO; subir para WARNING evita
  uma linha por check.

**Falhas possíveis.** Um segredo em formato não previsto (no **caminho** da URL,
ou num campo com nome inocente) não é mascarado. Está listado como limitação
(volume 1, H32).

## `src/pulseops/cli.py`

**Finalidade.** Comando `pulseops create-admin`, que cria a operadora. É o único
jeito de criar usuário: não há cadastro pela web.

**Dados.** Nome de usuário pelo argumento `--username`; senha pelo terminal (sem
eco) ou pela entrada padrão. Grava uma linha em `operators`. **Relações.**
Registrado como comando em `pyproject.toml` (`[project.scripts]`); usa
`services/auth.py`. Chamado pelo README e por `scripts/demo.sh`. **Testes.**
`tests/integration/test_cli.py` (`test_create_admin_from_stdin`,
`test_short_password_is_rejected`).

@@trecho src/pulseops/cli.py 21-43

- Linha 21: função assíncrona porque o acesso a banco do projeto é assíncrono.
- Linha 23: um engine próprio com uma conexão só (`pool_size=1`); o comando é
  curto.
- Linhas 26–32: uma transação. Com `--exists-ok`, se o usuário já existe, devolve
  `False` sem erro. A demonstração usa isso para poder rodar várias vezes.
- Linhas 33–34: `finally` fecha o engine em qualquer caso.
- Linhas 37–43: com `--password-stdin`, lê uma linha da entrada padrão (útil em
  scripts: `echo senha | pulseops ...`); senão, `getpass` pede a senha duas vezes
  sem mostrar o que se digita. Senha nunca vai como argumento, porque argumentos
  aparecem no histórico do shell e na lista de processos (docstring, linhas 3–4).

@@trecho src/pulseops/cli.py 46-68

- Linhas 47–55: `argparse` monta a interface: subcomando obrigatório
  (`required=True`), `--username` obrigatório e duas opções booleanas
  (`store_true`).
- Linha 59: `asyncio.run` cria um event loop, executa a corrotina e fecha o loop.
- Linhas 60–62: erros esperados (senha curta, senhas diferentes, usuário
  repetido) são `ValueError`: imprime em `stderr` e devolve código 1.
- Linha 63: `!r` imprime o nome entre aspas (`'amanda'`).
- Linhas 67–68: permite rodar também como `python -m pulseops.cli`.

**Falhas possíveis.** Banco inacessível: a exceção do driver não é `ValueError`,
então sai com *traceback* e código diferente de zero. Senha com menos de 12
caracteres: "erro: a senha precisa ter pelo menos 12 caracteres", código 1.
