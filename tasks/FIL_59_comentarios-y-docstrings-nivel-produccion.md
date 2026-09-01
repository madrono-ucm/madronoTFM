---
kind: fil
title: "Higiene de comentarios y docstrings a nivel de producción — pasada por todo el código, módulo a módulo"
owner: Filippos (interactive)
status: in_progress
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
- [ ] `modelado/` — features, training, evaluation, export, estudios.
- [ ] `ingesta/` — `capturas/`, `BronzeWriter`, `secretos.py`.
- [ ] `procesamiento/` — `silver_gold/`, suites GE.
- [ ] `grafo/` — `relaciones.py`, `geo.py`, `cargar_grafo.py`.
- [ ] `herramientas/` — `salud/`, utilidades.
- [ ] `infra/terraform/` — comentarios `.tf` (menos densos, pero
      `lambda.tf`/`glue_scheduling.tf` tienen bloques que valen).
- [ ] `tests/` — solo donde el comentario explique el *porqué* del caso.

Marcar cada casilla en el PR que la cierra.

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
