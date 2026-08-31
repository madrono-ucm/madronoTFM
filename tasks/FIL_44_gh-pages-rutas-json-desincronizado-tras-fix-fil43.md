---
kind: fil
title: "gh-pages: index.html se republicó con el fix de FIL_43 pero rutas.json quedó con datos viejos -- readout de rutas roto en vivo"
status: done
resolved_at: "2026-08-31"
created_at: "2026-08-31"
source: "QA pass sobre FIL_43 (fix mergeado, PR #214)"
severity: media (roto en el sitio público ahora mismo, arreglo mecánico)
---

## Resolución (2026-08-31) — ya estaba, carrera de despliegue

El ticket se abrió con un snapshot anterior a la republicación de
`gh-pages` (commit `80138df`). El flujo de `FIL_43` **sí** regeneró
`rutas.json` con el código nuevo (`python -m viz.build_mapa_animado`
antes del `cp -r`) — la ventana rota fue entre el merge de PR #214 y
ese push, unos minutos.

Verificado en vivo ahora (`curl https://madrono-ucm.github.io/madronoTFM/rutas.json`):
- `reduccion_exposicion_pct` = `24.4` (**número**, no diccionario).
- `cambio_por_senal_pct` presente: `{traf: 60.0, no2: 16.8, o3: 15.6, noise: 13.5}`.
- `pareto[].reduccion_ponderada_pct` presente.
- El JS del readout E3 recibe un número → sin `[object Object]` ni `undefined`.

(El `Last-Modified` de Pages no refleja bien la republicación, pero el
contenido servido es el correcto.)

## Qué estaba roto (snapshot del ticket)

`FIL_43` (mergeado a `main`, commit `2b8b182`, PR #214) corrigió
correctamente `viz/rutas.py`: verificado que el fix es matemáticamente
sólido (`E_ponderada_sana ≤ E_ponderada_rapida` siempre, por construcción
de Dijkstra — demostrado abajo) y empíricamente correcto (regenerado
`viz/mapa/rutas.json` en local: **0/144 combinaciones negativas, mínimo
+4,3 %**, los 7 tests de `tests/test_rutas.py` en verde).

**Pero el sitio público (`https://madrono-ucm.github.io/madronoTFM/`,
rama `gh-pages`) no se republicó correctamente con el fix**, pese a que
la resolución de `FIL_43` dice explícitamente "republicado a `gh-pages`
(`FIL_42`)":

- `index.html` en vivo **sí** tiene el JS nuevo (post-fix): espera
  `r.cambio_por_senal_pct` (objeto) y `r.reduccion_exposicion_pct` como
  **número**.
- `rutas.json` en vivo **no** se regeneró: sigue con la forma vieja
  (`reduccion_exposicion_pct` como diccionario por señal, sin
  `cambio_por_senal_pct`) — confirmado, `curl` real:
  `{'traf': 74.8, 'no2': 5.4, 'o3': 0.3, 'noise': -3.2}` (incluye un
  valor negativo, el bug original, todavía en producción).
- Los tres ficheros (`index.html`, `rutas.json`, `data.json`) tienen el
  **mismo** `last-modified` (`Mon, 31 Aug 2026 09:25:48 GMT`) — no es un
  problema de caché ni un despliegue a medias en el tiempo: se publicaron
  juntos, pero `rutas.json` se copió sin regenerar primero
  (`python -m viz.rutas` con el código nuevo) antes del `cp -r viz/mapa/.`
  al *worktree* de `gh-pages` (flujo descrito en `FIL_42`, sección "Flujo
  de actualización").

## Por qué importa

El desajuste de forma rompe el JS del readout de rutas en el mapa público
ahora mismo: `` `−${r.reduccion_exposicion_pct}%` `` con
`reduccion_exposicion_pct` siendo un objeto en vez de un número renderiza
literalmente **`−[object Object]%`**, y `` c[k] `` con `c = r.cambio_por_senal_pct
|| {}` siempre da `undefined`, así que cada señal muestra **`+undefined%`**.
Cualquier visitante que abra la capa E3 y seleccione una ruta ve texto
roto, no solo un número posiblemente negativo — peor que el bug que
`FIL_43` corrigió, porque ahora ni siquiera es legible.

## Qué hacer (propuesto, no aplicado aquí)

Ejecutar el flujo de actualización ya documentado en `FIL_42`
("Flujo de actualización"), asegurándose de regenerar `rutas.json` con el
código corregido antes de copiar:

```bash
python -m viz.build_mapa_animado   # o al menos python -m viz.rutas
git worktree add /tmp/ghp gh-pages
cp -r viz/mapa/. /tmp/ghp/ && (cd /tmp/ghp && git add -A && git commit -m "refrescar mapa (FIL_43)" && git push)
git worktree remove /tmp/ghp
```

Verificar después con `curl` (mismo criterio que `FIL_42`) que
`rutas.json` en vivo ya no tiene `reduccion_exposicion_pct` como
diccionario.

## Restricciones

- No se ha tocado la rama `gh-pages` aquí (ticket de solo lectura,
  además `gh-pages` no lleva CI/branch protection de `main` pero tampoco
  es el sitio de este ticket tocarla directamente sin coordinar).
- El código en `main` (`viz/rutas.py`, `viz/mapa/rutas.json`,
  `viz/mapa/index.html`) ya está correcto — este ticket es solo sobre el
  despliegue desincronizado en `gh-pages`.

## Nota aparte — precisión de la resolución de `FIL_43`

La resolución de `FIL_43` también dice que `asistente/ruta_saludable.py`
(la 12.ª tool MCP) "nace ya con la métrica corregida". Verificado: ese
fichero **no existe en `main`** — vive entero en la rama sin mergear
`feat/fil37-tool-mcp` (commits `406cda5`/`04778db`, PR #213 según el
propio mensaje, todavía sin mergear a fecha de esta nota). No es un bug
de código, pero la frase da a entender que la tool ya está en `main`
cuando no lo está — `FIL_37` (`status: in-progress`) ya lo refleja
correctamente, así que no hace falta un ticket aparte, solo se deja
constancia aquí para quien lea `FIL_43` después.

## Criterios de aceptación

- `curl https://madrono-ucm.github.io/madronoTFM/rutas.json` devuelve
  `reduccion_exposicion_pct` como número (no diccionario) y trae
  `cambio_por_senal_pct`.
- Abrir la capa E3 en el sitio público y comprobar visualmente que el
  readout no muestra `[object Object]` ni `undefined`.
