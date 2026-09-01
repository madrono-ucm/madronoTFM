# Estilo de comentarios y docstrings

Estándar del proyecto para que los comentarios sean útiles en producción y
no ruido. Se aplica en la pasada de `FIL_59` (módulo a módulo) y a todo el
código nuevo a partir de entonces.

## Principios

1. **Idioma: español.** Todo el repo está en español; no se mezcla.
2. **El comentario explica el *porqué*, no el *qué*.** Si el comentario
   parafrasea la línea siguiente, sobra. Se comenta lo que el código no
   puede decir por sí mismo: una decisión, un supuesto, una restricción
   externa, un caso límite, el motivo de un valor "mágico".
3. **Frases completas.** Mayúscula inicial, punto final. Nada de notas
   telegráficas ("hack", "ojo", "temp").
4. **Cero código muerto.** No se deja código comentado "por si acaso" —
   para eso está git. Un `TODO` sin dueño ni ticket se convierte en
   ticket o se borra.
5. **Sin referencias a herramientas internas en artefactos publicados.**
   Los números de ticket (`FIL_45`, `VIC_12`…) son procedencia útil y se
   **mantienen en el código fuente** (`.py`, `.tf`, `build_*.py`), pero se
   **eliminan de cualquier fichero que se sirva al público** — en concreto
   los comentarios del `<script>`/`<style>` del `index.html` del mapa
   (rama `gh-pages`). Ahí el comentario tiene que ser autocontenido.

## Docstrings (Python)

- **Módulo**: primera línea = qué hace y su papel en el sistema, no un
  título. Si el módulo produce artefactos, listarlos. Si tiene efectos
  (red, credenciales, escritura), decirlo.
- **Función/clase no trivial**: una o dos frases — qué recibe, qué
  devuelve, invariantes o efectos. Formato libre (no hace falta
  `Args:`/`Returns:` salvo que el módulo ya lo use).
- **Función trivial** (getter, glue de una línea, `__repr__`): sin
  docstring.
- **Tests**: docstring solo si el nombre no basta para saber qué escenario
  cubre y por qué importa.

## Comentarios inline (Python / JS / HCL)

- Encima de la línea o el bloque que explican, no al final salvo que sean
  muy cortos y encajen.
- Un bloque de lógica no obvia (una fórmula, un orden de operaciones que
  importa, un workaround de una librería) lleva 1-3 líneas de contexto
  encima.
- Los números "mágicos" con significado (umbrales, factores de escala,
  tiempos) llevan comentario con la unidad y la razón.

## Lo que NO se hace en una pasada de comentarios

- **Cero cambios de comportamiento.** Si al documentar aparece un bug o
  una simplificación clara, va a un ticket aparte; no se toca en el PR de
  comentarios.
- No renombrar identificadores ni reordenar código.
- No traducir a inglés.

## Enganche opcional en `ruff`

Si en algún momento se añade config de `ruff`, activar un subconjunto de
`pydocstyle` coherente con lo de arriba (p. ej. `D209`, `D210`, `D300`,
`D403`; **no** `D1xx`, que exige docstring en todo) y arreglar lo que
marque.
