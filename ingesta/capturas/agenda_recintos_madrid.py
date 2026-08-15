"""Captura de la agenda de grandes recintos de Madrid (deporte, conciertos, ferias; muestra).

Un partido en el Bernabéu o un concierto en el WiZink Center genera un pico de
afluencia enorme y conocido con antelación. En vez de perseguir una fuente
distinta por tipo de evento (una API de fútbol, otra de conciertos, otra de
ferias...), esta tarea captura **por recinto**: cada gran recinto tiene su
propia agenda con todo lo que allí ocurre, sea cual sea el tipo de evento.

## Hallazgo clave: no hace falta un scraper nuevo por recinto

Antes de escribir ningún scraper específico se investigó, para cada recinto,
si existía una fuente estructurada propia (JSON-LD, ICS, API). El hallazgo
más importante de esta investigación es que **la agenda de esMadrid /
Madrid Destino ya capturada en `agenda_eventos_madrid.py` (tarea 017,
dataset `agenda_turismo_esmadrid`) incluye, con nombre de recinto explícito
(`nombrert`), eventos de 6 de los 7 recintos objetivo** — partidos de LALIGA
en el Bernabéu y el Metropolitano, conciertos en Movistar Arena, ferias en
IFEMA, carreras en el Hipódromo de la Zarzuela y eventos en la Caja Mágica
(verificado en vivo descargando el feed completo durante esta sesión:
12-89 eventos reales por recinto, ver tabla más abajo). Es, con diferencia,
la fuente más estructurada, estable y ya verificada disponible para estos
recintos: reutilizarla evita escribir y mantener un scraper HTML frágil por
cada sitio web de cada recinto.

Por eso este módulo **no vuelve a hacer HTTP a ningún sitio nuevo**: filtra,
por nombre de recinto, el mismo feed XML que ya descarga
`agenda_eventos_madrid.fetch_esmadrid_services_raw`, y reutiliza
`normalize_esmadrid_event` para el parseo de cada `<service>`. El único
recinto sin cobertura en esa fuente (WiZink Center, ver más abajo) se
documenta como no disponible en vez de forzar un scraper aparte.

## Corrección sobre la lista de recintos del enunciado

Se investigó en vivo (varias fuentes de venta de entradas independientes,
contrastadas entre sí) y se confirmó que **"WiZink Center" y "Movistar
Arena" son el mismo recinto físico** (el Palacio de Deportes de la
Comunidad de Madrid, Avenida de Felipe II): cambió de nombre comercial el 1
de enero de 2025 al renovarse el patrocinio (de WiZink a Movistar), no son
dos recintos distintos. El "Palacio de Vistalegre" que el enunciado asocia
entre paréntesis a Movistar Arena ("antiguo Palacio de Vistalegre") es en
realidad **un edificio distinto, en Carabanchel** (nada que ver con el
Palacio de Deportes de Avenida de Felipe II) — la propia agenda de esMadrid
lo confirma: existe una entrada separada `"Palacio Vistalegre Arena"` (20
eventos reales) distinta de `"Movistar Arena"` (89 eventos reales). Por
tanto, de los 7 nombres del enunciado solo hay **6 recintos físicos
distintos**: se implementa un único `movistar_arena` que cubre lo que el
enunciado listaba como "WiZink Center" y "Movistar Arena" a la vez, y no se
cubre el Palacio de Vistalegre real (no estaba en el objetivo explícito de
la tarea).

Los nombres comerciales de los dos estadios de fútbol también han cambiado
por patrocinio: el feed usa `"Estadio Riyadh Air Metropolitano"` (el
Cívitas Metropolitano del enunciado cambió de patrocinador en 2025) y
`"Estadio Bernabéu"`. `VENUES` documenta ambos nombres (el del enunciado y
el comercial vigente) por claridad, y el filtrado hace *match* por el
nombre exacto que usa la fuente en el momento de esta captura — si vuelve a
cambiar el patrocinador, habrá que actualizar `esmadrid_names`, igual que
tendría que actualizarse cualquier scraper directo al sitio del recinto.

## Recintos cubiertos, fuente y eventos reales encontrados (verificado en vivo)

| `venue_id`           | Recinto (enunciado)                          | `nombrert` en esMadrid                              | eventos reales |
|-----------------------|-----------------------------------------------|------------------------------------------------------|-----------------|
| `bernabeu`            | Estadio Santiago Bernabéu                     | `Estadio Bernabéu`                                    | 12              |
| `metropolitano`       | Estadio Cívitas Metropolitano                 | `Estadio Riyadh Air Metropolitano`                     | 15              |
| `movistar_arena`      | WiZink Center / Movistar Arena                | `Movistar Arena`                                       | 89              |
| `ifema_madrid`        | IFEMA Madrid                                  | `IFEMA MADRID`, `IFEMA Palacio Municipal`              | 51 + 1          |
| `hipodromo_zarzuela`  | Hipódromo de la Zarzuela                      | `Hipódromo de la Zarzuela` (con espacio inicial en la fuente) | 2       |
| `caja_magica`         | Caja Mágica                                   | `Caja Mágica`                                          | 4               |

## WiZink Center (como dominio propio): bloqueado, y ya no hace falta

Se investigó `wizinkcenter.es` de forma independiente, antes de descubrir
que se trata del mismo recinto que Movistar Arena: el dominio devuelve
`403 Forbidden` en **toda petición, incluido `/robots.txt`**, con
cualquier User-Agent probado (a diferencia del bloqueo de esmadrid.com en
la tarea 017, que sí se resolvía con un User-Agent de navegador) — un
bloqueo de WAF a nivel de dominio completo, no de una ruta o User-Agent
concretos. No se investigó más a fondo porque, una vez confirmado que
`wizinkcenter.es` es simplemente el dominio heredado de un recinto que ya
se captura como `movistar_arena` vía esMadrid, forzar ese scraping no
aporta cobertura nueva.

## Otras fuentes investigadas y descartadas

- **IFEMA Madrid tiene su propia agenda pública con JSON-LD
  `schema.org/Event`** (`https://www.ifema.es/calendario`, verificado en
  vivo: 43 bloques `Event` reales con `name`/`startDate`/`endDate`/
  `location`). Es una fuente excelente, pero se descartó a favor de
  esMadrid por simplicidad: mantener un único mecanismo de captura
  (filtrar un feed ya integrado) para los 6 recintos es más simple y
  mantenible que combinar dos fuentes distintas para cubrir el mismo
  recinto. Queda anotado aquí por si una tarea futura prefiere esta fuente
  directa para IFEMA en concreto (más rica: trae fechas de inicio/fin por
  feria sin la simplificación de "solo el primer rango" que aplica
  `agenda_eventos_madrid.normalize_esmadrid_event`, ver docstring de ese
  módulo).
- **Calendario oficial de partidos de Real Madrid / Atlético de Madrid**
  (`realmadrid.com`, `atleticodemadrid.com`): ambos son aplicaciones Angular
  pesadas sin datos embebidos en el HTML servido (todo se carga por
  llamadas a APIs internas no documentadas) — se descartó por ser scraping
  frágil de un API privada, cuando la agenda de esMadrid ya cubre los
  partidos de ambos equipos en su propio estadio con más estabilidad.
- **`fixturedownload.com`** publica el calendario 2026/27 de LaLiga en JSON
  sin autenticación, con el campo `Location` (nombre del estadio) — de
  hecho la fuente más rica encontrada para fútbol. **Se descartó
  explícitamente**: su `robots.txt` incluye
  `User-agent: ClaudeBot` / `Disallow: /` (bloqueo dirigido específicamente
  a los rastreadores de Claude, además de `Content-Signal: ai-train=no` a
  nivel de sitio) — una señal explícita de que el operador del sitio no
  quiere que un agente de Claude acceda a su contenido, que se respeta
  aunque el acceso fuera técnicamente posible.
- **`openfootball/football.json`** (GitHub, datos abiertos de dominio
  público, sin autenticación, actualizado automáticamente cada semana
  durante la temporada): tiene el calendario completo de LaLiga por
  temporada, pero **no incluye el estadio** (solo equipo local/visitante) y,
  verificado en vivo, **la temporada 2026-27 aún no está publicada** en el
  repositorio en la fecha de esta captura (solo llega hasta 2025-26,
  finalizada) — otro motivo más para preferir esMadrid, que sí tiene ya
  partidos futuros de la temporada en curso.

## Aforo: no incluido, deliberadamente

El esquema normalizado incluye un campo `capacity`, pero se deja siempre a
`None`: la fuente usada (esMadrid) no publica aforo por evento, y las cifras
de aforo "oficiales" de los recintos investigados en vivo (en particular el
nuevo Santiago Bernabéu tras su reforma) están **contradichas entre sí por
distintas fuentes de prensa** (cifras entre 78.297 y 85.500, sin que el
club haga pública una cifra oficial) — se prefirió dejar el campo vacío
antes que incrustar un número no verificable. Una tarea futura que
necesite aforo por recinto debería tratarlo como una tabla de referencia
aparte (como `poi_madrid.py` o `barrios_distritos_madrid.py`), investigando
recinto a recinto una fuente fiable, no como parte de este productor de
agenda.

## Dos modos, mismo patrón que `bluesky_menciones_madrid.py` (tarea 016)

- `fetch_venue_agenda(venue_id, ...)`: agenda de un recinto concreto — modo
  bajo demanda, pensado para cuando el asistente conversacional necesite
  responder sobre un recinto concreto.
- `sweep_all_venues(...)`: agenda de todos los recintos de `VENUES` —
  descarga el feed de esMadrid **una sola vez** y filtra en memoria para
  cada recinto (no repite la descarga de ~4-5 MB por recinto), pensado para
  un futuro barrido programado a diario.

## Esto es una captura puntual de muestra, no un productor continuo

Igual que `agenda_eventos_madrid.py` y el resto de tareas 003-021, este
módulo no tiene modo `--interval-seconds` ni bucle, y no escribe en la capa
Bronze particionada: escribe un único fichero de muestra pequeño pensado
para commitearse como fixture.

TODO(kafka): igual que el resto de productores de muestra, el punto donde
se conectaría un productor Kafka para un futuro barrido diario real está
marcado aquí por consistencia, aunque no se despliega ningún scheduling en
esta tarea.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ingesta.capturas.agenda_eventos_madrid import (
    SOURCE_ESMADRID,
    CaptureConfig as EsmadridSourceConfig,
    fetch_esmadrid_services_raw,
    normalize_esmadrid_event,
)
from ingesta.capturas.bronze import now_madrid

logger = logging.getLogger(__name__)

SOURCE_NAME = "agenda_recintos_madrid"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "agenda_recintos_madrid_sample.json"

DEFAULT_SAMPLE_SIZE_PER_VENUE = 3


@dataclass(frozen=True)
class Venue:
    """Un gran recinto de Madrid y los nombres con los que aparece en la fuente esMadrid."""

    venue_id: str
    display_name: str
    esmadrid_names: "tuple[str, ...]"
    aliases: "tuple[str, ...]" = ()


# Nombres tal como los usa `basicData/nombrert` en el feed de esMadrid en el
# momento de esta captura (ver docstring del módulo, tabla de recintos
# cubiertos, para los recuentos reales verificados en vivo). Se comparan
# tras un `.strip()` (la fuente trae `" Hipódromo de la Zarzuela"` con un
# espacio inicial).
VENUES: "dict[str, Venue]" = {
    "bernabeu": Venue(
        venue_id="bernabeu",
        display_name="Estadio Santiago Bernabéu (Real Madrid)",
        esmadrid_names=("Estadio Bernabéu",),
    ),
    "metropolitano": Venue(
        venue_id="metropolitano",
        display_name="Estadio Cívitas Metropolitano (Atlético de Madrid)",
        esmadrid_names=("Estadio Riyadh Air Metropolitano",),
        aliases=("Estadio Cívitas Metropolitano", "Estadio Wanda Metropolitano"),
    ),
    "movistar_arena": Venue(
        venue_id="movistar_arena",
        display_name="Movistar Arena (antiguo WiZink Center; Palacio de Deportes de la Comunidad de Madrid)",
        esmadrid_names=("Movistar Arena",),
        aliases=("WiZink Center",),
    ),
    "ifema_madrid": Venue(
        venue_id="ifema_madrid",
        display_name="IFEMA Madrid (Feria de Madrid)",
        esmadrid_names=("IFEMA MADRID", "IFEMA Palacio Municipal"),
    ),
    "hipodromo_zarzuela": Venue(
        venue_id="hipodromo_zarzuela",
        display_name="Hipódromo de la Zarzuela",
        esmadrid_names=("Hipódromo de la Zarzuela",),
    ),
    "caja_magica": Venue(
        venue_id="caja_magica",
        display_name="Caja Mágica (Mutua Madrid Open y otros)",
        esmadrid_names=("Caja Mágica",),
    ),
}

# Recintos del enunciado sin cobertura en ninguna fuente accesible, y por qué
# (ver docstring del módulo, sección "WiZink Center"). No tienen entrada en
# `VENUES`; se exponen aquí solo para que `fetch_venue_agenda` pueda dar un
# mensaje de error útil si alguien lo pide por su nombre original.
UNAVAILABLE_VENUES = {
    "wizink_center": (
        "WiZink Center es el nombre comercial anterior de 'movistar_arena' "
        "(renombrado el 1 de enero de 2025); usa venue_id='movistar_arena'."
    ),
}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _infer_event_type(category: "Optional[str]") -> "Optional[str]":
    """Infiere deporte/concierto/otro a partir de la categoría `"Eventos > X > Y"` de esMadrid.

    La taxonomía real de esMadrid (verificada en vivo sobre los 6 recintos
    cubiertos) usa de forma consistente "Deporte" y "Música" como segundo
    nivel; cualquier otra cosa (Ferias, Exposiciones, Eventos de ciudad...)
    se agrupa en "otro".
    """
    if not category:
        return None
    parts = [p.strip() for p in category.split(">")]
    if len(parts) < 2:
        return "otro"
    segment = parts[1].lower()
    if segment == "deporte":
        return "deporte"
    if segment in ("música", "musica"):
        return "concierto"
    return "otro"


def _service_venue_name(service: ET.Element) -> "Optional[str]":
    node = service.find("basicData/nombrert")
    if node is None or node.text is None:
        return None
    return node.text.strip() or None


def normalize_venue_event(service: ET.Element, venue: Venue, captured_at: datetime) -> dict:
    """Normaliza un `<service>` de esMadrid al esquema mínimo de este productor.

    Reutiliza `agenda_eventos_madrid.normalize_esmadrid_event` para el
    parseo de campos (fechas, descripción, categoría...) y lo reproyecta al
    esquema pedido por esta tarea (recinto, tipo de evento, aforo).
    """
    base = normalize_esmadrid_event(service, captured_at)
    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "upstream_source": SOURCE_ESMADRID,
        "venue_id": venue.venue_id,
        "venue_name": venue.display_name,
        "event_id": base["event_id"],
        "title": base["title"],
        "event_type": _infer_event_type(base["category"]),
        "category": base["category"],
        "start_datetime": base["start_datetime"],
        "end_datetime": base["end_datetime"],
        "schedule_text": base["schedule_text"],
        "capacity": None,  # ver docstring del módulo, sección "Aforo"
        "url": base["url"],
        "captured_at": base["captured_at"],
    }


def fetch_venue_agenda(
    venue_id: str,
    config: "Optional[EsmadridSourceConfig]" = None,
    limit: "Optional[int]" = None,
    captured_at: "Optional[datetime]" = None,
    services: "Optional[list[ET.Element]]" = None,
) -> "list[dict]":
    """Agenda de un recinto concreto — modo bajo demanda.

    `services`, si se pasa, evita una nueva descarga del feed completo de
    esMadrid (lo usa `sweep_all_venues` para descargar una sola vez y
    filtrar varios recintos en memoria); si no se pasa, este modo bajo
    demanda hace su propia descarga.
    """
    if venue_id not in VENUES:
        if venue_id in UNAVAILABLE_VENUES:
            raise ValueError(f"Recinto '{venue_id}' no disponible: {UNAVAILABLE_VENUES[venue_id]}")
        raise ValueError(f"Recinto desconocido: '{venue_id}'. Recintos disponibles: {sorted(VENUES)}")

    venue = VENUES[venue_id]
    captured_at = captured_at or now_madrid()
    if services is None:
        config = config or EsmadridSourceConfig.from_env()
        services = fetch_esmadrid_services_raw(config)

    matches = [s for s in services if _service_venue_name(s) in venue.esmadrid_names]
    records = [normalize_venue_event(s, venue, captured_at) for s in matches]
    if limit is not None:
        records = records[:limit]
    return records


def sweep_all_venues(
    config: "Optional[EsmadridSourceConfig]" = None,
    limit_per_venue: "Optional[int]" = None,
    captured_at: "Optional[datetime]" = None,
) -> "list[dict]":
    """Agenda de todos los recintos de `VENUES` — modo barrido programado.

    Descarga el feed completo de esMadrid una única vez y filtra en
    memoria para cada recinto, en vez de repetir la descarga por recinto.
    """
    config = config or EsmadridSourceConfig.from_env()
    captured_at = captured_at or now_madrid()
    services = fetch_esmadrid_services_raw(config)

    records: "list[dict]" = []
    for venue_id in VENUES:
        records.extend(
            fetch_venue_agenda(
                venue_id,
                limit=limit_per_venue,
                captured_at=captured_at,
                services=services,
            )
        )
    return records


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: EsmadridSourceConfig, out_path: Path, sample_size_per_venue: int) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de todos los recintos cubiertos.

    Igual que el resto de capturas de muestra del proyecto, esto NO escribe
    en la capa Bronze particionada ni deja nada programado: escribe un
    único fichero de muestra pequeño y fijo (como mucho
    `sample_size_per_venue` eventos por recinto), pensado para commitearse
    como fixture.
    """
    records = sweep_all_venues(config, limit_per_venue=sample_size_per_venue)
    logger.info("Eventos de muestra capturados: %d (%d recintos)", len(records), len(VENUES))
    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura puntual de muestra de la agenda de grandes recintos de Madrid "
            "(deporte, conciertos, ferias), filtrando por recinto el dataset esMadrid ya "
            "capturado por agenda_eventos_madrid.py. No admite ejecución en bucle ni programada."
        )
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_PATH, help="Ruta del fichero de muestra a escribir")
    parser.add_argument(
        "--sample-size-per-venue",
        type=int,
        default=_env_int("AGENDA_RECINTOS_SAMPLE_SIZE_PER_VENUE", DEFAULT_SAMPLE_SIZE_PER_VENUE),
        help="Máximo de eventos por recinto en la muestra",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Nivel de logging (DEBUG, INFO, WARNING, ...)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = EsmadridSourceConfig.from_env()
    capture_sample(config, args.out, args.sample_size_per_venue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
