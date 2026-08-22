---
id: 73
slug: arreglo-lectura-incremental-glue-grupo-horario
title: "Lectura incremental para el resto del grupo horario (EMT, aparcamientos, calidad del aire, meteorología)"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-22T09:30:00+00:00"
updated_at: "2026-08-22T09:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Continúa la tarea 072 (mismo bug, mismo motivo de división: un primer
intento cubriendo los 14 datasets a la vez agotó presupuesto sin comitear
nada). La 072 arregló los dos datasets más urgentes (`trafico`, `bicimad`,
ya en `TIMEOUT` activo); esta tarea cubre los 4 restantes del grupo horario:
`transporte_publico_emt`, `aparcamientos`, `calidad_aire`, `meteorologia`.
Su coste actual es más bajo que trafico/bicimad pero comparten exactamente
el mismo bug y la misma trayectoria creciente (ver `doc/072-...md` para el
diagnóstico completo, no lo repitas aquí).

Sus triggers `SCHEDULED` están desactivados desde antes de la tarea 072
(mitigación aplicada fuera de cola, vía `aws glue stop-trigger`, sin pasar
por Terraform). **Confirma al empezar que siguen desactivados.**

**`force: false` deliberado**: mismo criterio que 072.

## Objetivo

Aplicar el mismo arreglo de lectura incremental (partición
`fecha`/`hora` en vez de la ruta raíz) que ya aplicó la 072 a
`trafico`/`bicimad`, a estos 4 datasets (8 ficheros), reactivar sus 4
triggers tras verificar, y confirmar con una ejecución real.

## Alcance concreto

1. En `procesamiento/silver_gold/{transporte_publico_emt,aparcamientos,
   calidad_aire,meteorologia}/glue_{bronze_to_silver,silver_to_gold}.py`
   (8 ficheros): mismo patrón exacto que ya aplicó la tarea 072 — revisa su
   diff/PR como referencia directa antes de reimplementar desde cero.
2. Actualiza los tests correspondientes si aplica (mismo criterio que 072).
3. `terraform apply` acotado con `-target` a los 8 `aws_glue_job` de estos
   4 datasets únicamente.
4. Reactiva sus 4 triggers `SCHEDULED` solo después de verificar.
5. Fuerza una ejecución real de Bronze→Silver y Silver→Gold de al menos 2
   de los 4 datasets y confirma coste/duración proporcional, sin `TIMEOUT`.
6. Documenta en
   `doc/073-arreglo-lectura-incremental-glue-grupo-horario.md`.

## Restricciones

- Alcance: solo estos 4 datasets (8 ficheros, 4 triggers) — el grupo diario
  es la tarea 074.
- NO ejecutes `terraform apply` sin `-target`.
- NO ejecutes `terraform destroy`.
- NO reactives los triggers hasta haber verificado el arreglo.
- **Antes de terminar, confirma que dejas un commit real.**

## Criterios de aceptación

- Los 4 datasets procesan solo datos nuevos por ejecución, verificado con
  al menos 2 ejecuciones reales sin `TIMEOUT` y con coste proporcional.
- Sus 4 triggers `SCHEDULED` están reactivados tras verificar.
- `doc/073-...md` documenta el resultado.
- Hay un commit real con estos cambios.
