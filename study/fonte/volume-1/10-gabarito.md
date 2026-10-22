# Gabarito comentado da parte J

As respostas dos níveis 2 a 4 foram **executadas** no commit explicado
({{COMMIT_CURTO}}): as saídas abaixo são as que o código produziu, e as alterações
dos exercícios J12, J14 e J15 foram feitas numa cópia descartável do repositório,
com a suíte inteira rodando depois.

## Nível 1

**J1.** `src/pulseops/domain/outcomes.py`. Contam como falha do alvo:
`unexpected_status`, `timeout`, `connection_error`, `tls_error` e `blocked`.
`healthy` e `slow` são sucesso; `internal_error` é falha do próprio PulseOps e não
conta para nada.

**J2.** `delivery_attempts` (uma linha por tentativa, com status, duração e erro)
e `health_changes` (de qual saúde para qual, quando e o `reason`).

**J3.** O serviço `migrate`. A `api` e o `worker` têm
`depends_on: migrate: {condition: service_completed_successfully}`: só sobem
depois de o `migrate` terminar com código 0. Assim, nunca rodam contra um banco
sem as tabelas.

**J4.** `test_monitor_name_is_escaped` em `tests/integration/test_dashboard.py`.
Previne **XSS** (*cross-site scripting*): um nome como
`<script>...</script>` apareceria como texto, e não seria executado pelo
navegador. Quem garante é o `autoescape=True` do Jinja (bug B3).

## Nível 2

**J5.** `20.0 300.0`. A 3ª falha espera `5 × 2² = 20` s. A 10ª daria
`5 × 2⁹ = 2560` s, mas o teto é 300.

**J6.** `True False False`. 404 é erro do pedido (permanente). 429 ("muitas
requisições") é exceção explícita: vale tentar mais tarde. 503 não é 4xx, então é
temporário.

**J7.** `300 None None 75.0`. Com 5 valores, a posição é `ceil(0,95 × 5) = 5`: o
maior, 300. Lista vazia e denominador zero dão `None` (o "N/A" do painel), nunca 0.

**J8.**

```text
http://0x7f.1/ recusada: endereço IP em forma não canônica
https://api.example.com:8443/x aceita Destination(scheme='https', host='api.example.com', port=8443)
http://[::ffff:127.0.0.1]/ recusada: ::ffff:127.0.0.1 aponta para endereço de loopback (::ffff:7f00:1)
http://example.com:5432/ recusada: porta 5432 não permitida (permitidas: 80, 443, 8080, 8443)
```

O terceiro caso é o mais traiçoeiro: um endereço IPv6 que "embrulha" um IPv4. A
política extrai o IPv4 de dentro (`ipv4_mapped`) e confere de novo. A
`UnsafeDestinationError` é uma subclasse de `ValueError`, por isso o `except
ValueError` do exercício a captura.

**J9.** Abre, no **3º** check. O erro interno não soma nem zera:

```text
timeout         none  degraded  falhas=1  "Falha 1 de 2 necessárias para abrir incidente"
internal_error  none  degraded  falhas=1  "Erro interno do PulseOps ignorado na contagem"
timeout         open  down      falhas=2  "Incidente confirmado após 2 falhas consecutivas"
```

**J10.** Não abre. Lento é **sucesso** para a contagem: zera as falhas.

```text
timeout  none  degraded  falhas=1 sucessos=0
slow     none  degraded  falhas=0 sucessos=1  "Resposta lenta"
timeout  none  degraded  falhas=1 sucessos=0
```

Se a pergunta numa entrevista for "um serviço que alterna entre lento e timeout
nunca abre incidente?", a resposta honesta é "com esses limiares, não; ele fica
degradado o tempo todo, e isso aparece no painel". É uma consequência da ADR 0004.

**J11.** `[200, 204, 304]`. A faixa `200-299` cobre 200 e 204; 304 está listado à
parte; 301 e 404 não.

## Nível 3

**J12.** Resultado obtido na cópia:

1. Antes: `17 passed`.
2. O teste novo, escrito primeiro, falhou como esperado:

```python
def test_slow_does_not_count_towards_recovery_during_incident() -> None:
    state, decisions = run([F, S, Outcome.SLOW, S], failure=1, recovery=2)
    assert actions(decisions)[2] is IncidentAction.NONE  # lento não soma
    assert decisions[2].state.consecutive_successes == 1  # nem zera
    assert actions(decisions)[3] is IncidentAction.RESOLVE
```

3. A alteração, no começo do ramo `if state.incident_open:` de `_on_success`:

```python
if obs.outcome is Outcome.SLOW:
    reason = f"Resposta lenta não conta para encerrar o incidente: {obs.explanation}."
    return Decision(replace(state, health=Health.DOWN), IncidentAction.NONE, state.health, reason)
```

   `replace(state, ...)` parte do estado **anterior**, então os contadores não
   mudam.

4. Na suíte inteira: `1 failed, 251 passed`. Falhou
   `test_slow_response_counts_towards_recovery`, que afirma a regra antiga. Aqui
   mudar o teste é correto, porque a **regra mudou de propósito**: ele deve ser
   substituído pelo teste novo, e o motivo vai na mensagem do commit. A regra R4
   proíbe outra coisa: mudar o esperado de um teste para esconder um bug, sem que a
   regra tenha mudado. Repare também que o trecho que deixava o monitor
   `degraded` ao se recuperar com resposta lenta virou código morto e pode sair.
5. Documentos: `docs/decisoes/0004-lentidao-nao-abre-incidente.md` (registrar a
   nova decisão, ou uma ADR nova que substitui a 0004), RF03 em
   `docs/requisitos.md`, a tabela de regras do README e este guia (partes A e H9).

**J13.** O teste `test_attempts_are_limited_then_failed` usa
`settings.webhook_max_attempts`, então continua certo sozinho. Mudam:
`src/pulseops/config.py` (padrão), `.env.example`, a tabela de variáveis em
`docs/operacao.md`, RF06.5 em `docs/requisitos.md` e o texto da parte G e de H11
deste guia. O `compose.demo.yaml` define 20 para a demonstração e não muda. Rode
`uv run python scripts/conferir_referencias.py` e a suíte.

## Nível 4

**J14.** Os dois usos estão em `src/pulseops/services/queries.py` (linhas 119 e
329). A forma recomendada é iterar o resultado direto, porque cada linha já se
comporta como tupla:

```python
counts = {status: count for status, count in rows}
```

Na cópia: `251 passed`, mypy sem erros, e o número de avisos caiu de 74 para 0.
Não use `dict(rows)`: esse é exatamente o bug B2.

**J15.** Na cópia, a solução abaixo passou na suíte e no mypy, e o teste novo
**falhou antes** da alteração (o hash gravado continuava `m=8192,t=1,p=1`):

```python
# security/passwords.py
def needs_rehash(password_hash: str) -> bool:
    """O hash foi feito com parâmetros diferentes dos atuais (por exemplo, mais fracos)."""
    return _hasher.check_needs_rehash(password_hash)


# services/auth.py, dentro de authenticate
if verify_password(operator.password_hash if operator else None, password):
    if operator is not None and needs_rehash(operator.password_hash):
        operator.password_hash = hash_password(password)
    return operator
```

```python
async def test_weak_hash_is_upgraded_on_login(sessions, operator, app_client) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(ADMIN_PASSWORD)
    async with sessions.begin() as s:
        await s.execute(update(Operator).values(password_hash=weak))
    await login(app_client, ADMIN_USER, ADMIN_PASSWORD)
    async with sessions() as s:
        stored = await s.scalar(select(Operator.password_hash))
    assert stored != weak
    assert "m=65536" in stored
```

Funciona porque a rota de login já faz `commit()` depois de criar a sessão, e a
alteração do hash vai junto na mesma transação. Ponto de atenção: `hash_password`
recusa senhas com menos de 12 caracteres; como o cadastro já exige 12, isso não
acontece com operadoras criadas pelo PulseOps.

## Nível 5

**J16.** O volume `pgdata` foi criado com a senha **antiga**; o PostgreSQL só lê
`POSTGRES_PASSWORD` na primeira inicialização. Confirme com
`docker compose logs migrate` (erro de autenticação). Correção: voltar à senha
antiga, ou trocar a senha dentro do banco (`ALTER USER`), ou apagar o volume com
`docker compose down -v`, **perdendo os dados**.

**J17.** O worker está parado ou sem acesso ao banco. Confirme com
`docker compose ps worker` e `docker compose logs worker`; o painel também mostra o
aviso "Worker sem sinal". Correção: `docker compose start worker` (ou resolver o
erro que aparece no log).

**J18.** O nome resolve para um IP privado (por exemplo, `10.x.x.x`), e a política
SSRF recusa de propósito. Não é um bug. O PulseOps foi feito para monitorar
endereços públicos; a única exceção é a lista do modo demonstração, que não deve
ser usada para contornar a política fora do laboratório.

**J19.** 404 é tratado como **erro permanente** (`is_permanent_status`), então não
há retentativa. A causa mais provável é a URL do destino errada (caminho trocado).
Confira a URL na página de notificações e teste com
`curl -X POST <url> -d '{}'`. Depois de corrigir o destino, os **próximos**
eventos serão entregues; os que já ficaram `failed` não são reenviados.

**J20.** O banco de testes não está rodando. `docker ps -a` mostra
`pulseops-testdb` parado ou inexistente. Correção: `docker start pulseops-testdb`,
ou o `docker run` da parte B.

**J21.** O tempo medido é o do **worker**, não o do seu computador, e inclui DNS,
conexão e TLS. Se o worker estiver em outra rede, ou se a conexão não é
reaproveitada (o PulseOps abre uma conexão nova a cada check, com
`max_keepalive_connections=0`), o tempo pode passar dos 300 ms que você vê no
navegador. Confira a duração dos checks no histórico e compare com o limite do
monitor; ajuste o limite se ele estiver abaixo do custo real de uma conexão nova.
