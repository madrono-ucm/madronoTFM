---
kind: vic-eval
title: "Evaluación técnica ronda 3 — consistencia final del conteo de tools (10, no 9)"
owner: Claude (QA)
status: done
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-3.md`](../doc/PLAN-EVALUACION-TECNICA-3.md).
Ningún cambio de código; fixes de documentación propia (no `documents/Memoria_TFM FV.docx`)
sí se pueden aplicar directamente si son triviales.

## Alcance

`FIL_26` (STGNN como 10.ª tool) aterrizó después de que `doc/VIKT-06/07/09/10.md`
se escribieran citando "9 tools" — ya se corrigió el encuadre del STGNN en
`07`/`09`/`10`, pero no se ha revisado si el **número** en sí (9→10) quedó
actualizado en todos los sitios. Ya confirmado (antes de crear este
ticket): `doc/VIKT-06-recorrido-e2e.md` todavía dice "9 tools" en dos
sitios.

- Grep de "9 tools"/"nueve tools"/"nueve herramientas" en `doc/VIKT-06/07/09/10.md`,
  `asistente/README.md`, `README.md` raíz — corregir cada uno a 10 con el
  nombre de la 10.ª tool (`calidad_aire_prevista_grafo`).
- Confirmar en vivo (`ClientSession` real, no solo grep) que siguen siendo
  exactamente 10 antes de dar el número por bueno.
- Revisar si `doc/VIKT-06-recorrido-e2e.md` §4 necesita una entrada nueva
  para la 10.ª tool (el notebook demo sí la tiene, el guion de la defensa
  también debería mencionarla si es relevante para la demo).

## Criterios de aceptación

- Cero menciones de "9 tools" en documentación que describe el estado
  actual (no en changelogs/históricos, esos se dejan).
- Verificado en vivo que son 10, no una suposición de que "ya se corrigió
  antes".

## Hecho (30/8)

**Nota**: este ticket se ejecutó por duplicado en paralelo (esta sesión y
otra, casi al mismo tiempo) — conflicto de fusión real resuelto
combinando ambos resultados, que coincidían en lo esencial.

Verificado en vivo primero (`ClientSession`/`mcp.list_tools()` sobre el
servidor real): exactamente **10** —
`afluencia_estimada, afluencia_prevista, calidad_aire, calidad_aire_prevista,
calidad_aire_prevista_grafo, disponibilidad_aparcamiento, eventos_cercanos,
opciones_movilidad, trafico_cercano, trafico_prevista`.

Corregidos los documentos vivos con "9 tools" desactualizado:
- `README.md` raíz: nodo Mermaid + fila de layout de `asistente/`.
- `doc/VIKT-06-recorrido-e2e.md`: §4.1, la "salida real" de un comando
  reproducible (corregida para que quien siga la guía hoy vea lo mismo
  que describe el documento, con la 10.ª tool en la lista), la nota de
  `FIL_24` actualizada de "hallazgo abierto" a "resuelto", y el guion del
  screencast.

Ya estaban correctos: `asistente/README.md` (`FIL_29`),
`doc/VIKT-07/09/10.md` (correcciones ya aplicadas tras `FIL_20`/`26`).
Dejados sin tocar a propósito: `doc/VIKT-09-consistencia-final.md:108`
("7 tools") es un changelog de una corrección anterior, no una afirmación
de estado actual; `doc/VIC-16-eval-asistente-v2.md` es un registro
fechado de una evaluación puntual (30/8, antes de `FIL_26`), no un
documento vivo.
