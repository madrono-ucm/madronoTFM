"""Agregación Silver -> Gold del dataset `aparcamientos`: ocupación media por aparcamiento y hora.

Se agrupa por **`(parking_id, fecha, hora)`**, mismo criterio de grano que
`trafico/aggregate.py`/`bicimad/aggregate.py` (un aparcamiento, igual que una
estación de BiciMAD, tiene una ubicación fija -- a diferencia de
`transporte_publico_emt`, donde `location` es la posición de un autobús en
movimiento). La hora de agregación se deriva de `measured_at` (hora de
Madrid).

## Registros sin `measured_at`: excluidos de la agregación, no del dataset

Silver (ver `transform.py`) admite registros con `measured_at` a `None`
(aparcamientos que no compartieron ocupación en ese instante) -- pero sin un
instante de medida no hay forma de saber a qué hora natural pertenecería la
fila, así que estos registros no pueden entrar en ningún bucket de Gold y se
excluyen de esta agregación (no es un error ni algo inesperado: es la
consecuencia directa de admitir esos registros en Silver, ver
`transform.py`). No se usa `ingested_at` como sustituto: a diferencia de
`transporte_publico_emt` (un servicio de tiempo real sin concepto de
"instante de medida" propio), aquí sí existe un instante de medida real
cuando la fuente lo comparte, y aproximarlo por la hora de captura
introduciría un desfase no siempre despreciable sin necesidad -- estos
registros ya quedan visibles en Silver para trazabilidad/auditoría de
cobertura, simplemente no contribuyen a ningún agregado horario.

Cada fila de Gold agrega, para las muestras con `measured_at` de un
aparcamiento dentro de una hora natural: `samples_count`,
`avg_free_spaces` y `avg_occupancy_ratio` (media de `free_spaces /
total_spaces` por muestra, solo sobre las muestras donde ambos campos
estaban disponibles -- mismo criterio que `avg_occupancy_ratio` en
`trafico/aggregate.py`/`bicimad/aggregate.py`: media de un ratio ya
calculado en Silver, no ratio de las medias de Gold). `total_spaces` se
conserva como el primer valor no nulo observado en el bucket (constante en
la práctica: la capacidad de un aparcamiento no cambia hora a hora), igual
que `name`/`location` (mismo criterio que `docks_total` en
`bicimad/aggregate.py`).
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Optional

SCHEMA_VERSION = 1


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _avg(values: "list[Optional[float]]") -> Optional[float]:
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def _first_present(values: "list[Optional[object]]") -> Optional[object]:
    for value in values:
        if value is not None:
            return value
    return None


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `aparcamientos` por aparcamiento y hora (Madrid).

    La hora de agregación se deriva de `measured_at` (ya en hora de Madrid),
    truncado a la hora en punto. Un registro sin `measured_at` parseable se
    ignora -- a diferencia de `bicimad`/`trafico` (donde Silver ya garantiza
    `measured_at` válido y esto "no debería ocurrir"), aquí es un caso
    esperado y frecuente: ver el docstring del módulo.
    """
    buckets: "dict[tuple[str, str, int], list[dict]]" = {}

    for record in records:
        measured_at = _parse_iso(record.get("measured_at"))
        parking_id = record.get("parking_id")
        if measured_at is None or not parking_id:
            continue
        key = (parking_id, measured_at.date().isoformat(), measured_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (parking_id, date_str, hour), bucket in sorted(buckets.items()):
        measured_ats = sorted(
            m for m in (_parse_iso(r.get("measured_at")) for r in bucket) if m is not None
        )
        location = bucket[0].get("location") or {}

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "parking_id": parking_id,
                "name": bucket[0].get("name"),
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "first_measured_at": measured_ats[0].isoformat() if measured_ats else None,
                "last_measured_at": measured_ats[-1].isoformat() if measured_ats else None,
                "avg_free_spaces": _avg([r.get("free_spaces") for r in bucket]),
                "avg_occupancy_ratio": _avg([r.get("occupancy_ratio") for r in bucket]),
                "total_spaces": _first_present([r.get("total_spaces") for r in bucket]),
                "location": {
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "srid": "EPSG:4326",
                },
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
