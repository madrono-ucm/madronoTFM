---
id: 90
slug: arreglo-gold-aparcamientos-cartelera
title: 'Prioridad 2 de NEXT_STEPS.md: verificar aparcamientos, arreglar cartelera_cines_estrenos y el mismo bug de fecha en otros datasets'
status: done
force: false
allow_infra_apply: true
branch: task/090-arreglo-gold-aparcamientos-cartelera
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: '2026-08-26T12:10:00Z'
started_at: '2026-08-26T09:00:00Z'
submitted_at: '2026-08-26T12:10:00Z'
merged_at: null
---

## Contexto

Prioridad 2 de `NEXT_STEPS.md`: dos tablas Gold rotas, `aparcamientos`
(`doc/052`, 0 filas escritas sin diagnosticar) y `cartelera_cines_estrenos`
(`doc/063`, `AnalysisException`, Silver vacío). Verifica ambos casos contra
AWS real (no te fíes de los diagnósticos antiguos sin comprobarlos primero
contra el estado actual del código y de los datos — ambos llevan semanas
de reescrituras encima, tareas 072/075/076) y arregla lo que siga roto.

## Qué se hizo

- `aparcamientos`: ya estaba resuelto (efecto colateral de la reescritura
  de lectura incremental, tareas 072/075) — verificado con Athena real
  (601 filas/día), solo hacía falta actualizar `NEXT_STEPS.md`.
- `cartelera_cines_estrenos`: causa real distinta y más profunda que el
  diagnóstico de `doc/063` — sin ningún escritor programado de sesiones
  de cine, la puerta de calidad de Silver rechazaba el 100% de los lotes
  reales. Añadido `sweep_showtimes`/`event.tipo=="sesiones"` al Lambda
  existente (mismo patrón que `aemet_prevision_avisos`) + schedule
  Terraform, aplicado de verdad (`terraform apply` acotado). Verificado de
  extremo a extremo contra AWS real: invocación Lambda real (52 sesiones
  reales escritas a Bronze), Bronze→Silver→Gold reales vía
  `aws glue start-job-run`, contenido final verificado con Athena.
- En la propia verificación se encontró un bug real
  (`AnalysisException: Column 'fecha' does not exist`, lectura de una
  única partición diaria que deja de exponer `fecha` como columna) — se
  buscó el mismo patrón en el resto de jobs Silver→Gold de cadencia diaria
  y se encontró también en `agenda_eventos` (rompiendo producción en
  directo desde el 2026-08-23) y `bluesky_menciones` (fallos
  intermitentes). Corregidos los 3, verificados relanzando los jobs reales
  donde había datos reales para ejercitar el `groupBy` corregido.
- Desplegados los 4 scripts Glue corregidos directamente a S3 (bypass
  deliberado de Terraform) para no arrastrar el reemplazo del zip
  `procesamiento_source`, compartido por ~40 referencias de casi todos los
  jobs Glue del proyecto — aplicar ese `-target` tal cual habría borrado
  la clave S3 vieja del zip mientras el resto de datasets seguían
  apuntando a ella, rompiéndolos en su próxima ejecución.

Detalle completo, decisiones y verificación real en `doc/090-arreglo-gold-
aparcamientos-cartelera-y-bug-fecha.md`.

## Restricciones respetadas

- `terraform apply` real acotado con `-target` solo al Lambda/schedule de
  `cartelera_cines_estrenos` (2 recursos) — el resto del despliegue fue
  fuera de Terraform, deliberadamente, ver doc/090.
- No se aplicó el fix de partition projection de `aforos_peatones_
  bicicletas` (tarea 087, ya escrito, sigue pendiente junto con la
  Prioridad 1).
- Ningún cambio irreversible: solo escritura de datos reales (el objetivo
  del propio dataset) y despliegue de código ya cubierto por 46+ tests
  unitarios en verde.
