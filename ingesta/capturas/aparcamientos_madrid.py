"""Productor de datos abiertos de ocupación de aparcamientos de Madrid (muestra puntual).

Descarga la ocupación en tiempo real (plazas libres) y, para cada aparcamiento
de la muestra, sus plazas totales, y lo normaliza a un esquema mínimo y
consistente. Igual que `transporte_publico_madrid.py` (tarea 003) y
`bicimad.py` (tarea 004), esto es a propósito **solo una captura puntual de
muestra** — ver "Alcance reducido" más abajo.

## Fuente elegida y por qué

Dataset "Aparcamientos públicos (rotacionales). Datos de ocupación en tiempo
real" (id `50027-0-aparcamientosocupacionyservicios`) de
[datos.madrid.es](https://datos.madrid.es/dataset/50027-0-aparcamientosocupacionyservicios):
agrega la ocupación en tiempo real de los aparcamientos públicos rotacionales
(municipales y privados) que comparten voluntariamente su dato con el
Ayuntamiento — el mismo sistema que alimenta la app "Parking Madrid". Se
prefirió sobre otras dos alternativas encontradas:

- **"Aparcamientos EMT"** (datos.emtmadrid.es): son los aparcamientos
  disuasorios operados por la EMT, un subconjunto más pequeño y sin un feed
  público de ocupación en tiempo real tan directo como este.
- **"Aparcamientos públicos municipales (rotacionales). Histórico de
  ocupación"** (dataset 300346): es un agregado mensual/histórico, no
  ocupación en tiempo real — no encaja con el objetivo de esta tarea.

A diferencia de los feeds HTTP simples usados en tareas anteriores (XML de
Informo en tráfico, JSON GBFS en BiciMAD), esta fuente **no publica un XML/JSON
descargable directamente**: el único recurso de datos del dataset es un
servicio **SOAP** (WSDL "infoParking"), cuyo WSDL sí está descargable desde
el portal:

    https://datos.madrid.es/dataset/50027-0-aparcamientosocupacionyservicios/resource/50027-1-aparcamientosocupacionyservicios/download/50027-1-aparcamientosocupacionyservicios.wsdl

El WSDL apunta al endpoint real:

    https://servayto.madrid.es/MTPAR_WSINFO/InfoParking

Se verificó en vivo desde este entorno que este endpoint SOAP es accesible
**sin ninguna autenticación ni API key**: la operación `GetListParking`
devuelve el listado completo de aparcamientos (75 en el momento de esta
captura) con nombre, dirección, coordenadas y, para los que comparten su
ocupación en tiempo real, plazas libres (`lstOccupation`) — no todos los
aparcamientos del listado la incluyen, ya que compartirla es voluntario.
Las plazas totales no vienen en `GetListParking`, pero sí en la operación
`GetDetailParking` (llamada una vez por aparcamiento), en `lstFeatures` como
la característica de tipo "Tipo plaza" con nombre "Total".

TODO(kafka): igual que en los productores anteriores, cuando exista un
broker Kafka (tarea 001), `normalize_record` es la única fuente de verdad
del esquema a reutilizar tanto para el fixture/Bronze como para un topic
Kafka.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import requests

from .bronze import BronzeWriter

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT_URL = "https://servayto.madrid.es/MTPAR_WSINFO/InfoParking"
SOAP_ACTION_LIST = "http://tempuri.org/iInfoParking/GetListParking"
SOAP_ACTION_DETAIL = "http://tempuri.org/iInfoParking/GetDetailParking"
SOAP_ENVELOPE_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TEMPURI_NS = "http://tempuri.org/"
DATA_NS = "http://schemas.datacontract.org/2004/07/InfoParking"

SOURCE_NAME = "madrid_aparcamientos_rotacionales"
DATASET_NAME = "aparcamientos"
DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "aparcamientos_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 5

_LIST_PARKING_BODY = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="{soap_ns}" xmlns:tem="{tempuri_ns}">
  <soap:Body>
    <tem:GetListParking>
      <tem:language>es</tem:language>
    </tem:GetListParking>
  </soap:Body>
</soap:Envelope>""".format(soap_ns=SOAP_ENVELOPE_NS, tempuri_ns=TEMPURI_NS)

_DETAIL_PARKING_BODY_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="{soap_ns}" xmlns:tem="{tempuri_ns}" xmlns:ns1="{data_ns}">
  <soap:Body>
    <tem:GetDetailParking>
      <tem:parametersDetailParking>
        <ns1:id>{parking_id}</ns1:id>
        <ns1:language>es</ns1:language>
        <ns1:family>001</ns1:family>
        <ns1:publicData>true</ns1:publicData>
        <ns1:date>{date}</ns1:date>
      </tem:parametersDetailParking>
    </tem:GetDetailParking>
  </soap:Body>
</soap:Envelope>""".format(
    soap_ns=SOAP_ENVELOPE_NS,
    tempuri_ns=TEMPURI_NS,
    data_ns=DATA_NS,
    parking_id="{parking_id}",
    date="{date}",
)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración del productor, leída de variables de entorno.

    No hay campos de credenciales: el servicio SOAP de aparcamientos de
    datos.madrid.es es público y no requiere API key.
    """

    endpoint_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            endpoint_url=os.environ.get("MADRID_PARKING_ENDPOINT_URL", DEFAULT_ENDPOINT_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_PARKING_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
        )


def _soap_post(config: CaptureConfig, soap_action: str, body: str) -> str:
    """Envía una petición SOAP 1.1, con reintentos simples y backoff lineal."""
    headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": soap_action}
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.post(
                config.endpoint_url,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al llamar a %s (intento %d/%d): %s",
                soap_action,
                attempt,
                config.max_retries,
                exc,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(
        f"No se pudo completar la llamada SOAP {soap_action} tras {config.max_retries} intentos"
    ) from last_exc


def fetch_raw_list_parking(config: CaptureConfig) -> str:
    """Llama a la operación SOAP `GetListParking`: listado completo de aparcamientos."""
    return _soap_post(config, SOAP_ACTION_LIST, _LIST_PARKING_BODY)


def fetch_raw_detail_parking(config: CaptureConfig, parking_id: str) -> str:
    """Llama a la operación SOAP `GetDetailParking` para un aparcamiento concreto."""
    body = _DETAIL_PARKING_BODY_TEMPLATE.format(
        parking_id=parking_id, date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    )
    return _soap_post(config, SOAP_ACTION_DETAIL, body)


def _tag(name: str) -> str:
    return f"{{{DATA_NS}}}{name}"


def _find_text(element: ET.Element, name: str) -> Optional[str]:
    child = element.find(_tag(name))
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _to_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def parse_list_parking(xml_text: str) -> Iterator[dict]:
    """Parsea la respuesta SOAP de `GetListParking` a registros crudos.

    Cada registro conserva `free_spaces`/`measured_at_raw` a `None` cuando el
    aparcamiento no comparte ocupación en tiempo real (campo `lstOccupation`
    ausente) — es voluntario, así que no todos los 75 aparcamientos del
    listado la incluyen.
    """
    root = ET.fromstring(xml_text)
    for parking in root.iter(_tag("lstParking")):
        occupation = parking.find(f"{_tag('lstOccupation')}/{_tag('occupation')}")
        yield {
            "parking_id": _find_text(parking, "id"),
            "name": _find_text(parking, "name"),
            "address": _find_text(parking, "address"),
            "latitude": _to_float(_find_text(parking, "latitude")),
            "longitude": _to_float(_find_text(parking, "longitude")),
            "free_spaces": _to_int(_find_text(occupation, "free")) if occupation is not None else None,
            "measured_at_raw": _find_text(occupation, "moment") if occupation is not None else None,
        }


def parse_total_spaces(xml_text: str) -> Optional[int]:
    """Extrae las plazas totales de una respuesta SOAP de `GetDetailParking`.

    Busca, dentro de `lstFeatures`, la característica de tipo "Tipo plaza"
    llamada "Total" (código `001`), que es la que expone el número total de
    plazas del aparcamiento.
    """
    root = ET.fromstring(xml_text)
    for feature in root.iter(_tag("feature")):
        if _find_text(feature, "name") == "Total" and _find_text(feature, "nameField") == "Tipo plaza":
            return _to_int(_find_text(feature, "content"))
    return None


def normalize_record(entry: dict, total_spaces: Optional[int], ingested_at: datetime) -> dict:
    """Normaliza un aparcamiento (listado + plazas totales) al esquema mínimo."""
    measured_at_raw = entry.get("measured_at_raw")
    measured_at = (
        datetime.fromisoformat(measured_at_raw).astimezone(timezone.utc).isoformat()
        if measured_at_raw
        else None
    )

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "parking_id": entry["parking_id"],
        "name": entry.get("name"),
        "address": entry.get("address"),
        "measured_at": measured_at,
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "free_spaces": entry.get("free_spaces"),
        "total_spaces": total_spaces,
        "location": {
            "lat": entry.get("latitude"),
            "lon": entry.get("longitude"),
            "srid": "EPSG:4326",
        },
    }


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de aparcamientos de Madrid.

    Igual que `transporte_publico_madrid.capture_sample` y
    `bicimad.capture_sample`, esto NO escribe en la capa Bronze particionada:
    escribe una única muestra pequeña (como mucho `config.sample_size`
    aparcamientos) en un fichero fijo, pensado para commitearse como
    fixture, no para acumular capturas.

    Solo se muestrean aparcamientos que comparten ocupación en tiempo real
    (`free_spaces` no nulo en `GetListParking`) — son el subconjunto
    relevante para el objetivo de la tarea (ocupación), de los 75
    aparcamientos que devuelve el listado completo.
    """
    ingested_at = datetime.now(timezone.utc)

    list_xml = fetch_raw_list_parking(config)
    entries = [e for e in parse_list_parking(list_xml) if e["free_spaces"] is not None]
    logger.info(
        "Listado descargado: %d aparcamientos con ocupación en tiempo real (de los devueltos por la fuente)",
        len(entries),
    )
    sample_entries = entries[: config.sample_size]

    records = []
    for entry in sample_entries:
        total_spaces = None
        try:
            detail_xml = fetch_raw_detail_parking(config, entry["parking_id"])
            total_spaces = parse_total_spaces(detail_xml)
        except RuntimeError:
            logger.warning(
                "No se pudieron obtener las plazas totales del aparcamiento %s", entry["parking_id"]
            )
        records.append(normalize_record(entry, total_spaces, ingested_at))

    logger.info("Descargados %d aparcamientos de muestra", len(records))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)

    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza TODOS los aparcamientos con ocupación en tiempo real.

    A diferencia de `capture_sample` (que corta a `config.sample_size` y usa
    los primeros aparcamientos del listado), esto es la captura completa
    pensada para el handler Lambda (tarea 026): pide `GetDetailParking` (una
    llamada SOAP por aparcamiento) para todos los que comparten ocupación en
    tiempo real, no solo la muestra.
    """
    ingested_at = datetime.now(timezone.utc)

    list_xml = fetch_raw_list_parking(config)
    entries = [e for e in parse_list_parking(list_xml) if e["free_spaces"] is not None]
    logger.info(
        "Listado descargado: %d aparcamientos con ocupación en tiempo real (captura completa)",
        len(entries),
    )

    records = []
    for entry in entries:
        total_spaces = None
        try:
            detail_xml = fetch_raw_detail_parking(config, entry["parking_id"])
            total_spaces = parse_total_spaces(detail_xml)
        except RuntimeError:
            logger.warning(
                "No se pudieron obtener las plazas totales del aparcamiento %s", entry["parking_id"]
            )
        records.append(normalize_record(entry, total_spaces, ingested_at))

    logger.info("Descargados %d aparcamientos (captura completa)", len(records))
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
            "Captura una muestra puntual de ocupación de aparcamientos públicos de Madrid "
            "(plazas libres y totales) y la guarda como fixture pequeño. "
            "No admite ejecución en bucle ni programada: es siempre una única captura."
        )
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

    config = CaptureConfig.from_env()
    out_path = capture_sample(config, args.out)
    logger.info("Captura completada: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
