"""Escritor genérico de la capa Bronze del lakehouse (medallón).

Aterriza lotes de registros normalizados (dicts JSON-serializables),
replicando la estructura de particionado de la capa Bronze:

    <base>/<dataset>/fecha=YYYY-MM-DD/hora=HH/<timestamp>_<sufijo>.json

La ruta base es configurable (variable de entorno `BRONZE_BASE_PATH`, ver
`CaptureConfig` en `trafico_madrid.py`). Soporta dos backends, elegidos según
la forma de `base_path`:

- **Local (disco)**: cualquier ruta que no empiece por `s3://` (por defecto,
  `./bronze`). Escribe con `Path.open()`, tal como desde la tarea 002.
- **S3**: rutas `s3://<bucket>/<prefijo-opcional>`, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/` (bucket real de la tarea 015).
  Escribe con `boto3` (`put_object`) usando las credenciales por defecto de
  `boto3` — en la EC2 de ingesta, las del rol de instancia
  `madrono-tfm-dev-ingestion-role`, sin necesidad de configurar ninguna
  credencial explícita. No hace falta ningún cambio en los productores que
  reutilizan esta clase: basta con apuntar `BRONZE_BASE_PATH` a la URI S3.

`write_batch` devuelve la ubicación del fichero escrito: un `Path` en modo
local (sin cambios respecto a la tarea 002), o un `str` con la URI
`s3://bucket/key` en modo S3.

El particionado (`fecha=/hora=`) y el nombre de fichero de cada lote se
calculan en **hora de Madrid** (tarea 034), no en UTC: `write_batch` usa
`now_madrid()` por defecto cuando no se pasa `moment` explícitamente. Ver
`now_madrid()` más abajo para el porqué.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import boto3

logger = logging.getLogger(__name__)

S3_URI_PREFIX = "s3://"

MADRID_TZ = ZoneInfo("Europe/Madrid")


def now_madrid() -> datetime:
    """Devuelve el instante actual como `datetime` *aware* en hora de Madrid.

    Usa `zoneinfo` (librería estándar, sin dependencias de terceros) con la
    zona `Europe/Madrid`, que aplica automáticamente el desfase real según
    la época del año (CET/UTC+1 en invierno, CEST/UTC+2 en verano) en vez de
    un offset fijo. Se usa como valor por defecto de `moment` en
    `BronzeWriter.write_batch`, para que el particionado (`fecha=/hora=`) de
    Bronze refleje la hora local de Madrid y no UTC (tarea 034).

    Verificado en el entorno de desarrollo/CI de este repo que
    `ZoneInfo("Europe/Madrid")` resuelve sin `ZoneInfoNotFoundError` (la base
    de datos IANA de zonas horarias está disponible en el sistema) — no ha
    hecho falta añadir `tzdata` a `ingesta/requirements.txt` como fallback.
    Si un entorno futuro (p. ej. una imagen base de Lambda distinta) careciera
    de esa base de datos, este `ZoneInfo(...)` de módulo fallaría al importar
    `ingesta.capturas.bronze`; en ese caso habría que añadir `tzdata` a
    `ingesta/requirements.txt` y reconstruir la Lambda Layer (tarea 032).
    """
    return datetime.now(MADRID_TZ)


def _parse_s3_uri(uri: str) -> "tuple[str, str]":
    """Descompone `s3://bucket/prefijo` en `(bucket, prefijo_sin_barra_final)`."""
    without_scheme = uri[len(S3_URI_PREFIX):]
    bucket, _, prefix = without_scheme.partition("/")
    return bucket, prefix.strip("/")


class BronzeWriter:
    """Escribe lotes de registros de un dataset en la capa Bronze (local o S3)."""

    def __init__(self, base_path: "str | os.PathLike[str]", dataset: str):
        self.dataset = dataset
        base_path_str = str(base_path)

        if base_path_str.startswith(S3_URI_PREFIX):
            self.base_path = base_path_str.rstrip("/")
            self.s3_bucket, self.s3_prefix = _parse_s3_uri(self.base_path)
            self.s3_client = boto3.client("s3")
        else:
            self.base_path = Path(base_path)
            self.s3_bucket = None
            self.s3_prefix = None
            self.s3_client = None

    @property
    def is_s3(self) -> bool:
        return self.s3_client is not None

    def partition_dir(self, moment: datetime) -> Path:
        """Solo modo local -- en modo S3 usar `partition_key()`.

        `self.base_path` es `str` en modo S3 y `Path` en modo local; el
        operador `/` de abajo solo tiene sentido sobre el `Path`. La guarda
        convierte un `TypeError` confuso de operador en un fallo inmediato y
        explicativo si alguna vez se llama en modo S3 (FIL_40).
        """
        if self.is_s3:
            raise RuntimeError(
                "partition_dir() no aplica en modo S3; usar partition_key()"
            )
        return (
            self.base_path
            / self.dataset
            / f"fecha={moment:%Y-%m-%d}"
            / f"hora={moment:%H}"
        )

    def partition_key(self, moment: datetime) -> str:
        """Equivalente a `partition_dir` para el modo S3: prefijo de la key."""
        parts = [p for p in (self.s3_prefix, self.dataset) if p]
        parts += [f"fecha={moment:%Y-%m-%d}", f"hora={moment:%H}"]
        return "/".join(parts)

    def write_batch(
        self, records: Iterable[dict], moment: "datetime | None" = None
    ) -> "Path | str":
        """Escribe `records` como un único fichero JSON en la partición de `moment`.

        Devuelve la ruta (local) o URI `s3://...` (S3) del objeto escrito.
        `moment` determina tanto la partición (fecha=/hora=) como el nombre
        del fichero; por defecto es el instante actual en hora de Madrid
        (`now_madrid()`, tarea 034).
        """
        moment = moment or now_madrid()
        records = list(records)
        # Sin sufijo "Z": ese sufijo ISO-8601 denota UTC, y `moment` ya no lo
        # es por defecto (hora de Madrid, tarea 034) — mantenerlo induciría a
        # error sobre en qué zona horaria está expresado el nombre.
        filename = f"{moment:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}.json"
        body = json.dumps(records, ensure_ascii=False).encode("utf-8")

        if self.is_s3:
            key = f"{self.partition_key(moment)}/{filename}"
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
            out_uri = f"{S3_URI_PREFIX}{self.s3_bucket}/{key}"
            logger.info(
                "Escritos %d registros de '%s' en %s", len(records), self.dataset, out_uri
            )
            return out_uri

        out_dir = self.partition_dir(moment)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename

        tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
        with tmp_path.open("wb") as f:
            f.write(body)
        tmp_path.replace(out_path)

        logger.info("Escritos %d registros de '%s' en %s", len(records), self.dataset, out_path)
        return out_path
