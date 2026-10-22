# D8 — Web: API JSON, painel e login

A camada web é o processo `api`. Ela não verifica nada: lê o que o worker gravou,
aceita cadastros e mostra tudo em HTML ou JSON. As regras ficam nos serviços (D6); as
rotas validam a entrada, chamam um serviço, fazem `commit` e escolhem a resposta.

## `src/pulseops/web/__init__.py`

Arquivo vazio (0 linhas). Só marca a pasta como pacote Python, para que
`from pulseops.web import api` funcione. Não há o que explicar linha a linha.

## `src/pulseops/web/app.py`

**Finalidade.** A fábrica `create_app`: monta a aplicação FastAPI, liga as rotas,
define o tratamento de erros e acrescenta os cabeçalhos de segurança a toda
resposta.

**Dados.** Recebe `Settings` e, opcionalmente, sessões, relógio e resolvedor (os
testes passam versões próprias). Produz um objeto `FastAPI`. **Relações.** É chamada
pelo comando da imagem (`uvicorn pulseops.web.app:create_app --factory`, no
`Dockerfile`, ver D10) e por `tests/conftest.py`. Usa `deps.py`, `api.py`, `pages.py`, `health.py` e
`templating.py`. **Testes.** `test_security_headers`, `test_not_found_page_is_html`
e `test_pages_redirect_to_login`, além de todo teste de integração que usa o
cliente HTTP da aplicação.

@@trecho src/pulseops/web/app.py 30-57

- Linhas 30–36: o `*` obriga a passar `sessions`, `clock` e `resolver` pelo nome. É
  **injeção de dependência** feita à mão: quem chama decide as peças.
- Linhas 40–57: o *lifespan*, código que roda uma vez ao subir (antes do `yield`) e
  outra ao desligar (depois). Linhas 44–47: em produção, cria o engine e as sessões;
  nos testes, usa as sessões recebidas e não cria engine. Linhas 48–54: guarda tudo
  num `AppState` (definido em `deps.py`) dentro de `app.state`. Linhas 56–57: fecha o
  engine só se foi criado aqui.

@@trecho src/pulseops/web/app.py 59-75

- Linhas 59–67: a documentação interativa (`/docs`, `/redoc`, `/openapi.json`) fica
  desligada. A API é do próprio operador, e expor o esquema não traria nada além de
  um mapa das rotas.
- Linha 68: arquivos estáticos (`style.css`, `app.js`) em `/static`.
- Linhas 69–71: as três coleções de rotas. A ordem importa pouco, porque os prefixos
  não se sobrepõem (`/health`, `/api/v1` e o resto).
- Linhas 73–75: quando uma página exige login e não há sessão, `deps.py` lança
  `LoginRequiredError`; aqui ela vira um redirecionamento `303` para
  `/login?next=<caminho>`. `quote` escapa o caminho para caber na URL.

@@trecho src/pulseops/web/app.py 77-114

- Linhas 77–96: erros HTTP (404, 403, 409...). Na API e no `/health`, JSON no formato
  padrão do FastAPI (`{"detail": ...}`). Nas páginas, o template `error.html` com um
  título em português. A mensagem é a do próprio erro, que o código escreveu; nada de
  *traceback*.
- Linhas 98–114: `DBAPIError` é a exceção do SQLAlchemy para falhas do driver
  (banco fora do ar, conexão perdida). Registra no log e responde 503, em JSON na API
  ou numa página "Banco de dados indisponível". Sem isso, o usuário veria um 500
  genérico.

@@trecho src/pulseops/web/app.py 116-129

- Linha 116: um *middleware* roda em volta de toda requisição. `call_next` chama a
  rota; depois disso, a resposta pode ser alterada.
- Linha 117: o `type: ignore` existe porque o FastAPI não oferece um tipo exato para
  `call_next`; é o único `type: ignore` desta camada.
- Linhas 119–121: `nosniff` impede o navegador de "adivinhar" o tipo de um arquivo;
  `X-Frame-Options: DENY` impede que o painel seja exibido dentro de um `<iframe>` de
  outro site (*clickjacking*); `Referrer-Policy: same-origin` não envia a URL do
  painel a outros sites.
- Linhas 122–126: a *Content Security Policy* (CSP). Só carrega scripts, estilos e
  imagens do próprio servidor (`'self'`); `data:` é permitido em imagens. Não há
  `unsafe-inline`: um `<script>` injetado no HTML **não** rodaria, mesmo que o
  escape falhasse. É a segunda camada contra XSS, depois do `autoescape` do Jinja.
- `setdefault` não sobrescreve um cabeçalho que a rota já tenha definido.

**Falhas possíveis.** Um erro sem tratador (por exemplo, um `KeyError` num bug)
vira 500 do próprio Starlette, sem detalhes para o usuário; o log registra.

## `src/pulseops/web/deps.py`

**Finalidade.** As **dependências** do FastAPI: funções que as rotas declaram nos
parâmetros e que o framework executa antes da rota, como "abra uma sessão de banco"
ou "exija login".

**Dados.** Lê o cookie de sessão e cabeçalhos. Produz `AppState`, `AsyncSession` e
`AuthContext`. **Relações.** Usado por `api.py`, `pages.py` e `health.py`; chama
`services/auth.py`. **Testes.** `tests/integration/test_auth.py` inteiro (16 funções, 26 casos),
em especial `test_api_mutation_requires_csrf_header`,
`test_form_action_requires_csrf_field` e `test_session_expires`.

@@trecho src/pulseops/web/deps.py 18-47

- Linhas 18–19: nomes dos dois cookies. `pulseops_session` guarda o token de sessão;
  `pulseops_login_csrf` só existe entre abrir a página de login e enviar o
  formulário.
- Linha 20: os métodos que alteram dados. Só eles exigem token CSRF; `GET` não deve
  alterar nada.
- Linhas 23–29: o pacote de objetos compartilhados pela aplicação inteira.
- Linhas 32–37: `Annotated[AppState, Depends(get_state)]` é um **apelido de tipo**:
  uma rota que declara `state: State` recebe o `AppState` sem repetir o `Depends`.
- Linhas 40–47: uma sessão de banco por requisição. A docstring é a regra da camada:
  quem altera dados chama `commit()`; o que não foi confirmado é desfeito ao fechar.

@@trecho src/pulseops/web/deps.py 50-77

- Linhas 50–61: `AuthContext` copia três valores **simples** da sessão (id, nome e
  token CSRF). A docstring conta o porquê: o bug B7. Guardar o objeto `Operator`
  do ORM fazia o template tentar recarregá-lo depois de um `rollback`, o que exige I/O
  fora do contexto assíncrono e quebrava a página.
- Linhas 64–74: lê o cookie; sem cookie, ou com sessão inválida ou expirada
  (`load_session` devolve `None`), não há usuário. O relógio vem do `AppState`, o que
  permite ao teste `test_session_expires` avançar o tempo.
- Linha 77: `MaybeAuth` é "talvez logado". A página de login usa este, porque precisa
  funcionar sem sessão.

@@trecho src/pulseops/web/deps.py 80-117

- Linhas 80–83: compara tokens com `hmac.compare_digest`, que leva o mesmo tempo
  qualquer que seja a posição da primeira diferença. Um `==` comum para no primeiro
  caractere diferente, e o tempo de resposta poderia revelar o token aos poucos
  (ataque de *timing*). Token vazio nunca confere.
- Linhas 86–94: a regra da API. Sem sessão, 401. Com sessão e método que altera
  dados, exige o cabeçalho `X-CSRF-Token` igual ao da sessão, senão 403. Um site
  malicioso pode fazer o navegador enviar o cookie, mas não consegue ler o token para
  pôr no cabeçalho.
- Linhas 100–109: nas páginas, a falta de sessão vira redirecionamento ao login (o
  tratador está em `app.py`, linhas 73–75), não um 401 seco.
- Linhas 115–117: nos formulários HTML, o token vem num campo escondido
  `csrf_token`, conferido do mesmo jeito.

**Falhas possíveis.** Se o banco cair, `current_auth` falha na consulta da sessão e
o tratador de `DBAPIError` responde 503.

## `src/pulseops/web/health.py`

**Finalidade.** Os dois endpoints de saúde do próprio PulseOps (RF09), sem login.

**Dados.** Nenhuma entrada. Produz JSON. **Relações.** O `compose.yaml` usa
`/health/ready` no *healthcheck* do contêiner `api` (linha 50); é ele que faz o
`docker compose up --wait` esperar a API ficar pronta. `/health/live` fica disponível para um orquestrador que reinicie
processos travados. **Testes.** `test_live_and_ready`,
`test_ready_returns_503_when_database_is_down` e `test_health_endpoints_are_public`.

@@arquivo src/pulseops/web/health.py

- Linhas 18–21: *liveness*: "o processo responde". Não consulta o banco **de
  propósito**: se consultasse, um orquestrador que reinicia processos "mortos"
  reiniciaria a API em laço sempre que o banco caísse, sem resolver nada.
- Linhas 24–45: *readiness*: "posso atender". Linha 30: `asyncio.timeout(2.0)`
  cancela tudo que passar de 2 s, para o endpoint não ficar pendurado num banco
  lento. Linha 32: o `SELECT 1` mais simples possível. Linhas 33–37: aproveita para
  informar o estado do worker. Linhas 38–40: qualquer erro vira 503 com
  `"unavailable"`. O `except Exception` amplo é intencional aqui: o endpoint existe
  justamente para dizer "não", e não para quebrar.
- Linhas 41–45: o worker parado **não** torna a API "não pronta". A API continua
  servindo o painel, que mostra os dados como desatualizados.

## `src/pulseops/web/schemas.py`

**Finalidade.** Os contratos JSON da API: o formato aceito na entrada e o
formato devolvido na saída, como classes Pydantic.

**Dados.** Classes `*In` (entrada), `*Out` (saída) e `*Page` (página com cursor).
**Relações.** Usado só por `api.py`. Os limites de tamanho vêm de
`domain/monitor_rules.py`. **Testes.** `test_unknown_fields_and_methods_rejected`,
`test_invalid_configuration_is_rejected` e os testes de `test_api_history.py`.

@@trecho src/pulseops/web/schemas.py 11-57

- Linha 12: a divisão de trabalho. O Pydantic confere **tipo e tamanho**; as regras
  que combinam campos (por exemplo, timeout menor que o intervalo) ficam em
  `domain/monitor_rules.py`, que o formulário HTML também usa. Assim, a API e o
  painel aplicam a mesma regra.
- Linha 14: `extra="forbid"` recusa campos desconhecidos com 422. Sem isso, um campo
  digitado errado (`interval_secs`) seria ignorado em silêncio e o valor padrão
  entraria no lugar.
- Linha 19: `Literal["GET", "HEAD"]` aceita só esses dois métodos.
- Linhas 27–28: converte para o `MonitorConfig` do domínio.
- Linha 32: `from_attributes=True` permite montar a saída direto de um objeto do ORM
  (`MonitorOut.model_validate(monitor)`).
- Linha 48: `stale` não é coluna do banco; `api.py` calcula e preenche.

@@trecho src/pulseops/web/schemas.py 153-203

- Linhas 153–167: as métricas. As porcentagens e latências são `float | None`:
  `None` vira `null` no JSON quando não há dados, em vez de um 0 que pareceria
  "0% disponível".
- Linhas 170–182: entrada de destinos de webhook; o `PATCH` só aceita `enabled`.
- Linhas 184–191: saída de destinos. **Ponto de atenção:** `url` sai completa. Se a
  URL de um webhook contiver um segredo (muitos serviços colocam o token no caminho),
  ele aparece para quem estiver logado. Como o único usuário é o operador que
  cadastrou o destino, isso foi aceito; com vários usuários, seria preciso mascarar.
- Linhas 194–203: o resumo usado pelo `app.js`.

As classes das linhas 59–150 (`CheckOut`, `IncidentOut`, `IncidentEventOut`,
`AttemptOut`, `DeliveryOut`, `AlertOut`, `IncidentDetailOut`) seguem o mesmo padrão
de `MonitorOut`: uma lista de campos com tipos e `from_attributes=True` quando são
montadas de objetos do ORM.

## `src/pulseops/web/api.py`

**Finalidade.** A API JSON em `/api/v1`: monitores, histórico de checks, métricas,
incidentes, alertas, destinos e resumo. Toda rota exige sessão (`ApiAuth`).

**Dados.** JSON validado por `schemas.py` e parâmetros de consulta. Produz JSON.
**Relações.** Chama `services/monitors.py`, `services/queries.py` e
`security/transport.py`. Usada pelo `app.js` (só `/summary`), por
`scripts/demo_flow.py` e por quem quiser automatizar. **Testes.**
`tests/integration/test_api_monitors.py` (17 casos) e `test_api_history.py` (8).

@@trecho src/pulseops/web/api.py 37-69

- Linha 39: `Limit` limita o tamanho da página entre 1 e 200 (`MAX_PAGE_SIZE`). Um
  `?limit=201` recebe 422, sem chegar ao banco (`test_pagination_limits`).
- Linhas 42–52: traduz as exceções dos serviços para HTTP: não encontrado 404,
  conflito 409, validação 422 no mesmo formato que o FastAPI usa para erros do
  Pydantic. Linha 52: uma exceção inesperada é relançada, não engolida.
- Linhas 55–69: monta a saída dos monitores com o campo `stale`. **Ponto de
  atenção:** carrega **todos** os monitores (linha 63) e filtra em Python, mesmo
  quando a rota quer um só (`get_monitor`, linha 99). Com dezenas de monitores não
  faz diferença; com milhares, seria uma consulta por id. É ineficiência, não bug: o
  resultado está certo.

@@trecho src/pulseops/web/api.py 72-142

- Linhas 72–77: lista; arquivados só com `?include_archived=true`.
- Linhas 80–94: cria. A política SSRF e o resolvedor vão para o serviço, que valida a
  URL (D4, D6). Só depois de `commit` a resposta é montada, com status 201.
- Linhas 97–102: busca um; 404 se não existe.
- Linhas 105–122: atualiza com `PUT` (a configuração inteira). Um monitor arquivado
  dá 409.
- Linhas 125–142: as quatro ações num caminho só (`/monitors/7/pause`). Linhas
  129–136: um dicionário de funções em vez de quatro rotas quase iguais; uma ação
  fora da lista dá 404.

@@trecho src/pulseops/web/api.py 145-211

- Linhas 145–171: histórico de checks com cursor e filtros. Linhas 152–153:
  `Query(alias="from")` porque `from` é palavra reservada do Python e não pode ser
  nome de parâmetro. Linha 154: `outcome` tipado como `Outcome`, então um valor
  inválido já dá 422. Linhas 167–168: cursor malformado vira 422. **Ponto de
  atenção:** para um `monitor_id` que não existe, a resposta é uma página vazia com
  200, não 404. Não é falso (não há checks), mas é menos informativo que a rota de
  métricas também não acusar.
- Linhas 174–205: métricas. Linhas 185–186: sem janela, últimas 24 h até agora.
  Linhas 187–188: janela invertida dá 422. O resto copia os campos para o contrato.
- Linhas 208–211: datas sem fuso são recusadas. `2026-10-22T10:00` é ambíguo (10 h
  em qual fuso?); `2026-10-22T10:00Z` não é (`test_naive_datetimes_are_rejected`).

@@trecho src/pulseops/web/api.py 214-272

- Linhas 214–231: incidentes. Linha 218: `pattern` limita `status` a três valores.
  **Ponto de atenção:** `status=closed` devolve incidentes `resolved` **e**
  `closed`, porque `queries.list_incidents` trata "closed" como "encerrados" (a
  interface usa o mesmo filtro). Já `status=resolved` devolve só os resolvidos.
  Quem usar a API esperando só os encerrados manualmente terá uma surpresa; o
  comportamento está no comentário de `services/queries.py`, linha 166.
- Linhas 234–253: converte a visão de um alerta (evento, entregas e tentativas) no
  contrato JSON. O `event_id` exposto é a `event_key` estável, a mesma enviada no
  webhook, para o receptor deduplicar.
- Linhas 256–265: detalhe de um incidente com a linha do tempo e os alertas.
- Linhas 268–272: últimos alertas.

@@trecho src/pulseops/web/api.py 275-337

- Linhas 281–304: cria destino. Linha 286: a mesma validação SSRF usada para
  monitores, porque o worker também fará requisições para esse endereço. Linhas
  300–303: nome repetido viola a restrição única do banco; o `IntegrityError` vira
  409. É o banco quem garante a unicidade, não uma consulta prévia, que teria uma
  janela de corrida.
- Linhas 307–317: liga ou desliga um destino.
- Linhas 320–337: o resumo do painel, com o estado do worker e a hora em que foi
  gerado.

**Falhas possíveis.** Banco indisponível: 503 pelo tratador de `app.py`. Sessão
expirada: 401. Mutação sem `X-CSRF-Token`: 403.

## `src/pulseops/web/pages.py`

**Finalidade.** As páginas HTML (RF07) e o login (RF08). Faz o mesmo que a API, mas
lendo formulários e devolvendo HTML ou redirecionamentos.

**Dados.** Formulários `application/x-www-form-urlencoded` e parâmetros de consulta.
Produz HTML e redirecionamentos 303. **Relações.** Usa `deps.py`,
`templating.py`, `charts.py` e os serviços. **Testes.**
`tests/integration/test_dashboard.py` (12 casos) e `test_auth.py` (26).

@@trecho src/pulseops/web/pages.py 35-69

- Linha 35: `include_in_schema=False`, porque páginas não fazem parte da API.
- Linha 37: as três janelas de tempo do detalhe do monitor.
- Linhas 41–58: `render` junta o contexto comum a toda página (fuso, modo
  demonstração, usuário e token CSRF) com o contexto da página.
- Linhas 61–62: 303 *See Other* depois de um `POST` faz o navegador abrir a página
  seguinte com `GET`. Recarregar a página não reenvia o formulário (padrão
  *Post/Redirect/Get*).
- Linhas 65–69: `_safe_next` só aceita caminhos internos. Sem isso,
  `/login?next=https://site-falso.example` mandaria a pessoa, recém-logada, para outro
  site (*open redirect*). `//site.example` também é recusado, porque o navegador o lê
  como outro domínio (`test_next_parameter_cannot_redirect_outside`).

@@trecho src/pulseops/web/pages.py 75-148

- Linhas 75–88: o formulário de login. Quem já está logado vai direto ao destino.
  Linha 79: gera um token aleatório, que vai **duas vezes** para o navegador: num
  cookie e num campo escondido do formulário. É o padrão *double submit cookie*: antes
  do login não existe sessão onde guardar o token. Linha 85: o cookie é
  `SameSite=Strict`, então não é enviado em requisições que partem de outro site.
- Linhas 91–102: o login confere se cookie e campo coincidem. Um site malicioso pode
  enviar um formulário para `/login`, mas não consegue ler nem definir esse cookie.
  Isso impede o *login CSRF* (logar a vítima numa conta do atacante).
- Linhas 103–123: senha errada ou usuário inexistente: a **mesma** mensagem e o
  status 401 (`test_unknown_user_gets_same_message`), com um token novo.
- Linhas 124–138: sucesso. Cria a sessão e confirma (`commit`). O cookie
  `pulseops_session` tem `max_age` igual à duração da sessão, `HttpOnly` (o
  JavaScript não lê), `SameSite=Lax` (linha 133) e `Secure` conforme a configuração.
  `Lax` permite que um link de outro site abra o painel já logado, mas não envia o
  cookie em `POST` vindo de outro site. A proteção dos formulários continua sendo o
  token CSRF. Linha 137: apaga o cookie de CSRF do login, que não serve mais.
- Linhas 141–148: logout exige token CSRF (senão um site qualquer poderia deslogar a
  pessoa), apaga a sessão no banco e o cookie.

@@trecho src/pulseops/web/pages.py 154-207

- Linhas 154–173: o painel. Calcula, para cada monitor, se os dados estão
  desatualizados.
- Linhas 176–202: `_form_config` converte o formulário em `MonitorConfig`. Linhas
  179–189: campos numéricos que não são inteiros viram erro de campo, não uma
  exceção. Linhas 194–198: os textos são cortados num tamanho bem acima do limite.
  O corte serve só para não processar textos enormes; o limite de verdade é
  conferido em `monitor_rules.py`, que dá a mensagem de erro.
- Linhas 205–207: lê o formulário e descarta campos que não são texto (arquivos).

@@trecho src/pulseops/web/pages.py 218-246

- Linha 221: o token CSRF é a primeira coisa conferida.
- Linhas 223–236: se a conversão deu certo, o serviço valida e cria. Erro de
  validação volta como lista de erros por campo.
- Linhas 237–246: com erro, a página é exibida de novo com status 422, os valores
  digitados (`form=form`) e as mensagens ao lado de cada campo. A pessoa não perde o
  que digitou.

@@trecho src/pulseops/web/pages.py 249-297

- Linha 256: `window` limitado a `1h`, `24h` ou `7d` por expressão regular.
- Linhas 269–278: últimos 25 checks com cursor e filtro de resultado.
- Linha 279: os pontos do gráfico (até 300, sem `internal_error`; ver
  `queries.latency_series`).
- Linhas 281–297: métricas da janela, o gráfico já montado (`charts.py`), as
  mudanças de saúde, os checks e os incidentes.

As demais rotas seguem os mesmos padrões e não trazem ideia nova:
`edit_monitor_form` e `edit_monitor` (linhas 300–348) repetem o fluxo de criação com
`update_monitor`; `monitor_action` (351–371) é a versão HTML da rota de ações da API,
com `verify_form_csrf`; `incidents_page` e `incident_page` (377–404) listam e
detalham; `notifications_page` (407–421) lista destinos e alertas.

@@trecho src/pulseops/web/pages.py 424-473

- Linhas 428–436: valida nome e URL (com a política SSRF) e junta os erros.
- Linhas 440–445: nome repetido. Linha 444: depois de um erro no `commit`, o SQLAlchemy exige
  `rollback` antes de usar a sessão de novo (a consulta da linha 447 precisa dela). O
  `rollback` expira os objetos do ORM carregados na sessão, e foi isso que causou o
  bug B7 (ver `deps.py`, `AuthContext`).
- Linhas 462–473: inverte `enabled` de um destino.

**Falhas possíveis.** Monitor inexistente: página 404 (`test_not_found_page_is_html`).
Monitor arquivado em edição: 409. Banco fora do ar: página 503.

## `src/pulseops/web/templating.py`

**Finalidade.** Configura o Jinja2 e registra os **filtros**, funções que formatam
valores nos templates (`{{ valor | pct }}`).

**Dados.** Valores do banco (datas em UTC, números, códigos). Produz texto em
português. **Relações.** `templates` é usado por `app.py` e `pages.py`; os filtros
aparecem em todos os templates. **Testes.** `test_times_are_shown_in_display_timezone`,
`test_monitor_name_is_escaped` e `test_monitor_detail_with_real_data`.

@@trecho src/pulseops/web/templating.py 15-47

- Linhas 15–17: `autoescape=True`. Todo `{{ ... }}` é escapado: `<` vira `&lt;` e
  assim por diante. O bug B3 explica a forma: a versão instalada do Starlette não aceita mais
  `Jinja2Templates(autoescape=True)`, então o projeto cria o próprio `Environment` e
  o entrega pronto (`env=`). No `Environment` do Jinja, o padrão é **sem** escape;
  por isso o `autoescape=True` explícito é indispensável, e
  `test_monitor_name_is_escaped` confere que ele está ligado.
- Linhas 20–26: `@pass_context` dá ao filtro acesso ao contexto do template, de onde
  vem o fuso `tz`. As datas ficam em UTC no banco e só são convertidas na exibição.
- Linhas 29–34: `None` vira "N/A", nunca 0. A vírgula decimal é trocada à mão
  (`replace`), sem depender da *locale* do sistema.
- Linhas 37–47: duração legível: "2 h 05 min", "3 min 07 s" ou "42 s".

@@trecho src/pulseops/web/templating.py 50-95

- Linhas 50–63: rótulos em português vindos dos enums do domínio. Um valor
  desconhecido aparece cru, em vez de quebrar a página.
- Linhas 66–81: rótulos dos estados guardados como texto no banco.
- Linhas 83–95: o registro dos filtros. `STATE_LABELS.get` já é uma função: recebe a
  chave e devolve o rótulo (ou `None`).

## `src/pulseops/web/charts.py`

**Finalidade.** Monta o gráfico de latência como dados para um SVG desenhado no
servidor, sem biblioteca de JavaScript (ADR 0010).

**Dados.** Recebe `LatencyPoint` (hora, duração, resultado) e o limite de latência.
Produz um `LatencyChart` com coordenadas e o texto de resumo. **Relações.** Chamado
em `pages.py`, linha 290; desenhado em `monitor_detail.html`. **Testes.**
`tests/unit/test_charts.py` (4 testes, dois deles de regressão de B9 e B10).

@@arquivo src/pulseops/web/charts.py

- Linhas 7–9: tamanho do desenho e margens, em unidades do `viewBox` do SVG (o
  navegador escala). Linha 9: `ACCEPTED` decide o **formato** do ponto: círculo para
  status aceito e quadrado para falha.
- Linhas 12–32: classes de dados imutáveis (`frozen=True`). O template só lê.
- Linhas 36–37: sem pontos, sem gráfico (`None`); o template mostra "sem dados".
- Linha 38: o topo do eixo é o maior valor entre os pontos e o limite, mais 15%,
  para a linha do limite sempre aparecer e o ponto mais alto não encostar na borda.
- Linhas 43–44: converte milissegundos em altura. No SVG, o `y` cresce para
  **baixo**, por isso `bottom - ...`.
- Linha 46: espaço horizontal igual entre pontos. `max(..., 1)` evita divisão por
  zero com um ponto só. **Consequência:** o eixo x é a **ordem** dos checks, não o
  tempo. Uma falta de checks de uma hora não aparece como espaço vazio no gráfico; ela
  aparece na lista de lacunas das métricas.
- Linhas 47–56: cada ponto com o texto de dica (`<title>` no SVG).
- Linha 57: quatro marcas no eixo y (0, 25%, 50% e 75% do topo).
- Linhas 58–68: o resumo em texto, que vai na `<desc>` do SVG (lida por leitores de
  tela) e na legenda. A latência mínima e a máxima usam `RESPONSE_OUTCOMES` (healthy,
  slow e unexpected_status), a **mesma base** da latência média e do p95 das
  métricas. Antes da correção B10, o resumo usava só `healthy` e `slow`, e as duas
  partes da mesma página descreviam conjuntos diferentes. Timeout e erro de conexão
  ficam fora, porque a duração deles mede o prazo, não uma resposta (B9).
- Linhas 69–80: a linha (`polyline`) liga todos os pontos na ordem.

## Templates (`src/pulseops/web/templates/`)

São 11 arquivos HTML com Jinja2. Os padrões se repetem, então mostramos os quatro
que definem a estrutura e resumimos os outros.

**Testes.** `tests/integration/test_dashboard.py` faz as requisições e confere o HTML
devolvido; `test_monitor_name_is_escaped` e `test_sql_injection_attempts_are_plain_data`
cadastram textos maliciosos e conferem que aparecem como texto.

@@arquivo src/pulseops/web/templates/base.html

- Linha 2: `lang="pt-BR"`, para leitores de tela pronunciarem em português.
- Linha 8: `defer` executa o script depois de montar a página.
- Linha 11: o link "Pular para o conteúdo" fica escondido até receber foco pelo
  teclado (CSS `.skip-link`); permite pular o menu.
- Linhas 12–16: a faixa de modo demonstração, só quando `PULSEOPS_DEMO_MODE` está
  ligado (`test_demo_banner_only_in_demo_mode`).
- Linhas 19–32: menu e logout só para quem está logado. O logout é um **formulário
  `POST`** com token CSRF, e não um link: um link (`GET`) poderia ser disparado por
  uma imagem em outro site.
- Linha 34: `tabindex="-1"` permite que o link da linha 11 mova o foco para o
  conteúdo.
- Linha 38: o rodapé diz em que fuso os horários estão.

@@arquivo src/pulseops/web/templates/_macros.html

- **Macros** são funções de template. Linhas 1–7: o selo de saúde; se os dados
  estão desatualizados, mostra isso **em vez** da saúde, que pode estar velha.
- Linhas 17–21: a mensagem de erro de um campo tem `id="<campo>-error"`. O campo do
  formulário aponta para ela com `aria-describedby`, e o leitor de tela lê a
  mensagem junto com o campo.
- Linhas 23–28: toda ação (pausar, arquivar...) é um formulário `POST` pequeno com o
  token CSRF.
- Os `-` em `{%-` e `-%}` removem espaços em branco em volta, para o HTML não ficar
  com quebras de linha sobrando dentro dos selos.

@@trecho src/pulseops/web/templates/dashboard.html 10-35

- Linhas 10–19: o aviso de worker parado, com `role="alert"`, e há quanto tempo
  (RF07.5).
- Linhas 21–35: o resumo. `data-summary-url` e `data-key` são os ganchos do
  `app.js`; sem JavaScript, os números do carregamento continuam lá. Linha 34:
  `aria-live="polite"` faz o leitor de tela anunciar "Resumo atualizado" sem
  interromper a pessoa.

@@trecho src/pulseops/web/templates/monitor_detail.html 84-105

- Linha 88: `role="img"` e `aria-labelledby` apontando para o título e a descrição
  dão ao SVG um nome acessível. `preserveAspectRatio="none"` deixa o desenho esticar
  para a largura da tela.
- Linha 89: `<desc>` com o resumo de `charts.py`.
- Linhas 90–95: linhas de grade, rótulos do eixo, o limite tracejado e a série.
- Linhas 96–102: quadrado para falha e círculo para sucesso. A **forma** distingue
  os dois, não só a cor, o que serve a quem não distingue cores. `<title>` dá a dica
  com hora, duração e resultado.
- Linha 104: a legenda explica a leitura e lembra que a tabela abaixo traz os mesmos
  dados em texto.

Os demais templates:

| Arquivo | O que mostra | Padrões a notar |
|--------------------|--------------------------|----------------------------------|
| `login.html` | formulário de login | campo escondido `csrf_token` com o token do cookie; `autocomplete` correto para gerenciadores de senha |
| `error.html` | título e mensagem de erro | `role="alert"`; nenhum detalhe interno |
| `monitor_form.html` | criar e editar monitor | `novalidate` deixa a validação para o servidor, que dá as mensagens; `aria-invalid` e `aria-describedby` nos campos com erro |
| `monitor_detail.html` | estado, métricas, gráfico, mudanças, incidentes, checks | abas da janela com `aria-current="page"`; ações pelo macro `action_button` |
| `incidents.html` | lista de incidentes | filtro por abas (`open`, `closed`, `all`) e paginação por cursor |
| `incident_detail.html` | um incidente | início versus confirmação, linha do tempo com motivos e os alertas |
| `notifications.html` | destinos e alertas | formulário de destino com erros por campo; botão de ligar e desligar com CSRF |
| `_alerts_table.html` | tabela de alertas com entregas e tentativas | incluído por `incident_detail.html` e `notifications.html` |

## `src/pulseops/web/static/app.js`

**Finalidade.** Atualiza os números do resumo do painel a cada 15 segundos. É o
único JavaScript do projeto.

**Relações.** Carregado por `base.html`; lê `/api/v1/summary`. **Testes.**
`test_javascript_has_no_token` confere que o arquivo não contém nenhum token. O
comportamento no navegador não tem teste automático; foi conferido nas capturas de
tela (`scripts/capturar_telas.mjs`, D9).

@@arquivo src/pulseops/web/static/app.js

- Linhas 1–2: a página funciona **sem** este script (*melhoria progressiva*). A
  autenticação é o cookie `HttpOnly`, que o script nem consegue ler.
- Linha 3: uma função que se executa na hora (IIFE), para as variáveis não vazarem
  para o escopo global.
- Linha 6: fora do painel, não faz nada.
- Linhas 10–13: `textContent`, e não `innerHTML`: o valor é sempre tratado como
  texto, nunca como HTML.
- Linha 18: `credentials: "same-origin"` envia o cookie de sessão. É um `GET`, então
  não precisa de token CSRF.
- Linhas 28–30: mostra a hora da atualização e avisa se o worker parou.
- Linhas 31–33: em erro (sessão expirou, servidor fora), diz o que houve em vez de
  falhar em silêncio.
- Linha 36: `setInterval` de 15 s.

## `src/pulseops/web/static/style.css`

**Finalidade.** O visual do painel: 136 linhas, sem *framework*. A primeira linha
resume as regras: contraste AA, foco visível e cor sempre acompanhada de texto.

@@trecho src/pulseops/web/static/style.css 1-34

- Linhas 2–17: as cores como **variáveis CSS** (`--nome`). Cada estado tem um par
  fundo e texto; o comentário da linha 1 promete contraste AA (conferido abaixo).
- Conferência do contraste, calculada com a fórmula da WCAG sobre as cores deste
  trecho: os pares dos selos ficam entre 6,5:1 (degradado) e 8,4:1 (neutro); o texto
  principal sobre o fundo dá 14,8:1 e o texto secundário (`--muted`), 6,2:1. Todos
  passam do mínimo AA para texto normal, 4,5:1.
- Linha 31: `:focus-visible` mostra um contorno amarelo grosso em quem recebe foco
  pelo teclado.
- Linhas 32–33: o link de pular conteúdo fica fora da tela até receber foco.
- Linha 34: `.visually-hidden` esconde da tela, mas não do leitor de tela (usado nos
  títulos do resumo e da tabela).

@@trecho src/pulseops/web/static/style.css 118-136

- Linhas 118–126: o gráfico. A linha do limite é tracejada; os pontos de falha têm
  cor escura e borda preta, além da forma quadrada.
- Linhas 128–136: em telas estreitas, a tabela rola na horizontal em vez de espremer
  as colunas.

O restante do arquivo (linhas 35–117) define o cabeçalho, os cartões, os botões, os
selos (`.badge-*`), os formulários e as tabelas, sem lógica para explicar.
