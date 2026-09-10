---
kind: fil
title: "Docs: número y tabla de tools generados desde una única fuente (fin del drift «7» vs «19»)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: []
milestone: "M7"
target: "2026-09-12"
---

## Motivación

El número de `tools` del asistente se ha desincronizado ya varias veces
(FIL_29 lo arregló 6→10; FIL_25 hizo lo mismo con el conteo de
productores). Estado a 2026-09-10, sin tocar nada:

- **`asistente/README.md`**: «**Estado (tarea `ML_09`): 7 `tools`, todas
  con lógica real.**» y un párrafo largo que describe el mundo de hace ~12
  tickets (habla de 7 endpoints, no menciona `consulta_grafo`,
  `mejor_hora_zona`, `calidad_aire_cams`, `avisos_meteo`…).
- **`asistente/mcp_agent/server.py`**: `_INSTRUCCIONES` dice «**19 tools**
  con lógica real» y `_ESPERADAS` lista **19**.
- **Tests**: `test_list_tools_expone_las_15` — nombre ya mentiroso.

Cada tool nueva obliga a editar README + el string de `server.py` + varios
asserts de conteo. Es ruido en todos los PR siguientes (FIL_71..FIL_84 lo
han sufrido).

## Relación con FIL_71

FIL_71 crea el **registro único de tools** (código). **Este ticket es la
mitad «documentación» y es independiente del orden**:

- Si FIL_71 llega antes → la tabla se genera desde su registro.
- Si no → se genera desde `_ESPERADAS` de `server.py`, que ya hoy es la
  única lista completa (nombre + título + función).

Hacerlo ya, sin esperar a FIL_71, quita ruido de todos los PR intermedios.

## Alcance

1. **Generador** — `asistente/gen_tabla_tools.py` (módulo ejecutable): a
   partir de `_ESPERADAS` + los routers montados en `asistente/main.py`,
   emite una tabla Markdown `| tool | endpoint HTTP | qué hace (1 línea) |`
   y la inserta entre marcadores `<!-- TOOLS:INI -->` /
   `<!-- TOOLS:FIN -->` en **`asistente/README.md`** y en el
   **`README.md` raíz** (que también cita un número). Flag `--check` que
   sale con código ≠ 0 si el bloque está desactualizado (para CI).
2. **Conteo derivado** — sustituir el literal de `server.py`
   (`"19 tools"`, y el de `_INSTRUCCIONES`) por
   `f"{len(_ESPERADAS)} tools"`. Un único sitio con el número.
3. **Tests** — renombrar `test_list_tools_expone_las_15` →
   `test_list_tools_coincide_con_esperadas`, comparar contra
   `len(_ESPERADAS)` (no un literal). Añadir
   `test_readme_tools_al_dia` que ejecuta el generador en modo `--check`
   (mismo patrón que «el HTML generado está al día» de
   `tests/test_mapa_animado.py`).
4. **Prosa** — corregir en `asistente/README.md` el «7 `tools`» y el
   párrafo de estado `ML_09` para que describa el catálogo actual
   (referenciar los tickets FIL que añadieron cada bloque, sin reescribir
   toda la sección).

## Fuera de alcance

- Crear el registro único de tools en código (FIL_71).
- Cambiar qué hace o cómo se llama ninguna tool.

## Verificación

- `python -m asistente.gen_tabla_tools --check` en verde ahora; en rojo si
  se añade una tool a `_ESPERADAS` y no se regenera.
- `README.md` raíz y `asistente/README.md` muestran las 19 tools con su
  endpoint, generadas, sin edición manual.
- Suite `asistente/` verde; ningún test con un número de tools literal en
  el nombre o en un assert.

## Prioridad

**Alta, hacer primero (con FIL_91).** Trivial (~2-3 h), sin dependencias,
y deja de contaminar el diff de todos los tickets siguientes.
