# D2 — Domínio: as regras sem banco e sem rede

Os arquivos de `src/pulseops/domain/` só usam a biblioteca padrão do Python. Não
importam SQLAlchemy, HTTPX nem FastAPI. Por isso as regras podem ser testadas com
objetos simples, em milissegundos (volume 1, parte G).

## `src/pulseops/domain/outcomes.py`

**Finalidade.** Lista as oito categorias de resultado de um check e diz quais
contam como falha do alvo.

**Dados.** Os valores são textos curtos (`"healthy"`, `"timeout"`...), os mesmos
gravados na coluna `checks.outcome` e aceitos pela constraint `ck_checks_outcome`.
**Relações.** Produzido por `checks/checker.py`; lido por `domain/health.py`,
`services/processing.py`, `services/queries.py` e pelos templates (rótulos).
**Testes.** `test_every_target_failure_category_counts` e
`test_internal_error_changes_nothing` (`tests/unit/test_health.py`).

@@trecho src/pulseops/domain/outcomes.py 1-28

- Linha 3: `StrEnum` (Python 3.11+) é uma enumeração cujos membros **também são
  textos**: `Outcome.TIMEOUT == "timeout"` é verdadeiro. Assim, o valor pode ir
  direto para o banco e para o JSON.
- Linhas 7–14: os oito membros. `BLOCKED` é o destino recusado pela política SSRF
  no momento da conexão; `INTERNAL_ERROR` é um erro do próprio PulseOps.
- Linhas 16–19: `is_failure` é uma *property*: lê-se como atributo
  (`outcome.is_failure`), sem parênteses. Consulta o conjunto `_FAILURES`.
- Linhas 21–24: `is_success`. **Observação honesta:** no commit explicado, essa
  propriedade não é usada em lugar nenhum; a regra de saúde trata "não é falha e
  não é erro interno" como sucesso. É código morto que poderia ser removido.
- Linhas 26–28: `label`, o texto em português para a tela.

@@trecho src/pulseops/domain/outcomes.py 31-50

- Linhas 31–39: as falhas do alvo, num `frozenset`. Erro interno fica de fora de
  propósito (RF03.1): se o PulseOps quebrar, isso não pode virar "o serviço caiu".
- Linhas 41–50: rótulos. Um dicionário indexado pelo próprio membro.

**Falhas possíveis.** Um valor de texto desconhecido em `Outcome("xyz")` levanta
`ValueError`; o banco já impede que um valor assim seja gravado.

## `src/pulseops/domain/status_codes.py`

**Finalidade.** Interpreta o texto da lista de status aceitos (`"200-299,304"`).

**Dados.** Entrada: texto digitado pela operadora. Saída: `AcceptedStatusCodes`,
uma tupla de faixas `(início, fim)`. **Relações.** Usado em
`domain/monitor_rules.py` (validação) e `services/processing.py` (monta o alvo do
check). **Testes.** `tests/unit/test_status_codes.py`
(`test_ranges_and_single_codes`, `test_invalid_specs_are_rejected`).

@@arquivo src/pulseops/domain/status_codes.py

- Linhas 8–10: `@dataclass(frozen=True)` gera `__init__`, `__eq__` e `__repr__`
  e impede alterar os campos depois de criado. `tuple[tuple[int, int], ...]` é "uma
  tupla de qualquer tamanho cujos itens são pares de inteiros".
- Linhas 12–13: `__contains__` é o método que o Python chama em `x in objeto`.
  Confere que é inteiro e que cai em alguma faixa. `any(...)` para no primeiro
  verdadeiro.
- Linhas 15–16: `__str__` refaz o texto (`200-299,304`), para exibir.
- Linha 21: remove espaços, então `"200 - 299"` é aceito.
- Linhas 22–25: vazio ou longo demais é recusado.
- Linhas 28–38: para cada trecho separado por vírgula, `partition("-")` divide em
  três partes: antes do hífen, o hífen (ou vazio) e depois. Linha 30: os dois
  lados precisam ser só dígitos (isso recusa números negativos e letras). Linhas
  32–33: sem hífen, a faixa é de um código só. Linhas 34–37: códigos HTTP vão de
  100 a 599, e a faixa não pode estar invertida.
- Linha 39: ordena as faixas, para o texto exibido ficar previsível.

**Falhas possíveis.** Entrada inválida levanta `ValueError` com mensagem própria
para a operadora (é mostrada no formulário).

## `src/pulseops/domain/monitor_rules.py`

**Finalidade.** Limites de cada campo do monitor e as validações que dependem de
mais de um campo.

**Dados.** Recebe um `MonitorConfig` (vindo do JSON da API ou do formulário) e
devolve uma lista de `FieldError` (campo + mensagem). **Relações.** Chamado por
`services/monitors.py`; o `MonitorConfig` é montado por `web/schemas.py` e
`web/pages.py`. Os mesmos limites estão repetidos como constraints no banco
(`db/models.py`), como segunda linha de defesa. **Testes.**
`tests/unit/test_monitor_rules.py` (seis testes: padrões válidos, fora de faixa,
timeout menor que intervalo, limite de latência, modo demo, todos os erros juntos).

@@trecho src/pulseops/domain/monitor_rules.py 7-37

- Linhas 7–12: limites como constantes nomeadas. `86_400` é o mesmo que `86400`
  (o sublinhado só ajuda a ler). A linha 8 atribui duas constantes de uma vez.
- Linhas 15–23: campos que, se mudarem, mudam o **significado** dos contadores.
  Mudar o nome ou a descrição não zera nada; mudar a URL ou o timeout sim. Usado
  por `update_monitor` em `services/monitors.py`.
- Linhas 26–37: a configuração com os valores padrão do projeto (intervalo 60 s,
  timeout 5 s, 3 falhas para abrir, 2 sucessos para fechar).

@@trecho src/pulseops/domain/monitor_rules.py 46-88

- Linha 46: o `*` obriga `min_interval_seconds` a ser passado pelo nome. Ele vem
  da configuração (30 s, ou 2 s no modo demo).
- Linha 47: a docstring diz a intenção: devolver **todos** os erros, não parar no
  primeiro. O formulário mostra tudo de uma vez.
- Linhas 50–52: uma função dentro da função (*closure*). Ela enxerga a lista
  `errors` de fora e acrescenta nela.
- Linhas 54–62: validações de um campo só.
- Linhas 64–69: faixas numéricas, todas com a mesma função.
- Linhas 71–72: validação entre dois campos: o timeout precisa ser menor que o
  intervalo.
- Linhas 74–81: o limite de lentidão depende do timeout: entre 50 ms e o timeout
  em milissegundos.
- Linhas 83–86: reaproveita `parse_status_codes` e transforma a exceção em erro de
  campo.

**Falhas possíveis.** Nenhuma exceção sai daqui: tudo vira item da lista.

## `src/pulseops/domain/health.py`

**Finalidade.** A regra central: dado o estado do monitor e o resultado de um
check, calcula o novo estado e o que fazer com o incidente (abrir, atualizar,
resolver ou nada), com o motivo em texto.

**Dados.** Entrada: `TrackerState` (lido das colunas do monitor e da existência de
incidente aberto) e `Observation` (resultado do check). Saída: `Decision`.
Nenhum efeito colateral. **Relações.** Chamado só por `_apply_domain` em
`services/processing.py`; `Health` também é usado em `services/monitors.py` e nos
templates. **Testes.** `tests/unit/test_health.py` (17 testes, incluindo os
quatro do exemplo obrigatório) e, com banco,
`tests/integration/test_incident_lifecycle.py`.

@@trecho src/pulseops/domain/health.py 15-38

- Linhas 15–30: os cinco estados de saúde de um monitor. `label` monta um
  dicionário e indexa pelo próprio membro.
- Linhas 33–37: as quatro ações possíveis sobre o incidente. A regra **não** abre
  incidente: ela devolve `OPEN`, e quem chama (`processing.py`) faz a gravação.
  Separar decisão de efeito é o que deixa a regra testável sem banco.

@@trecho src/pulseops/domain/health.py 40-73

- Linhas 40–43: os dois limiares, agrupados num objeto.
- Linhas 46–54: o estado que a regra lê e altera. `first_failure_at` guarda o
  horário da primeira falha da sequência (o "início" do incidente).
  `incident_open` diz se já há incidente aberto.
- Linhas 57–61: o que se observou num check.
- Linhas 64–73: o resultado da regra. `previous_health` permite saber se a saúde
  mudou (`health_changed`, linhas 71–73), o que decide se uma linha nova vai para
  `health_changes`.

Todos são `frozen=True`: imutáveis. A regra nunca altera o estado recebido; ela
cria um novo com `replace(...)`, que copia o objeto trocando só os campos
indicados.

@@trecho src/pulseops/domain/health.py 76-99

- Linhas 86–87: o rastreador guarda só os limiares.
- Linhas 89–96: erro interno sai cedo. Devolve o **mesmo** estado, ação `NONE` e
  um motivo. Nada soma, nada zera (RF03.8).
- Linhas 97–99: falha vai para `_on_failure`; o resto (saudável ou lento) vai para
  `_on_success`.

@@trecho src/pulseops/domain/health.py 101-128

- Linha 102: soma uma falha.
- Linha 103: se é a **primeira** falha da sequência (o contador anterior era 0),
  o início é o horário desta observação; senão, mantém o início anterior. Uma
  expressão `a if condição else b`.
- Linhas 104–109: novo estado: falhas somadas, sucessos zerados.
- Linhas 112–115: já existe incidente aberto: ação `UPDATE`, saúde
  "indisponível". O mesmo incidente recebe a nova falha; nunca um segundo.
- Linhas 117–124: atingiu o limiar: ação `OPEN`, saúde "indisponível". O motivo
  monta "Incidente confirmado após 3 falhas consecutivas; último resultado: ...".
  `_plural` (linhas 169–170) escolhe singular ou plural.
- Linhas 126–128: abaixo do limiar: "degradado", com o progresso ("Falha 2 de 3
  necessárias para abrir incidente").

@@trecho src/pulseops/domain/health.py 130-166

- Linhas 131–137: soma um sucesso, zera as falhas e esquece o início da sequência.
- Linhas 140–156: há incidente aberto.
  - Linhas 141–149: se os sucessos atingiram o limiar de recuperação, ação
    `RESOLVE`. A saúde final é "degradado" se o último sucesso foi lento (linha
    142), e "saudável" se foi rápido. Recuperar não apaga a lentidão.
  - Linhas 150–156: ainda não atingiu: continua "indisponível", com o progresso
    ("Sucesso 1 de 2...").
- Linhas 158–162: sem incidente, resposta lenta: "degradado", sem ação.
- Linhas 163–166: sem incidente, resposta rápida: "saudável".

**Falhas possíveis.** Nenhuma exceção é levantada aqui. O risco é de **regra**:
como o lento conta como sucesso, um serviço que alterna lento e timeout nunca abre
incidente com limiar 2 (volume 1, gabarito J10). É uma consequência documentada da
ADR 0004.

## `src/pulseops/domain/metrics.py`

**Finalidade.** Fórmulas das métricas: percentil, proporção e duração de incidente
recortada à janela.

**Dados.** Listas de números (latências em ms), contagens inteiras e datas com
fuso. Saídas `float`, `None` ou `timedelta`. **Relações.** `ratio` e
`clipped_duration` são usados em `services/queries.py`; `nearest_rank` é a
referência que o teste compara com o SQL. **Testes.**
`tests/unit/test_metrics_formulas.py` (oito testes) e
`test_sql_percentile_matches_nearest_rank`.

@@arquivo src/pulseops/domain/metrics.py

- Linhas 8–19: percentil *nearest-rank*. Linhas 13–14 recusam percentil fora de
  (0, 100]. Linhas 15–16: sem amostras, `None` (vira "N/A"). Linhas 17–19: ordena
  e pega a posição `ceil(p/100 × n)`; como listas do Python começam em 0, usa
  `rank - 1`.
- Linhas 22–26: proporção em porcentagem; sem base, `None`. A docstring é a
  regra do projeto: nunca inventar 0% ou 100%.
- Linhas 29–42: quanto de um incidente cai dentro da janela `[início, fim)`. O fim
  efetivo é o menor entre o fim da janela e o fim do incidente (ou "agora", se
  ainda aberto, linha 40). O começo efetivo é o maior entre os dois começos (linha
  41). Se o incidente está todo fora, a diferença seria negativa, e `max(...,
  timedelta(0))` devolve zero (linha 42).

**Falhas possíveis.** `nearest_rank` com percentil inválido levanta
`ValueError`; no código de produção ele só é chamado pelos testes (o painel usa o
`percentile_disc` do banco).
