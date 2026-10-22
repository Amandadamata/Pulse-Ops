# Modelo de ameaças

Versão inicial (Etapa 1), revisada na Etapa 7. A coluna "Teste" aponta o teste
automatizado que verifica cada controle; o que não tem teste está marcado.

## Contexto de uso suportado

- Instalação para **um operador**, em rede local ou atrás de um proxy reverso
  com HTTPS.
- O PulseOps não é um serviço público multiusuário. Quem tem a senha do
  operador pode fazer o servidor enviar requisições a destinos permitidos pela
  política de rede.

## Ativos

| Ativo | Por que importa |
|---|---|
| Credencial do operador (hash) e sessões | Controle total do sistema |
| Rede interna onde o PulseOps roda | O servidor pode alcançar serviços que a internet não alcança (SSRF) |
| Metadados de nuvem (`169.254.169.254`, `fd00:ec2::254`) | Podem expor credenciais da máquina |
| Histórico de checks e incidentes | Evidência dos incidentes; deve ser confiável |
| URLs de webhook | Podem conter tokens na query string |
| Disponibilidade do worker | Se o worker para, o monitoramento para |

## Ameaças, controles e testes

| # | Ameaça | Controle implementado | Teste ou verificação |
|---|---|---|---|
| T1 | SSRF para rede privada, loopback ou metadados via URL de monitor | Política de destino no cadastro (`DestinationPolicy.validate_url` + `validate_destination`, que resolve o nome) e na conexão (`GuardedNetworkBackend`): só IPs globais | `tests/unit/test_url_policy.py::test_blocked_urls`, `tests/unit/test_transport.py::test_name_resolving_to_metadata_is_refused_at_registration`, `tests/unit/test_checker.py::test_blocked_destination_at_connect_time` |
| T2 | Formas alternativas de IP (`2130706433`, `0x7f.1`, `0177.0.0.1`, `[::ffff:127.0.0.1]`, `[::1]`, 6to4, NAT64, Teredo) | Hosts numéricos não canônicos rejeitados no cadastro; IPv6 que embute IPv4 avaliado pelo IPv4 interno | `tests/unit/test_url_policy.py::test_blocked_urls`, `tests/unit/test_transport.py::test_ip_literal_in_policy_check` |
| T3 | DNS rebinding (nome resolve público no cadastro e privado na conexão) | Resolução e validação **no momento da conexão**; a conexão usa exatamente o IP validado, mantendo Host e SNI | `tests/unit/test_transport.py::test_rebinding_is_checked_at_connect_time`, `test_connects_to_validated_ip_and_keeps_host_header`, `test_mixed_public_and_private_answers_are_refused` |
| T4 | Redirecionamento para destino interno | `follow_redirects=False`; 3xx avaliado como status | `tests/unit/test_checker.py::test_redirect_is_not_followed`, `tests/unit/test_transport.py::test_redirects_are_not_followed_by_default` |
| T5 | Credenciais embutidas (`user:pass@host`) | Rejeitadas no cadastro | `tests/unit/test_url_policy.py::test_blocked_urls` |
| T6 | Portas internas (Postgres 5432, Redis 6379…) | Lista de portas permitidas (`80,443,8080,8443` por padrão) | `tests/unit/test_url_policy.py::test_blocked_urls`, `tests/unit/test_config.py::test_allowed_ports_parsing` |
| T7 | Proxy do ambiente desviando a conexão | `trust_env=False` nos clientes HTTPX | `tests/unit/test_transport.py::test_clients_ignore_proxy_environment` |
| T8 | SSRF via URL de webhook | Mesma política no cadastro do destino e no envio | `tests/integration/test_delivery.py::test_blocked_destination_fails_permanently` |
| T9 | Laboratório liberando a rede privada inteira | Exceção apenas para pares `host:porta` nominais e só com `PULSEOPS_DEMO_MODE=true`; serviços do laboratório só no perfil `demo`, sem portas publicadas | `tests/unit/test_url_policy.py::test_demo_allowlist_is_nominal_and_port_specific`, `test_demo_allowlist_is_ignored_outside_demo_mode`, `test_demo_allowlist_requires_host_and_port` |
| T10 | Respostas enormes ou lentas esgotando recursos | Corpo não é lido; prazo total por `asyncio.timeout`; pool sem keep-alive com limite de conexões; no máximo `worker_concurrency` checks simultâneos no worker | `tests/unit/test_checker.py::test_body_is_not_read`, `test_total_deadline_is_enforced` |
| T11 | Acesso sem autenticação | Dependências `require_api_auth` e `require_page_auth` em todas as rotas, exceto login, health e estáticos | `tests/integration/test_auth.py::test_api_requires_session`, `test_pages_redirect_to_login`, `test_mutations_without_session_are_rejected` |
| T12 | Roubo de sessão por XSS | Cookie `HttpOnly`; autoescape do Jinja2; nenhum `|safe` com dado do usuário; CSP `default-src 'self'` | `tests/integration/test_dashboard.py::test_monitor_name_is_escaped`, `test_security_headers`, `tests/integration/test_auth.py::test_session_cookie_flags`, `test_javascript_has_no_token` |
| T13 | CSRF | Token por sessão em formulários e header `X-CSRF-Token` na API; dupla submissão no login; `SameSite=Lax` | `tests/integration/test_auth.py::test_api_mutation_requires_csrf_header`, `test_form_action_requires_csrf_field`, `test_login_form_requires_its_csrf_cookie` |
| T14 | Senha fraca ou armazenada de forma reversível | Argon2id; mínimo de 12 caracteres; usuário inexistente verifica contra hash fictício (tempo parecido) | `tests/unit/test_passwords.py::test_hash_is_argon2id_and_verifies`, `test_short_password_is_rejected`, `tests/integration/test_auth.py::test_unknown_user_gets_same_message` |
| T15 | Token de sessão vazado pelo banco | Banco guarda só o SHA-256 do token; logout e expiração invalidam | `tests/integration/test_auth.py::test_session_token_is_stored_hashed`, `test_logout_invalidates_session`, `test_session_expires` |
| T16 | SQL injection | Somente consultas do SQLAlchemy com parâmetros. Revisão na Etapa 7: os únicos `text()` são `SELECT 1`, o advisory lock com parâmetro `:k` e predicados fixos de índices parciais | `tests/integration/test_dashboard.py::test_sql_injection_attempts_are_plain_data` |
| T17 | Segredos em logs (query string, `Authorization`, senha) | Filtro de redação nos logs; explicações dos checks sem URL nem query string | `tests/unit/test_logging.py::test_query_string_and_userinfo_are_redacted`, `test_sensitive_extra_fields_are_masked`, `tests/unit/test_checker.py::test_explanation_never_contains_url_or_query` |
| T18 | Segredos no Git | `.env`, `.demo/` e `docker/local-ca.pem` no `.gitignore`; `.env.example` sem valores reais; senha da demo gerada localmente | revisão do histórico na Etapa 7 (`git log -p` sem segredos; `git ls-files` sem `.env`) |
| T19 | Container com privilégios | Usuário não-root (uid 10001), sistema de arquivos somente leitura, `cap_drop: ALL`, `no-new-privileges`; banco sem porta publicada; API só em `127.0.0.1` | verificado com `docker inspect` e `docker compose exec api id` (ver `docs/evidencias/`) |
| T20 | Paginação e filtros abusivos | `limit` máximo 200; cursor opaco validado; datas sem fuso recusadas | `tests/integration/test_api_history.py::test_pagination_limits`, `test_naive_datetimes_are_rejected` |
| T21 | Segunda instância do worker duplicando alertas | Advisory lock do PostgreSQL | `tests/integration/test_consistency.py::test_second_worker_is_refused` |
| T22 | Redirecionamento aberto após o login (`next=`) | Só caminhos locais são aceitos | `tests/integration/test_auth.py::test_next_parameter_cannot_redirect_outside` |
| T23 | Dependência com vulnerabilidade conhecida | `uv.lock` fixa versões; `pip-audit` no CI | `pip-audit` sem vulnerabilidades conhecidas em 2026-10-22 (ver `docs/evidencias/`) |

## Limitações remanescentes (riscos aceitos)

Estes são **riscos antecipados**, não bugs observados.

- **Sem limite de tentativas de login.** Força bruta é possível se a tela de
  login estiver exposta. Recomendação: proxy reverso com rate limit ou acesso
  só por VPN.
- **Dependência de detalhe interno do HTTPX** (`AsyncHTTPTransport._pool`) para
  injetar o backend que conecta no IP validado. Uma atualização pode quebrar
  essa integração; os testes detectam.
- **IPv6 com zona** (`fe80::1%eth0`) e outras formas raras são rejeitadas por
  não serem globais, mas não há teste para cada variação possível.
- **Política de saída de rede** (firewall/egress) não é configurada pelo
  projeto. A proteção é da aplicação; a defesa em profundidade fica com quem
  instala.
- **Monitoramento hospedado junto dos alvos**: se a máquina ou a rede caírem,
  o PulseOps cai junto e não avisa ninguém. A indisponibilidade total exige
  observação externa (outro serviço consultando `/health/ready`).
- **Webhook sem assinatura HMAC.** O receptor não consegue provar que o evento
  veio do PulseOps. Fica no roadmap.
- **Código do laboratório dentro da imagem.** `lab/` vai na mesma imagem por
  simplicidade, mas só roda quando o perfil `demo` é ativado; fora dele, nada
  inicia esses serviços.
- **Headers de autenticação para alvos** não existem no MVP. Se forem
  adicionados, precisam de armazenamento cifrado e mascaramento (roadmap).
