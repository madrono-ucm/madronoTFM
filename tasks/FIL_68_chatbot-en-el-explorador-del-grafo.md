---
kind: fil
title: "Chatbot del asistente (Groq + MCP) dentro del explorador del grafo, con eco visual en el mapa"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_62, FIL_67]
milestone: "M7"
target: "2026-09-16"
---

## Qué

Añadir un panel de **chat en lenguaje natural** al explorador del grafo
(`viz/grafo_explorador_live.html`, FIL_67 Parte 3) que hable con el asistente
ya desplegado — Groq + las 15 herramientas MCP, muchas de ellas graph-first
(`consulta_grafo`, `contexto_urbano`, `trafico_cercano`, `ruta_saludable`,
`mejor_hora_zona`…). El usuario pregunta ("¿qué estación de aire cerca de
Retiro mide O₃?", "ruta a pie de Sol a Atocha", "¿qué líneas paran cerca de
Chamberí?") y el LLM decide qué tool(s) llamar contra el grafo/Gold y redacta
la respuesta.

Ya existe el endpoint: `POST /chat {mensaje, historial} -> {respuesta,
historial}` (`asistente/routers/chat.py`, FIL_62/M2). El explorador ya vive
en el mismo servicio FastAPI, así que es una llamada `fetch` a `/chat` desde
la misma página — sin CORS, sin despliegue nuevo.

## Alcance

1. **Panel de chat** en el explorador (`build_grafo_explorador.py`,
   variante `--live`): un cuadro plegable abajo-derecha bajo `#panel` con
   input + hilo de mensajes. Mantiene `historial` entre turnos (lo reenvía
   tal cual, es opaco para el cliente). Estado de "escribiendo…" mientras
   `/chat` responde (puede tardar varios segundos: Groq + tool calls).
2. **Eco visual en el mapa** (lo que lo hace distinto de la landing de
   FIL_62): cuando la respuesta cita entidades del grafo, resaltarlas.
   Opciones, de menos a más:
   - a) parsear ids/nombres conocidos de la prosa de la respuesta y
     hacer `seleccionar(id)` / dibujar la ruta con la maquinaria que ya
     tiene el explorador (`ruta` source, `nodo-sel`, `prox-sel`).
   - b) mejor: que `/chat` devuelva, además de `respuesta`, un bloque
     `contexto` estructurado con los ids/rutas que las tools tocaron
     (`chat.py` ya tiene el resultado tipado de cada tool antes de
     pasárselo a Groq — se puede acumular y devolver). El explorador lo
     pinta sin adivinar. **Recomendada** si hay tiempo; si no, (a).
3. **Preguntas sugeridas**: 4-5 chips de ejemplo que rellenan el input
   (descubribilidad — un mapa con un chat vacío no invita a usarlo).
4. **Endpoint**: reutilizar `POST /chat` tal cual. Si se hace (2b), añadir
   un campo opcional a `RespuestaChat` (`contexto: list[dict] = []`) sin
   romper el contrato existente (la landing de FIL_62 lo ignora).

## Fuera de alcance

- No cambiar el modelo ni el catálogo de tools de Groq (`chat.py`).
- No autenticación nueva (el explorador y `/chat` ya están detrás del mismo
  nginx/CloudFront que el resto, FIL_63).
- No streaming de la respuesta (el SDK de Groq del tier gratuito + el bucle
  de tool-calling no lo ponen fácil; un spinner basta).

## Criterios de aceptación

- Preguntar "¿qué mide la estación de aire más cercana a Retiro?" en el
  chat del explorador devuelve una respuesta coherente que usó
  `consulta_grafo`/`calidad_aire`, y (si 2) la estación queda resaltada en
  el mapa.
- El `historial` se mantiene entre turnos (una repregunta de seguimiento
  funciona).
- Fallo de Groq / de una tool → mensaje de error legible en el hilo, nunca
  la página rota (mismo contrato de degradación que el resto).
- Tests: router `/chat` ya cubierto; añadir un test del panel (jsdom, como
  `viz/test/mapa.test.mjs`) que dispare el envío con `fetch` mockeado y
  compruebe que el hilo se actualiza y no lanza.
- `<script>` generado válido (`node --check`), ids cableados (FIL_57).

## Notas

- La landing+chat de FIL_62 (S3/CloudFront) sigue siendo la puerta
  "producto"; esto es la variante "para explorar los datos", con el mapa al
  lado. Se puede enlazar una a otra.
- Coste: Groq tier gratuito, límite 12.000 TPM — las descripciones cortas
  de tool de `chat.py` ya están pensadas para eso; un chat de explorador de
  uso ocasional no lo mueve.
