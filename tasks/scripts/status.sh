#!/usr/bin/env bash
# Chequeo rápido del estado del demonio: proceso systemd + último heartbeat.
set -euo pipefail

REPO_PATH="${REPO_PATH:-/home/ubuntu/repos/madronoTFM-agent}"
HEALTH_FILE="$REPO_PATH/tasks/scripts/.state/health.json"

echo "== systemd =="
systemctl status madrono-agent --no-pager || true

echo
echo "== heartbeat (${HEALTH_FILE}) =="
if [ -f "$HEALTH_FILE" ]; then
    if command -v jq >/dev/null 2>&1; then
        jq . "$HEALTH_FILE"
    else
        cat "$HEALTH_FILE"
    fi
else
    echo "(sin heartbeat todavía: el demonio no ha completado ningún ciclo)"
fi

echo
echo "== últimas líneas de log =="
journalctl -u madrono-agent --no-pager -n 15
