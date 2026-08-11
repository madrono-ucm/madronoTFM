"""Escritor genérico de la capa Bronze del lakehouse (medallón).

Aterriza lotes de registros normalizados (dicts JSON-serializables) en disco,
replicando la estructura de particionado que tendrá la capa Bronze en S3 (ver
`infra/terraform/` de la tarea 001):

    <base>/<dataset>/fecha=YYYY-MM-DD/hora=HH/<timestamp>_<sufijo>.json

La ruta base es configurable (variable de entorno `BRONZE_BASE_PATH`, ver
`CaptureConfig` en `trafico_madrid.py`) precisamente para poder apuntar a un
punto de montaje S3 o cambiar de backend de almacenamiento sin tocar el
código de los productores que reutilicen esta clase.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


class BronzeWriter:
    """Escribe lotes de registros de un dataset en la capa Bronze local."""

    def __init__(self, base_path: "str | os.PathLike[str]", dataset: str):
        self.base_path = Path(base_path)
        self.dataset = dataset

    def partition_dir(self, moment: datetime) -> Path:
        return (
            self.base_path
            / self.dataset
            / f"fecha={moment:%Y-%m-%d}"
            / f"hora={moment:%H}"
        )

    def write_batch(self, records: Iterable[dict], moment: "datetime | None" = None) -> Path:
        """Escribe `records` como un único fichero JSON en la partición de `moment`.

        Devuelve la ruta del fichero escrito. `moment` determina tanto la
        partición (fecha=/hora=) como el nombre del fichero; por defecto es
        el instante actual en UTC.
        """
        moment = moment or datetime.now(timezone.utc)
        records = list(records)

        out_dir = self.partition_dir(moment)
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{moment:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}.json"
        out_path = out_dir / filename

        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)
        tmp_path.replace(out_path)

        logger.info("Escritos %d registros de '%s' en %s", len(records), self.dataset, out_path)
        return out_path
