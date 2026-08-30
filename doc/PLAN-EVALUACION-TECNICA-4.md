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
  → `FIL_31`.
- `VIC_27` (pip-audit): 3 CVEs reales, todos en dependencias transitivas
  sin ruta de explotación real en este proyecto, bump recomendado por
  higiene → `FIL_32`.

**2 `FIL_*` nuevos, ambos severidad baja.** El análisis estático (primera
vez en este proyecto) no encontró ningún bug funcional ni vulnerabilidad
de severidad media/alta explotable — corrobora, desde un ángulo
completamente distinto, la salud del código ya verificada en vivo por las
rondas 1-3.
