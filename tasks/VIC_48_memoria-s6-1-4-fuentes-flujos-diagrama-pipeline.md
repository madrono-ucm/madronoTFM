---
kind: vic-eval
title: "Memoria — §6.1–6.4 Fuentes, preparación, flujos, procesamiento: verificación + diagrama de pipeline Bronze→Silver→Gold"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: []
---

## Contexto

`VIC_02` (29/8) reescribió estas subsecciones a la arquitectura real. Desde
entonces el número de fuentes/atributos del grafo ha cambiado (`FIL_65`/
`66`/`67`), pero §6.1-6.4 describen las *fuentes de datos y su
procesamiento*, no el grafo (eso es §6.6/§6.7, ya cubierto por `VIC_38`) —
el riesgo aquí es más de **cifras desactualizadas** (nº de fuentes, cuáles
están en producción continua) que de arquitectura equivocada.

## Alcance

1. Recontar fuentes reales: `DATA_SOURCES.md`, `ingesta/capturas/` (un
   módulo por fuente), `infra/terraform/` (schedules reales). Confirmar
   si sigue siendo "24 fuentes (16 en producción continua)" o cambió.
2. Verificar §6.2 (preparación): la puerta de calidad Great Expectations,
   el manejo de valores ausentes/inconsistencias — sigue describiendo el
   proceso real, sin cambios esperados aquí, pero confirmar que ningún
   dataset nuevo (si lo hay) rompe la generalización.
3. Verificar §6.3/§6.4 (flujos/procesamiento): el flujo Lambda→Bronze→
   Glue→Silver→Gold sigue siendo el único real (sin ruta caliente) —
   confirmar que ninguno de los tickets `FIL_69`-`99` introdujo
   procesamiento en streaming o un componente nuevo en esta ruta (parece
   improbable dado que son todos de la capa de explotación, pero
   verificar en vez de asumir).
4. **Diagrama**: un diagrama de flujo Bronze→Silver→Gold genérico
   (aplicable a cualquier fuente), con las puertas de calidad marcadas,
   usando `graphviz` (mismo criterio que `VIC_47`, reutilizar el módulo/
   carpeta de figuras que cree ese ticket si ya existe — coordinar orden
   de ejecución, o crear la carpeta aquí si `VIC_47` no ha corrido
   todavía). Un segundo diagrama opcional: línea temporal de cuándo entró
   en producción cada fuente (si los datos de fecha son fiables via
   `doc/NNN-captura-*.md`), solo si aporta valor real y no es redundante
   con la figura de fases de `VIC_46`.

## Fuentes técnicas

`DATA_SOURCES.md`, `ingesta/README.md`, `procesamiento/README.md`,
`doc/002`-`doc/024` (capturas), `doc/025`-`doc/040` (bronzewriter/
productores).

## Criterios de aceptación

- Cifras de fuentes/producción continua verificadas contra el repo real.
- Diagrama de flujo Bronze→Silver→Gold insertado, con puertas de calidad
  marcadas.
- Sin afirmaciones sobre streaming/ruta caliente que no sean ciertas.
