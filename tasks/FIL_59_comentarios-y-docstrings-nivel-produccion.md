---
kind: fil
title: "Higiene de comentarios y docstrings a nivel de producción — pasada por todo el código, módulo a módulo"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
depends_on: []
---

## Contexto

Petición del usuario: dejar los comentarios del código "profesionales y
listos para producción". El repo tiene ~40k líneas de Python en 231
módulos (+ el JS del mapa + Terraform), con comentarios muy desiguales:
notas telegráficas, referencias a tickets como `# FIL_45` sin contexto,
comentarios que ya no describen el código, y `index.html` **publicado**
con números de ticket internos visibles en "ver código fuente".

No hay guía de estilo ni reglas de docstring en `pyproject`/`ruff`.

## Estándar (parte de este ticket definirlo y dejarlo escrito)

- **Idioma: español** (coherente con todo el repo).
- Cada módulo: docstring de módulo que diga *qué hace y su papel en el
  sistema*, no un título.
- Funciones no triviales: docstring de una o dos frases (qué recibe, qué
  devuelve, invariantes). Las triviales (getters, glue) no necesitan.
- Comentarios inline: frases completas que expliquen **el porqué**, no el
  qué. Nada de comentarios que repiten la línea siguiente.
- Referencias a tickets: **se mantienen en el código fuente** (`.py`,
  `build_*.py`) como procedencia útil; **se eliminan de artefactos
  públicos** — en concreto, quitar los `// FIL_NN:` del `_TEMPLATE` del
  mapa (el `index.html` de `gh-pages`) y sustituirlos por la explicación
  autocontenida.
- Nada de comentarios muertos (código comentado, TODOs sin dueño ni
  fecha, "arreglar esto").
- Recoger el estándar en `doc/ESTILO-COMENTARIOS.md` (o una sección de
  `README.md`); si tiene sentido, activar en `ruff` un subconjunto de
  `pydocstyle` (D2xx/D4xx) acorde y arreglar lo que marque.

## Ejecución — módulo a módulo, un PR por lote

Cada PR: un área coherente, diff solo de comentarios/docstrings (cero
cambios de comportamiento), tests en verde antes y después. Orden
sugerido por valor (lo más visible / lo más leído primero):

- [x] **`viz/`** — `build_mapa_animado.py` (+ `_TEMPLATE` → strip `FIL_NN`
      del `index.html` público), `rutas.py`, `build_grafo_*.py`,
      `export_gold_slices.py`, `build_prevision_animada.py`.  *(lote 1)*
- [x] **`asistente/`** — ya estaba a nivel producción; solo se reescribió
      la primera línea del docstring de `contexto_urbano.py` /
      `mejor_hora_zona.py` / `ruta_saludable.py` (lideraban con `FIL_NN —`).
      El resto de comentarios explican el porqué y son frases completas.  *(lote 2)*
- [x] **`modelado/`** — ya a nivel producción; solo se reescribió el
      docstring de `grafo_analitica/analisis.py` (lideraba con `FIL_52`).
- [x] **`ingesta/`** — ya a nivel producción; los 26 `capturas/*.py`
      lideran con "Productor/Captura/Carga de …", refs a ticket al final.
      Nada que tocar.
- [x] **`procesamiento/`** — ya a nivel producción; los ~90 ficheros de
      `silver_gold/` siguen el mismo patrón consistente ("Job de AWS
      Glue: …", "Agregación Silver → Gold: …", "Puerta de calidad GE: …").
      Nada que tocar.
- [x] **`grafo/`** — ya a nivel producción; solo se reescribió el
      docstring de `exportar_grafo.py` (lideraba con `FIL_51`).
- [x] **`herramientas/`** — ya a nivel producción. Nada que tocar.
- [x] **`infra/terraform/`** — los comentarios `.tf` que llevan prefijo
      `# FIL_NN` son frases completas que explican el *porqué* (retiradas
      de Google Maps, PATH de SSM en vez del valor, cadencias). El prefijo
      es procedencia y **se conserva** (no es artefacto publicado). Cero
      `TODO`/`FIXME`/`HACK`. Nada que tocar.
- [x] **`tests/`** — los comentarios existentes ya explican el *porqué*
      del caso (mocks, escenarios límite). Nada que tocar.

Marcar cada casilla en el PR que la cierra.

## Cierre (2026-09-01)

La pasada por todo el código encontró que **el resto del repo ya estaba a
nivel de producción**: comentarios que explican el porqué, frases
completas, cero código muerto, refs a ticket en paréntesis al final del
docstring. El trabajo real de `FIL_59` fue:

1. **`viz/`** (lote 1) — el módulo más flojo: docstrings reescritos +
   comentarios inline mejorados + **quitados los `// FIL_NN` del
   `_TEMPLATE`** (el `index.html` publicado en `gh-pages`), que es el único
   artefacto que se sirve al público.
2. **7 docstrings** en 6 módulos (`asistente/` ×3, `viz/` ×n, `grafo/` ×1,
   `modelado/` ×1) que lideraban con `FIL_NN —` en vez de con el propósito.
3. `doc/ESTILO-COMENTARIOS.md` — el estándar, para el código nuevo.

## Criterios de aceptación

- `doc/ESTILO-COMENTARIOS.md` escrito y enlazado desde el README.
- Cada lote: PR con diff exclusivamente de comentarios/docstrings, CI en
  verde, revisado.
- `viz/mapa/index.html` publicado sin `FIL_NN` en los comentarios (los
  `.py` los conservan).
- Al terminar todos los lotes, este ticket → `done`.

## Restricciones

- **Cero cambios de comportamiento.** Si al comentar se descubre un bug,
  va a un `FIL_*` aparte, no se arregla en el PR de comentarios.
- No traducir a inglés (el resto del repo es español).
- No borrar procedencia útil del código fuente por "limpieza" — solo de
  los artefactos publicados.
