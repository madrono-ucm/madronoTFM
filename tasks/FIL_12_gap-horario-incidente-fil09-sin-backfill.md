---
kind: fil
title: "FIL_09 se declaró resuelto verificando solo frescura por fecha — 6 datasets tienen ~17-21 horas perdidas el 29/8, nunca rellenadas"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-29"
---

> **✅ RESUELTO 30/8 — backfill hecho.** Nuevo modo `--backfill_fecha` en los
> 10 jobs de los 5 datasets horarios (PR #183) + `s3:DeleteObject` IAM.
> Ejecutado para 2026-08-29: **10/10 `SUCCEEDED`**; `trafico`/`calidad_aire`/
> `meteorologia`/`bicimad`/`aparcamientos` pasan de 3–4/24 h a **24/24 h**,
> **0 duplicados** (verificado en Athena). `transporte_publico_emt` queda
> 20/24 (su Bronze está incompleto — hueco propio del productor, no del
> incidente). Detalle en `doc/FIL-09` §"Completitud por hora del 29/8";
> runbook del modo backfill en `infra/OPERACION.md`.

> **Contexto**: encontrado en `VIC_11` (evaluación técnica de `asistente/`),
> verificando en vivo las tools contra Athena real — varias devolvían
> `sin_datos` para un `momento` de ayer (29/8) que debería tener datos de
> sobra. Investigado hasta la causa raíz real.

## Qué está roto (verificado en vivo)

`FIL_09` (incidente de la tarea 106: librería compartida de Glue rota)
verificó su resolución comprobando **frescura por fecha**
(`max(date) = 2026-08-29` en Athena) para 9-12 datasets, y lo dio por
bueno. Pero **frescura por fecha no implica completitud por hora** — estos
son datasets horarios, y una fecha con "algo" de datos ya cuenta como
"fresca" aunque falten casi todas las horas.

Verificado ahora, contando horas distintas con datos reales en
`date='2026-08-29'` para los 6 datasets que `FIL_09` reportó como
recuperados:

| Dataset | Horas con datos (de 24) | Horas perdidas |
|---|---|---|
| `trafico` | 3 (20, 22, 23) | **21** |
| `aparcamientos` | 4 | **20** |
| `calidad_aire` | 4 | **20** |
| `transporte_publico_emt` | 4 | **20** |
| `meteorologia` | 4 | **20** |
| `bicimad` | 4 | **20** |

Contrastado con el histórico real de `aws glue get-job-runs` para
`madrono-tfm-dev-trafico-bronze-to-silver`: **19 ejecuciones horarias
consecutivas fallaron** (`01:10` a `19:10` UTC del 29/8, todas con el
mismo `LAUNCH ERROR` de la librería compartida rota), recuperándose recién
a las `19:35` UTC — coincide exactamente con la ventana del incidente que
`FIL_09` ya documentó (28/8 ~15:13 a 29/8 ~19:35, ~28h). El "árbol" del
incidente (jobs volviendo a `SUCCEEDED`) se arregló; el "bosque" (las
horas que se perdieron mientras tanto) **nunca se rellenó**.

## Por qué importa

- Estos 6 datasets son parte de los "16 productores en producción
  continua" de la memoria — un hueco de ~20h en uno de ellos rompe
  silenciosamente cualquier análisis que asuma cobertura horaria completa
  para el 29/8.
- **`modelado/` lee directamente de estas tablas Gold** (`ML_01` feature
  store, panel horario) — un panel construido después de hoy incluirá un
  hueco real de ~20h para 6 fuentes el mismo día, que los modelos
  interpretarán como "sin lecturas" en vez de "no capturado por un
  incidente conocido". Puede sesgar lags/rolling de esa ventana si no se
  documenta o se excluye.
- `FIL_09`/`FIL_10` (y su documentación) dan la impresión de que el
  incidente se cerró sin pérdida de datos ("Gold fresco verificado") —
  matiz importante para la memoria si `VIC_15` (pasada de consistencia
  final) llega a tocar este punto.

## Qué investigar / hacer (sin aplicar nada aquí)

1. Decidir si merece la pena hacer backfill real de las ~20h perdidas por
   dataset (relanzar `bronze_to_silver`/`silver_to_gold` para cada hora
   concreta, si `procesamiento/silver_gold/<x>/glue_bronze_to_silver.py`
   soporta reprocesar una hora pasada explícita en vez de solo "ahora") —
   o si se acepta como una limitación histórica documentada (más barato,
   y ya hay precedente: la memoria ya documenta la ventana corta de datos
   como limitación en §7.4).
2. Si se decide backfill: identificar exactamente qué horas faltan por
   dataset (esta tarea ya dio el conteo, no el detalle hora a hora) y
   confirmar que el Bronze de esas horas siquiera existe (si Bronze
   también está vacío para esas horas —lambdas fallando en la misma
   ventana, no solo Glue—, el backfill de Silver/Gold no serviría de
   nada: revisar `aws lambda ...`/logs de las Lambdas productoras en esa
   ventana antes de asumir que Bronze está completo).
3. Si se decide no rellenar: añadir una nota explícita en
   `doc/FIL-09-...md` (sección nueva) y considerar si `modelado/ML_01`
   necesita saberlo (marcar el 29/8 como parcial en el feature store, o
   simplemente dejar que las horas ausentes se traten como huecos
   normales del pipeline, ya contemplado por el diseño de lags/rolling).
4. Revisar si el mismo patrón de comprobación ("solo `max(date)`, no
   horas") se ha usado en otras verificaciones de esta sesión (p. ej.
   `VIC_09`) y ajustar el criterio de "frescura" a futuro para datasets
   horarios.

## Restricciones

- No se ha relanzado ningún job ni tocado código en este ticket — solo
  lectura de `aws glue get-job-runs` y Athena real.

## Criterios de aceptación

- Decisión explícita (backfill vs. limitación documentada) para los 6
  datasets.
- Si se decide backfill, verificado en Athena real que las horas antes
  ausentes ahora tienen datos.
- Si se decide no rellenar, documentado en `doc/FIL-09-...md` y,si aplica,
  una nota en la memoria (§7.4, vía un ticket `VIKT_*` aparte — no se edita
  aquí).
