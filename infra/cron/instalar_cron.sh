#!/usr/bin/env bash
# Instalador manual de /etc/cron.d/madrono-retrain (ML_10 / tarea 105).
#
# Deliberadamente NO se ejecuta solo ni desde ningún pipeline automático:
# instala un cron que corre a diario con credenciales AWS reales sobre esta
# EC2, así que requiere criterio y aprobación humana, igual que un
# `terraform apply` (ver doc/105-desplegar-cron-reentrenamiento-nocturno.md).
#
# Uso (a mano, en la EC2 del demonio, tras revisar el resultado):
#   REPO=/home/ubuntu/repos/madronoTFM ./infra/cron/instalar_cron.sh
#
# Qué hace:
#   1. Comprueba espacio libre en / (aborta si hay menos de MIN_LIBRE_MB).
#   2. Comprueba que existe REPO/.venv con las dependencias de
#      modelado/requirements.txt instaladas (aborta si no).
#   3. Genera /etc/cron.d/madrono-retrain a partir de la plantilla con REPO
#      sustituido, y pide confirmación explícita antes de copiarlo (sudo).
set -euo pipefail

MIN_LIBRE_MB="${MIN_LIBRE_MB:-3072}"  # 3 GiB: margen para el panel + logs de una noche
REPO="${REPO:?"Define REPO=<ruta al checkout de producción>, p.ej. REPO=/home/ubuntu/repos/madronoTFM"}"
PLANTILLA="$(dirname "$0")/madrono-retrain.cron"
DESTINO="/etc/cron.d/madrono-retrain"

libre_mb=$(df -Pm / | awk 'NR==2 {print $4}')
if [ "$libre_mb" -lt "$MIN_LIBRE_MB" ]; then
    echo "ABORTADO: solo ${libre_mb} MiB libres en / (mínimo ${MIN_LIBRE_MB} MiB)." >&2
    echo "Resuelve el espacio en disco (ver doc/104-ec2-root-volume-al-limite.md) antes de activar el cron." >&2
    exit 1
fi

if [ ! -x "${REPO}/.venv/bin/python" ]; then
    echo "ABORTADO: no existe ${REPO}/.venv/bin/python." >&2
    echo "Crea el venv primero: python3 -m venv ${REPO}/.venv && ${REPO}/.venv/bin/pip install -r ${REPO}/modelado/requirements.txt" >&2
    exit 1
fi

if ! "${REPO}/.venv/bin/python" -c "import lightgbm, mlflow, pandas, pyarrow, boto3" >/dev/null 2>&1; then
    echo "ABORTADO: el venv de ${REPO} no tiene instaladas las dependencias de modelado/requirements.txt." >&2
    exit 1
fi

echo "Espacio libre: ${libre_mb} MiB (OK, >= ${MIN_LIBRE_MB} MiB)."
echo "Venv verificado en ${REPO}/.venv."
echo
echo "Se va a instalar:"
sed "s#<REPO>#${REPO}#g" "$PLANTILLA"
echo
read -r -p "¿Confirmas instalar este cron con privilegios de root? [escribe SI]: " confirmacion
if [ "$confirmacion" != "SI" ]; then
    echo "Cancelado, nada instalado."
    exit 1
fi

sed "s#<REPO>#${REPO}#g" "$PLANTILLA" | sudo tee "$DESTINO" >/dev/null
sudo chmod 644 "$DESTINO"
echo "Instalado en ${DESTINO}."
