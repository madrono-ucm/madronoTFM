---
id: 62
slug: verificar-silver-gold-lote2-completo
title: Verificar Silver→Gold para el segundo lote, parte 1/2 (ruido, aforos, agenda
  de eventos, Bluesky)
status: in_review
force: false
allow_infra_apply: true
branch: task/062-verificar-silver-gold-lote2-completo
pr_number: 109
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/109
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-17T21:50:00+00:00'
updated_at: '2026-08-19T22:45:34.417239+00:00'
started_at: '2026-08-19T22:36:23.271383+00:00'
submitted_at: '2026-08-19T22:45:34.417010+00:00'
merged_at: null
---

## Contexto

**Esta tarea ya se ha intentado dos veces y las dos terminó sin crear
ningún commit** (mismo patrón que las tareas 051/061). La primera vez
cubría los 8 datasets del segundo lote a la vez, y probablemente por eso se
quedó sin turnos/tiempo antes de comitear. Por eso se reduce a 4 datasets
(el resto, `aemet_prevision_avisos`, `cams_calidad_aire`,
`cartelera_cines_estrenos`, `afluencia_lugares`, es la tarea 063, creada
aparte).

**Verificado manualmente fuera de la sesión de `claude` (con `aws s3 ls` y
`aws glue get-job-runs`), no hace falta repetirlo**: el segundo intento SÍ
llegó a relanzar y completar con éxito el job Bronze→Silver de los 8
datasets del lote (ejecución real del 2026-08-19 ~22:01-22:06 UTC), y
Silver ya tiene datos reales para estos 4:

| Dataset | Partición Silver más reciente |
|---|---|
| `ruido` | `ruido/fecha=2026-08-17/...` (2026-08-19T22:05:14Z) |
| `aforos_peatones_bicicletas` | `aforos_peatones_bicicletas/fecha=2024-06-30/hora=21/...` (2026-08-19T22:05:06Z) |
| `agenda_eventos` | `agenda_eventos/fecha=2029-07-01/...` (2026-08-19T22:06:41Z) |
| `bluesky_menciones` | `bluesky_menciones/fecha=2026-08-19/hora=20/...` (2026-08-19T22:05:32Z) |

**No hace falta volver a lanzar el job Bronze→Silver de estos 4 — ya está
hecho y verificado.** El trabajo que falta es solo la etapa Silver→Gold
(nunca se llegó a lanzar en los dos intentos anteriores) y su verificación.

## Objetivo

Para estos 4 datasets, lanzar el job Silver→Gold contra el Silver ya
existente (arriba) y verificar que Gold contiene la agregación esperada.

## Alcance concreto

1. Para cada uno de los 4 datasets: `aws glue start-job-run` del job
   Silver→Gold, espera a que termine (`aws glue get-job-run`).
2. Confirma en S3 que Gold contiene el resultado esperado — compara a mano
   al menos un grupo de agregación contra los registros Silver de origen,
   por dataset (usa como referencia la forma de salida que ya se validó
   localmente contra los fixtures en las tareas 053-060: agregación por
   `(id, fecha, hora)` para ruido/aforos/bluesky, por `(categoría/lugar,
   fecha)` para agenda_eventos — revisa el `aggregate.py` de cada uno si
   tienes dudas de la clave exacta).
3. Documenta en `doc/062-verificar-silver-gold-lote2-completo.md`, por
   dataset: cuánto tardó Silver→Gold, cuántos registros entraron/salieron,
   y cualquier discrepancia con lo esperado.
4. Si algún dataset falla, documenta el error exacto — no intentes
   depurarlo más allá de un intento razonable, sería una tarea de
   seguimiento.

## Restricciones

- Alcance: solo estos 4 datasets (`ruido`, `aforos_peatones_bicicletas`,
  `agenda_eventos`, `bluesky_menciones`) — los otros 4 son la tarea 063.
- NO relances el job Bronze→Silver de estos 4 — ya está hecho, ver Contexto.
- NO crees ningún trigger/schedule de Glue — eso es la tarea 065.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni el primer lote de 6 datasets.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/062-...md` — un resultado parcial documentado es mucho más útil que
  terminar sin commitear nada, que es exactamente lo que ya falló dos veces
  en esta misma tarea.

## Criterios de aceptación

- Los 4 datasets tienen una ejecución real y verificada de Silver→Gold,
  documentada con los resultados reales obtenidos.
- `doc/062-verificar-silver-gold-lote2-completo.md` documenta el resultado.
- Hay un commit real con estos cambios.
