---
id: 27
slug: productores-lambda-handlers-lote2
title: Handlers Lambda de captura completa — lote 2/3 (meteorología, ruido, afluencia,
  aforos, Bluesky)
status: blocked
force: true
allow_infra_apply: false
branch: task/027-productores-lambda-handlers-lote2
pr_number: null
pr_url: null
attempts: 6
next_retry_at: '2026-08-14T21:42:58.703598+00:00'
last_error: You've hit your session limit · resets 8:10pm (UTC)
created_at: '2026-08-14T16:15:00+00:00'
updated_at: '2026-08-14T18:38:50.266532+00:00'
started_at: '2026-08-14T16:16:59.442638+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la tarea 026 (mismo objetivo, ver su contexto para el porqué del
alcance reducido: un primer intento con los 14 productores de una vez agotó el
presupuesto sin comitear nada). Este es el lote 2 de 3.

## Objetivo

Añadir un `lambda_handler(event, context)` a cada uno de estos 5 productores:

| Productor | Función |
|---|---|
| `meteorologia_madrid.py` (008) | captura completa |
| `ruido_madrid.py` (007) | captura completa (último día, todas las estaciones) |
| `afluencia_lugares_madrid.py` (012) | solo la parte de patrón típico (no la parte "vivo bajo demanda", esa la usará el asistente directamente) |
| `aforos_peatones_bicicletas_madrid.py` (013) | comprobación de recurso nuevo + captura si aplica |
| `bluesky_menciones_madrid.py` (016) | solo `search_district_sweep`, no `search_place` (esa también queda para el asistente bajo demanda) |

No toques ningún otro productor — tráfico/EMT/BiciMAD/aparcamientos/aire ya están
cubiertos en la tarea 026; agenda de eventos/AEMET/CAMS/cartelera de cines están
en la tarea 028.

## Alcance concreto

1. Para cada uno de los 5 productores, localiza la función que ya hace el
   fetch+normalize **sin** el recorte a "unos pocos registros" (confírmalo caso
   por caso, no lo asumas para todos).
2. Añade `lambda_handler(event, context)` que: llama a esa función de captura
   completa, construye un `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)`,
   y escribe el resultado con `write_batch`. Debe funcionar tanto en local como
   con `BRONZE_BASE_PATH=s3://...` (gracias a la tarea 025).
3. Si alguno quedara bloqueado por algo imprevisto, documenta el motivo en
   `doc/027-productores-lambda-handlers-lote2.md` y continúa con el resto; no
   dejes que uno bloquee todo el lote.
4. Añade tests para cada `lambda_handler` nuevo (con dobles, sin red real).
5. Actualiza `ingesta/README.md` señalando, para estos 5 productores, que ya
   tienen un `lambda_handler` listo para desplegar.

## Restricciones

- Alcance **estrictamente estos 5 productores** — no adelantes trabajo del lote 3
  (tarea 028), aunque parezca poco esfuerzo adicional.
- NO despliegues nada en AWS en esta tarea — es solo código.
- NO ejecutes una captura completa real que implique volumen grande de datos hacia
  ningún sitio; prueba con dobles/mocks.

## Criterios de aceptación

- Los 5 productores de la tabla tienen un `lambda_handler` funcional y probado.
- `doc/027-productores-lambda-handlers-lote2.md` deja constancia de cualquier
  productor sin resolver del todo, con el motivo.
- Todos los tests del proyecto siguen pasando.
