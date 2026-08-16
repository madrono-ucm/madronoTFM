"""Captura puntual de previsión de calidad del aire de Copernicus CAMS para Madrid.

Complementa a `calidad_aire_madrid.py` (tarea 006, mediciones **en tiempo
real** de la red de estaciones municipales, solo Madrid) con una señal que
esa fuente no da: una **previsión** horaria a 4 días vista, validada contra
observaciones oficiales (EEA) a escala europea. Fuente: el dataset "CAMS
European air quality forecasts" del Atmosphere Data Store (ADS) de
Copernicus (`ads.atmosphere.copernicus.eu`), tal como pedía el enunciado de
esta tarea (memoria del TFM, apartado 6.1: "fuentes europeas de cobertura
continental (calidad del aire validada y observación por satélite)").

## Bloqueo de registro: creación de cuenta con identidad y contraseña reales

Se investigó en vivo, durante esta sesión, el mecanismo de autenticación real
de la ADS API (distinto del de otras fuentes de este proyecto, ver más
abajo) y el formulario de alta
(`accounts.ecmwf.int/.../registrations?client_id=cds...`). A diferencia de
AEMET (tarea 018) o la EMT (tarea 003), este formulario **no tiene
reCAPTCHA ni otro CAPTCHA**: solo pide nombre, apellidos, email, contraseña
y confirmación de contraseña. Aun así, se decidió tratarlo como el mismo
tipo de bloqueo que en esas tareas: completar este alta implica **crear una
cuenta real, persistente y ligada a la identidad del usuario** (email real,
contraseña elegida por quien la crea) en un servicio de terceros ajeno a
este pipeline, y muy probablemente requiere confirmar esa alta desde el
buzón de correo del email usado (patrón estándar de Keycloak/EU Login, el
sistema de identidad que usa `accounts.ecmwf.int`) — un paso para el que
esta sesión no tiene acceso a ningún buzón de correo, exactamente la misma
razón de fondo que bloqueó la tarea 003. Elegir una contraseña y registrar
una cuenta a nombre de un tercero sin que haya un humano confirmando esa
acción en el momento no es algo que este pipeline autónomo deba hacer por
iniciativa propia (ver las guías de la propia sesión sobre acciones con
efectos reales fuera del repositorio), así que se documenta aquí como
bloqueo y se deja el código listo para el día en que alguien complete el
alta manualmente y configure `CAMS_ADS_API_KEY`.

## El mecanismo de autenticación real: un "personal access token" de ADS, no una API key clásica

Se investigó en vivo la página oficial "How to use the CDS/ADS API"
(`ads.atmosphere.copernicus.eu/how-to-api`, consultada durante esta sesión):
confirma que, una vez registrado, el token de acceso personal se obtiene del
perfil del usuario y se usa junto con la URL base del servicio
(`https://ads.atmosphere.copernicus.eu/api`) — normalmente ambos se guardan
en un fichero `$HOME/.cdsapirc` que el cliente oficial `cdsapi` lee
automáticamente. Este módulo, para no depender de un fichero de
configuración fuera del repositorio (y seguir la norma del proyecto de
"credenciales por variable de entorno, nunca hardcodeadas"), construye el
cliente `cdsapi.Client(url=..., key=...)` explícitamente a partir de
`CAMS_ADS_API_KEY` (el token) y `CAMS_ADS_URL` (por defecto la URL oficial
anterior), sin tocar `~/.cdsapirc`. La propia documentación advierte además
de que, antes de poder descargar cada dataset, hay que aceptar sus
"Terms of Use" desde su página en el ADS con la cuenta ya logueada — otro
paso manual explícitamente no automatizable, documentado también en la
página oficial.

## El esquema de la petición y de los datos sí se obtuvo, sin necesidad de un token válido

El ADS expone públicamente, sin autenticación, la descripción del proceso
de cada dataset (`GET /api/retrieve/v1/processes/cams-europe-air-quality-forecasts`,
verificado en vivo: `200 OK`, JSON). De ahí salen, con certeza, todos los
parámetros válidos de la petición usados por `_build_request` más abajo:
los nombres exactos de contaminante (`variable`), de modelo (`model`), de
nivel vertical (`level`), de tipo (`type`), de hora de "leadtime"
(`leadtime_hour`), el formato de salida (`data_format`, con el valor por
defecto real `"netcdf_zip"` — un `.zip` que contiene uno o varios ficheros
`.nc`, no un `.nc` suelto) y el recorte geográfico (`area`, `[norte, oeste,
sur, este]` en grados).

**Contaminantes validados (restricción explícita del enunciado de esta
tarea):** la propia descripción del dataset y la documentación pública
(`ads.atmosphere.copernicus.eu/datasets/cams-europe-air-quality-forecasts`)
confirman en vivo que solo el monóxido de nitrógeno (NO), dióxido de
nitrógeno (NO2), dióxido de azufre (SO2), ozono (O3), PM2.5, PM10 y polvo
se validan regularmente contra observaciones in situ; el resto de variables
del dataset (polen, compuestos orgánicos volátiles, amoniaco...) se declaran
explícitamente "experimentales, sin validar". `POLLUTANT_VARIABLES` más
abajo solo incluye esos 7 contaminantes validados, ninguno más.

**Cadencia real de publicación (investigada en vivo, ver también
`ingesta/README.md`):** la misma documentación confirma que se genera una
única corrida (`type=forecast`) al día, a partir de las 00:00 UTC, en dos
tandas de publicación: horas de previsión 0-48 disponibles a partir de las
06:45 UTC, y horas 49-96 a partir de las 08:30 UTC — "una vez al día" es
correcto, pero conviene precisar que la previsión completa (hasta 96h) no
está íntegra hasta la segunda tanda.

Los nombres cortos de variable **dentro** de cada fichero NetCDF (distintos
de los nombres de la petición ADS, p.ej. `nitrogen_dioxide` en la petición
frente a `no2_conc` dentro del `.nc`) se contrastaron con múltiples fuentes
públicas independientes que citan explícitamente `no2_conc`, `o3_conc`,
`pm10_conc`, `pm2p5_conc` y `so2_conc` como las variables reales de este
mismo dataset. Para `nitrogen_monoxide` y `dust` no se encontró ninguna
fuente pública que citara su nombre corto exacto dentro del NetCDF: se
mapean aquí como `no_conc`/`dust_conc` **por el mismo patrón** que las
cinco anteriores (fórmula química o nombre genérico + sufijo `_conc`), pero sin
poder contrastarlo contra un fichero real (bloqueo de registro, igual que
el aviso ya hecho en `aemet_prevision_avisos.py` para el esquema CAP de
avisos) — `normalize_forecast_file` es indiferente a qué subconjunto de
`POLLUTANT_VARIABLES` esté realmente presente en cada fichero: solo procesa
las variables que encuentra, así que un nombre equivocado para NO/polvo
simplemente no producirá registros para ese contaminante en vez de fallar
duro.

**Actualización (tarea 045, con credenciales y licencia reales ya
funcionando):** `no_conc`/`so2_conc` se confirmaron correctos contra un
fichero real. `dust_conc` **es incorrecto**: la variable real dentro del
NetCDF se llama simplemente `dust` (sin el sufijo `_conc` que sí llevan
todas las demás). No se ha corregido en esta tarea (fuera de su alcance
explícito, ver `doc/045-arreglo-parseo-fecha-cams.md`) — sigue produciendo
cero registros de polvo en vez de fallar, por el mismo diseño tolerante
descrito arriba, hasta que una tarea de seguimiento corrija
`POLLUTANT_VARIABLES["dust"]`.

## Formato real de fechas dentro del NetCDF (tarea 045)

El fixture usado para desarrollar `normalize_forecast_file` originalmente
asumía que `time.units` seguía el formato estándar CF
(`"<unidad> since <referencia>"`, p.ej. `"hours since 1900-01-01 00:00:00.0"`),
parseable directamente con `netCDF4.num2date`. Verificado en vivo contra
varios ficheros reales (credenciales y licencia ya aceptadas): **no es así**.
El `.nc` real tiene `time.units = "hours"` (sin cláusula "since") y **no**
tiene ninguna variable `forecast_reference_time`; la fecha de referencia real
está en `time.long_name`, con el formato `"FORECAST time from 20260815"`
(`AAAAMMDD`). `_parse_time_variable`/`_parse_reference_date` manejan este
formato real como caso principal, con el formato CF estándar como
alternativa (por si el dataset cambiara de formato en el futuro), no como
caso principal ya descartado por la evidencia real.

## Área geográfica: un recorte pequeño alrededor de Madrid, no toda Europa

El dataset cubre toda Europa (25°O-45°E, 30°N-72°N) a 0.1°×0.1°; pedir el
dominio completo por hora y contaminante generaría un fichero grande e
irrelevante para este proyecto (centrado en Madrid). El parámetro `area` de
la propia API permite recortar la petición en origen: `DEFAULT_AREA` es una
caja estrecha alrededor de Madrid capital (aprox. 3x3 celdas de la rejilla
de 0.1°), suficiente para quedarse con el punto de rejilla más cercano al
centro de Madrid sin descargar el resto de Europa.

## Esto es una captura puntual de muestra, no un productor continuo

Igual que las tareas 003-008, 012, 013, 016, 017 y 018, este módulo no
tiene modo `--interval-seconds` ni bucle, y no escribe en la capa Bronze
particionada: escribe un único fichero de muestra pequeño y fijo
(`DEFAULT_POLLUTANTS` x `DEFAULT_LEADTIME_HOURS`, unas pocas horas y
contaminantes, no la previsión horaria completa a 4 días de toda Europa),
pensado para commitearse como fixture. El fichero `.zip`/`.nc` descargado
temporalmente para una captura real se procesa en memoria y se borra al
terminar; no queda ningún dato crudo sin acotar en disco.

TODO(kafka): igual que el resto de productores de muestra, el punto donde
se conectaría un productor Kafka para una futura captura periódica real
está marcado aquí por consistencia. La cadencia real de CAMS (una corrida
diaria, con las dos tandas de publicación de arriba) debería determinar el
schedule final.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import netCDF4

from .bronze import MADRID_TZ, BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

SOURCE = "cams"
DATASET_ID = "cams-europe-air-quality-forecasts"
DATASET_NAME = "cams_calidad_aire"

DEFAULT_ADS_URL = "https://ads.atmosphere.copernicus.eu/api"

# Contaminante (nombre de variable de la petición ADS) -> nombre corto de
# variable dentro del NetCDF descargado. Ver docstring del módulo para el
# grado de confianza de cada uno (los 5 primeros contrastados con fuentes
# reales; NO y polvo, por patrón, sin contrastar).
POLLUTANT_VARIABLES = {
    "nitrogen_dioxide": "no2_conc",
    "nitrogen_monoxide": "no_conc",
    "sulphur_dioxide": "so2_conc",
    "ozone": "o3_conc",
    "particulate_matter_2.5um": "pm2p5_conc",
    "particulate_matter_10um": "pm10_conc",
    "dust": "dust_conc",
}

# Etiqueta corta legible por contaminante, para el campo `pollutant` del
# esquema normalizado (más cómodo de leer que el nombre de la petición ADS).
POLLUTANT_LABELS = {
    "nitrogen_dioxide": "NO2",
    "nitrogen_monoxide": "NO",
    "sulphur_dioxide": "SO2",
    "ozone": "O3",
    "particulate_matter_2.5um": "PM2.5",
    "particulate_matter_10um": "PM10",
    "dust": "polvo",
}

# Los 4 contaminantes regulados por la UE/OMS, pedidos explícitamente en el
# objetivo de la tarea. NO, SO2 y polvo también están validados y
# disponibles (ver POLLUTANT_VARIABLES), pero no forman parte de la muestra
# por defecto.
DEFAULT_POLLUTANTS = [
    "nitrogen_dioxide",
    "ozone",
    "particulate_matter_2.5um",
    "particulate_matter_10um",
]

# Caja estrecha alrededor de Madrid capital: [norte, oeste, sur, este], en
# grados. No todo el dominio europeo del dataset.
DEFAULT_AREA = [40.55, -3.85, 40.30, -3.55]
MADRID_CENTER_LAT = 40.4168
MADRID_CENTER_LON = -3.7038

DEFAULT_MODEL = "ensemble"
DEFAULT_LEVEL = "0"
DEFAULT_LEADTIME_HOURS = ["0", "1", "2", "3"]
DEFAULT_TIME = "00:00"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "cams_calidad_aire_madrid_sample.json"


def _env_list(name: str, default: "list[str]") -> "list[str]":
    raw = os.environ.get(name)
    return [item.strip() for item in raw.split(",") if item.strip()] if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    `api_key` es el "personal access token" de la ADS API (ver docstring
    del módulo, sección "El mecanismo de autenticación real").
    """

    api_key: str
    api_url: str
    pollutants: "list[str]"
    area: "list[float]"
    model: str
    level: str
    leadtime_hours: "list[str]"
    run_time: str

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            api_key=os.environ.get("CAMS_ADS_API_KEY", ""),
            api_url=os.environ.get("CAMS_ADS_URL", DEFAULT_ADS_URL),
            pollutants=_env_list("CAMS_POLLUTANTS", DEFAULT_POLLUTANTS),
            area=[float(v) for v in os.environ["CAMS_AREA"].split(",")] if os.environ.get("CAMS_AREA") else list(DEFAULT_AREA),
            model=os.environ.get("CAMS_MODEL", DEFAULT_MODEL),
            level=os.environ.get("CAMS_LEVEL", DEFAULT_LEVEL),
            leadtime_hours=_env_list("CAMS_LEADTIME_HOURS", DEFAULT_LEADTIME_HOURS),
            run_time=os.environ.get("CAMS_RUN_TIME", DEFAULT_TIME),
        )


def _build_request(config: CaptureConfig, run_date: date) -> dict:
    """Construye el diccionario de petición para `cdsapi.Client.retrieve`.

    Sigue exactamente el esquema de entradas publicado por
    `GET /api/retrieve/v1/processes/cams-europe-air-quality-forecasts` (ver
    docstring del módulo): un único día (`date` como rango de un solo día),
    la corrida de las 00:00 UTC, y `data_format="netcdf_zip"`.
    """
    date_str = run_date.isoformat()
    return {
        "variable": list(config.pollutants),
        "model": [config.model],
        "level": [config.level],
        "type": ["forecast"],
        "date": [f"{date_str}/{date_str}"],
        "time": [config.run_time],
        "leadtime_hour": list(config.leadtime_hours),
        "data_format": "netcdf_zip",
        "area": list(config.area),
    }


def _fetch_forecast_zip_bytes(config: CaptureConfig, run_date: date) -> bytes:
    """Envía la petición a la ADS API y devuelve el `.zip` descargado (en memoria).

    El cliente oficial `cdsapi` solo sabe escribir el resultado a un fichero
    en disco (no admite descargar directamente a memoria), así que se usa un
    fichero temporal que se borra en cuanto se han leído sus bytes: nunca
    queda un `.zip`/`.nc` de la petición real persistido en el repositorio o
    fuera del directorio temporal del sistema.
    """
    import cdsapi  # import perezoso: solo hace falta para la captura real, no para normalizar/testear

    client = cdsapi.Client(url=config.api_url, key=config.api_key)
    request = _build_request(config, run_date)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        client.retrieve(DATASET_ID, request, str(tmp_path))
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def _nearest_index(values: "list[float]", target: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


def _grid_value(variable, t_idx: int, lat_idx: int, lon_idx: int) -> float:
    """Lee un único valor escalar de una variable de contaminante, por nombre de dimensión.

    El fichero NetCDF real trae una dimensión `level` adicional
    (`(time, level, latitude, longitude)`, tamaño 1: la petición siempre pide
    un único nivel vertical, `CaptureConfig.level`) que el fixture de
    desarrollo original no tenía (`(time, latitude, longitude)`); indexar por
    posición fija asumía ese segundo esquema y fallaba con datos reales. Se
    indexa por nombre de dimensión para no depender de cuántas/qué orden
    tengan.
    """
    index = tuple(
        {"time": t_idx, "latitude": lat_idx, "longitude": lon_idx}.get(dim, 0) for dim in variable.dimensions
    )
    return float(variable[index])


# `long_name` real observado: "FORECAST time from 20260815" (ver docstring del
# módulo, sección sobre el formato real de fechas).
_REFERENCE_DATE_RE = re.compile(r"from (\d{8})\b")

# `netCDF4.num2date` solo entiende nombres de unidad en plural (p.ej.
# "hours"), que coinciden con los kwargs válidos de `timedelta`.
_TIMEDELTA_UNIT_NAMES = {"days", "hours", "minutes", "seconds", "milliseconds", "microseconds"}


def _parse_reference_date(long_name: str) -> datetime:
    """Extrae la fecha de referencia (AAAAMMDD) del `long_name` de la variable `time`."""
    match = _REFERENCE_DATE_RE.search(long_name or "")
    if not match:
        raise ValueError(f"No se pudo extraer la fecha de referencia de time.long_name: {long_name!r}")
    return datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)


def _parse_time_variable(time_var) -> "list[datetime]":
    """Convierte los valores numéricos de la variable `time` a `datetime` UTC.

    El fichero NetCDF real que devuelve la API de CAMS (verificado en vivo
    con credenciales reales, tarea 045) **no** sigue el formato estándar CF
    "<unidad> since <referencia>" que asumía este módulo originalmente
    (fixture de desarrollo, nunca contrastado contra un fichero real): su
    atributo `units` es simplemente `"hours"` (u otra unidad, sin cláusula
    "since"), y la fecha de referencia real está en el `long_name` de la
    propia variable (`"FORECAST time from 20260815"`), no en `units`. Se
    intenta primero el formato CF estándar (`netCDF4.num2date`, por si algún
    día el dataset lo sirve así) y solo si `units` no lo declara (sin
    "since") se recurre al formato real observado.
    """
    units = time_var.units
    if "since" in units:
        result = netCDF4.num2date(time_var[:], units, only_use_cftime_datetimes=False, only_use_python_datetimes=True)
        return list(result) if hasattr(result, "__len__") else [result]

    unit_name = units.strip().lower()
    if unit_name not in _TIMEDELTA_UNIT_NAMES:
        raise ValueError(f"Unidad de tiempo no reconocida en time.units: {units!r}")
    reference = _parse_reference_date(getattr(time_var, "long_name", ""))
    return [reference + timedelta(**{unit_name: float(v)}) for v in time_var[:]]


def normalize_forecast_file(
    nc_bytes: bytes,
    captured_at: datetime,
    model: str = DEFAULT_MODEL,
    target_lat: float = MADRID_CENTER_LAT,
    target_lon: float = MADRID_CENTER_LON,
    is_mock: bool = False,
) -> "list[dict]":
    """Normaliza un único fichero NetCDF (ya descomprimido) al esquema mínimo.

    Función pura (sin red ni zip), separada para poder testear la
    normalización con un fichero de ejemplo en memoria. Se queda con el
    punto de rejilla más cercano a `target_lat`/`target_lon` (por defecto,
    el centro de Madrid) y genera un registro por combinación de
    contaminante presente en el fichero x paso horario (`time`).

    Un fichero puede traer una o varias variables de `POLLUTANT_VARIABLES`;
    las que no estén presentes se ignoran sin error (ver docstring del
    módulo: `no_conc`/`dust_conc` son un mapeo sin contrastar, así que un
    nombre real distinto simplemente no generaría registros para ese
    contaminante).
    """
    dataset = netCDF4.Dataset("cams_forecast.nc", memory=nc_bytes)
    try:
        variable_to_pollutant = {v: k for k, v in POLLUTANT_VARIABLES.items()}
        present = [name for name in dataset.variables if name in variable_to_pollutant]
        if not present:
            return []

        latitudes = dataset.variables["latitude"][:].tolist()
        # El fichero real usa la convención [0, 360) para la longitud (p.ej.
        # 356.15 en vez de -3.85, verificado en vivo, tarea 045); sin
        # normalizar a [-180, 180) antes de comparar con `target_lon`,
        # `_nearest_index` no encuentra realmente el punto más cercano a
        # Madrid (todos los valores reales quedan igual de "lejos" de una
        # longitud negativa) y el registro guarda una longitud sin sentido.
        longitudes = [lon - 360 if lon > 180 else lon for lon in dataset.variables["longitude"][:].tolist()]
        lat_idx = _nearest_index(latitudes, target_lat)
        lon_idx = _nearest_index(longitudes, target_lon)
        # round(): la rejilla real es float32 (p.ej. 40.42499923706055 en vez de
        # 40.425), redondear a 4 decimales (~11 m) evita ese ruido de precisión
        # sin perder resolución real frente a la rejilla de 0.1°.
        grid_lat = round(latitudes[lat_idx], 4)
        grid_lon = round(longitudes[lon_idx], 4)

        time_var = dataset.variables["time"]
        valid_datetimes = _parse_time_variable(time_var)

        if "forecast_reference_time" in dataset.variables:
            frt_var = dataset.variables["forecast_reference_time"]
            forecast_issued_at = netCDF4.num2date(
                frt_var[...].item(), frt_var.units, only_use_cftime_datetimes=False, only_use_python_datetimes=True
            )
        elif "since" not in time_var.units:
            # Formato real (ver `_parse_time_variable`): sin variable
            # `forecast_reference_time`, la fecha de referencia real está en
            # `time.long_name`, no en el primer valor de `valid_datetimes`
            # (que dependería de qué `leadtime_hour` se haya pedido).
            forecast_issued_at = _parse_reference_date(getattr(time_var, "long_name", ""))
        else:
            forecast_issued_at = valid_datetimes[0]

        records = []
        for variable_name in present:
            pollutant_key = variable_to_pollutant[variable_name]
            values = dataset.variables[variable_name]
            unit = getattr(values, "units", "µg/m3")
            for t_idx, valid_dt in enumerate(valid_datetimes):
                # round(): mismo motivo que grid_lat/grid_lon, el dato fuente es float32.
                value = round(_grid_value(values, t_idx, lat_idx, lon_idx), 3)
                leadtime_hour = round((valid_dt - forecast_issued_at).total_seconds() / 3600)
                records.append(
                    {
                        "schema_version": 1,
                        "source": SOURCE,
                        "pollutant": POLLUTANT_LABELS[pollutant_key],
                        "pollutant_code": pollutant_key,
                        "value": value,
                        "unit": unit,
                        "valid_datetime": valid_dt.replace(tzinfo=timezone.utc).astimezone(MADRID_TZ).isoformat(),
                        "forecast_issued_at": forecast_issued_at.replace(tzinfo=timezone.utc).astimezone(MADRID_TZ).isoformat(),
                        "leadtime_hour": leadtime_hour,
                        "model": model,
                        "latitude": grid_lat,
                        "longitude": grid_lon,
                        "captured_at": captured_at.astimezone(MADRID_TZ).isoformat(),
                        "is_mock": is_mock,
                    }
                )
        return records
    finally:
        dataset.close()


def normalize_forecast_zip(zip_bytes: bytes, captured_at: datetime, model: str = DEFAULT_MODEL) -> "list[dict]":
    """Descomprime un `.zip` de la ADS API y normaliza todos los `.nc` que contenga.

    El formato de salida real (`data_format="netcdf_zip"`) es un `.zip` con
    uno o varios ficheros `.nc` dentro (ver docstring del módulo); esta
    función no asume cuántos trae, solo procesa todos los que encuentre.
    """
    records = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".nc"):
                records.extend(normalize_forecast_file(archive.read(name), captured_at, model=model))
    return records


def fetch_forecast(config: CaptureConfig, run_date: Optional[date] = None) -> "list[dict]":
    """Descarga y normaliza la previsión de calidad del aire para Madrid.

    Requiere `CAMS_ADS_API_KEY` configurada (ver docstring del módulo,
    "Bloqueo de registro").
    """
    # La corrida diaria de CAMS arranca a las 00:00 UTC (ver docstring del
    # módulo), no a medianoche de Madrid: se usa la fecha UTC, no
    # now_madrid().date(), para no pedir la corrida de "mañana" antes de que
    # exista (posible en verano, cuando la medianoche de Madrid ya cayó pero
    # aún no son las 00:00 UTC).
    run_date = run_date or datetime.now(timezone.utc).date()
    zip_bytes = _fetch_forecast_zip_bytes(config, run_date)
    captured_at = now_madrid()
    return normalize_forecast_zip(zip_bytes, captured_at, model=config.model)


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de previsión.

    Igual que en las tareas 003-008, 012, 013, 016, 017 y 018, esto NO
    escribe en la capa Bronze particionada ni deja nada programado.
    """
    if not config.api_key:
        raise RuntimeError(
            "CAMS_ADS_API_KEY no está configurada. Ver docstring del módulo, sección "
            "'Bloqueo de registro', para completar el alta (manual, cuenta ligada a "
            "identidad real) en https://ads.atmosphere.copernicus.eu/."
        )

    records = fetch_forecast(config)
    logger.info("Previsión de calidad del aire de muestra capturada: %d registros", len(records))
    _write_json(records, out_path)
    return out_path


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 028): captura completa a Bronze real.

    Reutiliza `fetch_forecast` tal cual: ya descarga y normaliza la
    previsión completa configurada (`config.pollutants` x
    `config.leadtime_hours`, no un recorte de muestra adicional).

    `event` admite opcionalmente `run_date` (cadena `AAAA-MM-DD`) para forzar
    la fecha de la corrida en vez de la fecha UTC de hoy (comportamiento por
    defecto, sin cambios). Añadido en la tarea 045 para poder reprocesar/
    verificar una corrida concreta cuando la de hoy aún no está publicada
    (ver docstring del módulo, "Cadencia real de publicación": la corrida
    diaria no está disponible hasta las 06:45/08:30 UTC).
    """
    config = CaptureConfig.from_env()
    if not config.api_key:
        raise RuntimeError(
            "CAMS_ADS_API_KEY no está configurada. Ver docstring del módulo, sección "
            "'Bloqueo de registro', para completar el alta (manual, cuenta ligada a "
            "identidad real) en https://ads.atmosphere.copernicus.eu/."
        )

    run_date = date.fromisoformat(event["run_date"]) if event and event.get("run_date") else None
    records = fetch_forecast(config, run_date=run_date)
    logger.info("Previsión de calidad del aire capturada (captura completa): %d registros", len(records))
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura puntual de muestra de previsión de calidad del aire de Copernicus "
            "CAMS para Madrid. No admite ejecución en bucle ni programada. Requiere "
            "CAMS_ADS_API_KEY."
        )
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_PATH, help="Ruta del fichero de muestra a escribir")
    parser.add_argument(
        "--log-level", default=os.environ.get("LOG_LEVEL", "INFO"), help="Nivel de logging (DEBUG, INFO, WARNING, ...)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = CaptureConfig.from_env()
    capture_sample(config, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
