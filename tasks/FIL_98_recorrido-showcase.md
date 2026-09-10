---
kind: fil
title: "«El Recorrido» (/tour): una página que hila las 6 capas — de la calle a la respuesta del asistente"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_74, FIL_95, FIL_96, FIL_97]
milestone: "M7"
target: "2026-09-15"
---

## Motivación

Showcase, pieza 4 de 5 (plan «hacer brillar todas las capas», 2026-09-10).

Cada componente brilla por separado (mapa, explorador, chat, ficha de
datos FIL_96, ficha de modelo FIL_97) pero **no hay un solo artefacto que
recorra el sistema entero**. La historia — «un dato entra por la calle y
sale como una respuesta del asistente apoyada en una previsión de ML» —
solo existe como guion de texto (`doc/VIKT-06-recorrido-e2e.md`), nada que
poner en pantalla en la defensa ni en el enlace del portfolio.

## Alcance

### 1. Página `/tour` (`viz/recorrido.html`, generada como el mapa; servida en `/tour` y publicada en gh-pages junto al mapa, FIL_74)

Un scroll narrativo, **«de la calle a la respuesta»**, con 6 paradas = las
6 capas. Cada parada:

1. **La pregunta** que se hace una persona de Madrid (una frase).
2. **El widget que responde**, embebido y vivo cuando se puede:
   - *Datos* → tabla + diagrama de linaje de FIL_96 (iframe a `/datos` o
     su fragmento).
   - *Grafo* → mini-vista del explorador (`grafo_explorador_live.html`) o
     una captura enlazada, con la consulta «un lugar → sus estaciones».
   - *ML* → la curva de skill de FIL_97 (iframe a `/modelo`).
   - *LLM/MCP* → un chat embebido (el del mapa, mismo origen) con la
     **traza de herramientas** de FIL_95 visible.
   - *Rutas* → `ruta_saludable` Sol→Atocha con sana vs rápida y mejor hora.
   - *Mapa* → el mapa animado abierto en un capítulo del tour guiado.
3. **«Cómo funciona»** plegable: qué capa, qué modelo/consulta, qué
   ventana de datos, con enlace al `doc/` correspondiente.
4. Chevron «siguiente».

### 2. `?demo=1` — modo defensa

Con el parámetro, la página **autoavanza** parada a parada con un temporal
razonable y un texto de narración por parada (el guion de la defensa),
pausable. Sirve de espina para el screencast de VIKT-06.

### 3. Sección final «Conéctate al servidor MCP»

Breve: el endpoint `streamable_http` real, cómo lo añade un cliente MCP
(mcp CLI / Claude Desktop), y un asciinema/gif corto de `list_tools` +
una `call_tool` contra la instancia viva. Prueba que es un servidor MCP
de verdad, no un chatbot. (Si el gif no cabe en plazo, dejar el bloque de
instrucciones + enlace a un `doc/` nuevo.)

### 4. Enlaces de entrada

- `web/index.html`: cambiar el enlace del pie («ver el mapa animado») por
  «ver el recorrido completo →» a `/tour` (el mapa cuelga del tour).
- `doc/VIKT-06-recorrido-e2e.md`: añadir al principio «Compañero visual:
  `/tour?demo=1`» y alinear el orden de las 6 paradas con el guion.

## Fuera de alcance

- Reimplementar mapa/explorador/fichas — el tour los **embebe/enlaza**.
- Backend nuevo (todo sale de FIL_95/96/97 y de lo ya servido).
- Narración por voz / vídeo montado (VIKT-06 se encarga del screencast).

## Verificación

- `/tour` recorre las 6 paradas; cada widget carga datos reales (o degrada
  con el mensaje estándar), en móvil (~400 px) y en dark mode, teclado con
  foco visible.
- `/tour?demo=1` autoavanza, se pausa y se reanuda; `prefers-reduced-motion`
  desactiva el autoavance.
- El chat embebido muestra la traza de FIL_95; la curva de FIL_97 y la
  tabla de FIL_96 se ven dentro del tour.
- Publicado en gh-pages con el mapa (FIL_74) y accesible desde la landing.
- Test jsdom: montar la página, comprobar que hay 6 paradas, que `?demo=1`
  arranca el temporizador y que cada iframe tiene `src` válido.

## Prioridad y secuencia

**Alta — es el entregable que amarra la defensa.** Va **después** de
FIL_95 (traza), FIL_96 (datos), FIL_97 (modelo) y FIL_74 (publicar).
Estimación ~1,5–2 días. Objetivo **2026-09-15**.
