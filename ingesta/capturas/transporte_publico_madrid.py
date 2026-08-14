"""Productor de datos abiertos de transporte público de Madrid (muestra puntual).

Descarga los próximos tiempos de llegada de autobús en una parada de la EMT
Madrid (Empresa Municipal de Transportes) usando la API REST "MobilityLabs"
de su portal de datos abiertos, la normaliza a un esquema mínimo y
consistente, y guarda una **muestra pequeña** como fixture versionado en
`ingesta/capturas/samples/`.

Fuente: https://openapi.emtmadrid.es — API MobilityLabs de la EMT, catalogada
en https://datos.emtmadrid.es. Documentación / registro:
https://mobilitylabs.emtmadrid.es/es/portal/opendata.

## Autenticación (credenciales de aplicación, v1.1)

La tarea 003 asumió que la API se autentica con email+contraseña de una
cuenta personal verificada por correo (endpoint v1). Esa asunción era
incorrecta y bloqueó la captura: el mecanismo real (verificado en vivo en la
tarea 024) es un login **v1.1** con credenciales de **aplicación**
(`x-ClientId` / `passKey`), no de usuario:

    GET https://openapi.emtmadrid.es/v1.1/mobilitylabs/user/login/
    Headers: x-ClientId: <client id>, passKey: <pass key>, Content-Type: application/json

que devuelve (si `code == "00"`) un `accessToken` en `data[0].accessToken`,
a reenviar en la cabecera `accessToken` de las siguientes llamadas (aquí, la
de llegadas a una parada, sin cambios respecto a la tarea 003). Este script
lee las credenciales de las variables de entorno `EMT_CLIENT_ID` /
`EMT_PASS_KEY` — nunca hardcodeadas, y nunca registradas en logs (solo se
registra el código de estado HTTP de la respuesta de login).

## Captura real completada (tarea 024)

Con `EMT_CLIENT_ID`/`EMT_PASS_KEY` ya configurados en el entorno de esta
sesión, el flujo completo (login v1.1 -> llegadas a la parada 71) se
verificó en vivo y funciona: login `200`/`code=00`, llegadas `200`/`code=00`.
El fixture de muestra commiteado en
`ingesta/capturas/samples/transporte_publico_madrid_sample.json` son datos
reales descargados con `capture_sample`, no inventados a mano (a diferencia
de la muestra original de la tarea 003).

TODO(kafka): igual que en `trafico_madrid.py`, cuando exista un broker Kafka
(tarea 001), `normalize_record` es la única fuente de verdad del esquema a
reutilizar tanto para el fixture/Bronze como para un topic Kafka.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import requests

from .bronze import BronzeWriter

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openapi.emtmadrid.es"
LOGIN_PATH = "/v1.1/mobilitylabs/user/login/"
ARRIVALS_PATH = "/v2/transport/busemtmad/stops/{stop_id}/arrives/"
SOURCE_NAME = "madrid_emt_llegadas"
DATASET_NAME = "transporte_publico_emt"
DEFAULT_STOP_ID = "71"
DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "transporte_publico_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 5


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración del productor, leída de variables de entorno."""

    base_url: str
    stop_id: str
    client_id: Optional[str]
    pass_key: Optional[str]
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls, stop_id: Optional[str] = None) -> "CaptureConfig":
        return cls(
            base_url=os.environ.get("EMT_API_BASE_URL", DEFAULT_BASE_URL),
            stop_id=stop_id or os.environ.get("EMT_STOP_ID", DEFAULT_STOP_ID),
            client_id=os.environ.get("EMT_CLIENT_ID"),
            pass_key=os.environ.get("EMT_PASS_KEY"),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("EMT_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
        )


def _request_with_retries(config: CaptureConfig, request_fn) -> dict:
    """Ejecuta `request_fn()` (una llamada `requests.*`) con reintentos simples."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = request_fn()
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo en petición a la API EMT (intento %d/%d): %s",
                attempt,
                config.max_retries,
                exc,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(
        f"No se pudo completar la petición a la API EMT tras {config.max_retries} intentos"
    ) from last_exc


def fetch_access_token(config: CaptureConfig) -> str:
    """Hace login en la API EMT (v1.1, credenciales de aplicación) y devuelve el `accessToken`.

    Requiere `EMT_CLIENT_ID`/`EMT_PASS_KEY` (credenciales de aplicación, no de
    una cuenta de usuario personal — ver docstring del módulo). Lanza
    `RuntimeError` si faltan credenciales o si la API responde con un código
    de error. Nunca registra las credenciales ni el `accessToken` obtenido en
    los logs.
    """
    if not config.client_id or not config.pass_key:
        raise RuntimeError(
            "Faltan credenciales EMT: define EMT_CLIENT_ID y EMT_PASS_KEY "
            "con las credenciales de aplicación de MobilityLabs (ver "
            "docstring del módulo)."
        )

    url = config.base_url.rstrip("/") + LOGIN_PATH
    body = _request_with_retries(
        config,
        lambda: requests.get(
            url,
            headers={
                "x-ClientId": config.client_id,
                "passKey": config.pass_key,
                "Content-Type": "application/json",
            },
            timeout=config.timeout_seconds,
        ),
    )

    # code="00": login nuevo ("Register user..."). code="01": la API ya
    # tenía una sesión reciente en caché para estas credenciales y devuelve
    # el token extendido ("Token extend...") en vez de crear uno nuevo.
    # Ambos traen un `accessToken` válido en `data[0]`; solo el resto de
    # códigos son error (verificado en vivo: "99" sin credenciales, "91"
    # email no verificado en el flujo v1 anterior).
    if body.get("code") not in ("00", "01"):
        raise RuntimeError(f"Login EMT fallido (code={body.get('code')})")
    logger.info("Login EMT correcto (code=%s)", body.get("code"))
    return body["data"][0]["accessToken"]


def fetch_raw_arrivals(config: CaptureConfig, access_token: str) -> dict:
    """Descarga las próximas llegadas a `config.stop_id`, ya autenticado."""
    url = config.base_url.rstrip("/") + ARRIVALS_PATH.format(stop_id=config.stop_id)
    body = _request_with_retries(
        config,
        lambda: requests.post(
            url,
            headers={"accessToken": access_token},
            json={"stopId": str(config.stop_id), "Text_EstimationsRequired_YN": "Y"},
            timeout=config.timeout_seconds,
        ),
    )

    if body.get("code") != "00":
        raise RuntimeError(
            f"Consulta de llegadas EMT fallida (code={body.get('code')}): "
            f"{body.get('description')}"
        )
    return body


def normalize_record(arrival: dict, stop_id: str, ingested_at: datetime) -> dict:
    """Normaliza un elemento `Arrive` de la respuesta de la API al esquema mínimo."""
    coordinates = arrival.get("geometry", {}).get("coordinates") or [None, None]

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "stop_id": str(stop_id),
        "line": str(arrival["line"]) if arrival.get("line") is not None else None,
        "bus_id": arrival.get("bus"),
        "destination": arrival.get("destination"),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "estimate_arrive_sec": arrival.get("estimateArrive"),
        "distance_bus_m": arrival.get("DistanceBus"),
        "is_head": str(arrival.get("isHead", "False")).lower() == "true",
        "deviation_sec": arrival.get("deviation", 0),
        "position_type_bus": arrival.get("positionTypeBus"),
        "location": {
            "lon": coordinates[0] if len(coordinates) > 0 else None,
            "lat": coordinates[1] if len(coordinates) > 1 else None,
            "srid": "EPSG:4326",
        },
    }


def parse_records(response_json: dict, stop_id: str, ingested_at: datetime) -> Iterator[dict]:
    """Parsea la respuesta cruda del endpoint de llegadas y produce registros normalizados."""
    data = response_json.get("data") or [{}]
    arrivals = data[0].get("Arrive", [])
    for arrival in arrivals:
        yield normalize_record(arrival, stop_id, ingested_at)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de llegadas a `config.stop_id`.

    A diferencia de `trafico_madrid.capture_once`, esto NO escribe en la capa
    Bronze particionada: escribe una única muestra pequeña (como mucho
    `config.sample_size` registros) en un fichero fijo, pensado para
    commitearse como fixture versionado, no para acumular capturas.
    """
    ingested_at = datetime.now(timezone.utc)
    access_token = fetch_access_token(config)
    response_json = fetch_raw_arrivals(config, access_token)
    records = list(parse_records(response_json, config.stop_id, ingested_at))[: config.sample_size]
    logger.info("Descargadas %d llegadas de muestra para la parada %s", len(records), config.stop_id)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)

    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza TODAS las llegadas a `config.stop_id` (sin recorte de muestra).

    A diferencia de `capture_sample` (que corta a `config.sample_size` para
    el fixture versionado), esto es la captura completa pensada para el
    handler Lambda (tarea 026): la API ya devuelve todas las llegadas
    vigentes de una única parada, así que "completa" aquí significa "sin el
    slicing `[:sample_size]`", no una fuente distinta.
    """
    ingested_at = datetime.now(timezone.utc)
    access_token = fetch_access_token(config)
    response_json = fetch_raw_arrivals(config, access_token)
    records = list(parse_records(response_json, config.stop_id, ingested_at))
    logger.info("Descargadas %d llegadas (captura completa) para la parada %s", len(records), config.stop_id)
    return records


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 026): captura completa a Bronze real."""
    config = CaptureConfig.from_env()
    records = capture_all(config)
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura una muestra puntual de próximas llegadas de autobús de la EMT "
            "Madrid a una parada, y la guarda como fixture pequeño. No admite "
            "ejecución en bucle ni programada: es siempre una única captura."
        )
    )
    parser.add_argument(
        "--stop-id",
        default=None,
        help=f"ID de parada EMT a consultar (por defecto: $EMT_STOP_ID o {DEFAULT_STOP_ID!r})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_SAMPLE_PATH,
        help="Ruta del fichero de muestra a escribir",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Nivel de logging (DEBUG, INFO, WARNING, ...)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = CaptureConfig.from_env(stop_id=args.stop_id)
    out_path = capture_sample(config, args.out)
    logger.info("Captura completada: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
