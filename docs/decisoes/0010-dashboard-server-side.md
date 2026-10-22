# ADR 0010 — Dashboard renderizado no servidor, gráfico em SVG

Status: aceita (2026-10-22)

## Decisão
- Páginas Jinja2 com autoescape ligado, formulários HTML com POST e CSRF.
- O gráfico de latência é um SVG gerado no servidor a partir dos checks reais.
  Não há biblioteca de gráficos no navegador.
- JavaScript mínimo (`static/app.js`): atualiza o resumo do painel a cada 15 s
  usando a API autenticada pelo cookie, com estados "Atualizando…" e "Falha ao
  atualizar". Sem ele, a página continua funcionando.

## Alternativas
- SPA em React/Vue: mais código, outro build e outro conjunto de testes, sem
  requisito que justifique.
- Chart.js por CDN: dependência externa na página e dados expostos em JSON
  inline; o SVG resolve o requisito com menos peças.

## Consequências
- Interações são recarregamentos de página. Para um operador isso é aceitável.
