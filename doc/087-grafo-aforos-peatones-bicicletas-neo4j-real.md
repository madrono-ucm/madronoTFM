# 087 — Grafo: Fase A de la especificación 086 (EstacionMedida{tipo: aforos_peatones_bicicletas})

**Corrección 25/8, misma sesión**: tras escribir este documento se
encontraron credenciales AWS reales configuradas en esta máquina
(`~/.aws/credentials`, perfil `madrono`, `aws sts get-caller-identity` ->
`madrono-terraform-deployer`) — la conclusión de "sin credenciales" de
abajo era un error de verificación (solo se había comprobado que las
claves *existieran* como nombres, no que tuvieran valor). Con acceso real:

1. **El hallazgo de "Gold anida `location`" era incorrecto.** `DESCRIBE
   aforos_peatones_bicicletas_por_estacion_modo_hora` contra Athena real
   confirma columnas `lat`/`lon` **planas**, igual que
   `trafico`/`calidad_aire`/`ruido` — el primer intento asumió lo
   contrario leyendo solo el `dict` Python de `aggregate.py`, sin
   comprobar el catálogo real. `grafo/extract.py` ya está corregido
   (`location.lat`/`location.lon` -> `lat`/`lon` planas).
2. **`fetch_estaciones_aforos_peatones_bicicletas` devuelve 0 filas contra
   Athena real, y no es un bug de esta consulta.** La tabla Gold real solo
   tiene un objeto Parquet, con fecha `2024-06-30` — fuera del rango de
   Partition Projection configurado (`2026-08-01,NOW+1DAY`), así que es
   invisible a cualquier consulta. Investigando más: el Bronze real
   (captura en vivo del 15/8/2026, 1971 filas) trae **`measured_at:
   "2024-06-30..."` en todas las filas** — la fuente real
   (`datos.madrid.es`, dataset `300321-0-aforos-peatones-bicicletas`) no
   publica datos nuevos desde esa fecha. No es un bug de scheduling ni de
   Partition Projection de este proyecto: es la fuente externa la que dejó
   de actualizarse. Ver la corrección en `doc/086-afluencia-estimada-grafo.md`
   — **`aforos_peatones_bicicletas` deja de ser señal primaria de
   `afluencia_estimada`**, sustituida por `trafico`/`calidad_aire`/
   `ruido`/`bicimad`.
3. La instancia real de Neo4j **sigue sin recargarse con este origen** —
   dado el hallazgo del punto 2, cargar `:EstacionMedida {tipo:
   "aforos_peatones_bicicletas"}` no aportaría ningún nodo real (0 filas en
   Gold), así que no se ha ejecutado `cargar_grafo.py` contra producción.
   El código queda listo por si la fuente externa vuelve a publicar en el
   futuro, pero no se recargará solo para confirmar que sigue devolviendo
   0 nodos.

**Confirmado de forma independiente contra la página real del dataset**
(`datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas`): cobertura
real de datos "1 de septiembre de 2019 a 30 de junio de 2024", frecuencia
de actualización nominal trimestral mientras que en la práctica lleva más
de dos años sin publicar un trimestre nuevo, y un hueco previo ya conocido
de agosto de 2021 a septiembre de 2022 por cambio de los detectores. No es
una interpretación de los datos capturados -- es lo que dice la propia
fuente.

El resto de este documento (por debajo) es el estado tal como se escribió
antes de tener acceso real — se deja sin reescribir como registro de lo que
realmente pasó en esta sesión, no como guía a seguir.

## Qué se implementó

Cuarto origen de `:EstacionMedida` (junto a `trafico`/`calidad_aire`/
`ruido`, tareas 067/069): `aforos_peatones_bicicletas` (conteos horarios
reales de peatones/bicicletas, tarea 054), siguiendo exactamente el patrón
ya existente para `ruido`. Es la Fase A de `doc/086-afluencia-estimada-grafo.md`
(tarea 086) — prerrequisito para que la Fase B (tarea 089, tool
`afluencia_estimada`) tenga una señal nueva sobre la que cruzar el grafo.

- **`grafo/extract.py::fetch_estaciones_aforos_peatones_bicicletas`**: un
  registro por `station_id` con `address`/`district`/ubicación más
  recientes (ventana de `_RECENT_WINDOW_DAYS` días, mismo criterio que el
  resto de orígenes de `:EstacionMedida`).
- **`grafo/nodos.py::estacion_medida_from_aforos_peatones_bicicletas_gold`**
  (+ plural): `id` = `f"aforos_peatones_bicicletas:{station_id}"`, `tipo`/
  `fuente` = `"aforos_peatones_bicicletas"` (nombre completo del dataset,
  fijado por la especificación 086, no una abreviatura), `nombre` =
  `address` si existe, si no `district`.
- **`grafo/cargar_grafo.py::cargar_grafo`**: añade esta lista a la unión de
  `estaciones_medida` que ya alimenta `PROXIMO_A`/`UBICADO_EN` —
  `relaciones.py` no necesitó ningún cambio (genérico sobre cualquier nodo
  con `ubicacion`+`tipo` distinto, ver tarea 070).
- **`grafo/README.md`**: documenta el origen nuevo y una excepción real al
  patrón general ("Gold aplana lat/lon") — ver "Hallazgo" abajo.

## Hallazgo: `aforos_peatones_bicicletas` Gold anida `location`, no la aplana

A diferencia de `trafico`/`calidad_aire`/`ruido` (que aplanan la ubicación a
columnas `lat`/`lon` planas en Gold), el Gold de `aforos_peatones_bicicletas`
(`procesamiento/silver_gold/aforos_peatones_bicicletas/aggregate.py`) deja
`location` como columna `struct` anidada, igual que Silver. El SQL de
`fetch_estaciones_aforos_peatones_bicicletas` proyecta
`location.lat AS lat, location.lon AS lon` para poder reutilizar
`extract._nest_location`/`grafo.nodos._location` sin ningún cambio en esas
funciones — documentado en `grafo/README.md` para que una tarea futura que
añada otro origen no asuma que todo Gold aplana la ubicación sin comprobarlo
primero contra el `aggregate.py` real del dataset.

## Limitación real de esta sesión: sin credenciales AWS/Neo4j

**Esta tarea se ejecutó desde un entorno de desarrollo local (máquina
Windows del usuario, no la EC2 del proyecto ni ningún entorno con
credenciales reales configuradas)** — verificado en vivo: no hay `aws` CLI
instalado, `~/.aws/credentials` existe pero con
`aws_access_key_id`/`aws_secret_access_key` vacíos (plantilla dejada por
una sesión anterior, nunca rellenada en esta máquina), y `boto3`/`neo4j` no
estaban instalados (se instaló `boto3` solo para poder ejecutar la
suite de tests con mocks, sin ninguna llamada de red real).

Por tanto, a diferencia de las tareas 067/069/080, **en esta tarea no se
ha podido**:

- Verificar el SQL de `fetch_estaciones_aforos_peatones_bicicletas` contra
  Athena real (nombre de tabla/columnas confirmado solo leyendo
  `procesamiento/silver_gold/aforos_peatones_bicicletas/aggregate.py`, no
  ejecutando la consulta).
- Ejecutar `python3 -m grafo.cargar_grafo` contra la instancia real de
  Neo4j AuraDB Free — **la instancia real NO se ha recargado con este
  origen nuevo**. Los 9327 nodos/41031 relaciones de la tarea 080 (más el
  enriquecimiento OSM de la tarea 083, si se recargó) siguen siendo el
  estado real de producción hasta que alguien con credenciales ejecute la
  recarga.

**Verificación aplicada en su lugar**: la suite completa de `grafo/tests/`
(93 tests, mocks de `boto3`/Athena, sin red) pasa en verde, incluyendo los
tests nuevos de este origen (`grafo/tests/test_extract.py::FetchGoldNodeSourcesTests::test_fetch_estaciones_aforos_peatones_bicicletas`,
`grafo/tests/test_nodos.py::EstacionMedidaTests` — 3 tests nuevos: nodo
básico, `nombre` cae a `district` sin `address`, dedup por `station_id`
entre horas distintas).

## Restricciones respetadas

- No se ha implementado la tool `afluencia_estimada` (Fase B) — es la
  tarea `089`, deliberadamente separada y posterior.
- No se ha usado ningún `tipo` distinto a `"aforos_peatones_bicicletas"`
  (el que fija `doc/086`).
- No se ha tocado `ingesta/capturas/afluencia_lugares_madrid.py` ni
  `populartimes`.
- No se ha cambiado el umbral de `PROXIMO_A` (300m, tarea 070).
- No se ha ejecutado ningún `terraform apply`/`destroy`.

## Relevante para tareas futuras

- **Pendiente real antes de que la tarea 089 pueda verificarse de extremo a
  extremo**: alguien con credenciales AWS/Neo4j reales (la EC2 del
  proyecto, o un entorno local con `~/.aws/credentials` real) debe:
  1. Confirmar el nombre/columnas exactos de
     `gold.aforos_peatones_bicicletas_por_estacion_modo_hora` contra Athena
     real (el SQL de este módulo asume la forma documentada en
     `aggregate.py`, no verificada en vivo).
  2. Ejecutar `python3 -m grafo.cargar_grafo` contra la instancia real —
     es idempotente (`MERGE`, verificado en la tarea 080), no debería
     afectar a los nodos/relaciones ya cargados.
  3. Verificar con Cypher real: `MATCH (e:EstacionMedida {tipo:
     "aforos_peatones_bicicletas"}) RETURN count(e)` > 0, y al menos un
     `:Lugar` conocido con una relación `PROXIMO_A` nueva hacia una de
     estas estaciones.
- Consulta la Prioridad 1 de `NEXT_STEPS.md` (drift de Terraform, tarea
  088) antes de asumir que el Gold desplegado realmente coincide con el
  código de `main` en el momento de ejecutar la recarga real.
