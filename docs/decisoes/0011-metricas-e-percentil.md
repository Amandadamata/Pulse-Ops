# ADR 0011 — Métricas por checks e p95 nearest-rank

Status: aceita (2026-10-22)

## Decisão
- As porcentagens são **proporções de checks**, não disponibilidade temporal.
- p95 pelo método **nearest-rank**: com `n` amostras ordenadas, o valor na
  posição `⌈0,95 × n⌉`. Referência: definição "nearest-rank method" do
  percentil (por exemplo, NIST/Wikipedia "Percentile"). Escolhido porque o
  resultado é sempre um valor observado e é fácil de calcular à mão.
- Janelas `[início, fim)`; incidentes que atravessam a janela são cortados nos
  limites.
- Sem base, mostra "N/A".

## Alternativa
- Interpolação linear (`numpy.percentile` padrão): suaviza amostras pequenas,
  mas produz valores que nunca foram medidos e exige explicar a fórmula.

## Consequências
- Com poucas amostras o p95 é o máximo. A interface mostra o `n`.
- O cálculo é feito no PostgreSQL com `percentile_disc(0.95)`, que devolve o
  primeiro valor cuja distribuição acumulada é ≥ 0,95, ou seja, o mesmo
  resultado do nearest-rank. Uma função Python equivalente
  (`pulseops.domain.metrics.nearest_rank`) documenta a regra, e um teste de
  integração confere que as duas dão o mesmo resultado.
