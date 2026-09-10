---
kind: fil
title: "«Explica esta respuesta»: la cadena completa datos→grafo→ML→LLM sobre una pregunta real, a un clic"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_73, FIL_95]
milestone: "M7"
target: "2026-09-16"
---

## Motivación

Showcase, pieza 5 de 5 y **feature nueva estrella** (plan «hacer brillar
todas las capas», 2026-09-10).

FIL_95 muestra *qué* herramientas se llamaron. Esto muestra *cómo encaja
todo*: en cualquier respuesta del chat, un botón **«Explica esta
respuesta»** despliega la cadena entera sobre esa pregunta concreta:

```
pregunta del usuario
  → herramientas llamadas (con sus argumentos)
    → payload crudo de cada tool (valor + versión de modelo + ventana de datos)
      → cómo el LLM lo convirtió en la prosa que se ve
```

Un clic y se ven las 4 capas cooperando sobre una pregunta de verdad. Es
el momento más contundente para la defensa y reutiliza datos que **ya
están** en el `historial` de la respuesta.

## Alcance

### 1. Backend — exponer el detalle (aditivo sobre FIL_95)

- `asistente/chat.py`: `pasos` de FIL_95 se enriquece por paso con
  `args` (los argumentos con los que se llamó) y `resultado` (el objeto
  que devolvió `_ejecutar_tool`: `disponible`, `motivo`, `datos`, y los
  campos de envoltorio — versión de modelo, ventana de datos, fiabilidad —
  cuando la tool los trae).
- Payloads potencialmente grandes: recortar `datos` a un tope (p. ej.
  primeras N filas + `filas_totales`) para no inflar la respuesta.
- `RespuestaChat`: `pasos` ya existe (FIL_95); solo cambia su forma
  interna. Documentar en el docstring del router que es material de
  depuración/explicación, no contrato estable.
- **Sin** segundo viaje al LLM y **sin** re-ejecutar tools: todo sale de
  lo que ya se calculó en el turno.

### 2. Frontend — el panel «Explica esta respuesta»

- Botón discreto en cada burbuja del bot (junto a la línea de traza de
  FIL_95). Al pulsarlo, un panel plegable **dentro del hilo** con:
  - la pregunta tal cual;
  - por herramienta: nombre, argumentos (formateados), y el payload en un
    bloque legible con `disponible`/`motivo` resaltados y los campos de
    envoltorio (modelo, ventana, fiabilidad) destacados;
  - una nota final: «el asistente redactó la respuesta a partir de estos
    resultados; no añade cifras que no estén aquí» (enlaza al
    `_SYSTEM_PROMPT` endurecido en `doc/`).
- Si `pasos` está vacío: el botón explica «esta respuesta no consultó
  datos» en vez de abrir el panel.
- Landing (`web/index.html`) y mapa (`viz/build_mapa_animado.py`), mismo
  componente. `:focus-visible`, `prefers-reduced-motion`, contraste AA.

### 3. Enganche con el tour

La parada «LLM/MCP» de FIL_98 usa este panel abierto como su widget
principal (una pregunta preparada con su cadena desplegada).

## Fuera de alcance

- Editar/re-lanzar la consulta desde el panel (solo lectura).
- Mostrar los tokens/prompt íntegros del LLM — se muestra el
  comportamiento (entra payload, sale prosa fiel), no el prompt completo.
- Cambiar la orquestación o el modelo.

## Verificación

- «¿Cómo está el aire en Retiro y me conviene salir a correr?» → el panel
  muestra `calidad_aire` y/o `calidad_aire_prevista` con sus args, el
  payload con µg/m³ + versión de modelo ONNX + ventana de datos, y la
  respuesta en prosa no contiene ninguna cifra que no esté en el payload.
- Pregunta con tool en fallo (`disponible:false`) → el panel muestra el
  `motivo` y la prosa lo refleja (no inventa) — comprueba el endurecimiento
  del prompt de forma visible.
- `pasos` vacío → el botón da el mensaje corto, no abre panel.
- El recorte de `datos` mantiene la respuesta por debajo de un tamaño
  razonable con una consulta que devuelve muchas filas.
- Test: `TestClient` /chat afirmando la forma de `pasos` (args + resultado
  + recorte); jsdom para abrir/cerrar el panel y el caso vacío.
- `pytest asistente/` verde.

## Prioridad y secuencia

**Alta si hay plazo; es el «wow» de la defensa.** Depende de FIL_95
(estructura `pasos`) y FIL_73 (envoltorio/logs). Va antes o en paralelo a
FIL_98, que lo consume. Estimación ~1–1,5 días. Objetivo **2026-09-16**.
Si el plazo aprieta, entra después de FIL_98 y el tour usa mientras la
traza simple de FIL_95.
