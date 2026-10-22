# ADR 0005 — SSRF: validar e conectar no mesmo IP; sem redirecionamentos

Status: aceita (2026-10-22)

## Contexto
O PulseOps faz requisições para URLs cadastradas. Validar o DNS antes e deixar
o cliente resolver de novo na conexão deixa espaço para *DNS rebinding*.

## Decisão
1. No cadastro: esquema `http`/`https`, sem credenciais, porta na lista
   permitida (`80, 443, 8080, 8443` por padrão), host não vazio, host que pareça
   IP em forma não canônica (decimal, octal, hexadecimal) é rejeitado, e se o
   host for IP literal ele precisa ser global.
2. Na conexão: um *network backend* próprio do `httpcore`
   (`GuardedNetworkBackend`) resolve o nome com `loop.getaddrinfo`, rejeita se
   **qualquer** endereço resolvido não for global (privado, loopback,
   link-local, reservado, multicast, compartilhado; IPv4 mapeado em IPv6 é
   avaliado pelo IPv4 interno) e conecta **no IP validado**. O `httpcore`
   continua usando o nome original para o header `Host`, o SNI e a validação
   do certificado.
3. `follow_redirects=False` e `trust_env=False` (o cliente ignora variáveis de
   proxy do ambiente, que desviariam a conexão do IP validado).
4. Exceção de demonstração: `PULSEOPS_DEMO_ALLOWED_HOSTS` lista pares
   `host:porta` nominais (por exemplo `lab-target:8081`) que podem resolver
   para IP privado. Só é lida quando `PULSEOPS_DEMO_MODE=true`. Não existe opção
   para liberar faixas de rede inteiras.

## Alternativas
- Só validar no cadastro: não protege contra rebinding.
- Proxy de saída dedicado (por exemplo, Smokescreen): melhor isolamento, mas
  mais um serviço para operar. Fica como recomendação no modelo de ameaças.

## Consequências
- O transporte substitui o pool interno do `httpx.AsyncHTTPTransport`
  (atributo `_pool`), o que depende de um detalhe interno do HTTPX. Os testes
  (`tests/unit/test_transport.py`) quebram se esse detalhe mudar numa
  atualização.
- Restrições de saída no nível de rede (firewall) continuam recomendadas.
