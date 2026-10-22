#!/usr/bin/env bash
# Laboratório de falhas do PulseOps: sobe o ambiente com o perfil "demo" e executa
# o roteiro de 11 passos (scripts/demo_flow.py). Pode ser executado várias vezes.
#
# Uso: scripts/demo.sh            (sobe, prepara e executa o roteiro)
#      scripts/demo.sh --down     (derruba o ambiente da demonstração, mantendo o banco)
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f compose.yaml -f compose.demo.yaml --profile demo)

if [[ "${1:-}" == "--down" ]]; then
  "${COMPOSE[@]}" down
  exit 0
fi

# Senha da operadora da demonstração: gerada uma vez e guardada fora do Git
# (.demo/ está no .gitignore), para que reexecutar o script reutilize o mesmo usuário.
mkdir -p .demo
if [[ ! -s .demo/admin-password ]]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(18))' > .demo/admin-password
  chmod 600 .demo/admin-password
fi
export PULSEOPS_DEMO_USERNAME="${PULSEOPS_DEMO_USERNAME:-demo}"
PULSEOPS_DEMO_PASSWORD="$(cat .demo/admin-password)"
export PULSEOPS_DEMO_PASSWORD

echo "==> Subindo banco, API, worker e serviços do laboratório"
"${COMPOSE[@]}" up -d --build --wait db migrate api worker lab-target lab-receiver

echo "==> Garantindo a operadora '${PULSEOPS_DEMO_USERNAME}'"
printf '%s\n' "$PULSEOPS_DEMO_PASSWORD" | "${COMPOSE[@]}" run --rm -T --no-deps api \
  pulseops create-admin --username "$PULSEOPS_DEMO_USERNAME" --password-stdin --exists-ok

echo "==> Executando o roteiro"
"${COMPOSE[@]}" run --rm --no-deps demo-runner

echo
echo "Painel: http://127.0.0.1:${PULSEOPS_PORT:-8000}  (usuário: ${PULSEOPS_DEMO_USERNAME}, senha em .demo/admin-password)"
