"""Relaciones espaciales del grafo urbano: `PERTENECE_A` (Barrio -> Distrito,
tarea 067), `UBICADO_EN` y `PROXIMO_A` (tarea 070).

`CONECTADO_CON` (adyacencia de red de transporte) sigue siendo una tarea de
seguimiento separada (071) -- ver `grafo/README.md` y `infra/neo4j/schema/
schema.cypher`. Python puro, mismo motivo que `grafo/nodos.py`: la geometría
en sí (point-in-polygon, Haversine) vive en `grafo/geo.py`, también Python
puro.
"""

from __future__ import annotations

from typing import Iterable

from grafo import geo


def pertenece_a_from_barrio_node(barrio_node: dict) -> dict:
    """`{barrio_codigo, distrito_codigo}` desde un nodo `:Barrio` ya
    construido por `grafo.nodos.barrio_from_bronze` (que ya trae
    `distrito_codigo`, un simple lookup por el código de distrito que ya
    incluye el propio registro de origen -- sin cálculo geométrico)."""
    return {
        "barrio_codigo": barrio_node["codigo"],
        "distrito_codigo": barrio_node["distrito_codigo"],
    }


def pertenece_a_from_barrios(barrio_nodes: "Iterable[dict]") -> "list[dict]":
    """Un par `PERTENECE_A` por cada nodo `:Barrio` -- no hace falta
    deduplicar: `barrio_codigo` ya es único (constraint `barrio_codigo_unique`
    en `schema.cypher`), así que cada barrio aporta exactamente un par."""
    return [pertenece_a_from_barrio_node(b) for b in barrio_nodes]


# ---------------------------------------------------------------------------
# UBICADO_EN -- point-in-polygon de cualquier nodo con ubicación contra los
# barrios de `barrios_distritos_madrid`.
# ---------------------------------------------------------------------------


def ubicado_en(nodos_con_ubicacion: "Iterable[dict]", barrios: "Iterable[dict]") -> "list[dict]":
    """`{nodo_id, barrio_codigo}` por cada nodo (`:Lugar`/`:EstacionMedida`/
    `:ParadaTransporte`, cualquiera con `ubicacion`) que caiga dentro de
    algún barrio.

    `barrios`: los registros **Bronce** de `barrios_distritos_madrid`
    (`neighbourhood_id` + `geometry`), tal como los devuelve
    `extract.fetch_barrios_bronze()` -- **no** los nodos `:Barrio` ya
    construidos por `nodos.barrios_from_bronze`, que no conservan la
    geometría (solo `codigo`/`nombre`/`distrito_codigo`, ver `schema.cypher`:
    `:Barrio` no tiene una propiedad de geometría). Nodos sin `ubicacion`
    (`None`) o que no caen en ningún barrio (p. ej. fuera de los límites del
    municipio) no generan ninguna relación.
    """
    barrios = list(barrios)
    relaciones = []
    for node in nodos_con_ubicacion:
        ubicacion = node.get("ubicacion")
        if not ubicacion:
            continue
        barrio_codigo = geo.find_barrio(ubicacion["lat"], ubicacion["lon"], barrios)
        if barrio_codigo is None:
            continue
        relaciones.append({"nodo_id": node["id"], "barrio_codigo": barrio_codigo})
    return relaciones


# ---------------------------------------------------------------------------
# PROXIMO_A -- proximidad genérica entre cualquier par de nodos con ubicación
# de tipos ("tipo", ver `nodos.py`) distintos, dentro de un umbral de
# distancia Haversine.
# ---------------------------------------------------------------------------

_PROXIMO_A_UMBRAL_M = 300.0


def proximo_a(nodos_con_ubicacion: "Iterable[dict]", umbral_m: float = _PROXIMO_A_UMBRAL_M) -> "list[dict]":
    """`{origen_id, destino_id, distancia_m}` por cada pareja de nodos con
    `ubicacion` y `tipo` distintos cuya distancia Haversine no supera
    `umbral_m` (300 m por defecto, ver `schema.cypher`: `PROXIMO_A
    {distancia_m: float}`).

    "Tipo distinto" usa la propiedad `tipo` del nodo (`"trafico"`,
    `"calidad_aire"`, `"bicimad"`, `"poi_turistico"`... -- la misma que fija
    `nodos.py`), no solo el label de Neo4j: dos nodos `:EstacionMedida` de
    tráfico no aportan información nueva relacionándose entre sí (ya
    comparten semántica por ser del mismo tipo de sensor), pero un
    `:EstacionMedida` de tráfico y uno de ruido sí, aunque compartan label.

    No se limita el número de relaciones por nodo -- una zona densa del
    centro puede generar decenas de `PROXIMO_A` por nodo, y es información
    real, no ruido a filtrar (ver enunciado de la tarea 070). La relación se
    genera en un único sentido por pareja (`a -> b`, no también `b -> a`),
    igual que documenta `schema.cypher` -- una consulta que necesite ambos
    sentidos usa un patrón no dirigido.
    """
    nodes = [n for n in nodos_con_ubicacion if n.get("ubicacion")]
    relaciones = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            if a.get("tipo") == b.get("tipo"):
                continue
            distancia_m = geo.haversine_m(
                a["ubicacion"]["lat"], a["ubicacion"]["lon"], b["ubicacion"]["lat"], b["ubicacion"]["lon"]
            )
            if distancia_m <= umbral_m:
                relaciones.append({"origen_id": a["id"], "destino_id": b["id"], "distancia_m": distancia_m})
    return relaciones
