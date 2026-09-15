---
kind: vic-eval
title: "Memoria — §7.4–7.5 Limitaciones y futuras líneas: cierre final contra el estado de entrega"
owner: Claude (Memoria)
status: pending
created_at: "2026-09-15"
depends_on: [VIC_49, VIC_50]
---

## Contexto

Esta es la sección que más rápido caduca — cada limitación resuelta por un
`FIL_*` posterior debe moverse o matizarse (patrón ya visto varias veces:
`FIL_16`/`17` pasaron de limitación a resuelto vía `VIKT_11`; `FIL_85`-`90`
igual esta ronda). Con la entrega a 2 días vista, este ticket debe correr
**después** de `VIC_49` (estado del pipeline) y `VIC_50` (explotación),
para no repetir el error de escribir una limitación sobre algo que otro
ticket de esta misma ronda acaba de resolver o de crear.

## Alcance

1. Releer las ~11 limitaciones actuales una a una contra el estado de HOY
   (no de hace 5 días): ¿el alertado sigue parcial? ¿la ventana de
   entrenamiento sigue fija en las mismas fechas o el pipeline se reanudó
   en algún momento entre el 10/9 y hoy (coordinar con `VIC_49`)? ¿la
   autenticación de la web sigue siendo básica?
2. Revisar si alguna limitación quedó obsoleta por el trabajo de
   `FIL_69`-`99` (p.ej. si `FIL_99` "explica esta respuesta" resuelve algo
   que antes era una limitación de explicabilidad del chat).
3. §7.5 (futuras líneas): confirmar que ninguna de las ~11 líneas
   futuras ya se construyó por accidente entre medias (p.ej. si "aplicación
   móvil" seguía en la lista pero alguien ya hizo un PWA, o si el
   explorador del grafo ya cubre parte de lo que se pedía como futuro).
4. Sin diagrama nuevo aquí — es una lista de limitaciones y líneas, no se
   presta a una figura salvo que se decida hacer una matriz visual
   impacto/esfuerzo de las futuras líneas (opcional, solo si sobra tiempo
   real dado el plazo del 17/9 — priorizar corrección de contenido sobre
   esto).

## Fuentes técnicas

Todo `doc/FIL-*` reciente, `NEXT_STEPS.md`, el resultado de `VIC_49` y
`VIC_50` (leer sus tickets cerrados antes de escribir, no en paralelo).

## Criterios de aceptación

- Cada limitación verificada contra el estado real de hoy (15-17/9).
- Ninguna línea futura describe algo ya construido.
- Coordinado explícitamente con `VIC_49`/`VIC_50` (citar sus hallazgos,
  no releer el código por triplicado).
