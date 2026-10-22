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

| # | Ameaça | Controle implementado | Teste |
|---|---|---|---|
| T1 | SSRF para rede privada, loopback ou metadados via URL de monitor | Política de destino no cadastro (`url_policy.validate_target_url`) e na conexão (`GuardedNetworkBackend`): só IPs globais | `tests/unit/test_url_policy.py`, `tests/unit/test_transport.py` |
| T2 | Formas alternativas de IP (`2130706433`, `0x7f.1`, `0177.0.0.1`, `[::ffff:127.0.0.1]`, `[::1]`) | Hosts numéricos não canônicos rejeitados no cadastro; resolução real validada na conexão; IPv4 mapeado em IPv6 avaliado pelo IPv4 interno | `tests/unit/test_url_policy.py` |
| T3 | DNS rebinding (nome valida público no cadastro e privado na hora da conexão) | Resolução e validação acontecem **no momento da conexão**, e a conexão usa exatamente o IP validado | `tests/unit/test_transport.py::test_rebinding_is_checked_at_connect_time` |
| T4 | Redirecionamento para destino interno | `follow_redirects=False`; 3xx avaliado como status | `tests/unit/test_checker.py::test_redirect_is_not_followed` |
| T5 | Credenciais embutidas (`user:pass@host`) | Rejeitadas no cadastro | `tests/unit/test_url_policy.py` |
| T6 | Portas internas (Postgres 5432, Redis 6379…) | Lista de portas permitidas (`80,443,8080,8443` por padrão) | `tests/unit/test_url_policy.py` |
| T7 | Proxy do ambiente desviando a conexão | `trust_env=False` nos clientes HTTPX | `tests/unit/test_transport.py::test_clients_ignore_proxy_environment` |
| T8 | SSRF via URL de webhook | Mesma política no cadastro do destino e no envio | `tests/integration/test_delivery.py::test_blocked_destination_fails_permanently` |
| T9 | Laboratório liberando rede privada inteira | Exceção apenas para pares `host:porta` nominais e só com `PULSEOPS_DEMO_MODE=true` | `tests/unit/test_url_policy.py::test_demo_allowlist_*` |
| T10 | Respostas enormes ou lentas esgotando recursos | Corpo não é lido; prazo total por `asyncio.timeout`; limite de conexões do pool; semáforo de concorrência | `tests/unit/test_checker.py` |
| T11 | Acesso sem autenticação | Dependência `require_operator` em todas as rotas, exceto login, health e estáticos | `tests/integration/test_auth.py` |
| T12 | Roubo de sessão por XSS | Cookie `HttpOnly`; autoescape do Jinja2; nenhum `|safe` com dado do usuário | `tests/integration/test_dashboard.py::test_monitor_name_is_escaped` |
| T13 | CSRF | Token por sessão em formulários e header na API; dupla submissão no login; `SameSite=Lax` | `tests/integration/test_auth.py` |
| T14 | Senha fraca armazenada de forma reversível | Argon2id; senha mínima de 12 caracteres na CLI | `tests/unit/test_passwords.py` |
| T15 | Token de sessão vazado pelo banco | Banco guarda só o SHA-256 do token | `tests/integration/test_auth.py::test_session_token_is_stored_hashed` |
| T16 | SQL injection | Somente consultas do SQLAlchemy com parâmetros; nenhum SQL montado com f-string de entrada | revisão de código (ver Etapa 7) |
| T17 | Segredos em logs (query string, `Authorization`, senha) | Filtro de redação nos logs; explicações dos checks sem query string | `tests/unit/test_logging.py` |
| T18 | Segredos no Git | `.env` no `.gitignore`; `.env.example` sem valores reais | revisão do diff (Etapa 8) |
| T19 | Container com privilégios | Usuário não-root na imagem; banco sem porta publicada no Compose padrão | revisão do `Dockerfile`/`compose.yaml` |
| T20 | Paginação abusiva | `limit` máximo 200; validação de parâmetros | `tests/integration/test_api_history.py` |
| T21 | Segunda instância do worker duplicando alertas | Advisory lock do PostgreSQL | `tests/integration/test_worker.py::test_second_worker_is_refused` |

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
- **Headers de autenticação para alvos** não existem no MVP. Se forem
  adicionados, precisam de armazenamento cifrado e mascaramento (roadmap).
