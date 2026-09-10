# VIC_35 — QA de `consulta_grafo` (15ª tool) y el enriquecimiento de `contexto_urbano` (2026-09-10)

Revisión de código (sin cambios de lógica salvo un endurecimiento puntual),
más ejecución real de la suite de tests.

## 1. Garantía de solo lectura — ✅ correcto, con un endurecimiento aplicado

Las 8 plantillas de `_PLANTILLAS_GRAFO` (`asistente/mcp_agent/tools.py`)
resuelven a 8 builders de `asistente/neo4j_client.py`
(`vecindario_de_lugar_query`, `estaciones_calidad_aire_que_miden_query`,
`estaciones_meteo_cerca_query`, `recintos_cerca_query`,
`aparcamientos_cerca_query`, `bicimad_cerca_query`,
`lineas_que_pasan_por_query`, `paradas_de_linea_query`) — todos son
`MATCH...RETURN` puros, sin `CALL`, sin `apoc`, y todos pasan sus
argumentos como parámetros Neo4j (`$nombre_lugar`, `$radio_m`, etc.),
nunca interpolados en el texto de la consulta. El único uso de
`CALL apoc.algo.dijkstra` del módulo (`ruta_proximo_query`) no forma parte
de ninguna plantilla de `consulta_grafo` — sirve a la tool `ruta_saludable`
(`FIL_54`), no a esta.

**Endurecimiento aplicado**: `run_neo4j_query` (el único punto por el que
pasan las 8 plantillas y ~15 puntos de llamada más en `asistente/`) abría
la sesión con el modo de acceso por defecto (`WRITE` en el driver oficial),
sin ninguna llamada real de escritura en el módulo. Añadido
`default_access_mode="READ"` explícito — mismo patrón que ya usaba
`grafo/consulta.py` (el CLI de desarrollo) desde antes. Esto rompió 4
dobles de prueba (`_FakeDriver`/`_RoutingNeo4jDriver` en
`test_afluencia_estimada.py`, `test_neo4j_client.py`, `test_mcp_tools.py`,
`test_opciones_movilidad.py`) que no aceptaban el nuevo kwarg — corregidos
para aceptar `**kwargs` (mismo patrón que ya usaba `test_consulta_grafo.py`).
Suite completa reverificada en verde tras el arreglo (ver punto de tests
abajo).

## 2. Contrato de degradación (`FIL_15`) — ✅ correcto

`_consulta_grafo_impl` cubre exactamente 3 caminos, ninguno con excepción
hacia el cliente: plantilla desconocida, parámetros obligatorios ausentes,
y cualquier excepción de `run_neo4j_query` (capturada con
`except Exception`). `run_neo4j_query` siempre devuelve una lista (la
comprensión `[dict(record) for record in result]` no puede devolver otra
cosa sin lanzar antes), así que no hay un cuarto camino de "tipo de
retorno inesperado". **Matiz no cubierto**: ni `run_neo4j_query` ni
`_driver_from_env` configuran un timeout explícito de conexión/transacción
— una degradación de red hacia AuraDB (lenta pero no caída del todo)
podría colgar la petición HTTP en vez de fallar limpiamente. No es parte
del alcance de esta revisión (no es un bug de `consulta_grafo`
específicamente, es de todo el cliente), lo dejo anotado pero sin abrir
ticket — bajo impacto práctico dado que AuraDB Free rara vez degrada así
en vez de caerse del todo.

## 3. El guard `_ESCRITURA` de `grafo/consulta.py` — ✅ más robusto de lo que el ticket sospechaba

Probé los 4 bypasses sugeridos:

- `CALL apoc.periodic.iterate('MATCH..','SET..')` — **capturado**: el
  primer término de la regex (`\bSET\b`) coincide con "SET" dentro del
  literal de cadena, porque la regex no distingue si el texto está entre
  comillas o no (efecto colateral de una regex "ancha", no un fallo).
- `CALL { CREATE ... }` (subquery) — **capturado**: "CREATE" es una
  palabra suelta, coincide directo.
- `MATCH (n) CALL apoc.create.addLabels(...)` — **capturado**, pero no por
  la rama específica de `apoc.*`: la segunda alternativa de la regex
  exige `apoc.<algo>.<verbo>` con un **segundo punto** antes del verbo, y
  `apoc.create.addLabels` no lo tiene tras "create". Lo atrapa la primera
  alternativa genérica, porque "create" aparece como palabra suelta
  igualmente.
- Comentarios que oculten una palabra clave — no aplica en Cypher: a
  diferencia de SQL, no hay forma de "ensamblar" una cláusula de escritura
  a partir de fragmentos de texto en tiempo de ejecución; si la palabra
  clave está en el texto, el guard la ve, y si no está, Cypher tampoco
  puede ejecutar la escritura.

**Límite real, documentado aquí en vez de en el propio código todavía**:
la lista de verbos de la segunda alternativa (`create|write|delete|set|
remove|drop`) no cubre procedimientos APOC que escriben sin ese sufijo
literal — p. ej. `apoc.schema.assert` (puede borrar/crear índices y
constraints) o `apoc.refactor.rename`. Ninguno de los 4 casos que probé
cae en este hueco (todos contienen alguna palabra de la lista genérica),
pero un atacante que conociera la lista podría en teoría construirlo.
**No es una carencia práctica**: `grafo/consulta.py` ya abre su sesión con
`default_access_mode="READ"` (confirmado en el código, línea 84) — Neo4j
rechaza la escritura real a nivel de protocolo Bolt/kernel
independientemente de lo que la regex capture o no. El guard es un mensaje
de error amigable para un desarrollador que se equivoca sin querer, no la
barrera de seguridad real (esa es el modo de sesión). Es un CLI de
desarrollo con credenciales reales de SSM, no una superficie expuesta a
usuarios no confiables.

## 4. Compatibilidad de `contexto_urbano` — ✅ correcto

`EstacionProxima` (`contaminantes`, `magnitudes`, `altitud_m`, `subarea`)
y `ContextoUrbano.lineas_cercanas` tienen todos valor por defecto
(`None`/`Field(default_factory=list)`). `test_mcp_transport.py::
_ESPERADAS` ya lista las 19 tools reales (no 15 — el ticket asumía un
número ya superado por `FIL_79`-`FIL_82`, que aterrizaron después de
escribirse). Test de esquema por transporte pasa.

## 5. Sincronía de `grafo_urbano.json.gz` — ✅ ambas copias, con la salvedad de `VIC_34`

`grafo/_data/grafo_urbano.json.gz` y `asistente/modelos/grafo_urbano.json.gz`
tienen el mismo md5 (`196c7a25d6a3f0983379cf7646252ed9`) y ambas están
commiteadas — no hay divergencia entre lo que usa `contexto_urbano`/`viz/`
y lo que hay en `grafo/_data/`. La salvedad ya la dejó `VIC_34`: ambas
copias están ~27 nodos de tráfico por detrás de la instancia Neo4j real
(tarea de mantenimiento, no bug — afecta a las dos por igual, así que no
hay una fuente más fresca que la otra escondida).

## 6. `_recent_date_filter` de FIL_66 — ⚠️ hallazgo real, no cosmético → `FIL_89`

La pregunta del ticket ("¿podrían quedar incompletas las columnas
`array_agg` si una estación no reportó en la ventana de 14 días?") tiene
una respuesta más seria de lo que sugiere: el filtro no usa una fecha
ancla, usa `current_date` real de Athena. Con la ingesta congelada desde
el 30/8, la ventana **avanza cada día** mientras los datos reales se
quedan fijos. Verificado con la fecha real de hoy (10/9): la ventana
todavía incluye el 29-30/8, pero deja de hacerlo a partir del **13-14 de
septiembre**, y para el día de entrega (17/9) la ventana completa
(3/9–17/9) no contendría ningún dato real — cualquier recarga del grafo
ejecutada esos días perdería silenciosamente `contaminantes`, `subarea`,
capacidades de aparcamiento/BiciMAD, etc. Abierto `tasks/FIL_89_grafo_
extract_recent_date_filter_ventana_deslizante.md` con la tabla de fechas,
las funciones afectadas y dos alternativas de fix (anclar la fecha, mismo
patrón que `FIL_84`, o quitar el filtro como ya se hizo para meteo/aforos).
No lo arreglé en esta revisión — cambia comportamiento de un módulo que no
es mío tocar sin coordinar con quien recargue el grafo.

## Tests

`pytest asistente/ grafo/`: **361 passed, 1 skipped, 57 subtests passed**
(tras el arreglo de los 4 dobles de prueba de neo4j — antes del arreglo,
26 tests fallaban en cascada por el cambio de `default_access_mode`,
todos con el mismo `TypeError`, no 26 bugs distintos).

## Recomendación explícita sobre `access_mode="READ"` (punto 1 del ticket)

**Sí, aplicarlo** — ya aplicado en este ticket. Es defensa en profundidad
de coste cero (ninguna llamada real necesita `WRITE`), alinea
`asistente/neo4j_client.py` con el mismo patrón que ya usaba
`grafo/consulta.py`, y convierte cualquier futuro error de plantilla que
intente escribir en un rechazo de protocolo claro en vez de una escritura
real silenciosa contra la instancia de producción.
