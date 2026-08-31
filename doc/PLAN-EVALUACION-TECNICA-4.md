# Plan de evaluación técnica — ronda 4 (análisis estático, primera vez)

**Fecha:** 2026-08-30 · **Contexto:** las rondas 1–3 (`VIC_08`–`24`,
`doc/PLAN-EVALUACION-TECNICA{,-2,-3}.md`) verificaron el sistema
exhaustivamente en vivo — ejecución real, datos reales, tests reales.
Ninguna tocó **análisis estático**: no hay `ruff`/`mypy`/`bandit`/`pip-audit`
configurados en el repo ni en CI (verificado: `pyproject.toml`,
`setup.cfg`, `ruff.toml`, `.github/workflows/ci.yml` — ninguno los
menciona). Dado que no ha aterrizado ningún cambio en el repo desde que
cerró la ronda 3 (`git log` sin commits nuevos), esta ronda 4 se centra en
esa herramienta distinta en vez de repetir verificación funcional ya
hecha tres veces.

## Tickets

| # | Ticket | Alcance |
|---|---|---|
| `VIC_25` | Lint estático con `ruff` sobre todo el código Python | Bugs reales de lógica (variables sin usar, comparaciones sospechosas, imports rotos), no solo estilo |
| `VIC_26` | Análisis de seguridad estático con `bandit` | Complementa la auditoría manual de `VIC_19` con un escáner automático — puede encontrar patrones que un grep no cubre |
| `VIC_27` | Vulnerabilidades conocidas en dependencias con `pip-audit` | `VIC_19` hizo una revisión "rápida, no exhaustiva" de dependencias — esta pasada usa la base de datos real de CVEs |

Sin cambios de código en ningún ticket (`ruff`/`bandit`/`pip-audit` son de
solo lectura); hallazgos reales → `FIL_*` nuevo (numeración siguiente:
**31**). Herramientas instaladas en el `.venv` compartido de esta EC2,
solo para esta auditoría — no se añaden a `requirements.txt` sin que un
`FIL_*` lo proponga primero.

## Cierre (30/8) — 3/3 completados

- `VIC_25` (ruff): 1237 hallazgos, prácticamente todos estilo/tipado nunca
  aplicado; cada categoría con potencial de bug real triada a mano →
  ningún `FIL_*`.
- `VIC_26` (bandit): 42 hallazgos; el de mayor volumen (`B608` SQL
  injection, 22 casos) resultó falso positivo en el 100% (el proyecto ya
  escapa con `sql_literal()`); el parseo XML sin `defusedxml` sí era real
  → `FIL_31` (renumerado a **`FIL_41`** el 31/8, ver nota de cierre más
  abajo).
- `VIC_27` (pip-audit): 3 CVEs reales, todos en dependencias transitivas
  sin ruta de explotación real en este proyecto, bump recomendado por
  higiene → `FIL_32` (renumerado a **`FIL_39`** el 30/8 tras aterrizar una
  rama sin mergear, `feat/fil31-trafico-stgnn-tool`, que reutiliza
  `FIL_32`/`33` para un tema no relacionado -- ver la nota de cierre de
  esta ronda más abajo).

**2 `FIL_*` nuevos, ambos severidad baja.** El análisis estático (primera
vez en este proyecto) no encontró ningún bug funcional ni vulnerabilidad
de severidad media/alta explotable — corrobora, desde un ángulo
completamente distinto, la salud del código ya verificada en vivo por las
rondas 1-3.

### Nota (30/8, posterior al cierre): colisión de numeración `FIL_32`/`33`

Una rama sin mergear de otra sesión, `feat/fil31-trafico-stgnn-tool`
(funcionalidad de mapa animado / grafo canónico, sin relación con esta
ronda), reutiliza `FIL_32`-`38` para tickets propios. Mientras esa rama
siga sin mergear, `main` conserva la numeración original de esta ronda sin
conflicto real -- pero para evitar una colisión en el momento del merge
(mismo patrón ya visto una vez con `FIL_26`), se renumeró
proactivamente el `FIL_32` de esta ronda a **`FIL_39`**
(`tasks/FIL_39_dependencias-con-cve-conocido.md`, mismo contenido, sin
cambios de fondo). **Pendiente de recomprobar cuando esa rama
efectivamente se mergee a `main`**: confirmar que `FIL_39`/`FIL_40` (ver
ronda 5) no colisionan con lo que aterrice, y renumerar de nuevo si hiciera
falta.

### Nota (31/8, actualización): colisión de numeración ampliada a `FIL_31`

El push más reciente de esa misma rama (`b68133f`, 31/8) añadió su propio
`tasks/FIL_31_stgnn-trafico-como-tool-mcp.md` (coincide con el propio
nombre de la rama) — colisiona con el `FIL_31` de esta ronda
(`xml-parsing-sin-defusedxml`), que hasta ahora no tenía conflicto.
Renumerado proactivamente, mismo criterio que arriba, a **`FIL_41`**
(`tasks/FIL_41_xml-parsing-sin-defusedxml.md`, mismo contenido). Con esto,
`FIL_31`, `FIL_32`/`33` (→ `39`/`40`) de esta sesión están todos fuera del
rango `31`-`38` que reclama esa rama.

### Nota (31/8, cierre): rama mergeada, sin colisión final

`feat/fil31-trafico-stgnn-tool` se mergeó a `main` (squash, commit
`ea879b6`, "[FIL_31] STGNN de trafico como tool del MCP", PR #209).
Verificado en vivo tras el merge: `main` tiene ahora `FIL_00`-`FIL_41`
completos y **sin ningún número duplicado** (`ls tasks/ | grep -oE
"^FIL_[0-9]+" | sort | uniq -c` sin ninguna línea con conteo > 1) — su
`FIL_31`-`38` (mapa animado/grafo canónico) conviven limpiamente con
nuestros `FIL_39`/`40`/`41` (renumerados desde `32`/`33`/`31`). La
renumeración proactiva funcionó exactamente como se esperaba. Cierra
definitivamente esta nota de seguimiento -- no hace falta más
recomprobación.
