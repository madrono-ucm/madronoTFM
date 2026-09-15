---
kind: fil
title: "Chat: hacer visible la capa MCP — traza de herramientas bajo cada respuesta + catálogo «¿qué puedo preguntar?»"
owner: Filippos (interactive)
status: in_review
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_62, FIL_71, FIL_73, FIL_91]
milestone: "M7"
target: "2026-09-12"
---

## Motivación

Showcase, pieza 1 de 5 (plan «hacer brillar todas las capas», 2026-09-10).

El chat de la landing (`web/index.html`) y el del mapa
(`viz/build_mapa_animado.py`) son hoy la **única** ventana a la capa
LLM+MCP, y esa capa es **invisible**: el visitante ve prosa y nunca sabe
que detrás hay 19 herramientas MCP reales, previsiones ONNX y un grafo
Neo4j. Un tribunal que no lo sabe asume «es un chatbot con un prompt».

Dos huecos concretos:

1. **La traza ya viaja y se tira.** `POST /chat` devuelve `historial`, que
   ya contiene los mensajes `role:"assistant"` con `tool_calls` y los
   `role:"tool"` con el payload (`asistente/chat.py`, bucle de rondas). El
   cliente lo guarda y lo reenvía tal cual, sin leerlo. No hace falta
   tocar la orquestación para saber qué herramientas se llamaron.
2. **No hay descubrimiento.** Las 4 sugerencias fijas de la landing tocan
   3 tools. No hay forma de ver la amplitud (aire ahora/previsto/episodio/
   CAMS, tráfico ahora/previsto/grafo, afluencia, aparcamiento, eventos,
   avisos AEMET, meteo, contexto urbano multi-salto, consulta de grafo,
   mejor hora, ruta saludable).

## Alcance

### 1. Campo `pasos` explícito en la respuesta del chat

- `asistente/chat.py`: el bucle ya arma la lista de `tool_calls` por ronda;
  acumular en una lista `pasos` los `{tool, ok, ms, filas}` de cada
  ejecución (reusar lo que `_ejecutar_tool` / los logs de FIL_73 ya
  calculan: `dur_ms`, `ok`, `filas`). `chat()` devuelve
  `{"respuesta", "historial", "pasos"}`.
- `asistente/routers/chat.py`: `RespuestaChat` gana `pasos: list[dict] = []`.
- Sin cambio de contrato para el cliente que no lo use (campo aditivo).

### 2. Render de la traza — landing + mapa

- Bajo cada burbuja del bot, una línea discreta y plegable:
  `🔧 ruta_saludable · trafico_prevista` (los nombres, en orden, sin
  argumentos). Al desplegar: por paso, `ok`/`fallo`, ms y nº de filas.
- Si `pasos` viene vacío (el modelo respondió sin herramientas), **no**
  se pinta la línea — y la respuesta lleva una marca sutil «sin consultar
  datos» para no dar a entender que hubo lectura real.
- Estilo: mismo lenguaje visual que FIL_75/FIL_92 (chip, `:focus-visible`,
  `prefers-reduced-motion`, contraste AA). Nada de framework.

### 3. Catálogo «¿Qué puedo preguntar?»

- Un panel plegable (icono `?` junto al composer) que lista las
  **familias** de herramientas con **un ejemplo real por familia**, una
  por capacidad del sistema. Al pulsar un ejemplo se envía como mensaje.
- La fuente de verdad son `DESCRIPCIONES_CHAT` / `NOMBRES_CHAT`
  (`asistente/mcp_agent/server.py`): generar el catálogo desde ahí en
  build-time (mapa) o servirlo en un endpoint `GET /chat/catalogo` que la
  landing consume — **no** una lista hardcodeada que se desincronice
  (misma lección que FIL_71).
- Sustituye/ą amplía las 4 sugerencias fijas actuales.

## Fuera de alcance

- Cambiar qué herramientas puede llamar el chat, o el modelo/límites
  (FIL_67/latencia).
- Mostrar los **argumentos** o el **payload crudo** de cada tool — eso es
  FIL_99 («Explica esta respuesta»), que se apoya en este campo `pasos`.
- Rediseño del hilo de chat.

## Verificación

- `POST /chat` con «ruta de Sol a Atocha» → `pasos` incluye
  `{"tool":"ruta_saludable","ok":true,...}`; con «hola» → `pasos: []`.
- En la landing y en el mapa, la respuesta a una pregunta real muestra la
  línea `🔧 …` con los nombres correctos y en orden; desplegar da ms/filas.
- El catálogo lista ≥1 ejemplo por capacidad (aire, tráfico, afluencia,
  aparcamiento, eventos, meteo/avisos, grafo, mejor hora, ruta); pulsar
  uno lo envía; añadir una tool a `NOMBRES_CHAT` la hace aparecer sin
  editar el HTML.
- Test jsdom (`viz/test/`): respuesta mock con `pasos` de 2 tools →
  aparece la línea; `pasos: []` → no aparece y sale la marca «sin datos».
- `pytest asistente/` verde; el test HTTP real de FIL_73 comprueba el
  nuevo campo.

## Prioridad y secuencia

**Alta, primero del plan.** Es barato (la traza ya existe en el payload) y
desbloquea los paneles «cómo funciona» de FIL_98 y toda la feature FIL_99.
Después de FIL_71 (registro de tools) y FIL_73 (métricas/logs) — ya en main.
Estimación ~0,5 día. Objetivo **2026-09-12**.

## Hecho (2026-09-11, rama `fil-95-chat-traza-y-catalogo`)

- **Backend — `pasos`**: `asistente/chat.py::chat()` acumula, por turno, la
  lista `pasos` de `{tool, ok, ms, filas}` (una entrada por ejecución real
  de tool, en orden) y la devuelve junto a `respuesta`/`historial`; también
  en las salidas degradadas. `asistente/routers/chat.py`: `RespuestaChat`
  gana `pasos: list[PasoChat] = []` (aditivo; documentado como traza, no
  contrato estable).
- **Backend — catálogo**: `ToolSpec` (registro único, `server.py`) gana
  `ejemplo_chat: str = ""`; las 11 tools con `en_chat=True` llevan un
  ejemplo en lenguaje natural. `CATALOGO_CHAT` derivado + endpoint
  `GET /chat/catalogo`. Una tool nueva en `NOMBRES_CHAT` sin `ejemplo_chat`
  hace fallar el test de guarda.
- **Landing (`web/index.html`)**: bajo cada respuesta del bot,
  `details.traza` plegable — resumen `🔧 tool1 · tool2`, detalle con
  ok/fallo · ms · filas por paso; si `pasos` viene vacío, marca discreta
  «respondido sin consultar datos». Botón `? Qué puedo preguntar` que abre
  un panel con una ficha por tool (título + descripción + ejemplo
  clicable); las sugerencias fijas se sustituyen por las del catálogo al
  cargar (si el endpoint falla, se quedan las estáticas). Delegación de
  eventos (sugerencias dinámicas), `aria-expanded`, `:focus-visible`,
  `prefers-reduced-motion`, tema claro/oscuro.
- **Mapa (`viz/build_mapa_animado.py` → `viz/mapa/index.html`)**: misma
  traza (línea discreta bajo la respuesta) y sugerencias del chat del rail
  alimentadas por `/chat/catalogo` (fallback a las fijas). `viz/mapa/`
  regenerado (solo `index.html`; `meta.json`/`rutas.json` revertidos —
  regenerarlos es FIL_74).
- **Tests**: `asistente/tests/test_chat.py` +`PasosDelTurnoTests` (2 tools
  → 2 pasos con ok/ms/filas; sin tools → `[]`; tool que lanza → `ok:false`)
  y +`CatalogoEndpointTests` (una entrada por tool del chat, todas con
  ejemplo). `viz/test/web-landing.test.mjs` +4 (traza pintada, marca «sin
  datos», catálogo llena sugerencias + panel abre/cierra, endpoint caído →
  sugerencias fijas). `pytest asistente/ tests/test_mapa_animado.py` →
  283 pass / 1 skip; `node --test viz/test/` → 29 pass.

Pendiente: PR, merge, redeploy EC2, y flip de `status` a `done`.
