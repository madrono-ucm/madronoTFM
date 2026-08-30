"""Captura puntual de previsión meteorológica y avisos de AEMET para Madrid.

Complementa a `meteorologia_madrid.py` (tarea 008, tiempo **actual** medido
por la red municipal de estaciones) con dos señales que esa fuente no da:
una **previsión** a varios días (necesaria para responder "¿voy esta noche?"
o "¿qué tiempo hará el sábado?") y los **avisos oficiales** de fenómenos
meteorológicos adversos vigentes (amarillo/naranja/rojo), la fuente oficial
española para ambas cosas es AEMET OpenData (`opendata.aemet.es`), tal como
pedía el enunciado de esta tarea.

## Bloqueo de registro: la API key de AEMET OpenData exige resolver un reCAPTCHA

Se investigó en vivo, durante esta sesión, el formulario de alta de usuario
(<https://opendata.aemet.es/centrodedescargas/altaUsuario>): pide un email y,
antes de poder enviarlo, **obliga a resolver un reCAPTCHA de Google**
(`grecaptcha.getResponse()` se comprueba explícitamente en el JS del propio
formulario antes de habilitar el envío). No hay ninguna vía de alta
alternativa sin CAPTCHA documentada. Esto es un bloqueo manual no
automatizable en este pipeline, de la misma naturaleza que el de la
verificación de correo de la EMT en la tarea 003 y el de la cuenta de Google
Cloud en la tarea 012 (afluencia de lugares): no hay ningún buzón de correo
ni navegador interactivo disponible en esta sesión para completarlo.

Se verificó también, en vivo y sin key, que el propio servicio de datos
exige un `api_key` con forma de JWT (`GET .../diaria/28079?api_key=test`
devuelve `401` con `"JWT strings must contain exactly 2 period characters.
Found: 0"`; con una cadena con la forma de un JWT pero inválida, devuelve
`401` con un error distinto de parseo del token) — confirma que no existe
ninguna clave de prueba/demo pública utilizable sin pasar por el alta.

Por eso este módulo sigue el mismo patrón que la tarea 012: el código queda
**completo y listo para ejecutarse tal cual** el día que alguien complete el
alta manualmente y configure `AEMET_API_KEY` (nunca hardcodeada); `main()`
falla explícitamente si la variable no está definida. La muestra commiteada
en `ingesta/capturas/samples/` se generó **a mano**, seguida exactamente del
esquema real (ver más abajo cómo se obtuvo cada una), con `"is_mock": true`
en cada registro.

## El esquema JSON real sí se obtuvo, sin necesidad de una key válida

AEMET publica su especificación OpenAPI completa **sin autenticación** en
<https://opendata.aemet.es/AEMET_OpenData_specification.json> (verificado en
vivo: `200 OK`, JSON completo). De ahí se tomaron, con certeza, los dos
endpoints usados por este módulo y su envoltorio de respuesta:

- `GET /api/prediccion/especifica/municipio/diaria/{municipio}` — código de
  municipio INE (`28079` = Madrid capital). Descripción oficial: *"Periodicidad
  de actualización: continuamente"* (ver sección de cadencia en
  `ingesta/README.md`).
- `GET /api/avisos_cap/ultimoelaborado/area/{area}` — código de área; `72` =
  "Madrid, Comunidad de" (tabla completa de códigos CCAA en la propia
  especificación).

Ambos, como el resto de la API de AEMET OpenData, devuelven **en dos pasos**:
la llamada con `api_key` a la URL anterior no trae el dato en sí, solo un
sobre `{"descripcion", "estado", "datos", "metadatos"}` con la URL real
(`datos`) donde está el payload — confirmado por el esquema `#/components/schemas/200`
de la propia especificación (usado tal cual por `_fetch_two_step_wrapper`).

## Previsión diaria: esquema verificado con datos reales de Madrid en vivo

El payload de `datos` de la previsión diaria es JSON con nombres de campo en
camelCase (`probPrecipitacion`, `estadoCielo`, `viento`, `rachaMax`,
`temperatura`, `sensTermica`, `humedadRelativa`, `uvMax`...), documentado de
forma consistente en el ecosistema de clientes de AEMET OpenData. Para no
depender solo de documentación de terceros, se contrastó ese esquema con
datos **reales y en vivo** de Madrid capital obtenidos, sin ninguna
autenticación, del feed público legado que la propia web de AEMET usa para
pintar la ficha de cada municipio
(`https://www.aemet.es/xml/municipios/localidad_28079.xml`, verificado en
vivo: `200 OK`, XML con los mismos campos que la API OpenData documentada,
solo que en `snake_case`/atributos XML en vez de JSON, y en codificación
`ISO-8859-15`). Los valores numéricos de la muestra commiteada
(`aemet_prevision_madrid_sample.json`) son justamente **esos valores reales**
de esa consulta en vivo (Madrid, 13 de agosto de 2026), reestructurados a
mano al esquema JSON documentado de OpenData — no están inventados, aunque
no se obtuvieron a través del endpoint de pago-con-key que pide la tarea, así
que igualmente se marcan `is_mock: true` por honestidad sobre la vía real de
captura.

**Importante (quirk documentado de AEMET):** el payload de `datos` de
OpenData se sirve realmente en **`ISO-8859-15`**, no en UTF-8, con
independencia de la cabecera `Content-Type` de la respuesta (mismo problema
de codificación que sufre el feed legado usado para contrastar el esquema);
`fetch_prediccion_raw` decodifica explícitamente con ese códec.

Solo se implementa la previsión **diaria** (`.../diaria/{municipio}`), no la
horaria (`.../horaria/{municipio}`): ambas comparten el mismo patrón de
envoltorio de dos pasos, pero el payload horario tiene una forma distinta
(un valor por hora en vez de máximo/mínimo por día) que no se ha podido
contrastar con datos reales en esta sesión (no existe un feed legado sin key
equivalente para horaria, verificado en vivo: las URLs candidatas devuelven
`404`). Añadirla en una tarea futura sin poder verificarla contra datos
reales habría supuesto un riesgo real de esquema incorrecto sin forma de
detectarlo; se prefiere dejarla fuera antes que una implementación a medias
sin verificar.

## Avisos: esquema CAP 1.2, sin contrastar con datos reales

El payload de `datos` de `avisos_cap` es un `.tar.gz` con uno o varios
documentos XML en formato CAP 1.2 (Common Alerting Protocol), el estándar
que AEMET declara usar explícitamente en su propia página de ayuda
(<https://www.aemet.es/es/eltiempo/prediccion/avisos/ayuda>, consultada en
vivo). Esa misma página documenta, sin necesidad de autenticación, los tres
niveles de aviso y su significado (amarillo: peligro bajo, "esté atento";
naranja: peligro importante, "esté preparado"; rojo: peligro extraordinario,
"actúe") y los periodos preferentes de emisión (ver cadencia en
`ingesta/README.md`). La estructura interna de cada documento CAP
(`<info><event>`, `<severity>`, `<urgency>`, `<certainty>`, `<onset>`/
`<expires>`, `<parameter>` con `AEMET-Meteoalerta nivel`/`fenomeno`/`zona`,
`<area><areaDesc>`...) sigue el estándar CAP 1.2 y el patrón ampliamente
documentado de los avisos de AEMET, pero a diferencia de la previsión diaria
**no se ha podido contrastar contra un documento CAP real** de AEMET en esta
sesión (no existe, que se haya encontrado, un feed público equivalente sin
key). `parse_cap_alert`/`_extract_cap_xml_documents` quedan implementados
contra el estándar documentado, pero con ese matiz de menor confianza
explícito aquí y en `ingesta/README.md`.

## Esto es una captura puntual de muestra, no un productor continuo

Igual que las tareas 003-008, 012, 013, 016 y 017, este módulo **no tiene
modo `--interval-seconds` ni bucle**, y no escribe en la capa Bronze
particionada: escribe dos ficheros de muestra pequeños y fijos, pensados
para commitearse como fixture.

TODO(kafka): igual que el resto de productores de muestra, el punto donde se
conectaría un productor Kafka para una futura captura periódica real está
marcado aquí por consistencia. La cadencia real de AEMET (ver
`ingesta/README.md`) debería determinar el schedule final: la previsión
diaria se actualiza "continuamente" según su propia documentación, y los
avisos tienen periodos de emisión preferentes conocidos (07:30-09:00,
10:30-11:30, 17:00-19:00, 23:50), así que no hace falta sondear con más
frecuencia que esos huecos.

## Handler Lambda (tarea 028): un único handler, elegido por `event["tipo"]`

Se implementa **un único** `lambda_handler`, no dos funciones separadas,
que decide qué capturar según `event.get("tipo")` (`"prevision"` por
defecto, o `"avisos"`): ambas capturas comparten `CaptureConfig.from_env()`
y la misma `AEMET_API_KEY`, así que dos EventBridge rules distintas —una
por cada cadencia real, ver el TODO anterior— pueden apuntar al mismo
Lambda pasando un `tipo` distinto en su `input` configurado, sin duplicar
el despliegue de función/rol IAM para algo que en el fondo es la misma
integración con la misma credencial.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tarfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests

from . import secretos
from .bronze import MADRID_TZ, BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

SOURCE_PREDICCION = "aemet_prediccion_municipio"
SOURCE_AVISOS = "aemet_avisos_cap"
DATASET_PREDICCION = "aemet_prevision"
DATASET_AVISOS = "aemet_avisos"

OPENDATA_BASE_URL = "https://opendata.aemet.es/opendata"
DEFAULT_PREDICCION_DIARIA_URL_TEMPLATE = (
    OPENDATA_BASE_URL + "/api/prediccion/especifica/municipio/diaria/{municipio}"
)
DEFAULT_AVISOS_URL_TEMPLATE = OPENDATA_BASE_URL + "/api/avisos_cap/ultimoelaborado/area/{area}"

# Código INE de Madrid capital (municipio) y código de área CCAA de AEMET
# para "Madrid, Comunidad de" (tabla de la especificación OpenAPI oficial).
DEFAULT_MUNICIPIO_CODE = "28079"
DEFAULT_AREA_CODE = "72"

DEFAULT_PREDICCION_SAMPLE_PATH = Path(__file__).parent / "samples" / "aemet_prevision_madrid_sample.json"
DEFAULT_AVISOS_SAMPLE_PATH = Path(__file__).parent / "samples" / "aemet_avisos_madrid_sample.json"

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    `api_key` es la única credencial: una API key gratuita de AEMET OpenData
    (ver docstring del módulo, sección "Bloqueo de registro").
    """

    api_key: str
    municipio_code: str
    area_code: str
    prediccion_url_template: str
    avisos_url_template: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            api_key=secretos.get_secret("AEMET_API_KEY") or "",
            municipio_code=os.environ.get("AEMET_MUNICIPIO_CODE", DEFAULT_MUNICIPIO_CODE),
            area_code=os.environ.get("AEMET_AREA_CODE", DEFAULT_AREA_CODE),
            prediccion_url_template=os.environ.get(
                "AEMET_PREDICCION_URL_TEMPLATE", DEFAULT_PREDICCION_DIARIA_URL_TEMPLATE
            ),
            avisos_url_template=os.environ.get("AEMET_AVISOS_URL_TEMPLATE", DEFAULT_AVISOS_URL_TEMPLATE),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            # AEMET OpenData es un tier gratuito con límite de peticiones (documentado como
            # "peticiones que sobrepasan los límites del servicio" -> 401/429); no tiene sentido
            # reintentar agresivamente un 429, así que los reintentos son pocos y solo cubren
            # fallos de red transitorios, no cuota agotada.
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


def _get_with_retries(config: CaptureConfig, url: str, params: Optional[dict] = None) -> requests.Response:
    """Petición GET con reintentos simples y backoff lineal, devuelve la `Response` cruda.

    No reintenta si AEMET responde 429 (cuota superada): reintentar un límite
    de cuota no lo resuelve, solo lo agrava.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=config.timeout_seconds)
            if response.status_code == 429:
                raise RuntimeError(
                    f"AEMET OpenData devolvió 429 (límite de peticiones del tier gratuito superado) en {url}"
                )
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


def _fetch_two_step_wrapper(config: CaptureConfig, url: str) -> dict:
    """Resuelve el sobre de dos pasos común a toda la API de AEMET OpenData.

    La llamada inicial (con `api_key`) no trae el dato: trae un JSON
    `{"descripcion", "estado", "datos", "metadatos"}` donde `datos` es la URL
    real del payload (ver docstring del módulo).
    """
    response = _get_with_retries(config, url, params={"api_key": config.api_key})
    payload = response.json()
    if payload.get("estado") != 200:
        raise RuntimeError(f"AEMET OpenData devolvió estado {payload.get('estado')}: {payload.get('descripcion')}")
    return payload


# ---------------------------------------------------------------------------
# Previsión diaria por municipio
# ---------------------------------------------------------------------------


def fetch_prediccion_raw(config: CaptureConfig, municipio_code: str) -> dict:
    """Descarga y decodifica el payload de previsión diaria de un municipio.

    Devuelve el primer (y único) objeto de municipio del array que trae la
    fuente, ya parseado desde JSON. AEMET sirve este payload en
    `ISO-8859-15` con independencia de la cabecera `Content-Type` (ver
    docstring del módulo): se decodifica explícitamente con ese códec antes
    de parsear el JSON.
    """
    url = config.prediccion_url_template.format(municipio=municipio_code)
    wrapper = _fetch_two_step_wrapper(config, url)
    datos_response = _get_with_retries(config, wrapper["datos"])
    text = datos_response.content.decode("iso-8859-15")
    payload = json.loads(text)
    return payload[0] if payload else {}


def _period_value(entries: "list[dict] | None", periodo: str = "00-24", key: str = "value"):
    """Busca, en una lista de objetos `{"periodo": ..., <key>: ...}`, el del periodo dado.

    El payload diario repite cada magnitud varias veces con distintos
    `periodo` (día completo `"00-24"`, mañana/tarde `"00-12"`/`"12-24"`...);
    esta captura se queda con el resumen del día completo. Devuelve `None`
    si la magnitud no trae ningún dato para ese periodo (ocurre en días
    lejanos de la previsión, con menos certidumbre).
    """
    for entry in entries or []:
        if entry.get("periodo") == periodo:
            value = entry.get(key)
            return value if value not in (None, "") else None
    return None


def normalize_prediccion_dia(raw_dia: dict, municipio_meta: dict, captured_at: datetime, is_mock: bool = False) -> dict:
    """Normaliza un día de previsión (`prediccion.dia[i]` del payload crudo) al esquema mínimo."""
    temperatura = raw_dia.get("temperatura") or {}
    sens_termica = raw_dia.get("sensTermica") or {}
    humedad = raw_dia.get("humedadRelativa") or {}
    viento_dia = _period_value(raw_dia.get("viento"), key="direccion")
    velocidad_dia = _period_value(raw_dia.get("viento"), key="velocidad")

    return {
        "schema_version": 1,
        "source": SOURCE_PREDICCION,
        "municipio_code": municipio_meta.get("id"),
        "municipio_name": municipio_meta.get("nombre"),
        "province": municipio_meta.get("provincia"),
        "elaborated_at": municipio_meta.get("elaborado"),
        "valid_date": (raw_dia.get("fecha") or "").split("T")[0] or None,
        "sky_state": _period_value(raw_dia.get("estadoCielo"), key="descripcion"),
        "sky_state_code": _period_value(raw_dia.get("estadoCielo"), key="value"),
        "precipitation_probability_pct": _period_value(raw_dia.get("probPrecipitacion")),
        "temperature_max_c": temperatura.get("maxima"),
        "temperature_min_c": temperatura.get("minima"),
        "thermal_sensation_max_c": sens_termica.get("maxima"),
        "thermal_sensation_min_c": sens_termica.get("minima"),
        "humidity_max_pct": humedad.get("maxima"),
        "humidity_min_pct": humedad.get("minima"),
        "wind_direction": viento_dia,
        "wind_speed_kmh": velocidad_dia,
        "wind_gust_max_kmh": _period_value(raw_dia.get("rachaMax")),
        "uv_max": raw_dia.get("uvMax"),
        "captured_at": captured_at.astimezone(MADRID_TZ).isoformat(),
        "is_mock": is_mock,
    }


def fetch_prediccion(config: CaptureConfig, municipio_code: Optional[str] = None, limit: Optional[int] = None) -> "list[dict]":
    """Descarga y normaliza la previsión diaria completa (todos los días que traiga la fuente).

    `limit`, si se da, recorta a los primeros `limit` días (pensado para la
    muestra pequeña, no para uso normal).
    """
    municipio_code = municipio_code or config.municipio_code
    raw = fetch_prediccion_raw(config, municipio_code)
    dias = (raw.get("prediccion") or {}).get("dia") or []
    if limit is not None:
        dias = dias[:limit]
    captured_at = now_madrid()
    return [normalize_prediccion_dia(dia, raw, captured_at) for dia in dias]


# ---------------------------------------------------------------------------
# Avisos de fenómenos meteorológicos adversos (CAP)
# ---------------------------------------------------------------------------


def fetch_avisos_archive(config: CaptureConfig, area_code: str) -> bytes:
    """Descarga el `.tar.gz` de avisos vigentes para un área (código CCAA de AEMET)."""
    url = config.avisos_url_template.format(area=area_code)
    wrapper = _fetch_two_step_wrapper(config, url)
    return _get_with_retries(config, wrapper["datos"]).content


def _extract_cap_xml_documents(archive_bytes: bytes) -> "list[bytes]":
    """Extrae los documentos CAP XML de un archivo `.tar(.gz)` de avisos de AEMET.

    Recorre todas las entradas del tar y se queda con las que terminan en
    `.xml`; no asume ninguna estructura de subcarpetas concreta (ver
    docstring del módulo: no se ha podido contrastar contra un archivo real).
    Un archivo sin ningún aviso vigente para el área consultada es un tar
    vacío (0 documentos), no un error.
    """
    documents = []
    with tarfile.open(fileobj=BytesIO(archive_bytes), mode="r:*") as tar:
        for member in tar.getmembers():
            if member.isfile() and member.name.lower().endswith(".xml"):
                extracted = tar.extractfile(member)
                if extracted is not None:
                    documents.append(extracted.read())
    return documents


def _cap_findtext(elem: ET.Element, path: str) -> Optional[str]:
    text = elem.findtext(path, namespaces=CAP_NS)
    return text.strip() if text and text.strip() else None


def parse_cap_alert(xml_bytes: bytes) -> "list[dict]":
    """Parsea un documento CAP 1.2 en memoria y devuelve un dict crudo por bloque `<info>`.

    Función pura (sin red ni tar), separada para poder testear la
    normalización con un XML de ejemplo sin depender de la descarga y
    extracción real del `.tar.gz`. Un mismo `<alert>` puede traer varios
    `<info>` (p.ej. uno por idioma); se devuelven todos, sin filtrar aquí.
    """
    root = ET.fromstring(xml_bytes)
    identifier = _cap_findtext(root, "cap:identifier")
    sent = _cap_findtext(root, "cap:sent")

    infos = []
    for info in root.findall("cap:info", CAP_NS):
        parameters = {}
        for parameter in info.findall("cap:parameter", CAP_NS):
            value_name = _cap_findtext(parameter, "cap:valueName")
            value = _cap_findtext(parameter, "cap:value")
            if value_name:
                parameters[value_name] = value
        areas = [
            desc
            for desc in (_cap_findtext(area, "cap:areaDesc") for area in info.findall("cap:area", CAP_NS))
            if desc
        ]
        infos.append(
            {
                "identifier": identifier,
                "sent": sent,
                "language": _cap_findtext(info, "cap:language"),
                "event": _cap_findtext(info, "cap:event"),
                "severity": _cap_findtext(info, "cap:severity"),
                "urgency": _cap_findtext(info, "cap:urgency"),
                "certainty": _cap_findtext(info, "cap:certainty"),
                "onset": _cap_findtext(info, "cap:onset"),
                "expires": _cap_findtext(info, "cap:expires"),
                "headline": _cap_findtext(info, "cap:headline"),
                "description": _cap_findtext(info, "cap:description"),
                "parameters": parameters,
                "areas": areas,
            }
        )
    return infos


def normalize_aviso(info: dict, captured_at: datetime, is_mock: bool = False) -> dict:
    """Normaliza un bloque `<info>` ya parseado (ver `parse_cap_alert`) al esquema mínimo.

    `level`/`phenomenon`/`zone` vienen de los `<parameter>` propios de AEMET
    (`AEMET-Meteoalerta nivel`/`fenomeno`/`zona`), documentados en su página
    de ayuda pública; si faltaran, se cae a los campos CAP estándar
    (`event`, primera `areaDesc`).
    """
    parameters = info.get("parameters") or {}
    areas = info.get("areas") or []
    return {
        "schema_version": 1,
        "source": SOURCE_AVISOS,
        "identifier": info.get("identifier"),
        "sent_at": info.get("sent"),
        "zone": parameters.get("AEMET-Meteoalerta zona") or (areas[0] if areas else None),
        "level": parameters.get("AEMET-Meteoalerta nivel"),
        "phenomenon": parameters.get("AEMET-Meteoalerta fenomeno") or info.get("event"),
        "probability": parameters.get("AEMET-Meteoalerta probabilidad"),
        "severity": info.get("severity"),
        "urgency": info.get("urgency"),
        "certainty": info.get("certainty"),
        "effective_from": info.get("onset"),
        "effective_until": info.get("expires"),
        "headline": info.get("headline"),
        "description": info.get("description"),
        "captured_at": captured_at.astimezone(MADRID_TZ).isoformat(),
        "is_mock": is_mock,
    }


def fetch_avisos(config: CaptureConfig, area_code: Optional[str] = None) -> "list[dict]":
    """Descarga, extrae y normaliza los avisos vigentes para un área (por defecto, Madrid).

    Devuelve una lista vacía, sin error, si no hay ningún aviso vigente para
    el área en el momento de la captura (caso normal la mayor parte del
    tiempo). Solo conserva los bloques `<info>` en español (`language`
    empieza por `"es"`) cuando un mismo aviso trae varios idiomas.
    """
    area_code = area_code or config.area_code
    archive_bytes = fetch_avisos_archive(config, area_code)
    captured_at = now_madrid()

    records = []
    for xml_bytes in _extract_cap_xml_documents(archive_bytes):
        for info in parse_cap_alert(xml_bytes):
            language = info.get("language")
            if language and not language.startswith("es"):
                continue
            records.append(normalize_aviso(info, captured_at))
    return records


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


def capture_sample(
    config: CaptureConfig,
    prediccion_out_path: Path,
    avisos_out_path: Path,
) -> "tuple[Path, Path]":
    """Descarga, normaliza y guarda una muestra pequeña de previsión y de avisos.

    Requiere `AEMET_API_KEY` configurada (ver docstring del módulo,
    "Bloqueo de registro"): a diferencia de otros productores de este
    proyecto, aquí no hay ningún endpoint público sin autenticación posible,
    así que no tiene sentido intentar la captura sin clave. Igual que en las
    tareas 003-008, 012, 013, 016 y 017, esto NO escribe en la capa Bronze
    particionada ni deja nada programado.
    """
    if not config.api_key:
        raise RuntimeError(
            "AEMET_API_KEY no está configurada. Ver docstring del módulo, sección "
            "'Bloqueo de registro', para completar el alta (manual, requiere resolver "
            "un reCAPTCHA) en https://opendata.aemet.es/centrodedescargas/altaUsuario."
        )

    prediccion_records = fetch_prediccion(config)
    logger.info("Previsión de muestra capturada: %d días", len(prediccion_records))
    _write_json(prediccion_records, prediccion_out_path)

    avisos_records = fetch_avisos(config)
    logger.info("Avisos de muestra capturados: %d", len(avisos_records))
    _write_json(avisos_records, avisos_out_path)

    return prediccion_out_path, avisos_out_path


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 028): previsión o avisos, según `event["tipo"]`.

    `event.get("tipo")`: `"prevision"` (por defecto) o `"avisos"` — ver
    docstring del módulo, "Handler Lambda", para por qué es un único
    handler y no dos funciones separadas.
    """
    tipo = (event or {}).get("tipo", "prevision")
    config = CaptureConfig.from_env()
    if not config.api_key:
        raise RuntimeError(
            "AEMET_API_KEY no está configurada. Ver docstring del módulo, sección "
            "'Bloqueo de registro', para completar el alta (manual, requiere resolver "
            "un reCAPTCHA) en https://opendata.aemet.es/centrodedescargas/altaUsuario."
        )

    if tipo == "avisos":
        records = fetch_avisos(config)
        dataset_name = DATASET_AVISOS
        logger.info("Avisos capturados (captura completa): %d", len(records))
    elif tipo == "prevision":
        records = fetch_prediccion(config)
        dataset_name = DATASET_PREDICCION
        logger.info("Previsión capturada (captura completa): %d días", len(records))
    else:
        raise ValueError(f"event['tipo'] desconocido: {tipo!r} (valores válidos: 'prevision', 'avisos')")

    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=dataset_name)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": dataset_name, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura puntual de muestra de previsión diaria y avisos vigentes de AEMET "
            "OpenData para Madrid. No admite ejecución en bucle ni programada. Requiere "
            "AEMET_API_KEY."
        )
    )
    parser.add_argument(
        "--prediccion-out",
        type=Path,
        default=DEFAULT_PREDICCION_SAMPLE_PATH,
        help="Ruta del fichero de muestra de previsión a escribir",
    )
    parser.add_argument(
        "--avisos-out",
        type=Path,
        default=DEFAULT_AVISOS_SAMPLE_PATH,
        help="Ruta del fichero de muestra de avisos a escribir",
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
    capture_sample(config, args.prediccion_out, args.avisos_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
