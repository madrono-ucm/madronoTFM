# 079 — Asistente: primera tool real (`calidad_aire`) contra Athena, de extremo a extremo

## Qué se implementó

Alcance deliberadamente pequeño (una sola `tool`, de extremo a extremo), tal
como pedía el enunciado: `calidad_aire(zona, momento=None)`, la más simple
de las 5 `tools` del esqueleto de la tarea 044 (una sola fuente Gold, ya
verificada en las tareas 049/066/068).

- **`asistente/athena.py`** (nuevo): `run_athena_query()` replica el patrón
  ya establecido en `grafo/extract.py` (tarea 069: `boto3` +
  `start_query_execution`/`get_query_execution`/`get_query_results`, mismo
  backoff de sondeo) en vez de importarlo directamente — mismo criterio ya
  aplicado en `asistente/timeutils.py` respecto a `ingesta/`: mantener
  `asistente/` autocontenido y desplegable de forma independiente del resto
  del monorepo.
- **`asistente/mcp_agent/tools.py`**: `calidad_aire()` consulta
  `gold.calidad_aire_por_estacion_contaminante_hora` filtrando por
  `station_name`/`station_id` (coincidencia de texto, case insensitive) y
  por la partición `date` de `momento` (o de hoy en hora de Madrid si es
  `None`). Si ninguna estación coincide, o no hay datos para la hora
  resuelta, devuelve `CalidadAireZona(indice_calidad="sin_datos")` en vez de
  lanzar una excepción. Si varias estaciones coinciden, agrega
  contaminante a contaminante tomando la de mayor `avg_value` (criterio
  conservador documentado en el código). El `contaminante_principal` se
  elige por su ratio frente a un límite/umbral de referencia oficial (Real
  Decreto 102/2011 / Directiva 2008/50/CE) — NO2/SO2/O3 usan su
  límite/umbral horario oficial; PM10/PM2.5/CO no tienen límite horario
  oficial, así que se usa su límite diario/anual/8h como referencia
  aproximada, documentado explícitamente como tal (no es el Índice de
  Calidad del Aire oficial, que combina más señales).
- **`asistente/models/herramientas.py`**: `CalidadAireZona` ampliado con
  `valor`/`unidad`/`hora`/`estaciones_consultadas` (antes solo tenía
  `indice_calidad`/`contaminante_principal`) para que el dato bruto quede
  trazable, no solo la etiqueta calculada.
- **`asistente/main.py`**: el agente MCP ya se monta en la app FastAPI
  (`MCPServer.streamable_http_app()` + `FastAPI.mount("/mcp-server", ...)`),
  paso que el `README.md` anterior dejaba pendiente. `FastAPI.mount()` no
  propaga por sí solo el `lifespan` de una sub-app montada (solo Uvicorn
  invoca el de la app raíz); el `lifespan` de la app principal entra
  explícitamente en el `lifespan_context` de la sub-app MCP con
  `contextlib.AsyncExitStack` — patrón documentado por el propio SDK de MCP
  para este caso. Verificado con `TestClient` como gestor de contexto: el
  log confirma que el `StreamableHTTPSessionManager` arranca y para
  correctamente.
- **`asistente/routers/calidad_aire.py`** (nuevo): `GET /calidad-aire`
  invoca la tool y construye una `RespuestaAsistente` real (veredicto
  derivado del índice calculado, fiabilidad `baja` si no hay estación,
  `media` si el índice es `sin_clasificar` o hay varias estaciones
  agregadas, `alta` en el resto; `fuentes` cita el dataset y las
  estaciones consultadas).

## Verificación con datos reales (cuenta `eu-west-1`, `222234418587`)

Arrancado el servicio real con `AWS_DEFAULT_REGION=eu-west-1 uvicorn
asistente.main:app` (necesario: la región IMDS por defecto de esta EC2 es
`eu-south-2`, distinta de donde vive la infraestructura real — sin esta
variable, `boto3.client("athena")` falla con `NoRegionError`; documentado en
`asistente/README.md`, "Cómo correrlo"):

- `GET /calidad-aire?zona=Ramón y Cajal` → NO2 = 5.0 µg/m³ a las 21:00,
  `veredicto="favorable"`, `fiabilidad="alta"`, `fuentes` citando
  `gold.calidad_aire_por_estacion_contaminante_hora` y la estación.
- `GET /calidad-aire?zona=Plaza del Carmen` → O3 = 82.0 µg/m³, mismo patrón.
- `GET /calidad-aire?zona=BarrioQueNoExiste` → `fiabilidad="baja"`,
  `veredicto="con_precaucion"`, explicación explícita de "sin estaciones
  coincidentes", sin ninguna excepción.

Los nombres de estación reales se obtuvieron con una consulta Athena
`SELECT DISTINCT station_name` previa a escribir el código de verificación
(confirmó, entre otras, "Ramón y Cajal" y "Plaza del Carmen" — ya citadas
como ejemplo en el enunciado de la tarea).

## Tests

20 tests en verde (`python3 -m unittest discover -s asistente/tests -t .`):
los 11 ya existentes de la tarea 044 (adaptados: solo las 4 `tools`
pendientes se comprueban con `assertRaises(NotImplementedError)`) más 9
nuevos — 7 de la lógica de `calidad_aire` mockeando Athena con un
`FakeAthenaClient` (mismo patrón que `grafo/tests/test_extract.py`: sin
estaciones, una estación, varias estaciones coincidentes, sin `momento`,
contaminante sin límite de referencia, `avg_value` nulo, `momento` en otra
zona horaria) y 2 del router `/calidad-aire` (con y sin estación
encontrada, mockeando `run_athena_query`).

Un revisor de código detectó, tras la primera versión de esta tarea, dos
bugs reales antes de comitear (ambos con test de regresión añadido, ver
arriba): (1) una fila de Gold con `avg_value=None` (posible si
`samples_count=0`) podía convertirse en el "peor caso" elegido y dejar
`valor=None`, que el router formateaba con `f"{valor:.1f}"` -- crash
`TypeError`; ahora esas filas se descartan explícitamente. (2) `momento.hour`
se usaba tal cual sin convertir a hora de Madrid -- un `momento` en UTC (o
cualquier otra zona) filtraba por la hora equivocada de Gold (que agrupa en
hora de Madrid) sin ningún error visible; ahora se convierte con
`astimezone(MADRID_TZ)` antes de leer `.hour`/`.date()`.

## Decisiones no obvias

- **`indice_calidad` es una etiqueta simplificada, no el Índice de Calidad
  del Aire oficial** (que combina más señales y periodos de promediado
  distintos por contaminante). Se documenta explícitamente como aproximación
  en el código — mismo criterio que la tarea 078 con el precio de Glue: dar
  un número simple y útil, con su limitación documentada, en vez de no dar
  ninguno o fingir precisión que no existe.
- **`calidad_aire` no usa `cams_calidad_aire_madrid`** (previsión Copernicus
  CAMS) — el enunciado de la tarea señala explícitamente que la tabla real a
  usar es solo `gold.calidad_aire_por_estacion_contaminante_hora`
  (medición), y el esqueleto original mencionaba CAMS como fuente futura
  para previsión. Fuera de alcance de esta tarea.
- **Se amplió `CalidadAireZona`** (modelo de retorno de la tool) con
  `valor`/`unidad`/`hora`/`estaciones_consultadas` — no estaba prohibido por
  el enunciado, y sin esos campos la tool no podría exponer el dato bruto
  que sustenta `indice_calidad`/`contaminante_principal`, dejando la
  respuesta del router sin nada real que citar en `explicacion`/`fuentes`.
- **No se importó `grafo.extract` directamente** para reutilizar
  `run_athena_query` — se replicó el patrón en `asistente/athena.py` en su
  lugar, siguiendo el precedente ya explícito en
  `asistente/timeutils.py` (no acoplar `asistente/` a otros paquetes del
  monorepo, para que siga siendo desplegable de forma independiente).
- **`boto3` añadido a `asistente/requirements.txt`** (no estaba, ya que
  ninguna `tool` real lo necesitaba antes de esta tarea) — mismo rango que
  `grafo/requirements.txt` (`>=1.34,<2`), ya instalado en esta EC2.

## Restricciones respetadas

- Solo se implementó `calidad_aire` — las otras 4 `tools` siguen levantando
  `NotImplementedError`, sin tocar su lógica.
- No se implementó resolución de barrio/distrito real — `zona` se resuelve
  por coincidencia de texto sobre `station_name`/`station_id`, documentado
  como limitación explícita en el código y en el README.
- No se ha desplegado nada ni se ha tocado ningún recurso Terraform — toda
  esta tarea es código de servicio, verificado localmente contra Athena real
  (solo lecturas `SELECT`, sin ningún efecto sobre los datos).
- No se instaló/eliminó ninguna dependencia salvo `boto3` (documentada
  arriba, imprescindible para consultar Athena).

## Relevante para tareas futuras

- **Gotcha de entorno**: esta EC2 resuelve su región de IMDS a
  `eu-south-2`, pero la infraestructura real del proyecto vive en
  `eu-west-1` — cualquier script/servicio que use `boto3.client(...)` sin
  `region_name` explícito (como `grafo/extract.py` y ahora
  `asistente/athena.py`) necesita `AWS_DEFAULT_REGION=eu-west-1` en el
  entorno o falla con `botocore.exceptions.NoRegionError`. No se ha
  hardcodeado el default en el código (mismo criterio que `grafo/extract.py`,
  que tampoco lo hace) — queda como variable de entorno a fijar por quien
  ejecute el servicio.
- Las 4 `tools` restantes son candidatas directas a tareas de seguimiento
  con el mismo patrón ya establecido aquí: tool en `tools.py` (consultando
  Athena vía `asistente/athena.py`) + router HTTP dedicado en
  `asistente/routers/` + tests mockeando Athena con `FakeAthenaClient`.
- Un router "pregunta en lenguaje natural" que decida qué `tool(s)` invocar
  sigue sin existir — cada tool real expone su propio endpoint HTTP
  dedicado (`GET /calidad-aire`), sin ningún orquestador todavía.
