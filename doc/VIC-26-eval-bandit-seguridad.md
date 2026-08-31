# VIC_26 — análisis de seguridad estático con bandit (ronda 4)

**Fecha:** 2026-08-30. `bandit` no estaba instalado ni configurado en el
repo — primera vez que corre. Instalado solo en el `.venv` local de esta
EC2 para la auditoría.

## Comando

```
bandit -r ingesta/ procesamiento/ grafo/ asistente/ modelado/ herramientas/ \
  --exclude '*/tests/*,*/test_*'
```

(`tests/` excluido a propósito, por indicación explícita del ticket: los
patrones que `bandit` marca como riesgo en producción son a menudo
intencionados en un test.)

**42 hallazgos** (0 High, 32 Medium, 10 Low por severidad). Desglose:

| Regla | Nº | Severidad | Qué es |
|---|---|---|---|
| `B608` | 22 | Medium | Posible SQL injection por construcción de query con f-string |
| `B314` | 10 | Medium | `ET.fromstring` sobre XML no confiable |
| `B405` | 8 | Low | Import de `xml.etree.ElementTree` (mismo problema que `B314`, a nivel de import) |
| `B110` | 2 | Low | `try`/`except`/`pass` |

## Triaje línea a línea de severidad media/alta (los 32 Medium)

### `B608` — SQL injection (22 casos, el hallazgo con más volumen)

Revisadas las 22 ubicaciones una por una, leyendo el código real:

- **14 en `asistente/mcp_agent/tools.py`** — la capa MCP expuesta al
  agente/LLM, el sitio donde un `B608` real importaría más porque el
  parámetro de zona/estación puede originarse en una petición externa.
  Las 14 interpolan un valor string en la query, pero **todas** pasan ese
  valor por `sql_literal()` (`asistente/athena.py:33`) antes de
  interpolarlo dentro de un literal `'...'` — `sql_literal` escapa
  comillas simples duplicándolas (`value.replace("'", "''")`), la
  convención estándar para literales SQL, y se usa siempre dentro de
  `LIKE`/`IN (...)`, nunca como nombre de columna/tabla. Verificado que
  ningún caso concatena sin pasar por esta función. Una ubicación
  (`tools.py:1094`) interpola solo fechas calculadas internamente
  (`instante.date()`), no ningún string de usuario. **Sin vulnerabilidad
  real: el código ya tiene una defensa explícita y consistente.**
- **7 en `grafo/extract.py`** — job de extracción batch para construir el
  grafo de Neo4j. Ningún valor interpolado proviene de entrada externa:
  todas las queries usan nombres de tabla/columna fijos y, cuando hay un
  `WHERE`, es `_recent_date_filter()` (calculado internamente, no
  parametrizable desde fuera). **Sin vulnerabilidad: no hay entrada no
  confiable en esta ruta de código.**
- **1 en `herramientas/salud/frescura_gold.py:92`** —
  `consulta_marca(tabla, campo)` interpola `tabla` sin escapar, pero
  `tabla` siempre proviene de iterar el diccionario interno hardcodeado
  `TABLAS` (definido en el propio módulo), nunca de un argumento de CLI ni
  de ninguna fuente externa (confirmado leyendo `main()` y el único call
  site). **Sin vulnerabilidad: `tabla` no es controlable por nadie fuera
  del propio fichero.**

**Veredicto global `B608`: 22/22 falsos positivos.** `bandit` no puede ver
que `sql_literal()` neutraliza el riesgo ni que el resto de interpolaciones
usan valores internos, así que marca cualquier f-string usado para
construir SQL. El patrón de `asistente/athena.py` (escapar con
`sql_literal()` en vez de placeholders parametrizados, justificado en su
propio docstring por ser Athena de solo lectura para consultas puntuales,
no un motor con API de prepared statements ligera) es una decisión de
diseño ya razonada, no un descuido.

### `B314`/`B405` — XML sin `defusedxml` (10+8 = 18 casos, 4 ficheros)

`ingesta/capturas/{emt_incidencias,parques_jardines,poi,trafico}_madrid.py`
parsean el cuerpo de la respuesta HTTP de un feed externo de
datos.madrid.es con `xml.etree.ElementTree.fromstring` en vez de
`defusedxml`. A diferencia de `B608`, **este sí es un hallazgo real**: la
entrada es la respuesta cruda de un feed de red, no un valor interno. El
riesgo concreto es bajo (CPython ≥3.7.1 ya no resuelve entidades externas
por defecto en `ElementTree`, así que no hay XXE clásico; queda expuesta
la expansión de entidades internas / "billion laughs", un DoS por memoria,
no una fuga de datos) y la fuente es un endpoint municipal de confianza,
pero el fix (`defusedxml.ElementTree`, API-compatible) es tan barato que
merece hacerse como higiene defensiva. → **`FIL_41`** (renumerado desde
`FIL_31` el 31/8 por colisión con una rama sin mergear, ver
`doc/PLAN-EVALUACION-TECNICA-4.md`; ver
`tasks/FIL_41_xml-parsing-sin-defusedxml.md`).

## Los 10 Low (resumidos, no ameritan detalle línea a línea)

- **`B110` (2, `try`/`except`/`pass`)** — `grafo/cypher.py:283`
  (reconexión Neo4j) y `modelado/registry/mlflow_setup.py:90` (promoción de
  champion). Ya llevan `# noqa: BLE001` con la razón explícita en el propio
  código ("el driver ya está roto, da igual" / mejor esfuerzo al marcar
  alias). Ya triados en `VIC_25` (misma pareja de líneas, allí bajo la
  óptica de `S110` de `ruff`) — decisión ya razonada, no un descuido.
  **Sin `FIL_*` nuevo, ya cubierto.**
- **`B405` (8, import de `ElementTree`)** — mismo hallazgo que `B314` a
  nivel de import, mismos 4 ficheros, ya cubiertos por `FIL_41`.

## Cruce con `VIC_19`

`VIC_19` (auditoría manual basada en `grep` sobre patrones de credenciales)
encontró la credencial de Bluesky (`FIL_28`) pero no tocó SQL injection ni
parseo de XML — no hay solape ni duplicación con los hallazgos de esta
ronda.

## Conclusión

1 `FIL_*` nuevo (`FIL_41`, severidad baja, higiene defensiva de XML). El
hallazgo de mayor volumen (`B608`, SQL injection, 22 casos) se verificó
línea a línea y resultó ser enteramente falso positivo: el proyecto ya
tiene una defensa explícita y consistente (`sql_literal()`) para el único
caso donde interpolaría un valor externo. `bandit` sí aportó valor
respecto a la auditoría manual previa (`VIC_19`): encontró una clase de
riesgo (parseo XML) que un `grep` de credenciales nunca habría cubierto.
