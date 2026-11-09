#!/usr/bin/env bash
# PulseOps failure lab: starts the environment with the "demo" profile and runs
# the 11-step script (scripts/demo_flow.py). It can run several times.
#
# Usage: scripts/demo.sh          (starts, prepares and runs the script)
#        scripts/demo.sh --down   (stops the demo environment, keeping the database)
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f compose.yaml -f compose.demo.yaml --profile demo)

if [[ "${1:-}" == "--down" ]]; then
  "${COMPOSE[@]}" down
  exit 0
fi

# Password for the demo operator: generated once and kept out of Git
# (.demo/ is in .gitignore), so running the script again reuses the same user.
mkdir -p .demo
if [[ ! -s .demo/admin-password ]]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(18))' > .demo/admin-password
  chmod 600 .demo/admin-password
fi
export PULSEOPS_DEMO_USERNAME="${PULSEOPS_DEMO_USERNAME:-demo}"
PULSEOPS_DEMO_PASSWORD="$(cat .demo/admin-password)"
export PULSEOPS_DEMO_PASSWORD

echo "==> Starting the database, API, worker and lab services"
"${COMPOSE[@]}" up -d --build --wait db migrate api worker lab-target lab-receiver

echo "==> Making sure the operator '${PULSEOPS_DEMO_USERNAME}' exists"
printf '%s\n' "$PULSEOPS_DEMO_PASSWORD" | "${COMPOSE[@]}" run --rm -T --no-deps api \
  pulseops create-admin --username "$PULSEOPS_DEMO_USERNAME" --password-stdin --exists-ok

echo "==> Running the script"
"${COMPOSE[@]}" run --rm --no-deps demo-runner

echo
echo "Dashboard: http://127.0.0.1:${PULSEOPS_PORT:-8000}  (user: ${PULSEOPS_DEMO_USERNAME}, password in .demo/admin-password)"
