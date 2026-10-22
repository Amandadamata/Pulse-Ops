# Parte J — Aprendizagem ativa

Ler não basta para fixar. Os exercícios vão do mais simples ao mais difícil.
Tente cada um **antes** de olhar o gabarito, que fica em uma seção separada logo
depois desta parte. Use um ramo do Git para os exercícios que mexem no código
(`git switch -c estudo`), e volte com `git switch -` e `git restore .` quando
quiser descartar.

Para rodar trechos de Python no ambiente do projeto:

```bash
uv run python
```

Isso abre o interpretador interativo (`>>>`) com o PulseOps importável. Saia com
`exit()`.

## Nível 1 — Ler e localizar

**J1.** Em que arquivo está a lista de resultados possíveis de um check
(`healthy`, `slow`...)? Quais deles contam como falha do alvo?

**J2.** Qual tabela guarda cada tentativa de envio de webhook? E qual guarda o
motivo de cada mudança de saúde?

**J3.** Abra `compose.yaml`. Qual serviço roda as migrações, e por que a `api`
só sobe depois dele?

**J4.** Encontre o teste que prova que o nome de um monitor é escapado no HTML.
Que ataque ele previne?

## Nível 2 — Prever o resultado antes de executar

Escreva a sua previsão num papel. Depois execute no `uv run python` e compare.

**J5.**

```python
from pulseops.services.alerts import backoff_delay

print(backoff_delay(3, 5, 300), backoff_delay(10, 5, 300))
```

**J6.**

```python
from pulseops.services.alerts import is_permanent_status

print(is_permanent_status(404), is_permanent_status(429), is_permanent_status(503))
```

**J7.**

```python
from pulseops.domain.metrics import nearest_rank, ratio

print(nearest_rank([120, 80, 300, 95, 110], 95), nearest_rank([], 95), ratio(0, 0), ratio(3, 4))
```

**J8.** Para cada URL, a política aceita ou recusa? Se recusa, com qual motivo?

```python
from pulseops.security.url_policy import DestinationPolicy

p = DestinationPolicy()
for url in [
    "http://0x7f.1/",
    "https://api.example.com:8443/x",
    "http://[::ffff:127.0.0.1]/",
    "http://example.com:5432/",
]:
    try:
        print(url, "aceita", p.validate_url(url))
    except ValueError as e:
        print(url, "recusada:", e)
```

**J9.** Com `failure_threshold=2` e `recovery_threshold=2`, a sequência é
timeout, erro interno, timeout. Abre incidente? Em qual check?

**J10.** Com os mesmos limiares, a sequência é timeout, lento, timeout. Abre
incidente?

**J11.**

```python
from pulseops.domain.status_codes import parse_status_codes

codes = parse_status_codes("200-299,304")
print([c for c in (200, 204, 301, 304, 404) if c in codes])
```

## Nível 3 — Alterar uma regra e atualizar os testes

**J12.** Hoje, uma resposta **lenta** conta como sucesso para encerrar um
incidente (ADR 0004). Suponha que a equipe decidiu o contrário: durante um
incidente, só respostas `healthy` contam para a recuperação; respostas lentas não
somam nem zeram a contagem de sucessos.

1. Antes de mexer, rode `uv run pytest tests/unit/test_health.py` e anote quantos
   passam.
2. Escreva primeiro o teste novo (ele deve falhar).
3. Altere `src/pulseops/domain/health.py`.
4. Qual teste existente vai falhar, e por quê? Ele deve ser apagado, alterado ou
   mantido? Justifique pela regra R4 (não mudar resultado esperado só para passar).
5. Que documentos precisam mudar junto?

**J13.** Mude o padrão de `webhook_max_attempts` de 6 para 8. Quais testes,
documentos e variáveis de ambiente você precisa conferir? (Dica: procure com
`grep -rn "max_attempts\|MAX_ATTEMPTS" src tests docs compose*.yaml .env.example`.)

## Nível 4 — Implementar uma pequena melhoria

**J14.** O SQLAlchemy 2.1 avisa que `Result.tuples()` está obsoleto (o aviso
aparece ao rodar os testes). Encontre os usos em `src/` e troque pela forma
recomendada. Rode a suíte inteira e confirme que o aviso sumiu e nada quebrou.

**J15.** Ao fazer login, o PulseOps não confere se o hash da senha foi gerado com
parâmetros antigos. Use `PasswordHasher.check_needs_rehash` do argon2-cffi para,
depois de um login bem-sucedido, regravar o hash quando necessário. Escreva um
teste que cria um hash com parâmetros mais fracos, faz login e confere que o hash
gravado mudou.

## Nível 5 — Diagnosticar sem olhar a resposta

Para cada sintoma, escreva: hipótese mais provável, o comando que confirma e a
correção.

**J16.** Depois de trocar `POSTGRES_PASSWORD` no `.env`, `docker compose up`
termina com `migrate` em `exited (1)`.

**J17.** O painel mostra todos os monitores como "desatualizados", mas a página
abre normalmente.

**J18.** Um monitor para `http://intranet.empresa.local/health` é recusado com
"aponta para endereço privado".

**J19.** Na página de notificações, todas as entregas para um destino aparecem
como `failed` depois de uma única tentativa, com status 404.

**J20.** `uv run pytest` falha logo no começo com `connection refused` na porta
5433.

**J21.** Um monitor está "lento" o tempo todo, mas a API responde em 300 ms
quando você testa do seu computador.

## Checklist de compreensão

Marque só o que você consegue **explicar em voz alta, sem ler**:

- [ ] O caminho de um check, da reserva à gravação, e por que são duas transações.
- [ ] O que é `run_key` e que problema resolve.
- [ ] A diferença entre `slow` e falha, e por que lento não abre incidente.
- [ ] O exemplo obrigatório (falha, falha, sucesso, falha × 3, sucesso × 2), com
      as datas de início e confirmação.
- [ ] Por que existem índices únicos **parciais**, e quais são os três.
- [ ] O que `FOR UPDATE SKIP LOCKED` faz.
- [ ] O padrão outbox e por que a entrega pode duplicar.
- [ ] As duas camadas da proteção SSRF e o que é DNS rebinding.
- [ ] Como o token de sessão é guardado e o que o token CSRF impede.
- [ ] Por que as métricas mostram "N/A", e qual é o denominador.
- [ ] O que acontece quando o worker reinicia.
- [ ] Como o painel mostra que o worker parou.
- [ ] Por que os testes usam PostgreSQL real e um relógio falso.
- [ ] Dois bugs do registro, com causa e lição.
- [ ] Três limitações do projeto e o que você faria em cada uma.
