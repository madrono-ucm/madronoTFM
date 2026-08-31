---
kind: fil
title: "Publicar el mapa animado del grafo en GitHub Pages (rama gh-pages dedicada)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: [FIL_34, FIL_35]
milestone: "M4 (hosting)"
target: "2026-09-10"
---

## Resolución (2026-08-31)

- Rama huérfana `gh-pages` creada vía `git worktree add --detach` +
  `git checkout --orphan` (el `--orphan` directo del worktree falla en git
  2.49/Windows) + `git rm -rf .` + `cp -r viz/mapa/. .` + `.nojekyll` +
  `README.md` mínimo → commit `[FIL_42]` → `git push -u origin gh-pages`.
  7 ficheros: `.nojekyll`, `README.md`, `index.html`, `data.json`,
  `meta.json`, `weather.json`, `rutas.json`.
- **Pages ya estaba configurado** a `gh-pages` / `root` (builds previos) —
  no hizo falta tocar Settings. `gh api .../pages` → `status: built`.
- Verificado: `https://madrono-ucm.github.io/madronoTFM/` → 200 `text/html`
  (`<title>Madrid — mapa animado del grafo</title>`); `/data.json`,
  `/meta.json`, `/weather.json`, `/rutas.json` → 200 `application/json`;
  `/.nojekyll` → 200.
- Ediciones post-live (este PR): `viz/PROGRESO_MAPA.md` (URL + M4 ✅),
  `README.md` raíz, `viz/README.md` (ítem "hosted endpoint" ✅).

## Decisión

El mapa animado (`FIL_34`/`FIL_35`) se sirve como HTML estático + JSON. Se
publica en **GitHub Pages desde una rama huérfana `gh-pages`**, no desde
`main`:

- El repo usa `doc/` (no `docs/`) para la memoria → servir Pages desde
  `/docs` en `main` chocaría conceptualmente y arrastraría todo el repo.
- Una rama huérfana `gh-pages` con **solo** el contenido de `viz/mapa/` deja
  el sitio mínimo, sin historia del monorepo, y `main` intacto.
- `viz/mapa/` en `main` **sigue siendo la fuente de verdad**; `gh-pages` es
  un artefacto de despliegue que se regenera.

## Pasos (rama huérfana)

Desde un árbol limpio en `main` (o un `git worktree` aparte si hay trabajo
en vuelo):

```bash
git checkout --orphan gh-pages
git rm -rf .
cp -r viz/mapa/. .           # index.html, meta.json, data.json, weather.json, rutas.json
touch .nojekyll              # OBLIGATORIO — sin esto Pages aplica Jekyll y
                             # puede ignorar ficheros/paths con guion bajo
printf '# Madroño — mapa animado del grafo\n\nDespliegue de `viz/mapa/` (rama `main`). Regenerar: `python -m viz.build_mapa_animado`.\n' > README.md
git add -A
git commit -m "[FIL_42] publicar el mapa animado del grafo en GitHub Pages"
git push -u origin gh-pages
git checkout main
```

Si **Settings → Pages** no apunta ya a `gh-pages` / `root`, hay que fijarlo
a mano (acción del usuario) — el push por sí solo no cambia la config.

## Verificación

```bash
curl -sI https://madrono-ucm.github.io/madronoTFM/            # -> 200
curl -sI https://madrono-ucm.github.io/madronoTFM/data.json   # -> 200
```

El primer despliegue tarda 1-2 min tras el push (workflow
`pages-build-deployment`).

## Flujo de actualización

Cuando cambie el mapa en `main`:

```bash
python -m viz.build_mapa_animado          # regenera viz/mapa/
git worktree add /tmp/ghp gh-pages
cp -r viz/mapa/. /tmp/ghp/ && (cd /tmp/ghp && git add -A && git commit -m "refrescar mapa" && git push)
git worktree remove /tmp/ghp
```

## Ediciones post-live (en un PR normal contra `main`, con CI)

Una vez el sitio responde 200:

- `viz/PROGRESO_MAPA.md` — cabecera: URL publicada + M4 🟡→✅.
- `README.md` raíz, sección "Mapa animado del grafo" — enlace a la URL.
- `viz/README.md` — ítem de encuadre "hosted endpoint" 🟡→✅.
- este ticket → `status: done`.

## Restricciones / notas

- `.nojekyll` es **obligatorio**.
- **No** poner CI de por medio en `gh-pages` (es esperado que no pase los
  checks de `tests`/`terraform` — es contenido, no código). El branch
  protection de `main` no aplica a `gh-pages`.
- `viz/mapa/` en `main` es la fuente de verdad; `gh-pages` no se edita a mano.
- Publicar `data.json` hace que los **slices congelados de Gold de agosto**
  (`FIL_33`/G1) queden indexables públicamente. **Aceptable**: son datos
  municipales abiertos del Ayuntamiento de Madrid (ver `DATA_SOURCES.md`),
  ya reutilizables con atribución.
