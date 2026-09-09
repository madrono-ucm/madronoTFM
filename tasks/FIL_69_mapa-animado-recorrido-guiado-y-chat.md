---
kind: fil
title: "Mapa animado: recorrido guiado (storytelling), rutas céntricas y chat con el asistente (MCP)"
owner: Filippos (interactive)
status: in_review
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_34, FIL_37, FIL_62, FIL_64, FIL_66]
milestone: "M7"
target: "2026-09-16"
---

## Motivación

El mapa animado (`viz/mapa/`) ya tenía días, hora, capas de color, rutas y
pulso de distrito, pero varias funciones estaban escondidas tras paneles
colapsados y no había un hilo narrativo. A petición del usuario: "important
insights and interactive ways to tell the story", "ver los días / cómo
cambian las métricas / las rutas", y "explorar todos los datos vía el
servidor MCP".

## Hecho

### 1. Recorrido guiado (`📖 Historia`)

Grupo nuevo, abierto por defecto, con **6 capítulos**. Cada uno pone el mapa
en el estado que ilustra un hallazgo (`setEstado()` sincroniza `state` +
todos los controles del DOM + `render()`):

1. **El modelo mejora la persistencia** — `trafico` + «modelo vs
   persistencia (E2)», horizonte h3.
2. **El aire depende de la hora** — dosis O₃, bandas OMS/UE, hora 16; botón
   «▶ animar» recorre las 24 h.
3. **Laborable vs domingo** — el mismo O₃ el 08-23 (domingo).
4. **Ruta saludable vs rápida** — Sol → Atocha, perfil ciclista: ~27 % menos
   exposición ponderada frente a la ruta más corta.
5. **La ruta cambia con quién eres** — misma ruta, perfil general.
6. **Hallazgos del grafo real (Neo4j)** — tarjeta con los números de
   `FIL_64`/`FIL_66` (683 puntos de articulación, 96 % de sensores de
   tráfico sin aire a ≤300 m, sesgo Fuencarral 544 / Vicálvaro 62) y
   remite a `grafo_explorador.html` / `/grafo/explorador`.

Botones ◀ / ▶ para navegar y «▶ animar» (reutiliza `tick()`).

### 2. Rutas céntricas reconocibles

`viz/rutas.py`: `LUGARES` += Callao, Gran Vía, Gregorio Marañón (eje
Castellana). `ejemplos` (5 rutas) ahora: **Callao→Retiro, Cibeles→Plaza
Castilla, Sol→Atocha, Atocha→Moncloa, Plaza Elíptica→Cibeles**. Reducción de
exposición por ruta 0–29 %. Regenerados `viz/mapa/rutas.json` (+
`asistente/modelos/grafo_ruta.json`, compartido con `ruta_saludable` /
`mejor_hora_zona` — ganan 3 lugares de referencia).

### 3. Chat con el asistente (`💬 Preguntar a los datos`)

Grupo nuevo: input + hilo + 4 sugerencias. `POST {API_BASE}/chat
{mensaje, historial}` → `{respuesta, historial}` — el `/chat` ya existente
(Groq + las 15 herramientas MCP, muchas graph-first). `API_BASE` = `?api=`
de la URL, o `https://35-42-164-183.nip.io` si se sirve desde `github.io`,
o `""` (mismo origen) si se sirve desde el propio asistente. Degradación:
fallo → mensaje de error en el hilo, nunca la página rota.

Esto **cierra el grueso de `FIL_68`** para el mapa animado; `FIL_68` queda
solo para el eco visual (resaltar en el mapa las entidades que las tools
tocaron), opcional.

## Verificación

- `viz/test/mapa.test.mjs` (jsdom): +clic a los 6 capítulos, ◀/▶/animar y
  las sugerencias del chat → 0 excepciones; `<script>` válido; ids
  cableados. 3/3 verde.
- `tests/test_mapa_animado.py` actualizado (17 hitos). `tests/test_rutas.py`
  verde. `asistente/tests/test_ruta_saludable.py` + `test_mejor_hora_zona`
  verde con el `grafo_ruta.json` nuevo.
- Playwright (Chromium real): capítulos cambian `state` y sincronizan los
  selects; ruta Sol→Atocha se dibuja; 0 errores de página.

## Pendiente / notas

- El chat necesita el asistente accesible desde el navegador; con la página
  en `gh-pages` apunta a la EC2 (CORS `*` ya configurado, `FIL_62`).
- `FIL_68` (eco visual del chat en el mapa) sigue abierto como mejora.
- Refrescar `gh-pages` con el flujo de `FIL_42` para publicar el recorrido.
