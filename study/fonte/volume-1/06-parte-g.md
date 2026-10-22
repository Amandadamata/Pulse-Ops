# Parte G — Testes, segurança e confiabilidade

## Teste unitário e teste de integração

O PulseOps tem 251 testes em duas pastas:

| Pasta | Quantos | O que testam | Precisam de banco? |
|---|---|---|---|
| `tests/unit/` | 133 | uma função ou classe isolada: regra de saúde, classificação de check, política SSRF, fórmulas | não |
| `tests/integration/` | 118 | várias peças juntas: API + serviços + PostgreSQL, worker + banco, migrações | sim, PostgreSQL de verdade |

Um **teste unitário** é rápido e aponta exatamente onde está o erro. Exemplo,
do arquivo `tests/unit/test_health.py`:

@@trecho tests/unit/test_health.py 21-45

- `run(...)` (linhas 21–32) é um ajudante: aplica uma lista de resultados à regra
  de saúde, um por minuto, e devolve o estado final e as decisões.
- `F, S` (linha 35) são apelidos curtos para "falha" (timeout) e "sucesso".
- O teste das linhas 41–45 é o exemplo obrigatório "falha, falha, sucesso não abre
  incidente". Ele não toca em banco nem em rede: só a regra pura de
  `src/pulseops/domain/health.py`.

Um **teste de integração** confere que as peças funcionam **juntas**. O mesmo
exemplo é repetido com o banco em
`test_threshold_example_with_database` (em
`tests/integration/test_incident_lifecycle.py`): ali o check é gravado, o
incidente é criado de verdade e as constraints do PostgreSQL estão valendo.

Os dois níveis se complementam. Se só houvesse testes unitários, um erro na
transação (bug B6, por exemplo) passaria despercebido. Se só houvesse de
integração, um erro na regra seria mais lento de achar.

## Fixtures e dublês

Uma **fixture** do pytest é uma peça preparada antes do teste e entregue como
parâmetro. Ficam em `tests/conftest.py`:

@@trecho tests/conftest.py 51-71

- `database_url` (escopo `session`): roda **uma vez por execução**. Apaga e recria o
  banco `pulseops_test` e aplica as migrações do Alembic. Assim, os testes usam o
  mesmo esquema da produção, não uma imitação.
- `engine`: uma conexão compartilhada por todos os testes.
- `sessions`: roda **antes de cada teste** e esvazia todas as tabelas com
  `TRUNCATE ... RESTART IDENTITY CASCADE`. Cada teste começa com o banco limpo e
  com os ids recomeçando em 1, então um teste não depende da ordem dos outros.

Um **dublê** (*test double*; "mock" é um tipo de dublê) substitui algo difícil de
controlar. O PulseOps usa poucos, todos em `tests/support.py`:

@@trecho tests/support.py 15-46

- `FakeClock` (linhas 15–30): um relógio parado que só anda quando o teste chama
  `advance`. O código de produção recebe um `Clock` como parâmetro (injeção de
  dependência, parte E), então o teste troca o relógio real por este. Resultado:
  nenhum teste usa `sleep`, e "esperar 3 intervalos" leva microssegundos.
- `FakeResolver` (linhas 33–46): responde a consultas DNS com IPs escolhidos pelo
  teste. É assim que os testes de SSRF simulam "o nome passou a apontar para
  127.0.0.1" sem depender de um DNS de verdade.
- `ScriptedTarget` (linhas 49–85, no mesmo arquivo): um alvo HTTP simulado com o
  `httpx.MockTransport`. O teste escolhe o comportamento: `ok`, `slow`, `error`,
  `timeout`, `refused` ou `tls`.

**O que não é dublê:** o banco. Os testes de integração usam PostgreSQL de
verdade.

## Por que PostgreSQL de verdade, e não SQLite

Seria mais simples rodar os testes com SQLite, que é um arquivo e não precisa de
servidor. Não daria para confiar no resultado, porque o PulseOps depende de
recursos que o SQLite não tem ou faz diferente:

| Recurso usado | No SQLite |
|---|---|
| `FOR UPDATE SKIP LOCKED` | não existe |
| `pg_try_advisory_lock` | não existe |
| `percentile_disc ... WITHIN GROUP` | não existe |
| `JSONB` | não existe (há JSON em texto) |
| `INSERT ... ON CONFLICT` com índice parcial | existe, com diferenças de sintaxe |
| `timestamptz` | não há tipo de data com fuso |

Um teste que passa no SQLite e falha no PostgreSQL é pior do que nenhum teste: ele
dá falsa confiança. O custo é exigir o container `pulseops-testdb` para rodar a
suíte; o CI sobe um PostgreSQL como *service*.

## Testes de regressão

Um **teste de regressão** é escrito para um bug que **aconteceu**, e falha na
versão com o bug. Ele impede que o bug volte. O processo seguido no projeto, para
cada bug do registro:

1. reproduzir o bug com um teste que falha;
2. corrigir o código;
3. ver o mesmo teste passar;
4. registrar em `docs/registro-de-bugs.md`: sintoma, como reproduzir, causa,
   correção, teste de regressão e limitação remanescente.

A regra de honestidade R4 proíbe o atalho de mudar o **resultado esperado** do
teste para ele passar. Quando um teste falha, a pergunta é "o código está errado ou
o teste está errado?", e a resposta precisa de um motivo. Nos bugs B4 e B5 o teste
estava certo e o código foi corrigido.

### Os dez bugs observados

| Bug | Em uma frase | Lição |
|---|---|---|
| B1 | o modelo ganhou uma coluna que a migração não tinha | o teste que compara modelos e migração pegou na hora |
| B2 | `dict()` sobre um resultado do SQLAlchemy levantava `TypeError` | `dict(x)` trata qualquer objeto com `keys()` como mapeamento |
| B3 | `Jinja2Templates(autoescape=True)` não existe no Starlette 1.x | conferir a API da versão instalada, não da memória |
| B4 | hash corrompido com acento derrubava o login com erro 500 | `UnicodeEncodeError` é um `ValueError`; tratar a família certa de exceções |
| B5 | fuso inexistente virava `ZoneInfoNotFoundError` em vez de erro de validação | o Pydantic só converte `ValueError` e `AssertionError` |
| B6 | check iniciado antes de pausar contava depois de retomar | qualquer evento que "recomeça a contagem" precisa invalidar execuções em voo |
| B7 | nome de destino repetido no formulário gerava erro 500 (`MissingGreenlet`) | depois de `rollback()`, objetos do ORM expiram; guardar valores simples |
| B8 | o worker atrasava checks quando havia mais vencidos que vagas | só um ensaio de carga mostrou; nenhum teste funcional pegaria |
| B9 | a legenda do gráfico contradizia as métricas | uma revisão visual da tela pega o que os testes de dados não pegam |
| B10 | a correção do B9 usou uma base de latência diferente da das métricas | conferir a definição no requisito antes de corrigir; explicar o código linha a linha achou o erro |

B8 e B9 merecem atenção numa entrevista: ambos passaram por todos os testes
existentes. B8 só apareceu medindo (ensaio de carga), e B9 só olhando a tela
(instalação limpa). Isso mostra os limites de uma suíte de testes, por maior
que seja.

## Cobertura

**Cobertura** é a porcentagem de linhas do código executadas pelos testes. Medida
no commit explicado (`docs/estrategia-de-testes.md`):

| Parte | Meta | Medido |
|---|---|---|
| `src/pulseops/domain/` | ≥ 95% | 98% |
| `src/pulseops/security/` | ≥ 95% | 97% |
| pacote inteiro | ≥ 90% | 95% |

Cobertura alta **não** prova que o código está certo: uma linha pode ser executada
sem que nenhum `assert` confira o resultado dela. Ela só mostra o que **nunca** foi
executado. A parte mais baixa é `worker/__main__.py` (44%), a montagem do processo
do worker, exercitada pela demonstração e não pelos testes.

## SSRF: um exemplo seguro

**SSRF** (*Server-Side Request Forgery*) é quando um atacante faz o **servidor**
pedir uma URL que o atacante escolheu. Num monitor de APIs, isso é o produto
funcionando: a operadora cadastra uma URL e o servidor a acessa. O risco é a URL
apontar para dentro: `http://127.0.0.1:5432` (o banco), `http://10.0.0.5/admin`
(a rede interna) ou `http://169.254.169.254/` (o serviço de metadados de nuvem, que
pode entregar credenciais).

O PulseOps se defende em duas camadas (ADR 0005):

**Camada 1 — no cadastro**, o texto da URL:

@@trecho src/pulseops/security/url_policy.py 39-68

- linha 47: só `http` e `https` (nada de `file://`, `gopher://`);
- linha 49: nada de usuário e senha na URL;
- linha 59: só as portas 80, 443, 8080 e 8443;
- linha 64: recusa IPs escritos de forma estranha, como `2130706433` ou `0x7f.1`,
  que o sistema operacional entende como 127.0.0.1;
- linha 67: se o host for um IP, confere se é público.

**Camada 2 — na conexão**, o IP de verdade:

@@trecho src/pulseops/security/transport.py 44-68

Esta é a camada que importa. Validar só no cadastro não basta, por causa do
**DNS rebinding**: o nome `api.exemplo.com` aponta para um IP público no cadastro
e, depois, o dono do domínio troca o registro para `127.0.0.1`. Por isso o PulseOps:

1. resolve o nome **no momento de cada conexão** (linha 46);
2. confere **todos** os IPs da resposta, e recusa se algum for proibido (linhas
   53–54); escolher "o IP bom" de uma resposta mista seria uma brecha;
3. conecta **no IP que acabou de validar** (linhas 66–67), não no nome. Assim não
   existe uma segunda resolução, que poderia dar outra resposta.

O teste que prova a camada 2 (`tests/unit/test_transport.py`):

@@trecho tests/unit/test_transport.py 72-82

O nome passa no cadastro apontando para um IP público. Depois, o teste troca a
resposta do DNS falso para `127.0.0.1`. A requisição é recusada com "loopback" e
`inner.connections == []` prova que **nenhuma conexão foi aberta**.

O laboratório de falhas precisa acessar `lab-target`, que é um IP privado da rede
do Docker. Para isso existe uma lista de exceções **por nome e porta**
(`PULSEOPS_DEMO_ALLOWED_HOSTS`), que só vale com `PULSEOPS_DEMO_MODE=true`.

**Limites honestos:** redirecionamentos não são seguidos (um 302 é tratado como
"status inesperado"), o que evita a volta pela porta dos fundos, mas também quer
dizer que monitores de URLs que redirecionam precisam apontar para o destino final.
O modelo de ameaças (`docs/modelo-de-ameacas.md`) lista os riscos que continuam.

## Autenticação, sessão e CSRF

**Autenticação** responde "quem é você?". O PulseOps tem uma operadora, criada pela
linha de comando, e login por formulário (ADR 0008).

- **Senha:** guardada como hash **Argon2id** (`src/pulseops/security/passwords.py`).
  Um hash é uma transformação de mão única: dá para conferir se uma senha bate, mas
  não dá para recuperar a senha a partir do hash. O Argon2id é lento de propósito,
  para que testar bilhões de senhas seja caro.
- **Mesmo tempo para usuário inexistente:**

@@trecho src/pulseops/services/auth.py 33-38

  `verify_password` roda mesmo quando o usuário não existe (com `None`). Sem isso, a
  resposta para um usuário inexistente seria mais rápida, e um atacante poderia
  descobrir quais usuários existem medindo o tempo.

- **Sessão:** depois do login, o servidor sorteia um token aleatório de 32 bytes
  (`secrets.token_urlsafe`) e o envia num **cookie**. O banco guarda só o
  **SHA-256 do token**:

@@trecho src/pulseops/services/auth.py 48-65

  Se alguém copiar a tabela `operator_sessions`, não consegue usar as sessões. O
  teste `test_session_token_is_stored_hashed` (em `tests/integration/test_auth.py`)
  confere isso.

- **Cookie:** `HttpOnly` (o JavaScript da página não lê), `SameSite=Lax` (o
  navegador não o envia em formulários `POST` vindos de outro site, mas envia ao
  seguir um link para o painel, o que mantém a operadora logada) e `Secure` quando
  configurado (só vai por HTTPS). O cookie temporário do formulário de login é
  `SameSite=Strict`. Teste: `test_session_cookie_flags`.

**CSRF** (*Cross-Site Request Forgery*): um site malicioso faz o navegador da
operadora, que está logada, enviar um formulário para o PulseOps, por exemplo
"arquivar monitor 3". O cookie iria junto automaticamente. A defesa: cada sessão tem
um segundo token, o **token CSRF**, que precisa vir no corpo do formulário (campo
`csrf_token`) ou no header `X-CSRF-Token` da API. O site malicioso não consegue
ler esse valor, então não consegue montar o pedido.

@@trecho src/pulseops/web/deps.py 80-95

`hmac.compare_digest` compara os tokens em tempo constante, sem parar no primeiro
caractere diferente. Testes: `test_api_mutation_requires_csrf_header` e
`test_form_action_requires_csrf_field`.

**Limites honestos:** não há limite de tentativas de login nem bloqueio após erros,
não há segundo fator e não há usuários com papéis diferentes.

## Retentativas e duplicidade

O envio de alertas segue o padrão **outbox** (ADR 0007):

1. Na **mesma transação** que abre o incidente, o PulseOps grava o evento
   (`alert_events`) e uma entrega por destino ativo (`deliveries`).
2. Um laço separado do worker reserva entregas vencidas e faz o POST do webhook.
3. O resultado é gravado em `delivery_attempts`, uma linha por tentativa.

Por que não enviar direto, na hora de abrir o incidente? Porque o envio pode
falhar ou demorar. Se fosse dentro da transação, um destino lento seguraria o
banco; se fosse depois do commit, uma queda entre o commit e o envio perderia o
alerta para sempre.

**Retentativas com espera exponencial:**

@@trecho src/pulseops/services/alerts.py 92-99

Depois da 1ª falha, espera `base`; depois da 2ª, `2 × base`; depois da 3ª,
`4 × base`; e assim por diante, até o teto. Com os padrões (5 s e teto de 300 s), as
esperas são 5 s, 10 s, 20 s, 40 s e 80 s; se a 6ª tentativa (o máximo padrão) também falhar, a entrega fica `failed`. O teto só entra em jogo com mais tentativas configuradas. Esperar cada vez mais dá tempo para o
destino se recuperar sem ser bombardeado. Erros 4xx (exceto 408 e 429) são
**permanentes**: o destino recusou o pedido, e repetir não muda nada.

**Duplicidade:** a garantia é **pelo menos uma vez**, não "exatamente uma vez".
Se o worker morrer depois de o destino receber o POST e antes de gravar o sucesso,
a reserva vence e o envio é repetido. Por isso cada evento leva um `event_id`
estável (`incident:42:opened`), e o destino deve ignorar ids repetidos. O receptor
do laboratório faz isso, e o passo 11 da demonstração confere. Teste:
`test_expired_lease_is_retried_which_may_duplicate` (o nome já admite a
duplicata).

**"Exatamente uma vez"** entre dois sistemas que não compartilham transação não é
possível de garantir só de um lado. Dizer isso numa entrevista mostra que você
entende o problema.

## Limitações conhecidas

Coletadas do README, do modelo de ameaças e de `docs/operacao.md`:

| Limitação | Consequência |
|---|---|
| Um worker só | não há alta disponibilidade; se a máquina cair, ninguém é avisado |
| Tick de 1 s | um check pode começar até cerca de 1 s depois do horário previsto |
| Um operador, sem papéis | não serve para uma equipe com permissões diferentes |
| Sem limite de tentativas de login | uma senha fraca pode ser descoberta por tentativa e erro |
| Webhook sem assinatura HMAC | o destino não consegue provar que o alerta veio do PulseOps |
| Sem autenticação nos alvos | não monitora APIs que exigem token |
| Redirecionamentos não seguidos | URL que redireciona aparece como "status inesperado" |
| Uma migração só | evolução de esquema com dados nunca foi exercitada |
| Ensaio de carga local | 200 monitores numa máquina; não é teste de capacidade em produção |
| `Result.tuples()` obsoleto | o SQLAlchemy 2.1 avisa que o método está obsoleto (aviso nos testes); funciona, mas precisa ser trocado antes de uma versão que o remova |
