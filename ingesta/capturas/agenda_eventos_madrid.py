"""Captura puntual de la agenda oficial de eventos culturales y de ocio de Madrid.

Complementa a `bluesky_menciones_madrid.py` (tarea 016, opiniones/menciones
informales sobre lugares) con una fuente de mayor calidad para "eventos" en
concreto: dato oficial y programado (conciertos, exposiciones, actividades
en bibliotecas/centros culturales/juveniles/de mayores...), justo el tipo de
señal que ayuda a explicar picos de afluencia esperados en un lugar y
momento concretos (ver `documents/Memoria_TFM FV.docx`, apartado 6.1). A
diferencia de la tarea 012 (zona gris) y de intentar inferir eventos solo de
redes sociales (tarea 016), esta fuente es dato abierto oficial sin
scraping ni zona gris.

Se investigaron y descartaron dos alternativas antes de esta tarea:
Eventbrite (su búsqueda pública de eventos está descontinuada; su API solo
gestiona eventos propios de una cuenta) y Foursquare (reseñas/tips detrás de
un tier de pago).

## Dos fuentes, un mismo esquema normalizado

- **`agenda_eventos_madrid_municipal`**: dataset "Actividades culturales y de
  ocio municipal en los próximos 100 días" del portal de datos abiertos del
  Ayuntamiento de Madrid (id `206974-0-agenda-eventos-culturales-100`,
  licencia CC-BY 4.0, dato abierto sin restricción). Cubre únicamente
  actividades en centros **municipales** (culturales, socioculturales,
  juveniles, bibliotecas, centros de mayores, museos, Juntas de Distrito...).
- **`agenda_turismo_esmadrid`**: dataset "Agenda de la ciudad de Madrid"
  (id `300028-0-agenda-turismo`), gestionado por Madrid Destino
  (`esmadrid.com`, el portal de promoción turística de la ciudad) y también
  listado en el catálogo de datos.madrid.es. Se investigó tal como pedía el
  enunciado de la tarea: **sí aporta cobertura relevante que la agenda
  municipal no tiene** — conciertos y espectáculos en salas/teatros
  privados (verificado en vivo: p.ej. "Zucchero (Madrid Live Experience
  2026)", "Real Madrid - Ajax Vrouwen (UEFA Women's Champions League)"),
  ferias, exposiciones y grandes eventos de ciudad que no se celebran en
  centros municipales. Por eso se decidió **incluirla en esta misma tarea**,
  no dejarla anotada para el futuro: el volumen de trabajo extra (un
  segundo `fetch_*`/`normalize_*` que parsea XML en vez de JSON-LD) es
  moderado y el esquema normalizado ya absorbe ambas fuentes con los mismos
  campos.

Ambas se combinan en **un único fichero de muestra** con el campo `source`
para distinguirlas (mismo patrón que `bluesky_menciones_madrid.py`, tarea
016, para "un único dataset con campo que distingue el origen"), en vez de
dos ficheros separados: quien consuma la agenda para responder "¿qué hay
hoy en Malasaña?" quiere ambas fuentes juntas, no una por evento municipal
y otra por evento privado.

### Licencia de `agenda_turismo_esmadrid`: texto y datos sí, fotos no

`package_show` marca este dataset como `"isopen": false` (licencia
`madrid-destino`, no CC-BY), a diferencia del dataset municipal. Se leyó la
licencia completa
(<https://datos.madrid.es/pages/condiciones-reutilizacion-informacion-madrid-destino>,
consultada en vivo durante esta sesión): permite expresamente "la
reutilización de los documentos textuales y datos... para fines comerciales
y no comerciales", pero **limita la reutilización de fotografías y material
gráfico**. Por eso `normalize_esmadrid_event` no incluye ninguna URL de
imagen del bloque `<multimedia>` del XML de origen, aunque el dato esté
disponible — solo se capturan campos de texto/geolocalización/fechas.

## Fuente elegida para cada dataset, y por qué

- **Municipal**: se investigó el endpoint CKAN `datastore_search`
  (`https://datos.madrid.es/api/action/datastore_search?resource_id=...`)
  que sugiere el enunciado de la tarea, pero **respondió con una página HTML
  de mantenimiento** ("Ayuntamiento de Madrid - En mantenimiento",
  verificado en vivo durante esta sesión) en vez de JSON. En su lugar se usa
  el recurso JSON-LD del propio catálogo
  (`https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json`,
  resource `206974-0-...-json` de `package_show`), que respondió con
  normalidad (669 eventos en el momento de la captura) y es, de hecho, más
  simple de consumir que CKAN: una lista `@graph` de objetos ya tipados, sin
  paginación que gestionar para una muestra pequeña.
- **esMadrid**: el propio dataset solo ofrece recursos XML (uno por idioma:
  es/en/fr/it/ru/pt/de). Se usa el recurso en español
  (`https://www.esmadrid.com/opendata/agenda_v1_es.xml`), el idioma nativo
  del resto de fuentes de este proyecto; no hay recurso JSON.

## Simplificación deliberada: solo el primer rango de fechas

El dato municipal ya viene con un único `dtstart`/`dtend` por evento. El
dato de esMadrid, en cambio, modela recurrencia real (`<fechas><rango>` con
`inicio`/`fin`/`dias`, más `<exclusion>`/`<inclusion>` para sesiones sueltas
que se saltan o añaden al patrón — p.ej. "Miserable Parte II", todos los
sábados entre el 19 de septiembre y el 12 de diciembre, salvo el 10 de
octubre y el 28 de noviembre, más una sesión extra el 9 de octubre). Modelar
esa recurrencia completa (RRULE-like) excede el alcance de "esquema mínimo y
consistente" de esta tarea: `normalize_esmadrid_event` solo toma el
`inicio`/`fin` del primer `<rango>` como `start_datetime`/`end_datetime` (el
periodo en que el evento está activo, sin desglosar cada sesión concreta) y
conserva el texto libre de `<item name="Horario">` en un campo separado
`schedule_text`, para que quien lo necesite pueda leer el patrón exacto
("Sábados: 22:30 h. No hay función los días: 10 de octubre y 28 de
noviembre"). Si una tarea futura necesita fechas de sesión individuales
exactas, debería parsear ese texto o `dias`/`exclusion`/`inclusion`
explícitamente — no está hecho aquí. El dataset municipal también se
normaliza con un `schedule_text` (su campo `time`, p.ej. `"22:00"`) para que
ambas fuentes compartan la misma clave.

## Esto es una captura puntual de muestra, no un productor continuo

Igual que las tareas 003-008, 012, 013 y 016, este módulo **no tiene modo
`--interval-seconds` ni bucle**, y no escribe en la capa Bronze
particionada: escribe un único fichero de muestra pequeño (por defecto 5
eventos de cada fuente) pensado para commitearse como fixture.

TODO(kafka): igual que el resto de productores de muestra, el punto donde
se conectaría un productor Kafka para una futura captura periódica real
(el dataset municipal se actualiza a diario, según su metadato
`frequency`) está marcado aquí por consistencia, aunque no se despliega
ningún scheduling en esta tarea.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import requests

from .bronze import BronzeWriter

logger = logging.getLogger(__name__)

SOURCE_MUNICIPAL = "agenda_eventos_madrid_municipal"
SOURCE_ESMADRID = "agenda_turismo_esmadrid"
DATASET_NAME = "agenda_eventos"

DEFAULT_MUNICIPAL_URL = (
    "https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json"
)
DEFAULT_ESMADRID_URL = "https://www.esmadrid.com/opendata/agenda_v1_es.xml"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "agenda_eventos_madrid_sample.json"

DEFAULT_DESCRIPTION_MAX_LENGTH = 400


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    No requiere ninguna credencial: ambos datasets son de lectura pública
    sin autenticación.
    """

    municipal_url: str
    esmadrid_url: str
    municipal_sample_size: int
    esmadrid_sample_size: int
    description_max_length: int
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            municipal_url=os.environ.get("AGENDA_MADRID_MUNICIPAL_URL", DEFAULT_MUNICIPAL_URL),
            esmadrid_url=os.environ.get("AGENDA_MADRID_ESMADRID_URL", DEFAULT_ESMADRID_URL),
            municipal_sample_size=_env_int("AGENDA_MADRID_MUNICIPAL_SAMPLE_SIZE", 5),
            esmadrid_sample_size=_env_int("AGENDA_MADRID_ESMADRID_SAMPLE_SIZE", 5),
            description_max_length=_env_int(
                "AGENDA_MADRID_DESCRIPTION_MAX_LENGTH", DEFAULT_DESCRIPTION_MAX_LENGTH
            ),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


_REQUEST_HEADERS = {
    # esmadrid.com devuelve 403 (bloqueo de WAF) con el User-Agent por defecto de
    # `requests`, verificado en vivo durante esta sesión; con un User-Agent de
    # navegador responde 200 con normalidad. datos.madrid.es no lo necesita, pero
    # se envía en ambas peticiones por simplicidad, sin efecto adverso.
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml, */*",
}


def _get_with_retries(config: CaptureConfig, url: str) -> requests.Response:
    """Petición GET con reintentos simples y backoff lineal, devuelve la `Response` cruda."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, headers=_REQUEST_HEADERS, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al consultar %s (intento %d/%d): %s", url, attempt, config.max_retries, exc
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo consultar {url} tras {config.max_retries} intentos") from last_exc


def _truncate(text: Optional[str], max_length: int = DEFAULT_DESCRIPTION_MAX_LENGTH) -> Optional[str]:
    """Recorta una descripción larga a `max_length` caracteres, con puntos suspensivos."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _strip_html(raw_html: Optional[str]) -> Optional[str]:
    if not raw_html:
        return None
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip() or None


def _last_path_segment(uri: Optional[str]) -> Optional[str]:
    """Extrae el último segmento de una URI del vocabulario de datos.madrid.es.

    Usado tanto para la categoría (`@type`, p.ej.
    `.../actividades/CineActividadesAudiovisuales` -> `"CineActividadesAudiovisuales"`)
    como para el distrito/barrio (`address.district["@id"]`, p.ej.
    `.../Distrito/Hortaleza` -> `"Hortaleza"`).
    """
    if not uri:
        return None
    return unquote(uri.rstrip("/").rsplit("/", 1)[-1]) or None


# ---------------------------------------------------------------------------
# Dataset municipal (JSON-LD)
# ---------------------------------------------------------------------------


def fetch_municipal_events_raw(config: CaptureConfig) -> "list[dict]":
    """Descarga el catálogo JSON-LD completo y devuelve la lista cruda `@graph`."""
    response = _get_with_retries(config, config.municipal_url)
    payload = response.json()
    return payload.get("@graph") or []


def _parse_municipal_datetime(raw: Optional[str]) -> Optional[str]:
    """`"2026-08-21 22:00:00.0"` -> `"2026-08-21T22:00:00"`; deja el original si no encaja."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw.split(".")[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw
    return dt.isoformat()


def normalize_municipal_event(raw: dict, captured_at: datetime) -> dict:
    """Normaliza un evento crudo del catálogo municipal al esquema mínimo común."""
    address = raw.get("address") or {}
    area = address.get("area") or {}
    location = raw.get("location") or {}
    lat = location.get("latitude")
    lon = location.get("longitude")
    free_raw = raw.get("free")
    return {
        "schema_version": 1,
        "source": SOURCE_MUNICIPAL,
        "event_id": raw.get("id") or raw.get("uid"),
        "title": raw.get("title") or None,
        "description": _truncate(raw.get("description")),
        "category": _last_path_segment(raw.get("@type")),
        "start_datetime": _parse_municipal_datetime(raw.get("dtstart")),
        "end_datetime": _parse_municipal_datetime(raw.get("dtend")),
        "schedule_text": raw.get("time") or None,
        "free": bool(free_raw) if free_raw is not None else None,
        "price_info": raw.get("price") or None,
        "location": {
            "venue_name": raw.get("event-location") or None,
            "address": area.get("street-address") or None,
            "district": _last_path_segment((address.get("district") or {}).get("@id")),
            "neighborhood": _last_path_segment(area.get("@id")),
            "postal_code": area.get("postal-code") or None,
            "lat": lat,
            "lon": lon,
            "srid": "EPSG:4326" if lat is not None and lon is not None else None,
        },
        "url": raw.get("link") or None,
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
    }


def fetch_municipal_events(config: CaptureConfig, limit: Optional[int] = None) -> "list[dict]":
    """Descarga y normaliza los primeros `limit` eventos del dataset municipal."""
    limit = config.municipal_sample_size if limit is None else limit
    raw_events = fetch_municipal_events_raw(config)
    captured_at = datetime.now(timezone.utc)
    return [normalize_municipal_event(raw, captured_at) for raw in raw_events[:limit]]


# ---------------------------------------------------------------------------
# Dataset esMadrid / Madrid Destino (XML)
# ---------------------------------------------------------------------------


def fetch_esmadrid_services_raw(config: CaptureConfig) -> "list[ET.Element]":
    """Descarga el XML completo y devuelve la lista cruda de elementos `<service>`."""
    response = _get_with_retries(config, config.esmadrid_url)
    root = ET.fromstring(response.content)
    return root.findall("service")


def parse_esmadrid_xml(xml_bytes: bytes) -> "list[ET.Element]":
    """Parsea un documento XML de la agenda de esMadrid ya en memoria (sin red, para tests)."""
    root = ET.fromstring(xml_bytes)
    return root.findall("service")


def _element_text(service: ET.Element, path: str) -> Optional[str]:
    node = service.find(path)
    if node is None or node.text is None:
        return None
    return node.text.strip() or None


def _parse_esmadrid_date(raw: Optional[str]) -> Optional[str]:
    """`"19/09/2026"` -> `"2026-09-19"`; deja el original si no encaja."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%d/%m/%Y")
    except ValueError:
        return raw
    return dt.date().isoformat()


def normalize_esmadrid_event(service: ET.Element, captured_at: datetime) -> dict:
    """Normaliza un `<service>` crudo de la agenda de esMadrid al esquema mínimo común.

    Solo toma el primer `<rango>` de fechas como periodo del evento (ver
    docstring del módulo, "Simplificación deliberada"); no se incluye
    ninguna URL de `<multimedia>` (ver docstring, "Licencia").
    """
    tipo = _element_text(service, ".//extradata/item[@name='Tipo']")
    categoria = _element_text(service, ".//extradata/categorias/categoria/item[@name='Categoria']")
    subcategoria = _element_text(
        service, ".//extradata/categorias/categoria/subcategorias/subcategoria/item[@name='SubCategoria']"
    )
    category = " > ".join(part for part in (tipo, categoria, subcategoria) if part) or None

    rango = service.find(".//extradata/fechas/rango")
    start_raw = rango.findtext("inicio") if rango is not None else None
    end_raw = rango.findtext("fin") if rango is not None else None

    lat_raw = _element_text(service, "geoData/latitude")
    lon_raw = _element_text(service, "geoData/longitude")
    lat = float(lat_raw) if lat_raw else None
    lon = float(lon_raw) if lon_raw else None

    return {
        "schema_version": 1,
        "source": SOURCE_ESMADRID,
        "event_id": service.get("id"),
        # Algunos eventos (p.ej. partidos de LALIGA) traen el título con entidades
        # HTML sin decodificar dentro del propio CDATA de origen (`"M&aacute;laga"`
        # en vez de `"Málaga"`), a diferencia del resto del feed que sí usa UTF-8
        # directo; se decodifica igual que ya se hacía para `description`/`schedule_text`.
        "title": html.unescape(_element_text(service, "basicData/name") or "") or None,
        "description": _truncate(_strip_html(_element_text(service, "basicData/body"))),
        "category": category,
        "start_datetime": _parse_esmadrid_date(start_raw),
        "end_datetime": _parse_esmadrid_date(end_raw),
        "schedule_text": _strip_html(_element_text(service, ".//extradata/item[@name='Horario']")),
        "free": None,
        "price_info": _strip_html(_element_text(service, ".//extradata/item[@name='Servicios de pago']")),
        "location": {
            "venue_name": _element_text(service, "basicData/nombrert"),
            "address": _element_text(service, "geoData/address"),
            "district": None,
            "neighborhood": None,
            "postal_code": _element_text(service, "geoData/zipcode"),
            "lat": lat,
            "lon": lon,
            "srid": "EPSG:4326" if lat is not None and lon is not None else None,
        },
        "url": _element_text(service, "basicData/web"),
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
    }


def fetch_esmadrid_events(config: CaptureConfig, limit: Optional[int] = None) -> "list[dict]":
    """Descarga y normaliza los primeros `limit` eventos del dataset de esMadrid."""
    limit = config.esmadrid_sample_size if limit is None else limit
    raw_services = fetch_esmadrid_services_raw(config)
    captured_at = datetime.now(timezone.utc)
    return [normalize_esmadrid_event(service, captured_at) for service in raw_services[:limit]]


# ---------------------------------------------------------------------------
# Captura combinada
# ---------------------------------------------------------------------------


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña combinando ambas fuentes.

    Igual que las tareas 003-008, 012, 013 y 016, esto NO escribe en la capa
    Bronze particionada ni deja nada programado: escribe un único fichero de
    muestra pequeño y fijo (como mucho `municipal_sample_size +
    esmadrid_sample_size` eventos), pensado para commitearse como fixture.
    """
    records: "list[dict]" = []
    records.extend(fetch_municipal_events(config))
    records.extend(fetch_esmadrid_events(config))
    logger.info("Eventos de muestra capturados: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza TODOS los eventos de ambas fuentes (sin recorte de muestra).

    A diferencia de `fetch_municipal_events`/`fetch_esmadrid_events` (que
    cortan a `municipal_sample_size`/`esmadrid_sample_size`), esto es la
    captura completa pensada para el handler Lambda (tarea 026): los ~669
    eventos municipales y todos los `<service>` de la agenda de esMadrid.
    """
    captured_at = datetime.now(timezone.utc)
    records = [normalize_municipal_event(raw, captured_at) for raw in fetch_municipal_events_raw(config)]
    records += [normalize_esmadrid_event(s, captured_at) for s in fetch_esmadrid_services_raw(config)]
    logger.info("Normalizados %d eventos de la agenda (captura completa)", len(records))
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
            "Captura puntual de muestra de la agenda de eventos culturales de Madrid, "
            "combinando el dataset municipal de datos.madrid.es y la agenda turística de "
            "esmadrid.com. No admite ejecución en bucle ni programada."
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
    capture_sample(config, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
