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
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import boto3

logger = logging.getLogger(__name__)

S3_URI_PREFIX = "s3://"


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
        del fichero; por defecto es el instante actual en UTC.
        """
        moment = moment or datetime.now(timezone.utc)
        records = list(records)
        filename = f"{moment:%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}.json"
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
