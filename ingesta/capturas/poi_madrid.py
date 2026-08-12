"""Carga batch puntual de puntos de interés turístico de Madrid (muestra, referencia).

Descarga el catálogo de puntos de interés turístico del Ayuntamiento de
Madrid (edificios y monumentos, museos, parques, instalaciones culturales...)
y lo normaliza a un esquema mínimo pensado para que el asistente
conversacional resuelva preguntas como «¿merece la pena ir a X lugar?» (ver
`documents/Memoria_TFM FV.docx`, apartado 6.1, categoría «Contexto urbano»:
puntos de interés).

## Esto es una carga puntual de referencia, NO una captura periódica

Igual que `callejero_madrid.py` (tarea 009) y `barrios_distritos_madrid.py`
(tarea 010), los puntos de interés turístico de Madrid son un dato de
**referencia**: la ficha de un monumento o museo no cambia minuto a minuto
como el tráfico o la calidad del aire (la propia fuente se declara de
actualización "diaria", pero para incorporar altas/bajas/correcciones
puntuales de fichas, no para reflejar un estado que varía por sí solo). No
tiene sentido programar su recaptura ni siquiera cuando exista
infraestructura real: por eso este módulo, a propósito, **no tiene modo
`--interval-seconds` ni bucle**. La carga completa real de todas las
categorías de POI relevantes, el día que se aplique la infraestructura de la
tarea 001, seguirá siendo una carga batch puntual invocada a mano (p.ej. tras
una actualización relevante del catálogo), no un productor en bucle.

## Fuente elegida y por qué

Dataset "Puntos de interés turístico de la ciudad de Madrid. Qué visitar en
Madrid (www.esmadrid.com)" (id `300030-0-puntos-interes-turistico`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300030-0-puntos-interes-turistico),
publicado por Madrid Destino, Cultura, Turismo y Negocio, S.A. Es un único
XML con **935 fichas** (a fecha de esta captura) de espacios "para visitar"
(museos, monumentos, salas de exposiciones, parques, instalaciones
culturales/deportivas...), cada una con descripción, geoposición, dirección
postal, horario y coste de acceso si aplica — exactamente el tipo de
contenido que el objetivo de la tarea pedía (datasets de datos.madrid.es por
categoría de POI: monumentos y lugares de interés turístico, instalaciones
deportivas, bibliotecas, mercados...).

Se descartaron dos alternativas encontradas en la investigación:

- **"Edificios de carácter monumental"** (id `208844-0-monumentos-edificios`):
  un listado más estrecho (solo edificios catalogados como Bien de Interés
  Cultural o similar), sin descripción turística ni horarios/precios.
- **"Planeamiento Urbanístico. Catálogo de Elementos Singulares"**
  (id `300486-0-planeamiento-elemento-singulares`): un dataset urbanístico
  (protección patrimonial), no de contenido turístico orientado al visitante.

### Una sola categoría elegida, no dos: "Edificios y monumentos"

El propio XML clasifica cada ficha con una o varias categorías (campo
`extradata/categorias/categoria`). Sobre las 935 fichas totales, la
distribución de categorías es: 395 "Instalaciones culturales", 355
"Edificios y monumentos", 63 "Parques y jardines", 40 "Parques y centros de
ocio", 31 "Empresas de guías turísticos", 25 "Otros", 21 "Espacios para
eventos", 20 "Servicios", 13 "Instalaciones deportivas", 11 "Escuelas de
cocina y catas de vinos y aceites", 8 "Cotrabajo", 4 "Consignas" (una ficha
puede tener más de una categoría, por eso la suma supera 935).

Se eligió **una única categoría, "Edificios y monumentos"** (`idCategoria`
`7173`), no dos: es la que más directamente encaja con "monumentos y lugares
de interés turístico" (el ejemplo que da el propio objetivo de la tarea) y
con la pregunta guía «¿merece la pena ir a X lugar?» — a diferencia de
categorías como "Empresas de guías turísticos" o "Servicios" (agencias,
no lugares que visitar) o "Cotrabajo"/"Consignas" (infraestructura de
soporte, no atractivos turísticos). Añadir una segunda categoría solo
habría diluido el objetivo de esta primera captura sin aportar más
variedad de *esquema* (todas las categorías comparten la misma estructura
XML); una tarea futura de carga completa puede iterar sobre el resto de
categorías reutilizando este mismo módulo sin cambios de esquema.

Se ha verificado en vivo desde este entorno que el recurso es accesible
**sin ninguna autenticación ni API key**. El servidor `esmadrid.com` sí
devuelve `403 Forbidden` a peticiones sin cabecera `User-Agent` o con la que
usan por defecto `requests`/`curl -A` (un filtro básico anti-bot, no una
restricción de acceso real); este módulo declara un `User-Agent` de
navegador convencional para evitarlo (ver `_REQUEST_HEADERS`).

### Licencia: textos libres, fotografías no

El propio dataset advierte de condiciones de uso específicas ("Condiciones
reutilización información Madrid Destino"): *"Los textos son de libre uso
pero no así las fotografías"*. Por eso este módulo, a propósito, **no
incluye las URLs de `<multimedia><media>` en el esquema normalizado**: solo
texto y metadatos (nombre, categoría, descripción, dirección, coordenadas,
horario, precio, contacto), que la fuente sí permite reutilizar libremente.

### Formato real encontrado y decisiones de parseo

El XML se publica en varios idiomas (`turismo_v1_<es|en|de|fr|it|pt|ru>.xml`);
este módulo usa el español por defecto. Cada `<service>` trae, entre otros,
`basicData` (nombre, contacto, descripción en HTML dentro de `body`, enlace),
`geoData` (dirección, código postal, y coordenadas) y `extradata`
(categorías/subcategorías, horario, forma de pago). El PDF de estructura
que publica el propio dataset etiqueta `latitude`/`longitude` como "UTM",
pero los valores reales son grados decimales WGS84 (p.ej. `40.429992`,
`-3.706535` para un punto en Madrid) — un error de documentación de la
fuente, no un dato real en UTM; se han comprobado en vivo y se tratan como
WGS84 (`EPSG:4326`) sin ninguna reproyección.

Los campos de texto libre (`name`/`title`, `body`, "Horario", "Servicios de
pago") traen HTML embebido y, en el caso de `name`/`title`, entidades HTML
**doblemente escapadas** (p.ej. el texto ya parseado por XML contiene
literalmente `&eacute;` en vez de `é`, porque la fuente escribió
`&amp;eacute;` en el XML crudo). `_strip_html` quita las etiquetas HTML,
aplica `html.unescape` (que resuelve tanto las entidades XML estándar que
XML ya decodificó como las entidades HTML nombradas que quedaron sin
resolver) y colapsa espacios, produciendo texto plano legible en ambos
casos.

No hay dato de **distrito ni barrio** en la fuente (solo dirección postal y
código postal): a diferencia de otras capturas de este proyecto, aquí no se
intenta derivarlo (una derivación fiable requeriría un cruce
punto-en-polígono con los límites de `barrios_distritos_madrid.py`, tarea
010 — fuera del alcance de esta captura de muestra); se deja `district` y
`neighbourhood` a `null`, tal como permite el objetivo de la tarea cuando el
dato "no viene incluido en la fuente ni se puede derivar" de forma simple.

TODO(kafka): igual que `callejero_madrid.py` y `barrios_distritos_madrid.py`,
esta fuente es de referencia y no encaja con el patrón de un topic Kafka por
evento — su destino natural es directamente el grafo Neo4j (o una tabla de
dimensión en el lakehouse), no un stream. Se deja la nota igualmente por
consistencia con el resto de módulos, pero no se espera que esta fuente
conecte nunca a un broker Kafka.
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

import requests

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_URL = "https://www.esmadrid.com/opendata/turismo_v1_es.xml"

SOURCE_NAME = "madrid_poi_turismo"

# "Edificios y monumentos": la categoría elegida para esta primera captura
# (ver docstring del módulo, sección "Una sola categoría elegida").
DEFAULT_CATEGORY_ID = "7173"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "poi_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 5

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno.

    No hay campos de credenciales: el recurso de datos.madrid.es usado aquí
    es público y no requiere API key.
    """

    source_url: str
    category_id: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            source_url=os.environ.get("MADRID_POI_SOURCE_URL", DEFAULT_SOURCE_URL),
            category_id=os.environ.get("MADRID_POI_CATEGORY_ID", DEFAULT_CATEGORY_ID),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_POI_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
        )



# El servidor de esmadrid.com devuelve 403 Forbidden a peticiones sin
# User-Agent o con el user-agent por defecto de `requests`/`curl -A`; un
# navegador habitual sí pasa. No es una API con autenticación: es un filtro
# básico de bot por cabecera, así que basta con declarar un User-Agent
# corriente.
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; madrono-ingesta/1.0)"}


def _fetch_with_retries(config: CaptureConfig, url: str) -> bytes:
    """Descarga una URL, con reintentos simples y backoff lineal."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, headers=_REQUEST_HEADERS, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al descargar %s (intento %d/%d): %s", url, attempt, config.max_retries, exc
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo descargar {url} tras {config.max_retries} intentos") from last_exc


def fetch_raw_pois(config: CaptureConfig) -> str:
    """Descarga el XML completo del catálogo de puntos de interés (español)."""
    return _fetch_with_retries(config, config.source_url).decode("utf-8")


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _text(element: Optional[ET.Element], path: str) -> Optional[str]:
    if element is None:
        return None
    child = element.find(path)
    if child is None or child.text is None:
        return None
    return _clean(child.text)


def _unescape(raw: Optional[str]) -> Optional[str]:
    """Deshace entidades HTML, incluidas las que la fuente deja doblemente escapadas.

    `name`/`title` traen entidades HTML nombradas (p.ej. `&eacute;`) que ya
    llegan como texto literal tras el parseo XML (el XML crudo las escribe
    como `&amp;eacute;`); `html.unescape` las resuelve. Es un no-op seguro
    sobre texto que ya está resuelto (la mayoría de campos, con acentos como
    bytes UTF-8 directos).
    """
    value = _clean(raw)
    if value is None:
        return None
    return html.unescape(value)


def _strip_html(raw: Optional[str]) -> Optional[str]:
    """Convierte un campo de texto con HTML embebido (`body`, horario, precio) a texto plano."""
    value = _clean(raw)
    if value is None:
        return None
    without_tags = _TAG_RE.sub(" ", value)
    unescaped = html.unescape(without_tags)
    collapsed = _WHITESPACE_RE.sub(" ", unescaped).strip()
    return collapsed or None


def _to_float(raw: Optional[str]) -> Optional[float]:
    value = _clean(raw)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _matched_category(service: ET.Element, category_id: str) -> Optional[dict]:
    """Si `service` tiene la categoría `category_id`, devuelve su nombre y subcategorías.

    Devuelve `None` si el servicio no tiene esa categoría asociada (un
    servicio puede tener varias categorías; solo importa si la buscada está
    entre ellas).
    """
    categorias = service.find("extradata/categorias")
    if categorias is None:
        return None
    for categoria in categorias.findall("categoria"):
        id_item = categoria.find("item[@name='idCategoria']")
        if id_item is None or _clean(id_item.text) != category_id:
            continue
        name_item = categoria.find("item[@name='Categoria']")
        subcategories = [
            _unescape(sub_item.text)
            for sub_item in categoria.findall("subcategorias/subcategoria/item[@name='SubCategoria']")
            if _clean(sub_item.text)
        ]
        return {"name": _unescape(name_item.text if name_item is not None else None), "subcategories": subcategories}
    return None


def select_sample_pois(pois_xml: str, category_id: str, sample_size: int) -> list[tuple[ET.Element, dict]]:
    """Recorre el XML en orden y toma los primeros `sample_size` servicios de `category_id`.

    Se descartan los puntos sin coordenadas conocidas: no debería ocurrir
    en la práctica (los 355 puntos de "Edificios y monumentos" verificados
    en la investigación de esta tarea traían coordenadas), pero se comprueba
    por robustez, igual que `select_sample_vias` en `callejero_madrid.py`
    (tarea 009).
    """
    root = ET.fromstring(pois_xml)
    selected: list[tuple[ET.Element, dict]] = []
    for service in root.findall("service"):
        match = _matched_category(service, category_id)
        if match is None:
            continue
        if not _text(service.find("geoData"), "latitude") or not _text(service.find("geoData"), "longitude"):
            continue
        selected.append((service, match))
        if len(selected) >= sample_size:
            break
    return selected


def normalize_record(service: ET.Element, category: dict, ingested_at: datetime) -> dict:
    """Normaliza un `<service>` del catálogo al esquema mínimo de puntos de interés."""
    basic_data = service.find("basicData")
    geo_data = service.find("geoData")
    extradata = service.find("extradata")

    name = _unescape(_text(basic_data, "name")) or _unescape(_text(basic_data, "title"))

    schedule_item = extradata.find("item[@name='Horario']") if extradata is not None else None
    price_item = extradata.find("item[@name='Servicios de pago']") if extradata is not None else None

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "poi_id": _clean(service.get("id")),
        "name": name,
        "category": category["name"],
        "subcategories": category["subcategories"],
        "description": _strip_html(_text(basic_data, "body")),
        "address": _clean(_text(geo_data, "address")),
        "postal_code": _clean(_text(geo_data, "zipcode")),
        "locality": _clean(_text(geo_data, "locality")),
        "country": _clean(_text(geo_data, "country")),
        "district": None,
        "neighbourhood": None,
        "website": _clean(_text(basic_data, "web")),
        "phone": _clean(_text(basic_data, "phone")),
        "email": _clean(_text(basic_data, "email")),
        "schedule": _strip_html(schedule_item.text if schedule_item is not None else None),
        "price_info": _strip_html(price_item.text if price_item is not None else None),
        "last_updated": _clean(service.get("fechaActualizacion")),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "location": {
            "lat": _to_float(_text(geo_data, "latitude")),
            "lon": _to_float(_text(geo_data, "longitude")),
            "srid": "EPSG:4326",
        },
    }


def _write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de puntos de interés.

    Igual que `callejero_madrid.py` (tarea 009) y `barrios_distritos_madrid.py`
    (tarea 010), esto NO escribe en la capa Bronze particionada ni deja nada
    programado: escribe un único fichero de muestra pequeño y fijo (como
    mucho `config.sample_size` puntos de interés), pensado para commitearse
    como fixture, no para acumularse en disco. El catálogo completo (935
    fichas) se descarga en memoria porque la fuente no ofrece filtrado
    remoto, pero nunca se escribe a disco.
    """
    ingested_at = datetime.now(timezone.utc)

    pois_xml = fetch_raw_pois(config)
    sample = select_sample_pois(pois_xml, config.category_id, config.sample_size)
    records = [normalize_record(service, category, ingested_at) for service, category in sample]
    logger.info("Puntos de interés de muestra seleccionados: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de puntos de interés turístico de "
            "Madrid y la guarda como fixture pequeño. No admite ejecución en bucle "
            "ni programada: es una carga puntual invocada a mano, pensada para no "
            "repetirse salvo que el catálogo cambie de forma relevante."
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
