#!/usr/bin/env bash
# Bootstrap del demonio madrono-agent:
#   1. Clona (si hace falta) el clon dedicado REPO_PATH, separado del checkout interactivo.
#   2. Configura la identidad git local de ese clon.
#   3. Crea tasks/scripts/config.env a partir de config.example.env si no existe.
#   4. Instala y arranca el servicio systemd.
#
# Requiere: `gh auth login` ya hecho para el usuario que ejecuta este script (necesario
# para que `git push` y `gh pr create` funcionen dentro del servicio).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Defaults desde el config.example.env del checkout que estamos ejecutando (existe
# tanto la primera vez, desde el repo interactivo, como en reinstalaciones posteriores
# desde el propio clon dedicado).
# shellcheck disable=SC1091
set -a
source "$SCRIPT_DIR/config.example.env"
set +a

if ! REPO_URL_DETECTED="$(git -C "$SOURCE_REPO" remote get-url origin 2>/dev/null)"; then
    REPO_URL_DETECTED="$REPO_URL"
fi
REPO_URL="$REPO_URL_DETECTED"

echo "== madrono-agent install =="
echo "REPO_URL:  $REPO_URL"
echo "REPO_PATH: $REPO_PATH"

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: 'gh' no está instalado." >&2
    exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
    echo "ERROR: 'gh' no tiene sesión iniciada. Ejecuta 'gh auth login' antes de continuar." >&2
    exit 1
fi

if [ ! -d "$REPO_PATH/.git" ]; then
    echo "Clonando $REPO_URL en $REPO_PATH ..."
    git clone "$REPO_URL" "$REPO_PATH"
else
    echo "$REPO_PATH ya existe, no se vuelve a clonar."
fi

git -C "$REPO_PATH" config user.name "$GIT_AUTHOR_NAME"
git -C "$REPO_PATH" config user.email "$GIT_AUTHOR_EMAIL"

CONFIG_ENV="$REPO_PATH/tasks/scripts/config.env"
if [ ! -f "$CONFIG_ENV" ]; then
    echo "Creando $CONFIG_ENV a partir de config.example.env ..."
    cp "$REPO_PATH/tasks/scripts/config.example.env" "$CONFIG_ENV"
else
    echo "$CONFIG_ENV ya existe, no se sobreescribe."
fi

SERVICE_UNIT="$REPO_PATH/tasks/scripts/madrono-agent.service"
echo "Instalando unidad systemd desde $SERVICE_UNIT ..."
sudo cp "$SERVICE_UNIT" /etc/systemd/system/madrono-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now madrono-agent.service

echo
echo "Servicio instalado y arrancado. Comprueba el estado con:"
echo "  systemctl status madrono-agent"
echo "  journalctl -u madrono-agent -f"
