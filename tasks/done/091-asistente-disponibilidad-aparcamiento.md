---
id: 91
slug: asistente-disponibilidad-aparcamiento
title: 'Asistente: implementar disponibilidad_aparcamiento (Prioridad 4, desbloqueada por la tarea 090)'
status: done
force: false
allow_infra_apply: false
branch: task/091-asistente-disponibilidad-aparcamiento
pr_number: 135
pr_url: 'https://github.com/madrono-ucm/madronoTFM/pull/135'
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: '2026-08-26T12:30:00Z'
started_at: '2026-08-26T12:15:00Z'
submitted_at: '2026-08-26T12:30:00Z'
merged_at: null
---

## Contexto

La tarea 090 verificó que Gold de `aparcamientos` ya tiene datos reales
(el bug de `doc/052` estaba resuelto sin que nadie lo hubiera comprobado) —
eso desbloquea `disponibilidad_aparcamiento`, la `tool` del asistente que
hasta ahora levantaba `NotImplementedError` (`asistente/README.md`,
Prioridad 4 de `NEXT_STEPS.md`). Implementa esta `tool` de extremo a
extremo, mismo patrón que `calidad_aire` (tarea 079): una sola tabla Gold
vía Athena, sin grafo.

## Qué se hizo

`_disponibilidad_aparcamiento_impl` (Athena real sobre
`gold.aparcamientos_por_parking_hora`, resolución de `zona` por
coincidencia de texto) + router HTTP + registro + 10 tests nuevos
(mockeando Athena). A diferencia de `calidad_aire` (peor caso entre
estaciones coincidentes), varios aparcamientos que coinciden con `zona`
representan capacidad real y aditiva — se suman.

Verificado en vivo contra AWS real (`uvicorn` local + cuenta AWS del
proyecto): `Plaza de Oriente` → 189/212 plazas, `Santo Domingo` → 266/333
— mismos valores exactos que las filas reales de Gold verificadas por
separado en la tarea 090.

Detalle completo en `doc/091-asistente-disponibilidad-aparcamiento.md`.

## Restricciones respetadas

- Ningún cambio de infraestructura Terraform (se pospone hasta que se
  decida desplegar de verdad, mismo criterio que las tareas 044/079).
- No se ha tocado `opciones_movilidad`/`eventos_cercanos`.
