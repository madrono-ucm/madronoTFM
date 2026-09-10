# VIC_40 — QA de la tool `calidad_aire_cams` (FIL_80) y su contraste en `calidad_aire_prevista` (2026-09-10)

Verificación de `asistente/mcp_agent/tools.py::calidad_aire_cams` (17.ª tool
cronológicamente, hoy una de 19), el DDL de Gold que consume
(`cams_calidad_aire_por_contaminante_fecha_validez`), y los campos
`referencia_cams`/`delta_vs_cams` que añade a `calidad_aire_prevista`.
Solo lectura de código + `asistente/tests/`; sin acceso a Athena real
(todo mockeado, patrón estándar del repo).

## 1. Parseo de la fila Gold — ✅ correcto, y probado contra el formato real de Athena

`leadtime_hours` es `array<int>` en el esquema de Glue
(`F.sort_array(F.collect_set("leadtime_hour"))`,
`procesamiento/silver_gold/cams_calidad_aire/*.py`), pero el cliente Athena
de este proyecto (`asistente/athena.py::_collect_results`/
`_cast_athena_value`) usa la API cruda de `boto3` (`get_query_results`), que
devuelve **todo** como `VarCharValue` de texto y solo castea explícitamente
`_INTEGER_TYPES`/`_FLOAT_TYPES` — el tipo `array` no está en ninguna de las
dos listas, así que en producción `leadtime_hours` llega **siempre** como
el string `"[1, 3, 6]"`, nunca como lista real. El código lo maneja bien
(`tools.py:1483-1484`: `if isinstance(lt, str): lt = [int(x) for x in
lt.strip("[]").split(",") if ...]`), y crucialmente el test por defecto
(`test_cams.py::_row`, `lt="[1, 3, 6]"`) ya usa ese formato realista, no el
caso trivial de "ya es una lista" (que también está cubierto aparte, en
`test_leadtime_ya_lista`, por robustez). `avg_value`/`max_value` llegan
como `float` real (tipo Athena `double`, sí está en `_FLOAT_TYPES`);
`fecha_validez` como string ISO (no es un tipo numérico, pasa tal cual).

## 2. Frescura sin `fecha` explícita — ✅ correcto

Sin `fecha`, se toma la `fecha_validez` máxima de las filas devueltas y se
declara en `motivo` ("última previsión CAMS disponible: ... (pipeline de
datos pausado)"), cubierto por
`test_ultima_fecha_sin_fecha_explicita`. Con `fecha` explícita, `motivo` es
`None` (no hay nada que advertir) — `test_fecha_explicita`.

## 3. Signo del `delta` — ✅ correcto en el cálculo, pero **sin cobertura real** antes de este ticket (bug de aislamiento de test, corregido)

`delta_vs_cams = previsto - c.avg_ugm3` en `tools.py:1350`, que coincide con
el contrato documentado en `asistente/models/herramientas.py:246`
(`# valor_previsto − referencia_cams`) y en `asistente/README.md:284`. El
signo es correcto.

**Pero no había ningún test que lo ejerciera de verdad.** El bloque de
contraste CAMS dentro de `_calidad_aire_prevista_impl` está detrás de `if
athena_client is None:` con un comentario que decía *"solo en producción,
no en los tests con Athena mockeada"* — falso en la práctica: ningún test
del repo llama a `_calidad_aire_prevista_impl` pasando `athena_client`
explícito (todos mockean `run_athena_query` a nivel de módulo, el patrón
estándar de todo el repo), así que ese `if` es **siempre verdadero**
también en los tests, y el bloque de contraste CAMS se ejecutaba de
verdad — solo que reutilizando las mismas filas de aire mockeadas para la
previsión principal, con una forma completamente distinta a una fila CAMS
(sin `fecha_validez`/`max_value`/`leadtime_hours`).

Verificado empíricamente antes de tocar nada:

```
valor_previsto: 31.5
referencia_cams: 40.0   # <- es la lectura de NO2 más reciente del propio mock, NO un valor de CAMS
delta_vs_cams: -8.5     # <- por tanto, sin ningún sentido
```

Esto afectaba silenciosamente a `test_calidad_aire_prevista.py::
test_devuelve_prevision_real_desde_onnx` y `test_mcp_hardening.py::
test_calidad_aire_ok_rellena_el_envoltorio` — ninguno de los dos fallaba
porque ninguno afirma nada sobre `referencia_cams`/`delta_vs_cams`, pero
ambos generaban ese dato basura en cada ejecución sin que nadie lo viera.

**Corregido:**
- `asistente/tests/test_cams.py::ContrasteCamsEnPrevistaTests` (3 tests
  nuevos): mockea `calidad_aire_cams` directamente (el punto de inyección
  correcto, no `athena_client`) y verifica el signo del delta con valores
  fijos, que CAMS no disponible da `referencia_cams`/`delta_vs_cams=None`
  sin romper la previsión propia, y que el veredicto/`valor_previsto` no
  cambia según CAMS esté disponible o no (punto 6 de este ticket).
- Los dos tests preexistentes ahora mockean `calidad_aire_cams` con
  `disponible=False` para no seguir generando el dato basura sin querer.
- Comentario corregido en `tools.py` para no afirmar una protección que no
  existe, apuntando a la cobertura real.

No se abre ticket `FIL_*` — era un hueco de aislamiento de tests sin
impacto en producción (en producción `run_athena_query` no está mockeada,
la fila que llega a `calidad_aire_cams` siempre es una fila CAMS real),
corregido directamente como parte de esta QA.

## 4. Normalización de contaminante — ⚠️ la referencia a "FIL_72" en el ticket es incorrecta; no hay duplicado real

Tanto `tasks/FIL_80_tool-cams-copernicus-contraste.md` (punto 4 de su
alcance) como este ticket (`VIC_40`, punto 4) afirman que la normalización
de contaminante está "compartida con FIL_72". **`FIL_72` es en realidad
`tasks/FIL_72_consulta-grafo-plantillas-robustas-y-tuning.md`** — no tiene
nada que ver con contaminantes. Es una cita equivocada en ambos tickets
(probablemente un número de ticket confundido al redactarlos), no un bug
de código.

Dicho esto, verificado que **no hay ningún duplicado real**: `grep` de
`ALIAS`/`normaliz` en `tools.py` fuera del bloque CAMS no encuentra ningún
otro mapa de alias de contaminante — `_CAMS_ALIAS`/`_cams_token`
(`tools.py:1427-1439`) es el único, autocontenido, y correcto para su
propósito (normalizar contra el propio particionado `pollutant` de la Gold
CAMS: `no2/o3/pm10/pm2/so2`, con las variantes con tilde/subíndice/coma
decimal ya cubiertas y probadas en `test_normaliza_contaminante`). No hace
falta ninguna corrección — el punto 4 queda cerrado como "sin hallazgo",
con la cita equivocada documentada aquí para que no se repita.

## 5. Registro 16→17 (hoy 19) — ✅ ya consistente

`server.py` (`_TOOLS` + `_INSTRUCCIONES` + comentario "Las 19 tools..."),
`test_mcp_tools.py`, `test_mcp_transport.py`, `asistente/README.md` (fila
de `calidad_aire_cams` con `GET /calidad-aire-cams` y su relación con
`referencia_cams`/`delta_vs_cams`), y el diagrama/tabla de `README.md` raíz
ya dicen "19" de forma consistente — confirmado que esto ya lo dejó
correcto la sesión de `FIL_80`/`FIL_82`/`FIL_83` y la pasada de `VIC_37`
que corrió en paralelo a este ticket. Nada que corregir.

## 6. `calidad_aire_prevista` no depende de CAMS para su veredicto — ✅ correcto, ahora con test explícito

`test_veredicto_no_depende_de_cams` (nuevo, en `test_cams.py`) llama a la
tool dos veces con el mismo mock de aire, una con CAMS "disponible" (con
un valor absurdo, `avg_ugm3=999.0`, para maximizar la posibilidad de que
contaminara el resultado si hubiera un acoplamiento) y otra con CAMS no
disponible: `valor_previsto` y `nivel_previsto` son idénticos en ambos
casos; solo cambia `referencia_cams` (el contexto). Confirma por código y
por test que `referencia_cams`/`delta_vs_cams` son *append-only* al final
de la función, después de calcular `previsto`/`nivel` — no hay forma de
que influyan.

## Verificación

```
asistente/tests/test_cams.py asistente/tests/test_calidad_aire_prevista.py \
  asistente/tests/test_mcp_hardening.py asistente/tests/test_mcp_tools.py \
  asistente/tests/test_mcp_transport.py
→ 66 passed, 57 subtests passed
```

## Resumen

5 de 6 puntos sin hallazgos (ya correctos); 1 punto con hallazgo real (un
hueco de aislamiento de tests que producía datos basura silenciosos,
corregido con 3 tests nuevos + 2 tests existentes endurecidos + un
comentario corregido); 1 punto con una cita de ticket equivocada mencionada
por transparencia, sin bug de código detrás. Ningún hallazgo requiere un
ticket `FIL_*` nuevo.
