---
id: 87
slug: grafo-aforos-peatones-bicicletas-neo4j-real
title: 'Grafo: Fase A de la especificación 086 -- añadir EstacionMedida{tipo: aforos_peatones_bicicletas}'
status: pending
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: null
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

**Esta tarea implementa la "Fase A" de la especificación ya diseñada y
revisada en `doc/086-afluencia-estimada-grafo.md` (tarea 086) — léela
entera antes de empezar, es la fuente de verdad del diseño, no reabras
ninguna decisión que ya toma.** Sustituye a un diseño anterior propio
(`tipo: "aforo"`) que quedó descartado en favor del naming exacto que fija
`086`: `tipo: "aforos_peatones_bicicletas"` (mismo nombre que el dataset,
consistente con cómo se nombran `trafico`/`calidad_aire`/`ruido`).

Resumen de por qué existe esta tarea (detalle completo en `086`): tras
descartar Google Maps por coste (tarea 083, `doc/083-...md` — verificado en
código que `populartimes` exige una llamada de pago antes de poder
scrapear, no hay forma de tener datos reales a coste 0), se decidió
sustituir la señal de afluencia por una basada en el grafo Neo4j sobre
`aforos_peatones_bicicletas` (gratis, ya en producción desde la tarea 054).
El grafo real no tiene hoy ningún nodo de este origen — solo
`trafico`/`calidad_aire`/`ruido` alimentan `:EstacionMedida` (ver
`grafo/README.md`).

**Antes de tocar la instancia real, verifica la Prioridad 1 de
`NEXT_STEPS.md`** (drift de Terraform descubierto en la tarea 083): si no
se ha reconciliado todavía, confirma al menos que el código real de
`aforos_peatones_bicicletas` desplegado (Glue Job) coincide con lo que hay
en `main` antes de asumir que `gold.aforos_peatones_bicicletas_por_estacion_
modo_hora` tiene datos reales y actualizados -- si encuentras que no
coincide, para y documenta el hallazgo en vez de continuar a ciegas.

## Objetivo

Añadir `:EstacionMedida {tipo: "aforos_peatones_bicicletas"}` al pipeline
de extracción/carga del grafo (Fase A de `086`), y recargar la instancia
real de Neo4j.

## Alcance concreto

Sigue el punto "Fase A" de `doc/086-afluencia-estimada-grafo.md` al pie de
la letra:

1. `grafo/extract.py`: `fetch_estaciones_aforos_peatones_bicicletas()`,
   mismo patrón que `fetch_estaciones_ruido` -- confirma primero el nombre
   exacto de la tabla Gold y sus columnas reales en
   `procesamiento/silver_gold/aforos_peatones_bicicletas/aggregate.py`
   (columna de ubicación anidada: `location.lat`/`location.lon`, no
   columnas planas como en `trafico_por_punto_hora` -- ajusta el SQL).
2. `grafo/nodos.py`: `estacion_medida_from_aforos_peatones_bicicletas_gold`
   (`id` = `f"aforos_peatones_bicicletas:{station_id}"`, `tipo:
   "aforos_peatones_bicicletas"`, `fuente: "aforos_peatones_bicicletas"`,
   `nombre`: `address` si existe, si no `district`) + su plural, mismo
   contrato que las tres funciones equivalentes ya existentes.
3. `grafo/cargar_grafo.py::cargar_grafo`: añade la lista resultante a la
   unión de `estaciones_medida` -- no toques `relaciones.py` (genérico
   sobre cualquier nodo con `ubicacion`+`tipo` distinto).
4. Tests: replica `grafo/tests/test_extract.py`/`test_nodos.py` de
   `ruido` para este nuevo origen (Athena mockeada, sin conexión real).
5. **Recarga real**: ejecuta `python3 -m grafo.cargar_grafo` contra la
   instancia real (credenciales de SSM, región `eu-west-1` explícita --
   ver el bug corregido en `PLAN.md`). Es idempotente (`MERGE`, verificado
   en la tarea `080`), no borra nada de lo ya cargado. Verifica con Cypher
   real: `MATCH (e:EstacionMedida {tipo: "aforos_peatones_bicicletas"})
   RETURN count(e)` > 0, y al menos un `:Lugar` conocido con una relación
   `PROXIMO_A` nueva hacia una de estas estaciones.
6. `grafo/README.md`: añade `aforos_peatones_bicicletas` a la tabla de
   orígenes de `:EstacionMedida` y actualiza los conteos reales.
7. Documenta en `doc/087-grafo-aforos-peatones-bicicletas-neo4j-real.md` el
   esquema real de Athena encontrado, el resultado de la comprobación del
   drift de Terraform, la recarga realizada, y los conteos finales.

## Restricciones

- No implementes aquí la tool `afluencia_estimada` (Fase B) -- es la tarea
  `088`, deliberadamente separada y posterior.
- No uses el naming `tipo: "aforo"` ni ningún otro distinto al que fija
  `doc/086` (`"aforos_peatones_bicicletas"`) -- consistencia con la
  especificación ya revisada.
- No toques `ingesta/capturas/afluencia_lugares_madrid.py` ni
  `populartimes` -- quedan documentados como están.
- No cambies el umbral de `PROXIMO_A` (300m, tarea 070).
- No ejecutes ningún `terraform apply`/`destroy` -- si la verificación de
  drift de arriba encuentra algo, documéntalo y para, no lo reconcilies
  aquí (esa reconciliación es la Prioridad 1 de `NEXT_STEPS.md`, fuera de
  alcance de esta tarea).

## Criterios de aceptación

- `:EstacionMedida {tipo: "aforos_peatones_bicicletas"}` existe en la
  instancia real de Neo4j con conteo > 0, verificado con Cypher real.
- `PROXIMO_A` incluye relaciones nuevas hacia esos nodos, verificado con
  Cypher real.
- Tests en verde.
- `grafo/README.md` y `doc/087-...md` reflejan el esquema real y los
  conteos reales tras la recarga, incluyendo el resultado de la
  comprobación de drift de Terraform.
