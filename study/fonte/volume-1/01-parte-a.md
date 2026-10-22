# Parte A — Problema e produto

## O que é uma API

Um programa conversa com outro por meio de uma **API** (Application Programming
Interface, interface de programação de aplicações). Em uma API web, essa conversa
usa o protocolo **HTTP**: quem pede (o *cliente*) envia uma **requisição** e quem
atende (o *servidor*) devolve uma **resposta**.

Uma requisição HTTP tem:

- um **método**, que diz a intenção: `GET` (ler), `POST` (criar), `PUT` (substituir),
  `PATCH` (alterar parte), `DELETE` (apagar), `HEAD` (como `GET`, mas sem o corpo
  da resposta);
- uma **URL**, como `https://api.exemplo.com/pedidos?pagina=2`, com esquema
  (`https`), host (`api.exemplo.com`), porta (443, implícita no `https`),
  caminho (`/pedidos`) e *query string* (`?pagina=2`);
- **cabeçalhos** (*headers*), pares nome/valor como `Content-Type: application/json`;
- opcionalmente um **corpo**, por exemplo um JSON.

A resposta traz um **código de status** de três dígitos, cabeçalhos e, às vezes,
um corpo. Os códigos se agrupam pela centena:

| Faixa | Significado | Exemplos |
|---|---|---|
| 2xx | deu certo | 200 OK, 201 Created, 204 No Content |
| 3xx | redirecionamento | 301 Moved Permanently, 302 Found |
| 4xx | erro de quem pediu | 400 Bad Request, 401 Unauthorized, 404 Not Found, 422 Unprocessable Entity |
| 5xx | erro do servidor | 500 Internal Server Error, 503 Service Unavailable |

O PulseOps aparece dos dois lados: ele **é** uma API (o painel e as rotas
`/api/v1/...`) e ele **consome** APIs (faz requisições aos endereços monitorados
e envia webhooks).

## O que é monitoramento

Monitorar uma API é perguntar a ela, de tempos em tempos, "você está
respondendo?", e guardar as respostas. No PulseOps, cada pergunta se chama
**check** (verificação). Um **monitor** é a configuração de uma pergunta
recorrente: qual URL, a cada quantos segundos, quanto tempo esperar, quais
status contam como "deu certo" e quantas falhas seguidas confirmam um problema.

Esse tipo é chamado de **monitoramento ativo** (ou *sintético*): o monitor
inicia o contato. No **monitoramento passivo**, o serviço é que avisa que está
vivo; o Healthchecks, comparado na pesquisa de mercado, funciona assim. O
PulseOps só faz monitoramento ativo de HTTP/HTTPS.

## Lenta não é o mesmo que indisponível

Uma resposta pode chegar com status 200 e mesmo assim demorar 3 segundos. O
serviço está **disponível** (respondeu e respondeu certo), mas está **lento** para
quem usa. Tratar as duas coisas como iguais causa dois problemas:

- se lentidão contasse como falha, um pico de carga abriria incidentes e
  dispararia alertas de "fora do ar" para um serviço que está no ar;
- se lentidão fosse ignorada, a equipe só descobriria a degradação quando ela
  virasse queda.

Por isso o PulseOps classifica um check com status aceito e tempo acima do limite
como **lento** (`slow`). O monitor fica **degradado** (amarelo), mas nenhum
incidente é aberto (ADR 0004). Já timeout, erro de conexão, erro TLS ou status
fora da lista aceita são **falhas** e contam para abrir incidente.

O **timeout** fica na fronteira: se a resposta não chega dentro do prazo
configurado (por exemplo, 5 s), o PulseOps desiste e conta uma falha, porque do
ponto de vista de quem usa o serviço "não respondeu".

## O que é um incidente

Um **incidente** é um período em que o serviço é considerado indisponível, com
começo, confirmação, fim e evidências. Um check isolado com erro não é um
incidente: redes falham por instantes. O PulseOps só abre um incidente depois de
`failure_threshold` falhas **seguidas** (3 por padrão) e só o encerra depois de
`recovery_threshold` sucessos **seguidos** (2 por padrão).

Exemplo com os valores padrão (é o exemplo obrigatório da especificação, testado
em `tests/unit/test_health.py`):

| Check | Resultado | Falhas seguidas | Sucessos seguidos | Saúde | Incidente |
|---|---|---|---|---|---|
| 1 | falha | 1 | 0 | degradado | nenhum ("Falha 1 de 3") |
| 2 | falha | 2 | 0 | degradado | nenhum ("Falha 2 de 3") |
| 3 | sucesso | 0 | 1 | saudável | nenhum (contagem zerada) |
| 4 | falha | 1 | 0 | degradado | nenhum |
| 5 | falha | 2 | 0 | degradado | nenhum |
| 6 | falha | 3 | 0 | indisponível | **abre**; início = check 4, confirmação = check 6 |
| 7 | falha | 4 | 0 | indisponível | o **mesmo** incidente é atualizado |
| 8 | sucesso | 0 | 1 | indisponível | continua aberto ("Sucesso 1 de 2") |
| 9 | sucesso | 0 | 2 | saudável | **resolvido** |

Repare em duas datas diferentes: o incidente **começou** na primeira falha da
sequência (check 4), mas só foi **confirmado** no check 6. As duas ficam gravadas.

## O que cada funcionalidade resolve

| Problema da equipe (cenário fictício) | Funcionalidade | Onde está |
|---|---|---|
| "Descobrimos quando alguém reclama" | Checks periódicos feitos pelo worker | `worker/runner.py`, `checks/checker.py` |
| "Não sabemos se foi lentidão ou queda" | Classificação de cada check e saúde degradado/indisponível | `domain/outcomes.py`, `domain/health.py` |
| "Um erro de rede isolado vira alarme" | Limiares de falhas e sucessos seguidos | `domain/health.py` |
| "Não sabemos por que o sistema decidiu isso" | Motivo gravado em cada mudança de estado e no incidente | `health_changes`, `incident_events` |
| "Recebemos o mesmo alerta dez vezes" | Só transições geram alerta; identificador único do evento | `services/alerts.py` |
| "Se o canal de alerta cai, perdemos o aviso" | Outbox com retentativas | `services/alerts.py`, laço de entregas |
| "Um alerta travado atrasa tudo" | Entregas em laço separado dos checks | `worker/runner.py` |
| "Quanto tempo ficou fora do ar este mês?" | Métricas por janela, com N/A quando não há dados | `services/queries.py`, `domain/metrics.py` |
| "Alguém pode usar o monitor para atacar a rede interna?" | Política SSRF | `security/` |
| "Como mostramos isso funcionando?" | Laboratório de falhas | `lab/`, `scripts/demo.sh` |

## Cenário fictício e limites do projeto

O cenário é **fictício**: não existe a equipe, nem as APIs dela. Ele serve para
dar direção aos requisitos. O PulseOps é um projeto pessoal de estudo, não um
produto em uso.

Limites assumidos (detalhados no README e no modelo de ameaças):

- um operador só, sem cadastro de usuários e papéis;
- um worker só, sem escala horizontal;
- só HTTP/HTTPS, sem TCP, ping ou DNS;
- sem autenticação nos alvos (headers secretos ficam no roadmap);
- webhooks sem assinatura HMAC;
- sem limite de tentativas de login;
- quando a máquina inteira cai, o PulseOps não consegue avisar ninguém.

Funcionalidades comuns, como checar HTTP, mandar alerta e mostrar um painel, não
são invenções do projeto. Ferramentas maduras fazem isso há anos (parte I mostra
como falar disso numa entrevista). O que o PulseOps tenta mostrar é a lógica bem
resolvida: regra explícita, histórico confiável, alertas desacoplados e testes que
provam cada comportamento.
