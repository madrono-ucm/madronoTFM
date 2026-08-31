---
kind: fil
title: "Acceso en lenguaje natural a la capa social (tool `mejor_hora_zona`) + alertas anticipadas por distrito (parcial)"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_45]
---

## Resuelto en parte (2026-08-31) — la pregunta en lenguaje natural, SÍ; el canal de alertas, no

El usuario pidió promover la parte construible. Hecho: **`mejor_hora_zona`,
la 14.ª tool MCP** — responde «tengo asma, ¿cuándo paseo hoy por Vallecas?»
componiendo sustrato que ya existía, sin infra ni entrenamiento nuevo.

- `asistente/mejor_hora_zona.py` (Python puro, reutiliza
  `asistente/ruta_saludable.py` → `grafo_ruta.json`):
  - **Resolución de zona por texto libre a distrito**: nombre exacto,
    `id` (`"13"`), subcadena, y alias coloquiales
    (`vallecas`→ambiguo entre Puente/Villa, `moncloa`→`Moncloa - Aravaca`,
    `san blas`, `el pardo`, `cuatro caminos`→`Tetuán`…). Ambigüedad y zona
    desconocida → `ValueError` con la lista de los 21 distritos.
  - **Barrido «mejor hora hoy»** por distrito + perfil: para cada una de las
    24 h, exposición **media de los nodos del distrito** (tráfico previsto
    STGNN + NO₂ + O₃ + ruido diario), ponderada con los 9 perfiles de
    `FIL_45`/`FIL_37`. Devuelve `mejor_hora`, `peor_hora`, la **franja
    limpia** (racha consecutiva ≤ mín + 20 % del rango), `reduccion_vs_peor_pct`
    y la `serie_horaria` (24 valores).
- `asistente/models/herramientas.py::MejorHoraZona` (+ `nota` con el
  encuadre de `FIL_45`). Tool `mejor_hora_zona(zona, perfil, momento)` en
  `tools.py`; router `GET /mejor-hora-zona`; `server.py` a **14 tools**;
  `main.py` incluye el router. `asistente/tests/test_mejor_hora_zona.py`
  (17). Suite `asistente/` → 162 en verde. `test_mcp_tools.py` /
  `test_mcp_transport.py` a 14.

**Sigue siendo trabajo futuro** (encuadre, sin cambio): el **canal de
notificación** (push/correo/webhook) y la **política de umbral por
distrito** para las *alertas anticipadas*. El asistente sigue siendo
petición-respuesta, sin estado ni suscripción. `mejor_hora_zona` da la
franja limpia bajo demanda; convertir eso en un aviso proactivo cuando la
previsión cruza un umbral OMS/UE necesita las dos piezas de arriba.

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
