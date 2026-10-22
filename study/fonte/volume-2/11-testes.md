# D11 — Os testes

São 3.130 linhas em 31 arquivos (`wc -l tests/*.py tests/*/*.py`), com 173 funções de
teste que o pytest expande em 251 casos, por causa de `@pytest.mark.parametrize`
(`uv run pytest --collect-only -q`). Os testes se repetem em forma: prepare,
execute, confira. Por isso este capítulo explica as **peças compartilhadas** linha a
linha, mostra um exemplo de cada padrão e resume os outros arquivos numa tabela.

Os três arquivos `__init__.py` (`tests/`, `tests/unit/`, `tests/integration/`)
estão vazios. Só existem para que `from tests.support import ...` funcione.

## `tests/conftest.py`

**Finalidade.** As *fixtures* compartilhadas. Uma *fixture* é uma função que prepara
algo para o teste. O teste a pede pelo nome do parâmetro, e o pytest a executa antes.

**Relações.** O pytest carrega o `conftest.py` sozinho; nenhum teste o importa, a não
ser para usar `login` e as constantes.

@@trecho tests/conftest.py 1-56

- Linhas 1–6: a regra: PostgreSQL de verdade, nunca SQLite. Constraints parciais,
  `FOR UPDATE SKIP LOCKED` e *advisory locks* não existem no SQLite, e um teste nele
  provaria pouco.
- Linhas 28–31: a URL vem de `PULSEOPS_TEST_DATABASE_URL`, ou usa o banco local da
  porta 5433.
- Linha 32: o usuário e a senha de teste. Ficam no código porque não protegem nada
  (S105 e S106 estão liberados para `tests/`).
- Linhas 35–42: apaga e recria o banco de teste. `WITH (FORCE)` derruba conexões
  abertas. **Ponto de atenção:** a função apaga **o banco que a variável indicar**. Se
  alguém apontasse `PULSEOPS_TEST_DATABASE_URL` para um banco com dados reais, eles
  seriam perdidos. A proteção é só o nome padrão (`pulseops_test`); não há uma trava
  que recuse outros nomes.
- Linhas 45–48: monta a configuração do Alembic com a URL do teste. O `env.py` das
  migrações lê `config.attributes["database_url"]` (D3).
- Linhas 51–55: `scope="session"`: recria o banco e aplica as migrações **uma vez**
  por execução da suíte, e não a cada teste. Assim, os testes rodam sobre o esquema
  que as migrações criam, o mesmo da produção, e não sobre `create_all`.

@@trecho tests/conftest.py 58-98

- Linhas 58–62: um engine para a suíte toda.
- Linhas 65–71: antes de **cada** teste, `TRUNCATE` em todas as tabelas, com
  `RESTART IDENTITY` (os ids voltam a 1) e `CASCADE`. Cada teste começa com o banco
  vazio e não depende da ordem em que os outros rodaram.
- Linhas 74–81: um relógio falso e um resolvedor falso novos por teste.
- Linhas 89–97: a aplicação com as peças falsas. `lifespan_context` roda o *lifespan*
  (D8) como num servidor de verdade. `ASGITransport` entrega as requisições direto à
  aplicação, **sem rede**: o teste exercita roteamento, dependências, cookies e
  templates, mas não abre porta nenhuma.

@@trecho tests/conftest.py 100-132

- Linhas 103–118: login pelo **formulário**, igual a um navegador: lê o token do
  login, envia, espera 303 e lê o token CSRF da sessão no painel. Os testes de API
  passam pelo mesmo login da interface.
- Linhas 121–124: cria a operadora.
- Linhas 127–132: `api` é o cliente já logado, com o cabeçalho CSRF em toda
  requisição. Um teste que pede `api` recebe, encadeadas, as fixtures `app_client`,
  `operator`, `sessions`, `engine` e `database_url`.

## `tests/support.py`

**Finalidade.** As peças falsas que substituem o tempo, o DNS e a rede.

@@arquivo tests/support.py

- Linha 12: uma data fixa para todos os testes. Um teste que usasse a data real
  poderia mudar de resultado conforme o dia.
- Linhas 15–30: o `FakeClock`. Fica **parado** até o teste chamar `advance`. Com
  ele, "esperar 60 s" é instantâneo, e o resultado não depende da velocidade da
  máquina. É por isso que a suíte não tem `sleep` (volume 1, parte G).
- Linhas 33–46: o `FakeResolver`. Nomes conhecidos resolvem para os IPs que o teste
  escolheu; `.invalid` falha (é um domínio reservado que nunca existe); o resto vai
  para um IP público. `calls` registra o que foi consultado. É ele que permite
  simular o DNS *rebinding*: o teste troca o IP no meio do caminho.
- Linhas 49–85: o `ScriptedTarget`, um alvo HTTP falso. O `httpx.MockTransport`
  chama `handler` em vez de abrir uma conexão. Cada modo produz o que a rede real
  produziria: 500, `ReadTimeout`, conexão recusada ou erro de certificado. A
  lentidão avança o relógio falso (linha 66) em vez de dormir.
- Linhas 74–80: para simular o erro TLS, o código levanta um
  `SSLCertVerificationError` e o encadeia (`from exc`) num `ConnectError`, porque é
  assim que o httpx entrega esse erro. O verificador (D5) procura a causa encadeada
  para classificar como `tls_error`.
- Linhas 83–85: um `HttpChecker` de verdade, só com o transporte trocado.

## `tests/support_db.py`

**Finalidade.** Atalhos dos testes de integração: criar monitores, montar o worker,
dar um "tique" e ler o banco.

@@trecho tests/support_db.py 19-73

- Linhas 19–27: a configuração base de um monitor. Cada teste muda só o que importa
  (`create_monitor(..., failure_threshold=1)`), com `dataclasses.replace`.
- Linhas 30–39: cria pelo **serviço**, com as mesmas validações da API.
- Linhas 42–49: um notificador falso que registra os envios e devolve sucesso, a
  menos que o teste troque `result`.
- Linhas 52–66: um `Worker` real com o alvo falso.
- Linhas 69–73: `tick` executa os checks vencidos e avança o relógio um intervalo.
  Uma sequência de `tick`s é uma linha do tempo, sem espera real.

@@trecho tests/support_db.py 115-142

- `insert_checks` grava checks prontos em horários exatos, sem passar pelo worker.
  Os testes de métricas usam isso para montar janelas com valores conhecidos.
- **Ponto de atenção:** a linha 138 grava `status_code=200` só para `healthy` e
  `slow`, e `None` para os demais. Um check `unexpected_status` real tem um código
  (por exemplo, 500). Para as métricas isso não muda nada, porque elas não leem
  `status_code`, mas é uma simplificação do dado de teste.

As funções das linhas 76–112 (`reload`, `incidents_of`, `count_checks` e
`update_monitor`) só abrem uma sessão e leem ou alteram uma coisa.

## Padrão 1: regra pura, sem banco

`tests/unit/test_health.py` testa a regra de saúde (D2) sem banco nem rede.

@@trecho tests/unit/test_health.py 18-45

- Linha 18: o estado inicial, sem dados.
- Linhas 21–31: `run` aplica uma sequência de resultados e devolve o estado final e
  as decisões. Cada observação fica um minuto depois da anterior.
- Linha 34: `F` e `S` deixam as sequências legíveis: `[F, F, S]`.
- Linhas 41–45: o primeiro caso do exemplo obrigatório: falha, falha, sucesso **não**
  abre incidente e deixa os contadores em (0, 1).

Arquivos com o mesmo padrão: `test_monitor_rules.py`, `test_status_codes.py`,
`test_metrics_formulas.py`, `test_url_policy.py`, `test_charts.py`,
`test_passwords.py`, `test_config.py`.

## Padrão 2: um cenário de ponta a ponta com o worker real

@@trecho tests/integration/test_incident_lifecycle.py 21-68

- Linhas 25–27: monitor, alvo falso e worker real.
- Linhas 29–34: falha, falha, sucesso: nenhum incidente.
- Linhas 36–44: três falhas: um incidente aberto, com o motivo **exato** e o início
  anterior à confirmação.
- Linhas 46–49: mais quatro falhas atualizam o **mesmo** incidente (7 falhas no
  total).
- Linhas 51–58: um sucesso não encerra; o segundo encerra, com o motivo.
- Linhas 60–68: só **dois** alertas (abertura e recuperação), não um por falha, e a
  linha do tempo completa.

Mesmo padrão: `test_first_slice.py`, `test_delivery.py`, `test_retention.py` e a
maior parte de `test_consistency.py`.

## Padrão 3: provar que o banco recusa o impossível

@@trecho tests/integration/test_consistency.py 104-141

- Linhas 104–129: tenta inserir **direto no banco** um segundo incidente aberto para
  o mesmo monitor, sem passar pelo código. O teste espera um `IntegrityError` com o
  nome do índice único parcial. Assim fica provado que a garantia está no banco, e
  não depende de o código estar certo.
- Linhas 132–141: quatro reservas **ao mesmo tempo** (`asyncio.gather`) sobre dez
  monitores. A soma dá exatamente dez, sem repetição: é o `FOR UPDATE SKIP LOCKED`
  funcionando com concorrência de verdade, em conexões separadas.

## Padrão 4: segurança com rede simulada no nível do socket

@@trecho tests/unit/test_transport.py 38-82

- Linhas 38–48: um *backend* de rede falso do `httpcore` (a biblioteca por baixo do
  httpx). Ele registra para onde tentaram conectar e devolve uma resposta pronta.
- Linhas 51–59: monta o cliente protegido de verdade e troca só o socket final.
  **Ponto de atenção:** a linha 56 acessa atributos **privados** do httpx
  (`_transport._pool._network_backend`). Funciona na versão travada no `uv.lock`, mas
  uma atualização do httpx pode quebrar este teste sem que o PulseOps tenha mudado.
- Linhas 62–69: conecta no IP validado e mantém o cabeçalho `Host` original.
- Linhas 72–82: o DNS *rebinding*. No cadastro, o nome aponta para um IP público e é
  aceito. Depois, o "DNS" passa a responder `127.0.0.1`. A requisição é recusada
  **e nenhuma conexão é aberta** (linha 82). Essa última linha é a prova mais
  importante: recusar depois de conectar já seria tarde.

## Padrão 5: migrações num banco vazio

@@trecho tests/integration/test_migrations.py 31-66

- Linhas 31–41: um banco à parte, criado vazio só para este teste.
- Linhas 44–54: aplica as migrações e compara o banco resultante com os modelos
  (`compare_metadata`, a mesma comparação do `alembic revision --autogenerate`).
  Uma lista vazia de diferenças prova que a migração e os modelos dizem a mesma
  coisa.
- Linhas 57–66: desce até o zero (só sobra a tabela `alembic_version`) e sobe de
  novo.

## Os demais arquivos

| Arquivo | Casos | O que cobre | Padrão |
|------------------------|-----|------------------------|----------|
| `unit/test_charts.py` | 4 | gráfico de latência, B9 e B10 | 1 |
| `unit/test_checker.py` | 15 | classificação de cada resultado de check | alvo falso (`ScriptedTarget`) |
| `unit/test_config.py` | 3 | padrões e validação das variáveis | 1 |
| `unit/test_health.py` | 17 | regra de saúde e incidentes | 1 |
| `unit/test_lab_receiver.py` | 3 | deduplicação do receptor do laboratório | 1 |
| `unit/test_logging.py` | 4 | logs JSON, contexto e segredos mascarados | 1 |
| `unit/test_metrics_formulas.py` | 8 | percentil e razões | 1 |
| `unit/test_monitor_rules.py` | 16 | regras combinadas do cadastro | 1 |
| `unit/test_passwords.py` | 3 | Argon2 e hash corrompido (B4) | 1 |
| `unit/test_status_codes.py` | 10 | leitura de `200-299,304` | 1 |
| `unit/test_transport.py` | 12 | SSRF no momento da conexão | 4 |
| `unit/test_url_policy.py` | 38 | URLs aceitas e recusadas | 1 |
| `integration/test_api_history.py` | 8 | paginação, filtros e janelas de tempo | API |
| `integration/test_api_monitors.py` | 17 | cadastro, ações e conflitos pela API | API |
| `integration/test_auth.py` | 26 | sessão, CSRF, cookies e redirecionamento | API e páginas |
| `integration/test_cli.py` | 2 | `pulseops create-admin` | 2 |
| `integration/test_consistency.py` | 14 | duplicidade, concorrência, reinício e B8 | 2 e 3 |
| `integration/test_dashboard.py` | 12 | páginas, escape e cabeçalhos | páginas |
| `integration/test_delivery.py` | 17 | outbox, retentativas e webhook | 2 |
| `integration/test_first_slice.py` | 1 | o primeiro fluxo completo | 2 |
| `integration/test_health_endpoints.py` | 2 | `/health/live` e `/health/ready` | API |
| `integration/test_incident_lifecycle.py` | 9 | ciclo de vida dos incidentes | 2 |
| `integration/test_metrics.py` | 6 | métricas sobre dados gravados | `insert_checks` |
| `integration/test_migrations.py` | 2 | migração do zero e volta | 5 |
| `integration/test_retention.py` | 2 | limpeza de checks antigos, preservando incidentes | 2 |

"API" e "páginas" querem dizer: o teste usa as fixtures `api` ou `app_client` e
confere o status, o JSON ou o HTML devolvido.

**Como estudar este capítulo.** Escolha um teste da tabela, leia só o nome e
escreva o que você acha que ele faz. Depois abra o arquivo e compare. Em seguida,
quebre de propósito a linha do código que ele protege (numa cópia, como na parte J
do volume 1) e confira que o teste falha. Um teste que não falha quando o código está
errado não protege nada.
