---
id: 63
slug: verificar-silver-gold-lote2-completo-parte2
title: Verificar Silver→Gold para el segundo lote, parte 2/2 (AEMET, CAMS, cartelera,
  afluencia)
status: in_progress
force: false
allow_infra_apply: true
branch: task/063-verificar-silver-gold-lote2-completo-parte2
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-19T22:45:00+00:00'
updated_at: '2026-08-19T22:58:50.520091+00:00'
started_at: '2026-08-19T22:58:50.520068+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la tarea 062 (mismo motivo: se dividió el segundo lote en dos
partes de 4 datasets para no repetir el fallo de dos intentos previos sin
commit). Esta es la segunda mitad: `aemet_prevision_avisos` (dos pares de
jobs, previsión y avisos), `cams_calidad_aire`, `cartelera_cines_estrenos`,
`afluencia_lugares`.

**Verificado manualmente fuera de la sesión de `claude` — no hace falta
repetirlo**: el job Bronze→Silver de estos 4 (5 contando los dos jobs de
AEMET) ya se relanzó y completó con éxito el 2026-08-19 ~22:01-22:06 UTC:

| Dataset | Partición Silver más reciente |
|---|---|
| `aemet_prevision` | `aemet_prevision/fecha=2026-08-22/...` (2026-08-19T22:05:15Z) |
| `aemet_avisos` | `aemet_avisos/fecha=2026-08-19/...` (2026-08-19T22:05:24Z) |
| `cams_calidad_aire` | `cams_calidad_aire/fecha=2026-08-19/hora=03/...` (2026-08-19T22:05:10Z) |
| `cartelera_cines_estrenos` | **vacío** — 0 objetos en Silver |
| `afluencia_lugares` | **vacío** — 0 objetos en Silver |

**Los dos últimos vacíos son esperados, no un bug** (ya documentado en la
tarea 061): la muestra de `cartelera_cines_estrenos` tiene fecha de sesión
ya pasada respecto al momento de la ejecución (la puerta de calidad las
descarta correctamente), y `afluencia_lugares` sigue bloqueado sin
`GOOGLE_MAPS_API_KEY` real. **No hace falta volver a lanzar Bronze→Silver
de ninguno de los 4 — ya está hecho.**

## Objetivo

Lanzar el job Silver→Gold de estos 4 datasets (5 jobs, por los dos pares de
AEMET) y verificar el resultado — incluyendo confirmar que Gold sale
correctamente vacío (no con error) para los dos datasets sin datos en
Silver.

## Alcance concreto

1. Para `aemet_prevision_avisos` (los dos jobs Silver→Gold, previsión y
   avisos), `cams_calidad_aire`, `cartelera_cines_estrenos` y
   `afluencia_lugares`: `aws glue start-job-run` del job Silver→Gold
   correspondiente, espera a que termine.
2. Para `aemet_prevision_avisos` y `cams_calidad_aire`, confirma en S3 que
   Gold contiene el resultado esperado — compara a mano al menos un grupo
   de agregación contra los registros Silver de origen (revisa
   `aggregate.py` de cada uno si tienes dudas de la clave exacta:
   `(municipio, leadtime_días)`/`(zona, fecha, nivel)` para AEMET,
   `(pollutant, fecha_validez)` para CAMS).
3. Para `cartelera_cines_estrenos` y `afluencia_lugares`, confirma que el
   job Silver→Gold **completa sin error** aunque no escriba ningún dato
   (Gold vacío es el resultado correcto aquí, no un fallo) — si en cambio
   falla con una excepción real (no solo "0 registros"), documenta el error
   exacto y no lo des por esperado sin comprobarlo.
4. Documenta en `doc/063-verificar-silver-gold-lote2-completo-parte2.md`,
   por dataset: cuánto tardó, cuántos registros entraron/salieron (o 0, si
   corresponde), y cualquier discrepancia con lo esperado.

## Restricciones

- Alcance: solo estos 4 datasets (5 jobs Silver→Gold contando AEMET) — los
  otros 4 son la tarea 062.
- NO relances el job Bronze→Silver de estos 4 — ya está hecho, ver Contexto.
- NO crees ningún trigger/schedule de Glue — eso es la tarea 065.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni el primer lote de 6 datasets.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/063-...md`.

## Criterios de aceptación

- Los 4 datasets (5 jobs Silver→Gold) tienen una ejecución real y
  verificada, documentada con los resultados reales.
- `doc/063-verificar-silver-gold-lote2-completo-parte2.md` documenta el
  resultado.
- Hay un commit real con estos cambios.
