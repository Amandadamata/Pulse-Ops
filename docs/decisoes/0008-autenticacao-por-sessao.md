# ADR 0008 — Sessão em banco, cookie HttpOnly e CSRF por token

Status: aceita (2026-10-22)

## Decisão
- Operador criado por CLI; hash **Argon2id** via `argon2-cffi` com parâmetros
  padrão da biblioteca.
- Login gera token aleatório (`secrets.token_urlsafe(32)`); o banco guarda só o
  SHA-256 do token. Cookie `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure`
  configurável.
- Expiração absoluta (padrão 8 h); logout apaga a linha.
- CSRF: token aleatório por sessão (*synchronizer token*), comparado com
  `hmac.compare_digest`. Formulários usam campo oculto; a API JSON usa header
  `X-CSRF-Token`. O formulário de login usa cookie de dupla submissão.
- A mesma sessão serve à API JSON e ao dashboard.

## Alternativas
- JWT: exige lidar com revogação; não traz benefício para um operador.
- Token administrativo fixo: proibido no JavaScript e ruim para revogar.

## Consequências
- Não há limite de tentativas de login (risco de força bruta documentado no
  modelo de ameaças; mitigação recomendada: proxy reverso com rate limit).
