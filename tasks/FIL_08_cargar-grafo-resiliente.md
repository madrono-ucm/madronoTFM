---
kind: fil
title: "cargar_grafo.py resiliente a cortes de conexión de AuraDB Free (UNWIND + reintento)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-28"
---

> **Surgido el 28/8** ejecutando `FIL_04`. Bloquea el cierre de `FIL_04`
> (relaciones `PROXIMO_A` de los parques) y la parte 2 de `FIL_06`.

## Problema

`python -m grafo.cargar_grafo` contra la instancia real de Neo4j (AuraDB
Free) muere de forma intermitente con:

```
neo4j.exceptions.SessionExpired: Failed to read from defunct connection ...
```

El 28/8 falló **3 veces seguidas** (a los ~8, ~13 y ~? min) durante la fase
de relaciones. Una recarga completa que sí terminó ese mismo día tardó **51
min** — fue suerte. La causa es el patrón de escritura: `grafo/cypher.py::
_run_all` hace **una `session.run()` por nodo y por relación**, secuencial
(sin `UNWIND`), para los 9 tipos de carga. Son decenas de miles de idas y
vueltas al free tier; AuraDB Free corta la conexión antes de que termine.

Los nodos (`:Distrito`/`:Barrio`/`:EstacionMedida`/`:ParadaTransporte`/
`:Lugar`) suelen cargarse antes de que caiga; lo que queda sin crear son las
relaciones (`UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`), sobre todo de los
nodos añadidos en la última recarga.

## Objetivo

Una recarga completa de `cargar_grafo.py` contra la instancia real que
**termine de forma fiable** (idealmente en minutos, no ~1 h).

## Alcance

1. **`UNWIND` para agrupar los `MERGE`** (`grafo/cypher.py`): en vez de N
   llamadas `session.run(MERGE ...)`, una llamada
   `session.run("UNWIND $filas AS f MERGE (...) SET ...", filas=lote)` por
   lote de ~1000-5000. Aplica a los 9 `load_*` (nodos y relaciones). El
   esquema ya tiene los índices (`schema.cypher`, tarea 094), así que el
   `MERGE` por `id` dentro del `UNWIND` es barato.
2. **Reintento con reconexión por lote**: si un lote falla con
   `SessionExpired`/`ServiceUnavailable`, reabrir sesión y reintentar ese
   lote (backoff corto, 3-5 intentos). El driver ya reintenta a nivel de
   transacción con `session.execute_write`; usarlo.
3. **Idempotencia intacta**: sigue siendo todo `MERGE`, una recarga a medias
   no corrompe nada (ya es así).
4. Tests: `grafo/tests/test_cypher.py` — verificar la forma de las
   sentencias `UNWIND` generadas (inspección de cadena, sin conexión real,
   mismo patrón que los tests actuales de `*_query()`).
5. Recarga real de verificación: `python -m grafo.cargar_grafo` contra la
   instancia real → termina sin `SessionExpired`; Cypher:
   `MATCH (l:Lugar {tipo:"parque"})-[:PROXIMO_A]-(e) RETURN count(DISTINCT l)`
   > 0 (cierra `FIL_04`).

## Restricciones

- No cambiar el contrato de `nodos.py`/`relaciones.py` (siguen devolviendo
  `list[dict]`); el cambio es solo en cómo `cypher.py` los escribe.
- Credenciales Neo4j de SSM, nunca a disco (ver `infra/OPERACION.md`).
