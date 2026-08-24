# 081 — Asistente: `trafico_cercano`, primera `tool` que cruza datasets vía el grafo

## Qué se implementó

Nueva `tool` `trafico_cercano(lugar, radio_m=300.0, momento=None)` en
`asistente/mcp_agent/tools.py`, la primera del asistente que combina dos
fuentes distintas por proximidad geográfica **usando el grafo urbano en
Neo4j** (tarea 080: 9327 nodos, 41031 relaciones ya cargados) en vez de
reimplementar cálculo de distancias — el mismo patrón que ya usa la memoria
del TFM (apartado 6.7) y que quedó anotado como siguiente paso tras la 080.

- **`asistente/neo4j_client.py`** (nuevo): cliente de solo lectura,
  independiente de `grafo/cypher.py` (que solo tiene métodos de escritura,
  `Neo4jLoader`, pensados para `cargar_grafo.py` — no se tocó, siguiendo la
  restricción explícita de no modificar `grafo/`). `run_neo4j_query(query,
  params, *, driver=None, database=None)` replica la forma de
  `asistente/athena.py::run_athena_query` (función con cliente/driver
  inyectable) en vez de una clase con gestor de contexto como
  `Neo4jLoader`: aquí solo hace falta una consulta puntual por invocación de
  la tool. El driver real se construye perezosamente desde
  `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE` (mismas
  variables que `grafo/cargar_grafo.py::main()`) y se cachea por proceso
  (`lru_cache`) — abrir un driver nuevo por petición HTTP sería un coste
  innecesario, el driver oficial ya gestiona su propio pool.
  `lugares_proximos_a_estaciones_trafico_query(nombre_lugar, radio_m)`
  construye el Cypher: `MATCH (l:Lugar) WHERE toLower(l.nombre) CONTAINS
  toLower($nombre_lugar) MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo:
  'trafico'}) WHERE r.distancia_m <= $radio_m RETURN ...` — patrón **no
  dirigido** (`-[r:PROXIMO_A]-`, sin flecha): la relación se carga en un
  único sentido por pareja de nodos (`grafo/relaciones.py::proximo_a`, cuyo
  propio docstring documenta "una consulta que necesite ambos sentidos usa
  un patrón no dirigido" — exactamente este caso, ya que el sentido real
  depende del orden de carga de `cargar_grafo.py`, no del esquema).
- **`asistente/models/herramientas.py`**: `EstacionTraficoCercana`
  (`point_id`, `distancia_m`, `avg_intensity_vph`/`avg_occupancy_ratio`/
  `avg_service_level` opcionales) y `TraficoCercano` (`lugar`, `momento`,
  `radio_m`, `resumen`, `hora`, `estaciones`, `fuente_grafo`, `fuente_gold`).
- **`asistente/mcp_agent/tools.py`**: `_trafico_cercano_impl` hace el cruce
  en dos pasos — (1) Cypher real contra Neo4j para resolver `lugar` y
  encontrar `point_id` de estaciones de tráfico cercanas (extraídos del
  `id` del nodo, `"trafico:4260"` → `"4260"`); (2) con esos `point_id`,
  consulta `gold.trafico_por_punto_hora` vía Athena (mismo `asistente/athena.py`
  ya existente) filtrando por la partición `date` de `momento` (o de hoy) y
  por `point_id IN (...)`. Si ningún `:Lugar` coincide, o ninguna estación
  de tráfico está dentro de `radio_m`, devuelve `resumen="sin_datos"` sin
  lanzar ninguna excepción (mismo criterio que `calidad_aire`, tarea 079).
  Si el grafo encuentra estaciones pero Gold no tiene fila para esa hora,
  las estaciones se listan igualmente (la proximidad ya es un dato real)
  con sus campos de tráfico en `None`, en vez de omitirlas en silencio.
  `resumen` (`"fluido"`/`"denso"`/`"congestionado"`/`"sin_datos"`) se
  calcula sobre la media de `avg_service_level` (campo real "nivelServicio"
  de la API de tráfico de Madrid, escala 0-6, ver
  `ingesta/capturas/trafico_madrid.py`) entre las estaciones con dato; si
  ninguna trae `avg_service_level`, usa como respaldo la media de
  `avg_occupancy_ratio` (0-1) — etiqueta simplificada y documentada como tal,
  no una métrica oficial (mismo criterio que `indice_calidad` de
  `calidad_aire`).
- **`asistente/routers/trafico_cercano.py`** (nuevo): `GET /trafico-cercano`
  invoca la tool y construye una `RespuestaAsistente`, citando dos fuentes
  (`fuentes[0]` el grafo, `fuentes[1]` Gold) cuando hay datos.
- Registrada en `asistente/mcp_agent/server.py` junto a `calidad_aire`, y en
  `asistente/main.py` (`app.include_router`).
- `neo4j>=5,<6` añadido a `asistente/requirements.txt` (mismo rango que
  `grafo/requirements.txt`, ya instalado en esta EC2).

## Tests

32 tests en verde (`python3 -m unittest discover -s asistente/tests -t .`):
los 20 ya existentes de la tarea 079 más 12 nuevos —
`asistente/tests/test_neo4j_client.py` (2 tests de la consulta Cypher por
inspección de la cadena, sin conexión ni el paquete `neo4j` instalado,
mismo criterio que `grafo/tests/test_cypher.py`; 2 tests de
`run_neo4j_query` con un driver falso mínimo), `TraficoCercanoToolTests` en
`test_mcp_tools.py` (6 escenarios: sin lugar coincidente, una estación con
dato Gold real, varias estaciones ordenadas por distancia con `resumen`
agregado, estación encontrada sin dato Gold para la hora, respaldo a
`avg_occupancy_ratio` sin `avg_service_level`, sin `momento` usa la hora más
reciente — mockeando Neo4j con un `FakeNeo4jDriver` y Athena con el
`FakeAthenaClient` ya existente), y 2 tests de
`test_trafico_cercano_router.py` (con y sin estación encontrada, mockeando
ambos clientes).

## Verificación real: Athena sí, Neo4j no (limitación real de esta sesión)

**Athena/Gold**: verificado con una consulta real contra la cuenta AWS del
proyecto (`eu-west-1`, `222234418587`) — `trafico_por_punto_hora` devolvió
filas reales del día de la ejecución (`point_id="10053"`,
`avg_intensity_vph=72.0`, `avg_service_level=0.0` a las 22:00 del
2026-08-24), confirmando que la mitad Gold del cruce funciona contra datos
de producción reales.

**Neo4j: no se pudo verificar contra la instancia real**, a diferencia de
lo que asumía el enunciado de la tarea ("Credenciales de Neo4j en SSM"). Se
comprobó explícitamente que no lo están:
`aws ssm describe-parameters` sobre toda la cuenta solo devuelve
`aemet-api-key`/`cams-ads-api-key`/`emt-client-id`/`emt-pass-key`/
`google-maps-api-key` — ningún parámetro `neo4j-*`. El rol de esta EC2
(`madrono-terraform-deployerEC2`) tampoco tiene ningún permiso
`secretsmanager:GetSecretValue` (`AccessDeniedException` explícita contra
varios nombres de secreto plausibles, no "no encontrado"). Esto es coherente
con `infra/neo4j/README.md` (tarea 043): documenta explícitamente que nunca
se añadió un parámetro SSM para Neo4j "porque todavía no existe ningún
proceso de carga Gold → Neo4j que lo consuma" — la tarea 080, que sí cargó
datos reales en Neo4j, debió recibir las credenciales de forma efímera (p.ej.
pegadas en su conversación) sin persistirlas en ningún gestor de secretos.
Tampoco había ninguna variable `NEO4J_*` en el entorno de esta sesión, ni
rastro en `.bash_history`/ficheros `.env` del sistema.

Ante este bloqueo real (no evitable sin una acción humana fuera de este
pipeline), se verificó exhaustivamente todo lo demás en su lugar: el driver
`neo4j` está instalado y es importable (5.28.4), la consulta Cypher se
genera correctamente por inspección de la cadena, y la lógica completa de
cruce grafo+Gold se probó con un `FakeNeo4jDriver`+`FakeAthenaClient`
cubriendo los 6 escenarios listados arriba. La tool está lista para
ejercitarse contra la instancia real en cuanto alguien con las credenciales
las fije como variables de entorno (o, mejor, las persista en SSM — ver
"Relevante para tareas futuras").

## Decisiones no obvias

- **No se reutilizó ni amplió `grafo/cypher.py`** (restricción explícita del
  enunciado): ese módulo solo tiene métodos de escritura pensados para
  `cargar_grafo.py`. `asistente/neo4j_client.py` es un cliente de lectura
  nuevo y autocontenido, mismo criterio que `asistente/athena.py` frente a
  `grafo/extract.py`.
- **Patrón Cypher no dirigido para `PROXIMO_A`**: aunque en la práctica el
  orden de carga de `cargar_grafo.py` (estaciones antes que lugares) hace
  que el sentido real siempre sea `EstacionMedida -> Lugar`, la consulta no
  depende de ese detalle de implementación — usa el patrón sin flecha que el
  propio `grafo/relaciones.py` documenta como forma correcta de consultar
  ambos sentidos.
- **`radio_m` se filtra explícitamente en el `WHERE` de la consulta**, no
  solo confiando en el umbral de 300m con el que se cargó `PROXIMO_A` (tarea
  070): permite pedir un radio más estricto; un radio mayor simplemente no
  encuentra relaciones que nunca se cargaron (documentado en el docstring de
  la tool, no es un error).
- **Estaciones sin dato Gold para la hora se listan con valores `None`**, en
  vez de omitirse: la proximidad geográfica (dato del grafo) es información
  real y trazable en sí misma, independiente de si Gold tiene lectura para
  ese instante concreto.
- **Clasificación de `resumen` con respaldo a `avg_occupancy_ratio`**: en
  vez de devolver "sin_datos" cada vez que `avg_service_level` es nulo
  (posible para sensores con lecturas parciales, ver
  `procesamiento/silver_gold/trafico/transform.py`), se intenta primero con
  `avg_service_level` (la señal más directa, escala real "nivelServicio") y
  solo cae a "sin_datos" si tampoco hay `avg_occupancy_ratio`.

## Restricciones respetadas

- No se ha tocado `calidad_aire` (tarea 079) ni implementado ninguna de las
  otras 4 `tools` con `NotImplementedError`.
- No se ha implementado geocodificación de texto libre — `lugar` se resuelve
  por coincidencia de texto sobre el nombre del nodo `:Lugar`, igual que
  `calidad_aire` con `zona`.
- No se ha modificado `grafo/` en absoluto.
- No se ha desplegado nada ni tocado ningún recurso Terraform.
- Se deja un commit real con el resultado real de la verificación
  (documentado arriba: Athena real, Neo4j solo mockeado por el bloqueo de
  credenciales explicado).

## Relevante para tareas futuras

- **Pendiente real, no completable sin intervención humana en esta
  sesión**: verificar `trafico_cercano` contra la instancia real de Neo4j
  en cuanto `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` estén disponibles
  (pedirlas a quien las usó en la tarea 080, o rotarlas desde la consola de
  Aura si se han perdido) — probar contra un `:Lugar` real
  (`MATCH (l:Lugar) RETURN l.nombre LIMIT 20` para elegir uno).
- **Recomendado, para que este bloqueo no se repita**: completar el punto ya
  señalado en `infra/neo4j/README.md` desde la tarea 043 y nunca hecho —
  añadir `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` como parámetros SSM
  `SecureString`. Aquella tarea no lo hizo porque "todavía no existe ningún
  consumidor real"; esta tarea ya lo es.
- El patrón de esta tarea (Cypher real vía `asistente/neo4j_client.py` +
  Athena vía `asistente/athena.py`, combinados en una única `tool`) es
  reutilizable para cualquier futura `tool` que necesite cruzar proximidad
  espacial con series temporales de Gold — p.ej. una variante para calidad
  del aire o ruido cerca de un lugar, siguiendo exactamente esta misma
  estructura.
