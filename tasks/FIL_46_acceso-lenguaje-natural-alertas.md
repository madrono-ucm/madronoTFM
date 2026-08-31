---
kind: fil
title: "Acceso en lenguaje natural a la capa social + alertas anticipadas por distrito (ENCUADRE)"
owner: Filippos (interactive)
status: framing
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_45]
---

## Qué es

**Trabajo futuro, no implementado.** Este ticket existe para que la memoria
lo cite con precisión: describe qué se podría construir sobre el sustrato
que ya hay y qué es exactamente lo que falta.

## La idea

El asistente MCP respondiendo a preguntas del tipo:

> «Tengo asma, ¿cuándo puedo pasear hoy por Vallecas?»

**componiendo tools que ya existen** más el perfil de sensibilidad de
`FIL_45`:

1. `calidad_aire_prevista_grafo` (`FIL_26`) → previsión por nodo del
   distrito indicado.
2. El barrido **"mejor hora hoy"** de `FIL_45` (mínimo de exposición
   ponderada en las 24 h).
3. El perfil **`asma_epoc`** (mismo dict de pesos que `ruta_saludable`) para
   ponderar NO₂/O₃ como más dañinos.

Respuesta: la franja horaria del día con el aire más limpio en esa zona
para ese perfil, con el encuadre de `FIL_45` (previsión, no consejo médico).

## Alertas anticipadas por distrito

Concepto: cuando la previsión (STGNN de grafo) cruza un umbral OMS/UE para
un distrito en las próximas N horas, se emite un aviso. Anticipada porque
usa la previsión, no la medición actual.

## Qué falta (esto es lo que la memoria debe decir)

El **sustrato existe**: los modelos de previsión, el barrido de mejor hora,
los perfiles, los umbrales. Lo que **no** existe:

- Un **canal de notificación** (push / correo / webhook) — hoy el asistente
  es petición-respuesta, no hay estado ni suscripción.
- Una **política de umbral por distrito**: qué banda dispara aviso, con qué
  antelación, con qué frecuencia máxima, quién la define.
- Resolución de zona por texto libre a distrito (hoy los lugares son 14
  referencias fijas en `viz/rutas.py`; el asistente resuelve `:Lugar` del
  grafo, no "Vallecas" como distrito).

## Coste

Cero — no se construye nada aquí.

## Entregable / progreso

Fila de encuadre en `viz/PROGRESO_MAPA.md`. Se cita en `FIL_36`
(memoria, sección "Beneficiarios" y trabajo futuro).
