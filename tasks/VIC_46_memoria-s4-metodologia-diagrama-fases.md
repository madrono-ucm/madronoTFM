---
kind: vic-eval
title: "Memoria — §4 Metodología: verificar Tabla 1 (fases) contra lo realmente ejecutado + diagrama de fases/cronograma"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: []
---

## Contexto

§4.1 describe el diseño general (arquitectura lambda simplificada a solo
ruta fría, el "bucle cerrado" observación→predicción→decisión) y §4.2
anuncia "Tabla 1. Fases del proyecto y entregables asociados" — verificar
si esa tabla existe realmente en el `.docx` con contenido real, o es un
placeholder heredado del borrador de junio (patrón ya visto varias veces
este proyecto: un título de tabla/figura sin el contenido real detrás).

## Alcance

1. Confirmar si Tabla 1 tiene filas reales. Si es un placeholder,
   reconstruirla con las fases reales ejecutadas (no las planeadas en
   junio): puede apoyarse en `PLAN.md` (fases originales) contrastado con
   `PROGRESS.md`/`doc/README.md` (lo que realmente pasó, con fechas) —
   sin inventar fechas, solo las que hay evidencia real (commits, tickets
   con `created_at`).
2. Verificar que §4.1 sigue describiendo fielmente el sistema final: el
   "bucle cerrado" ejemplificado con `calidad_aire_prevista` sigue siendo
   válido, pero ahora hay más ejemplos posibles (p.ej. el explorador del
   grafo en vivo, o el chat con traza de herramientas de `FIL_95`) —
   valorar si merece la pena citar un segundo ejemplo más rico, sin
   sobrecargar el párrafo.
3. **Diagrama**: crear una figura de líneas de tiempo/fases del proyecto
   (Gantt simplificado o cronograma de hitos) usando `graphviz` (ya
   instalado en esta sesión, `dot` + binding Python) o `matplotlib`
   (mismo criterio que las figuras ya existentes de `modelado/grafo_
   analitica/`), basada en fechas reales verificables (primer commit,
   arranque de la ingesta 14/8, congelación 30/8, ronda de QA `VIC_34`-`44`
   10/9, entrega 17/9). Guardar el script generador bajo control de
   versiones (sugerido: `documents/figuras/` como carpeta nueva, o
   `doc/figuras/` — decidir un sitio y documentarlo en el propio script,
   siguiendo el patrón de `modelado/grafo_analitica/analisis.py` de dejar
   el generador junto al resultado). Insertar la imagen en el `.docx`
   junto a la Tabla 1 (o sustituyéndola si tras el punto 1 se decide que
   una figura cuenta la historia mejor que una tabla).

## Fuentes técnicas

`PLAN.md`, `PROGRESS.md`, `doc/README.md`, `git log --oneline --reverse`
del repo para fechas reales de hitos.

## Criterios de aceptación

- Tabla 1 tiene contenido real y verificable, no un placeholder.
- Nueva figura de cronograma insertada (imagen real embebida, mismo
  patrón que `grafo_resiliencia.png` — `python-docx` `run.add_picture`).
- Ninguna fecha inventada; todas trazables a un commit/ticket real.
