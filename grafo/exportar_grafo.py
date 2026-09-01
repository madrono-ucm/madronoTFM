"""Reconstruye el grafo urbano como artefacto offline, sin tocar Neo4j.

Corre el mismo flujo que `grafo.cargar_grafo.cargar_grafo()` (`extract`
Athena/S3 → `nodos` → `relaciones`) pero, en vez de `Neo4jLoader.load_*`,
serializa a JSON. Así la analítica de grafo y la tool multi-salto pueden
usar el grafo real sin acceso de lectura a la instancia. Añadido en `FIL_51`.

    AWS_PROFILE=madrono AWS_REGION=eu-west-1 python -m grafo.exportar_grafo

Salida: `grafo/_data/grafo_urbano.json` — los 5 labels
(`Distrito`/`Barrio`/`EstacionMedida`/`ParadaTransporte`/`Lugar`) y las 4
relaciones (`PERTENECE_A`/`UBICADO_EN`/`PROXIMO_A`/`CONECTADO_CON`). Si una
fuente Gold ya no es consultable (partition projection deslizante), se salta
y se deja constancia en `_meta.avisos`.

Substrato de `FIL_52` (analítica de grafo) y `FIL_53` (tool multi-salto).
Cero escritura, cero Neo4j.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from grafo import extract, nodos, relaciones

logger = logging.getLogger(__name__)
# se versiona el .gz (~0,65 MB); el .json suelto (~9 MB) está en .gitignore
_OUT = Path(__file__).resolve().parent / "_data" / "grafo_urbano.json.gz"


def cargar(path: "Path | None" = None) -> dict:
    """Lee el grafo urbano reconstruido (`FIL_51`). Sin AWS, sin Neo4j."""
    path = path or _OUT
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _try(nombre: str, fn, avisos: "list[str]", default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - reconstruir con lo que haya
        avisos.append(f"{nombre}: {type(exc).__name__}: {exc}")
        logger.warning("fuente %s no disponible: %s", nombre, exc)
        return [] if default is None else default


def construir() -> dict:
    avisos: "list[str]" = []

    barrio_records = list(_try("barrios_bronze", extract.fetch_barrios_bronze, avisos))
    barrio_nodes = nodos.barrios_from_bronze(barrio_records)
    distrito_nodes = nodos.distritos_from_bronze(
        _try("distritos_bronze", extract.fetch_distritos_bronze, avisos)
    )

    estaciones_medida = (
        nodos.estaciones_medida_from_trafico_gold(_try("est_trafico", extract.fetch_estaciones_trafico, avisos))
        + nodos.estaciones_medida_from_calidad_aire_gold(_try("est_aire", extract.fetch_estaciones_calidad_aire, avisos))
        + nodos.estaciones_medida_from_ruido_gold(_try("est_ruido", extract.fetch_estaciones_ruido, avisos))
        + nodos.estaciones_medida_from_aforos_peatones_bicicletas_gold(
            _try("est_aforos", extract.fetch_estaciones_aforos_peatones_bicicletas, avisos)
        )
    )

    rutas_crtm = list(_try("rutas_crtm", extract.fetch_paradas_crtm_bronze, avisos))
    paradas_transporte = (
        nodos.paradas_transporte_from_transporte_publico_emt_gold(_try("par_emt", extract.fetch_paradas_emt, avisos))
        + nodos.paradas_transporte_from_bicimad_gold(_try("par_bicimad", extract.fetch_paradas_bicimad, avisos))
        + nodos.paradas_transporte_from_crtm_bronze(rutas_crtm)
    )

    lugares = (
        nodos.lugares_from_poi_bronze(_try("poi_bronze", extract.fetch_poi_bronze, avisos))
        + nodos.lugares_from_parques_bronze(_try("parques_bronze", extract.fetch_parques_bronze, avisos))
        + nodos.lugares_from_aparcamientos_gold(_try("aparcamientos", extract.fetch_lugares_aparcamientos, avisos))
        + nodos.lugares_from_cartelera_cines_gold(_try("cines", extract.fetch_lugares_cartelera_cines, avisos))
    )
    lugares = nodos.enrich_lugares_con_osm(
        lugares, _try("osm_pois_sample", extract.fetch_osm_pois_sample, avisos)
    )

    nodos_con_ubicacion = estaciones_medida + paradas_transporte + lugares
    rels = {
        "PERTENECE_A": relaciones.pertenece_a_from_barrios(barrio_nodes),
        "UBICADO_EN": relaciones.ubicado_en(nodos_con_ubicacion, barrio_records),
        "PROXIMO_A": relaciones.proximo_a(nodos_con_ubicacion),
        "CONECTADO_CON": relaciones.conectado_con(rutas_crtm),
    }

    nds = {
        "Distrito": distrito_nodes,
        "Barrio": barrio_nodes,
        "EstacionMedida": estaciones_medida,
        "ParadaTransporte": paradas_transporte,
        "Lugar": lugares,
    }
    return {
        "_meta": {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fuente": "grafo.extract (Athena Gold + S3 Bronze) — reconstrucción offline del grafo de Neo4j",
            "conteos_nodos": {k: len(v) for k, v in nds.items()},
            "conteos_relaciones": {k: len(v) for k, v in rels.items()},
            "tipos_estacion": _contar(estaciones_medida, "tipo"),
            "tipos_lugar": _contar(lugares, "tipo"),
            "avisos": avisos,
        },
        "nodos": nds,
        "relaciones": rels,
    }


def _contar(items: "list[dict]", clave: str) -> "dict[str, int]":
    out: "dict[str, int]" = {}
    for it in items:
        out[it.get(clave) or "?"] = out.get(it.get(clave) or "?", 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _redondear(g: dict) -> dict:
    for r in g["relaciones"]["PROXIMO_A"]:
        r["distancia_m"] = round(r["distancia_m"])
    for lab in g["nodos"].values():
        for n in lab:
            u = n.get("ubicacion")
            if u and u.get("lat") is not None:
                u["lat"], u["lon"] = round(u["lat"], 6), round(u["lon"], 6)
    return g


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    g = _redondear(construir())
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(g, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(_OUT, "wt", encoding="utf-8") as fh:
        fh.write(txt)
    m = g["_meta"]
    print(f"\n{_OUT}  ({_OUT.stat().st_size / 1024:,.0f} KB gz)")
    print("  nodos:", m["conteos_nodos"])
    print("  relaciones:", m["conteos_relaciones"])
    if m["avisos"]:
        print("  avisos:")
        for a in m["avisos"]:
            print("   -", a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
