# D4 — Segurança: política de destino, transporte protegido e senhas

## `src/pulseops/security/url_policy.py`

**Finalidade.** Decide se uma URL e um IP podem ser usados como destino de check ou
de webhook (proteção contra SSRF, ADR 0005).

**Dados.** Entrada: texto da URL (digitado pela operadora) e objetos
`IPv4Address`/`IPv6Address` (vindos da resolução DNS). Saída: `Destination` ou
`UnsafeDestinationError` com mensagem legível. **Relações.** A política é criada a
partir de `Settings` em `web/app.py` e `worker/__main__.py`; usada por
`security/transport.py`, `services/monitors.py`, `web/api.py`, `web/pages.py` e
`notifications/webhook.py`. **Testes.** `tests/unit/test_url_policy.py` (seis
funções e 38 casos, com listas parametrizadas de URLs aceitas e recusadas) e
`tests/unit/test_transport.py`.

@@trecho src/pulseops/security/url_policy.py 1-37

- Linhas 1–7: a docstring resume as duas camadas.
- Linha 14: um apelido de tipo para "IPv4 ou IPv6".
- Linhas 16–18: expressão regular que reconhece hosts escritos só com números ou
  hexadecimal separados por ponto. O resolvedor do sistema aceita formas como
  `2130706433` (127.0.0.1 em decimal) e `0x7f.1`; o PulseOps só aceita a forma
  canônica (`127.0.0.1`), que é verificada como IP.
- Linha 19: `64:ff9b::/96` é o prefixo NAT64, que embute um IPv4 dentro de um IPv6.
- Linhas 22–23: a exceção herda de `ValueError`. Quem já trata `ValueError`
  (validações) a captura sem código extra.
- Linhas 26–30: o destino validado.
- Linhas 33–37: a política, imutável. Portas permitidas por padrão e a lista de
  exceções do laboratório (vazia fora do modo demo).
  `field(default_factory=frozenset)` cria um conjunto vazio novo por instância.

@@trecho src/pulseops/security/url_policy.py 39-79

- Linhas 40–44: `urlsplit` divide a URL; ler `parts.port` pode levantar
  `ValueError` (porta não numérica ou acima de 65535), que vira "URL inválida".
- Linhas 46–53: esquema, credenciais e host. `parts.hostname` já vem em minúsculas
  e sem colchetes de IPv6.
- Linha 54: porta padrão do esquema, se não informada.
- Linhas 56–57: a exceção do laboratório é **nominal**: vale para o par exato
  (`lab-target`, 8081) e nada mais.
- Linhas 59–61: porta fora da lista.
- Linhas 63–67: se o host é um IP escrito na forma canônica, confere o IP já no
  cadastro; se parece número mas não é IP canônico, recusa.
- Linhas 70–71: compara o host sem ponto final (`lab-target.` é o mesmo nome).
- Linhas 73–79: `check_address` é a função chamada **na hora da conexão** pelo
  transporte. A mensagem cita o host, o motivo e o IP.

@@trecho src/pulseops/security/url_policy.py 82-111

- Linhas 84–89: IPv6 que embute IPv4 (mapeado `::ffff:a.b.c.d`, 6to4 ou NAT64):
  extrai o IPv4 e confere **ele**, recursivamente. Sem isso, `::ffff:127.0.0.1`
  passaria por "IPv6 público".
- Linhas 90–91: Teredo é um túnel IPv6 sobre IPv4; recusado.
- Linhas 92–103: as categorias, na ordem do mais específico para o mais geral. A
  biblioteca `ipaddress` já sabe classificar (`is_loopback`, `is_private`...). A
  linha 95 lembra que `169.254.169.254`, o serviço de metadados de nuvem, é
  link-local. A linha 102 é a rede de segurança: tudo que não é "global" é
  recusado.
- Linhas 107–111: tenta interpretar o texto como IP; se não for, `None`.

**Falhas possíveis.** Uma URL que redireciona para a rede interna não é seguida
(o cliente não segue redirecionamentos). Endereços que a biblioteca `ipaddress`
classifique errado passariam; a lista de casos testados está em
`tests/unit/test_url_policy.py`.

## `src/pulseops/security/transport.py`

**Finalidade.** Faz o HTTPX conectar **só** em IPs aprovados, resolvendo e
validando no momento da conexão (defesa contra DNS rebinding).

**Dados.** Recebe nome e porta do `httpcore`; devolve um *stream* de rede aberto
no IP validado. **Relações.** `build_guarded_client` é chamado por
`worker/__main__.py` (dois clientes: checks e webhooks); `validate_destination` é
chamado por `services/monitors.py` e pelas rotas de destinos; `Resolver` é
substituído por `FakeResolver` nos testes. **Testes.** `tests/unit/test_transport.py`
(doze testes, entre eles `test_rebinding_is_checked_at_connect_time`,
`test_mixed_public_and_private_answers_are_refused`,
`test_clients_ignore_proxy_environment`, `test_redirects_are_not_followed_by_default`).

@@trecho src/pulseops/security/transport.py 1-30

- Linhas 1–7: a docstring explica a técnica: o HTTPX (por meio do `httpcore`) pede
  ao *network backend* para abrir cada conexão. Substituindo o backend, o PulseOps
  decide em qual IP conectar. O `Host`, o SNI (nome enviado no TLS) e a
  verificação do certificado continuam usando o nome da URL.
- Linhas 21–22: protocolo do resolvedor, uma função assíncrona que devolve a lista
  de IPs.
- Linhas 25–30: o resolvedor real. `loop.getaddrinfo` executa a função bloqueante
  do sistema numa thread, sem travar o event loop. `type=socket.SOCK_STREAM` pede
  só endereços TCP. `info[4][0]` é o IP dentro da tupla que o `getaddrinfo`
  devolve.

@@trecho src/pulseops/security/transport.py 33-80

- Linha 33: herda de `httpcore.AsyncNetworkBackend`, a interface que o `httpcore`
  espera.
- Linhas 34–42: recebe a política, o resolvedor (real por padrão) e o backend
  "de verdade" (`AnyIOBackend`), para o qual delega a conexão.
- Linhas 44–55: resolve e valida (volume 1, parte G). Erros de DNS viram
  `httpcore.ConnectError`, que o HTTPX traduz para `httpx.ConnectError` e o
  verificador classifica como falha de conexão.
- Linhas 57–68: `connect_tcp` é chamado pelo `httpcore`. Conecta no
  `str(address)`, o IP validado. O `# noqa: ASYNC109` silencia uma regra do Ruff
  que não gosta de parâmetros chamados `timeout` em funções assíncronas: a
  assinatura é imposta pelo `httpcore`.
- Linhas 70–76: socket Unix (arquivo local) é sempre recusado.
- Linhas 78–79: `sleep` faz parte da interface; delega.

@@trecho src/pulseops/security/transport.py 82-104

- Linha 90: `trust_env=False` ignora `HTTP_PROXY` e afins do ambiente: um proxy
  faria a conexão sair de outro lugar, sem passar pela validação. `retries=0`: o
  HTTPX não repete conexões por conta própria.
- Linhas 91–98: troca o pool interno do transporte por um com o backend protegido.
  O comentário admite que é um **detalhe interno** do HTTPX 0.28 e aponta o teste
  que quebra se isso mudar. `max_keepalive_connections=0`: cada requisição abre uma
  conexão nova, então cada check passa pela validação de IP (e mede o custo de
  conexão de verdade).
- Linhas 99–104: o cliente final: sem proxy, sem seguir redirecionamentos, com o
  `User-Agent` do PulseOps.

@@trecho src/pulseops/security/transport.py 107-123

Validação de **cadastro**: texto da URL e, se o nome resolver agora, os IPs atuais.
Um nome que não resolve é aceito (linhas 120–121), porque o serviço pode estar fora
do ar no momento do cadastro; a proteção definitiva acontece em cada conexão.

**Falhas possíveis.** Uma atualização do HTTPX que mude `_pool` quebra a injeção;
o teste `test_connects_to_validated_ip_and_keeps_host_header` detecta. Um DNS que
devolve listas diferentes a cada consulta não é problema, porque só uma consulta
é feita por conexão e o IP usado é o validado.

## `src/pulseops/security/passwords.py`

**Finalidade.** Gera e confere hashes de senha com Argon2id.

@@arquivo src/pulseops/security/passwords.py

- Linha 6: tamanho mínimo da senha.
- Linha 8: um `PasswordHasher` com os parâmetros padrão da biblioteca (Argon2id,
  64 MiB de memória, 3 iterações, na versão travada).
- Linha 11: hash de uma senha fixa, calculado uma vez na importação. Serve para
  conferir "alguma coisa" quando o usuário não existe, gastando o mesmo tempo.
- Linhas 14–17: recusa senha curta e devolve o hash (o texto começa com
  `$argon2id$v=19$m=65536,t=3,p=4$...`, que guarda os parâmetros junto).
- Linhas 20–26: confere. Linha 22: se não há hash (usuário inexistente), confere
  contra o hash fictício e, mesmo que batesse, devolve `False` por causa do `and
  password_hash is not None`. Linhas 23–26: qualquer erro de formato vira "não
  confere" (bug B4).

**Dados.** Senha em texto (vinda do formulário ou da linha de comando) e hash
(texto do banco). **Relações.** `services/auth.py`. **Falhas.** Senha curta levanta
`ValueError` (tratado pelo `cli.py`). **Testes.** `tests/unit/test_passwords.py`
(`test_hash_is_argon2id_and_verifies`, `test_short_password_is_rejected`,
`test_missing_user_never_verifies`).
