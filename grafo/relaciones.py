"""Relaciones del grafo urbano cubiertas por esta tarea (043/067): solo
`PERTENECE_A` (Barrio -> Distrito).

`UBICADO_EN` (point-in-polygon), `PROXIMO_A` (proximidad genérica) y
`CONECTADO_CON` (adyacencia de red de transporte) son tareas de seguimiento
separadas -- ver `grafo/README.md` y `infra/neo4j/schema/schema.cypher`.
Python puro, mismo motivo que `grafo/nodos.py`.
"""

from __future__ import annotations

from typing import Iterable


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
