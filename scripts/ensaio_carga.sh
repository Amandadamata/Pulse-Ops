#!/usr/bin/env bash
# Ensaio de carga local. Requer o ambiente da demonstração (scripts/demo.sh já executado).
# Uso: scripts/ensaio_carga.sh [--monitors N] [--interval S] [--duration S] [--api-clients N]
# Grava o relatório em docs/evidencias/ensaio-de-carga.md.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f compose.yaml -f compose.demo.yaml --profile demo)
OUT=docs/evidencias/ensaio-de-carga.md
mkdir -p docs/evidencias
PULSEOPS_DEMO_PASSWORD="$(cat .demo/admin-password)"
export PULSEOPS_DEMO_PASSWORD

{
  echo "# Ensaio de carga local"
  echo
  echo "Gerado por \`scripts/ensaio_carga.sh $*\` em $(date -u +%Y-%m-%dT%H:%MZ)."
  echo "Commit: \`$(git rev-parse --short HEAD 2>/dev/null || echo desconhecido)\`."
  echo
  echo "## Máquina"
  echo
  echo "- Sistema: $(uname -srm)"
  echo "- CPUs visíveis: $(nproc)"
  echo "- Memória total: $(awk '/MemTotal/ {printf "%.1f GiB", $2/1048576}' /proc/meminfo)"
  echo "- Docker: $(docker version --format '{{.Server.Version}}')"
  echo "- Worker: concorrência $("${COMPOSE[@]}" exec -T worker printenv PULSEOPS_WORKER_CONCURRENCY 2>/dev/null || echo '20 (padrão)')"
  echo
  echo "## Resultado"
  echo
} > "$OUT"

# Amostra de CPU e memória dos containers no meio da janela medida.
( sleep 70; docker stats --no-stream --format '| {{.Name}} | {{.CPUPerc}} | {{.MemUsage}} |' \
    > /tmp/pulseops-stats.txt ) &
STATS_PID=$!

"${COMPOSE[@]}" run --rm --no-deps -T demo-runner python scripts/ensaio_carga.py "$@" | tee -a "$OUT"
wait "$STATS_PID" || true

{
  echo
  echo "## Uso de recursos (amostra única no meio da janela)"
  echo
  echo "| Container | CPU | Memória |"
  echo "|---|---|---|"
  grep pulseops /tmp/pulseops-stats.txt || echo "| (sem amostra) | | |"
  echo
  echo "## Como ler"
  echo
  echo "Os números valem para esta máquina, esta configuração e esta duração. Não indicam"
  echo "capacidade máxima nem comportamento em produção; o alvo é local e responde em"
  echo "poucos milissegundos, o que não acontece com APIs reais."
} >> "$OUT"
echo "Relatório: $OUT"
