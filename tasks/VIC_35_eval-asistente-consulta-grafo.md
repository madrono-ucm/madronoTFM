---
kind: vic-eval
title: "Evaluación de la tool consulta_grafo (nº 15) y el enriquecimiento de contexto_urbano"
owner: Claude (QA)
status: done
created_at: "2026-09-09"
depends_on: [FIL_67]
---

## Hecho (2026-09-10, Claude QA)

Los 6 puntos verificados. Solo lectura y parametrización confirmadas en
las 8 plantillas; aplicado `default_access_mode="READ"` explícito en
`run_neo4j_query` (recomendación del propio ticket, punto 1) — requirió
arreglar 4 dobles de prueba que no aceptaban el nuevo kwarg. El guard
`_ESCRITURA` de `grafo/consulta.py` resistió los 4 bypasses sugeridos
(documentado por qué, y su límite real: la enforcement de verdad es
`default_access_mode="READ"`, no la regex). `contexto_urbano` mantiene
compatibilidad hacia atrás (tests de esquema en verde). Las dos copias de
`grafo_urbano.json.gz` coinciden entre sí (con la salvedad ya conocida de
`VIC_34`). **Hallazgo real**: `grafo/extract.py::_recent_date_filter` usa
`current_date` real en vez de una fecha ancla — con la ingesta congelada
desde el 30/8, la ventana de 14 días se queda sin datos reales a partir
del ~13-14/9, justo antes de la entrega del 17/9. Abierto `FIL_89`.

`pytest asistente/ grafo/`: 361 passed, 1 skipped, 57 subtests (tras
arreglar los dobles de prueba rotos por el endurecimiento del punto 1).

Detalle completo en
[`doc/VIC-35-eval-asistente-consulta-grafo.md`](../doc/VIC-35-eval-asistente-consulta-grafo.md).

## Contexto

FIL_67 añadió la 15ª herramienta MCP `consulta_grafo` (8 plantillas de
**solo lectura** parametrizadas contra Neo4j, sin Cypher libre), 7
constructores nuevos en `asistente/neo4j_client.py`, el CLI
`grafo/consulta.py`, y amplió `contexto_urbano` (meteo + atributos FIL_66 +
`lineas_cercanas`) tocando los modelos `EstacionProxima` / `ContextoUrbano`.

## Alcance — revisión de código, sin cambios

1. **`consulta_grafo` — garantía de solo lectura.** ¿Alguna de las 8
   plantillas (`_PLANTILLAS_GRAFO`) puede escribir o disparar un
   procedimiento caro? Revisar cada `*_query` de `neo4j_client.py`: son
   `MATCH ... RETURN` puros, sin `CALL`, sin `apoc`. Confirmar que
   `run_neo4j_query` no permite inyección (params siempre parametrizados,
   nunca interpolados). Considerar si conviene un `access_mode="READ"`
   explícito en `run_neo4j_query` (hoy usa el modo por defecto).
2. **Contrato de degradación (`FIL_15`).** Los 3 caminos de fallo de
   `_consulta_grafo_impl` (plantilla desconocida / parámetros que faltan /
   Neo4j caído) devuelven `disponible=false` + `motivo`, nunca excepción.
   ¿Falta algún camino? (p. ej. `run_neo4j_query` devolviendo algo que no
   sea lista, timeout).
3. **`grafo/consulta.py` — el guard anti-escritura.** ¿El regex `_ESCRITURA`
   cubre todo? Casos a probar: `CALL apoc.periodic.iterate('MATCH..','SET..')`
   (SET dentro de string), `CALL { CREATE ... }` (subquery), `MATCH (n)
   CALL apoc.create.addLabels(...)`, comentarios que oculten palabras clave.
   Es un CLI de dev, pero documentar los límites del guard.
4. **`contexto_urbano` — compatibilidad.** `EstacionProxima` ganó campos
   opcionales (`nombre`/`contaminantes`/`magnitudes`/`altitud_m`/`subarea`)
   y `ContextoUrbano` ganó `lineas_cercanas`. Todos con `default` → el
   `output_schema` MCP sigue siendo válido y ningún cliente que esperara el
   esquema anterior se rompe. Verificar con `test_mcp_transport` (esquema
   real por transporte).
5. **`asistente/modelos/grafo_urbano.json.gz`** se re-sincronizó desde
   `grafo/_data/`. Confirmar que están commiteadas **las dos** copias y que
   coinciden (`md5sum`), y que `contexto_urbano` y `viz/` no divergen.
6. **`_recent_date_filter` en los `fetch_*` de FIL_66**: con el pipeline
   congelado, las columnas `array_agg` (`contaminantes`, `magnitudes`,
   `modos`) se calculan sobre la ventana de 14 días — ¿podrían quedar
   incompletas si una estación no reportó en esos días? (meteo y aforos ya
   escanean sin filtro; aire/tráfico sí lo aplican).

## Criterios de aceptación

- Los 6 puntos revisados; hallazgos de seguridad/robustez → `FIL_*`.
- `python -m pytest asistente/ grafo/` verde en el momento de la revisión.
- Recomendación explícita sobre el `access_mode="READ"` (punto 1).
