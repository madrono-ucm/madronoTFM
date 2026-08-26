---
id: 94
slug: recargar-grafo-osm-aforos-instancia-real
title: 'QA: la instancia real de Neo4j no tiene el enriquecimiento OSM (083) ni los
  nodos de aforos (087), pese a estar dados por completados'
status: failed
force: false
allow_infra_apply: false
branch: task/094-recargar-grafo-osm-aforos-instancia-real
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: claude finalizó sin crear ningún commit
created_at: '2026-08-26T10:55:00+00:00'
updated_at: '2026-08-26T12:09:54.782469+00:00'
started_at: '2026-08-26T12:06:02.219979+00:00'
submitted_at: null
merged_at: null
---

## Hallazgo de QA (verificado en vivo contra la instancia real, no contra tests)

Consulta directa a la instancia real de Neo4j AuraDB (vía
`neo4j+s://`, credenciales de SSM `eu-west-1`) hoy (26/8):

```
MATCH (n) RETURN labels(n)[0], count(n)
EstacionMedida  4738
ParadaTransporte 4056
Lugar            381
Barrio           131
Distrito          21
```

Estos números son **idénticos** a los de `doc/080-cargar-grafo-neo4j-real.md`
(24/8) — es decir, ningún nodo nuevo ha entrado en la instancia real desde
entonces. Sin embargo, dos tareas posteriores implementaron y verificaron
(con tests, no contra la instancia real) enriquecimientos que deberían
haber cambiado estos números:

- **Tarea `083-grafo-enriquecimiento-poi-osm`** (`tasks/done/083-grafo-enriquecimiento-poi-osm.md`,
  PR #131): añade etiquetas de OpenStreetMap a `:Lugar` (`osm_categoria`,
  etc.) — verificado que la instancia real tiene **0** nodos `:Lugar` con
  esos campos (`MATCH (l:Lugar) WHERE l.osm_categoria IS NOT NULL ... RETURN
  count(l)` → `0`). El propio `doc/083-...md` ya admite que no se recargó
  la instancia real; este ticket es para no perder de vista ese pendiente.
- **Tarea `087-grafo-aforos-peatones-bicicletas-neo4j-real`**
  (`tasks/done/087-...md`): añade `:EstacionMedida {tipo:
  "aforos_peatones_bicicletas"}` — el conteo de `EstacionMedida` (4738) no
  ha cambiado desde antes de esa tarea, así que tampoco está en la
  instancia real. El propio `doc/087-...md` ya lo admite explícitamente.

Ninguna de las dos cosas es una sorpresa (ambos `doc/` ya lo dicen), pero
**no existe ningún ticket en `tasks/` que lo trate como pendiente
accionable** — vive solo como una frase dentro de un documento de archivo,
fácil de perder de vista según avanza el proyecto y más sesiones dan por
hecho que "el grafo está cargado" (como hace, por ejemplo, la entrada de
`089-asistente-tool-afluencia-estimada`, que si hubiera dependido de
`aforos_peatones_bicicletas` en el grafo habría fallado en silencio contra
datos reales pese a que sus tests mockeados pasan en verde).

## Objetivo

Recargar la instancia real de Neo4j con ambos enriquecimientos y verificar
con Cypher real (no mocks) que los datos están ahí.

## Alcance concreto

1. Obtén las credenciales de Neo4j de SSM en `eu-west-1` (con `--region`
   explícito, ver el bug ya corregido en `doc/082-...md` — no lo repitas).
2. Ejecuta el pipeline de carga/enriquecimiento de la tarea 083
   (`grafo/` — revisa qué función/script expone el enriquecimiento OSM,
   probablemente en `grafo/extract.py`/`grafo/nodos.py`, ver
   `doc/083-grafo-enriquecimiento-poi-osm.md` para el punto de entrada
   exacto) contra la instancia real.
3. Ejecuta el pipeline de la tarea 087 (nodos `EstacionMedida` de
   `aforos_peatones_bicicletas`) contra la instancia real — **nota**: la
   fuente de aforos peatones/bicicletas está descontinuada en Athena por un
   problema de partition projection (ver `doc/087`, `doc/090`, y la
   Prioridad 2 de `NEXT_STEPS.md`) que sigue sin aplicarse (depende del
   `apply` de Terraform de la Prioridad 1) — si por eso no hay datos reales
   que cargar todavía, documenta explícitamente que sigue bloqueado por esa
   dependencia, no lo fuerces con datos falsos.
4. Verifica con Cypher real, tras la carga: cuántos `:Lugar` tienen ahora
   campos OSM, y si aparece algún `:EstacionMedida {tipo:
   "aforos_peatones_bicicletas"}` (puede ser 0 si el punto 3 sigue
   bloqueado — está bien, documenta por qué).
5. Actualiza `doc/083-...md` y `doc/087-...md` (añade una sección
   "Actualización 26/8", no los reescribas) marcando qué se cargó
   realmente y qué sigue pendiente.

## Restricciones

- No escribas ninguna credencial de Neo4j en el repositorio.
- No toques `infra/terraform/` — no depende de Terraform (aparte de la
  posible dependencia de datos de aforos, ver punto 3).
- Si el enriquecimiento OSM requiere llamar a la API de Overpass en vivo,
  respeta el mismo patrón de rate-limit/caché ya usado en la tarea 083.
- Documenta en `doc/094-...md` el resultado real (conteos antes/después,
  verificados con Cypher, no con tests).

## Criterios de aceptación

- La instancia real de Neo4j tiene nodos `:Lugar` con campos OSM (verificado
  con Cypher real), o queda documentado por qué no fue posible.
- Queda documentado, con la misma honestidad que `doc/087`, si los nodos de
  aforos se cargaron o siguen bloqueados por la fuente descontinuada.
- Hay un commit real con `doc/094-...md`.
