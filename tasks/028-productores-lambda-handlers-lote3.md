---
id: 28
slug: productores-lambda-handlers-lote3
title: "Handlers Lambda de captura completa — lote 3/3 (agenda eventos, AEMET, CAMS, cines)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-14T16:15:00+00:00"
updated_at: "2026-08-14T16:15:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Continúa las tareas 026 y 027 (mismo objetivo, ver el contexto de la 026 para el
porqué del alcance reducido). Este es el lote 3 de 3 — al terminar, los 14
productores programados tendrán su `lambda_handler`, y la tarea 029 (Terraform)
podrá desplegarlos todos.

## Objetivo

Añadir un `lambda_handler(event, context)` a cada uno de estos 4 productores:

| Productor | Función |
|---|---|
| `agenda_eventos_madrid.py` (017) | captura completa de la agenda |
| `aemet_prevision_avisos.py` (018) | dos handlers separados o uno con `event` indicando `previsión`/`avisos` — decide y documenta |
| `cams_calidad_aire_madrid.py` (019) | captura completa |
| `cartelera_cines_madrid.py` (023) | solo `sweep_premieres`, no `fetch_cinema_showtimes` (esa queda para el asistente bajo demanda) |

(022 no necesita handler propio: reutiliza el feed que ya descarga 017, según
documentó su propia tarea — no dupliques la captura.)

No toques ningún otro productor — el resto ya está cubierto en las tareas 026 y
027.

## Alcance concreto

1. Para cada uno de los 4 productores, localiza la función que ya hace el
   fetch+normalize **sin** el recorte a "unos pocos registros".
2. Añade `lambda_handler(event, context)` que: llama a esa función de captura
   completa, construye un `BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=...)`,
   y escribe el resultado con `write_batch`. Debe funcionar tanto en local como
   con `BRONZE_BASE_PATH=s3://...` (gracias a la tarea 025).
3. Si alguno quedara bloqueado por algo imprevisto, documenta el motivo en
   `doc/028-productores-lambda-handlers-lote3.md` y continúa con el resto; no
   dejes que uno bloquee todo el lote.
4. Añade tests para cada `lambda_handler` nuevo (con dobles, sin red real).
5. Actualiza `ingesta/README.md` señalando, para estos 4 productores, que ya
   tienen un `lambda_handler` listo para desplegar.

## Restricciones

- NO despliegues nada en AWS en esta tarea — es solo código.
- NO ejecutes una captura completa real que implique volumen grande de datos hacia
  ningún sitio (especialmente CAMS/AEMET si finalmente tienen credenciales reales);
  prueba con dobles/mocks.
- No captures secretos (API keys) en ningún fichero commiteado.

## Criterios de aceptación

- Los 4 productores de la tabla tienen un `lambda_handler` funcional y probado.
- `doc/028-productores-lambda-handlers-lote3.md` deja constancia de cualquier
  productor sin resolver del todo, con el motivo.
- Todos los tests del proyecto siguen pasando.
