# 087 — Grafo: `aforos_peatones_bicicletas` como `:EstacionMedida` (Fase A de la 086)

Implementa la **Fase A** de `doc/086-afluencia-estimada-grafo.md`: añade
`aforos_peatones_bicicletas` (conteos horarios reales de la red de
estaciones permanentes de aforo de peatones/bicicletas de Madrid, tarea
054) como cuarto origen de `:EstacionMedida`, con el mismo patrón que
`trafico`/`calidad_aire`/`ruido` (tareas 067/069).

## Código

- `grafo/extract.py::fetch_estaciones_aforos_peatones_bicicletas()`: mismo
  patrón que `fetch_estaciones_ruido` (`GROUP BY station_id`, `max_by(col,
  date)`, ventana de 14 días). Un único `GROUP BY station_id` basta como
  identidad — no hace falta agrupar también por `mode`, porque las redes de
  peatones (`PERM_PEA##`) y de bicicletas (`PERM_BICI##`) usan
  identificadores de estación propios (ver docstring de
  `procesamiento/silver_gold/aforos_peatones_bicicletas/aggregate.py`).
- `grafo/nodos.py::estacion_medida_from_aforos_peatones_bicicletas_gold` (+
  plural): `id = f"aforos_peatones_bicicletas:{station_id}"`, `tipo`/
  `fuente = "aforos_peatones_bicicletas"`, `nombre = address or district`
  (respaldo, mismo criterio que fija `doc/086`).
- `grafo/cargar_grafo.py::cargar_grafo()`: la lista nueva se une a
  `estaciones_medida` junto a `trafico`/`calidad_aire`/`ruido` — no hizo
  falta tocar `relaciones.py` (genérico sobre cualquier nodo con
  `ubicacion`+`tipo`, tal como preveía `doc/086`).
- `infra/neo4j/schema/schema.cypher`: `"aforos_peatones_bicicletas"` añadido
  al comentario de valores esperados de `EstacionMedida.tipo`.

## Esquema real de Athena encontrado (distinto de lo que suponía el enunciado)

El enunciado de la tarea asumía `location` **anidado** en Gold (`location.lat`/
`location.lon`), por analogía con `aggregate.py` (la referencia documental/
de test, Python puro). Verificado contra el **job real desplegado**
(`procesamiento/silver_gold/aforos_peatones_bicicletas/glue_silver_to_gold.py`,
el PySpark que de verdad corre en Glue, no `aggregate.py`):

```python
F.first("location.lat", ignorenulls=True).alias("lat"),
F.first("location.lon", ignorenulls=True).alias("lon"),
```

Gold **aplana** `location` a columnas `lat`/`lon` sueltas — confirmado
además contra la definición real de la tabla en
`infra/terraform/glue.tf::aws_glue_catalog_table.aforos_peatones_bicicletas_gold`
(columnas `lat double`, `lon double`, no un `struct`). Es decir: **el mismo
esquema plano que `trafico_por_punto_hora`/`calidad_aire_por_estacion_
contaminante_hora`/`ruido_por_estacion_periodo_fecha`**, no el esquema
anidado que sí tiene la tabla **Silver** de este dataset (`location
struct<lat:double,lon:double,srid:string>`, esa sí anidada). `extract.py`
usa por tanto exactamente el mismo patrón (`_nest_location`) que el resto de
`:EstacionMedida`, sin ninguna rama especial.

## Comprobación de drift de Terraform (Prioridad 1 de `NEXT_STEPS.md`)

Pedida explícitamente por el enunciado antes de tocar la instancia real.
**El código real desplegado de este dataset concreto SÍ coincide con
`main`** — no hay drift aquí, a diferencia del hallazgo general de la tarea
083 (que sí encontró 48 objetos de código desactualizados en el `terraform
plan` sin acotar, para *otros* datasets):

```
$ aws glue get-job --job-name madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold \
    --query 'Job.Command.ScriptLocation' --output text
s3://.../glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py

$ md5sum procesamiento/silver_gold/aforos_peatones_bicicletas/glue_silver_to_gold.py
1ed5acbc05f8bc8dc8c53eae4e789893  ...
```

Mismo resultado para `glue_bronze_to_silver.py` (`d037fa3c...`, coincide
exactamente). El hash MD5 embebido en la key de S3 (`aws_s3_object.glue_script_*`
usa `filemd5(...)` del fichero local como parte de la key, ver `glue.tf`) es
justo el mismo hash que produce el fichero de este `main` — prueba directa,
no una inferencia, de que el código en ejecución es el código fusionado.
Con esto verificado, se continuó asumiendo que el Gold de este dataset (a
diferencia de `aparcamientos`/`cartelera_cines_estrenos`) sí refleja lo que
el pipeline real produce hoy.

## Bug real encontrado: Gold tiene datos reales, pero Athena no puede verlos

Al intentar verificar que `gold.aforos_peatones_bicicletas_por_estacion_
modo_hora` tenía filas reales (paso previo antes de asumirlo, tal como pide
el enunciado), la consulta de `extract.py` —y de hecho cualquier consulta,
incluso sin filtro de fecha— devolvió **0 filas**. Investigado paso a paso:

1. **El dato real existe en S3**: `aws s3 ls` sobre el prefijo Gold real
   muestra exactamente una partición, `date=2024-06-30/`, con un fichero
   Parquet real de 30 KB (escrito el 2026-08-23, es decir, ya con el código
   actual). Silver tiene la partición equivalente
   (`fecha=2024-06-30/hora=00..23/`, 4 ficheros por hora).
2. **Pero ni siquiera una coincidencia exacta de partición la ve**:
   `SELECT * FROM aforos_peatones_bicicletas_por_estacion_modo_hora WHERE
   date = '2024-06-30'` (sin depender de `_recent_date_filter()`) también
   devuelve 0 filas.
3. **Causa raíz**: ambas tablas (`aforos_peatones_bicicletas` Silver y
   `..._por_estacion_modo_hora` Gold) usan **Partition Projection**
   (`infra/terraform/glue.tf`, tarea 068) con
   `"projection.date.range" = "2026-08-01,NOW+1DAY"` /
   `"projection.fecha.range" = "2026-08-01,NOW+1DAY"`. Con projection
   activado, Athena **calcula** las particiones válidas por fórmula a partir
   de ese rango — no lista S3 realmente — así que una partición con fecha
   fuera del rango declarado es indistinguible de "no existe", aunque el
   fichero esté físicamente ahí.
4. **Por qué la fecha real es `2024-06-30` y no la fecha de ingesta**: leído
   un objeto Bronze real (`aforos_peatones_bicicletas/fecha=2026-08-15/
   hora=19/20260815T194706_fe93f48c.json`, `ingested_at` real
   `2026-08-15T19:46:53...`), cada registro trae
   `"measured_at": "2024-06-30T00:00:00+02:00"` — la propia fuente
   (`madrid_aforos_peatones_bicicletas`) publica sus conteos horarios con
   esa fecha, no con la fecha de la petición HTTP. El pipeline Silver→Gold
   particiona por `measured_at` (mismo criterio, documentado y correcto,
   que usan `trafico`/`calidad_aire`/`ruido`) — nadie anticipó, al desplegar
   la tabla en la tarea 054, que esta fuente en concreto tendría una fecha
   tan alejada de "hoy".

Esto **no es el mismo tipo de bug** que `aparcamientos` (Gold vacío de
verdad) ni que `cartelera_cines_estrenos` (job que falla): aquí el dato
real existe, está bien formado, y el pipeline lo escribió correctamente —
solo es inalcanzable desde Athena por una ventana de partition projection
mal calibrada para esta fuente en particular.

### Fix (código, sin aplicar)

`infra/terraform/glue.tf`: `projection.fecha.range` (tabla Silver) y
`projection.date.range` (tabla Gold) de `aforos_peatones_bicicletas`,
ampliados de `"2026-08-01,NOW+1DAY"` a `"2024-01-01,NOW+1DAY"` — solo para
estas dos tablas, sin tocar el resto de datasets. Siguiendo la instrucción
del enunciado ("no ejecutes terraform apply/destroy"), el cambio queda
escrito y comentado en el propio `.tf`, **no aplicado** — aplicar esto es
responsabilidad de quien reconcilie la Prioridad 1 de `NEXT_STEPS.md` (o
antes, si se decide aislarlo con cuidado; ver la advertencia sobre
`-target` de la tarea 083 en el propio `NEXT_STEPS.md`).

## Recarga real de Neo4j

Ejecutado `python3 -m grafo.cargar_grafo` contra la instancia real
(credenciales de
`/madrono-tfm/dev/secrets/neo4j-{uri,username,password,database}`, SSM
`eu-west-1`, cargadas solo en variables de entorno del proceso — nunca
escritas en el repositorio). Es idempotente (`MERGE`), no destructivo sobre
lo ya cargado (tarea 080).

**Verificado con Cypher real antes/después** (`python3 -m grafo.cargar_grafo`
ejecutado 2026-08-25, ~4 minutos, `exit=0`):

| | Antes | Después |
|---|---|---|
| `MATCH (n) RETURN count(n)` | 9327 | 9327 |
| `MATCH ()-[r]->() RETURN count(r)` | 67158 | 67158 |
| `MATCH (e:EstacionMedida {tipo: "aforos_peatones_bicicletas"}) RETURN count(e)` | 0 | 0 |

Por label (`MATCH (n) RETURN labels(n)[0], count(n)`): `Barrio` 131,
`Distrito` 21, `EstacionMedida` 4738, `Lugar` 381, `ParadaTransporte` 4056
— idénticos a la tarea 080. Por relación: `CONECTADO_CON` 11998,
`PERTENECE_A` 131, `PROXIMO_A` 46008 (más que los 19880 de la tarea 080 —
esperado, `proximo_a_query` es un `MERGE` sobre el par exacto de nodos, así
que no duplica; el número más alto refleja que la 083 añadió más `:Lugar`
con `ubicacion` que ahora también generan `PROXIMO_A`, no un problema de
esta tarea), `UBICADO_EN` 9021.

Consistente con el bug documentado arriba: `fetch_estaciones_aforos_
peatones_bicicletas()` devuelve `[]` contra la instancia real de hoy — no
por ningún error de la consulta (verificada exhaustivamente con
`FakeAthenaClient` en los tests, ver abajo), sino porque Athena
efectivamente no ve ninguna fila de Gold hasta que se aplique el fix de
partition projection. El resto del grafo (`trafico`/`calidad_aire`/
`ruido`/`transporte_publico_emt`/`bicimad`/`aparcamientos` vacío/
`cartelera_cines_estrenos` vacío/`poi_madrid`/CRTM/distritos/barrios) se
recargó sin cambios de conteo respecto a la tarea 080 (mismo dato de origen,
`MERGE` idempotente) — la recarga en sí confirma que `cargar_grafo.py`
sigue funcionando end-to-end contra la instancia real tras añadir el cuarto
origen de `:EstacionMedida`, aunque ese origen en concreto no aporte nodos
todavía.

## Tests

`grafo/tests/` completo: 94 tests (89 de la tarea 083 + 5 nuevos), todos en
verde:

```
$ python3 -m unittest discover -s grafo/tests -t .
Ran 94 tests in 0.236s
OK (skipped=1)
```

- `test_extract.py::FetchGoldNodeSourcesTests::test_fetch_estaciones_
  aforos_peatones_bicicletas`: `FakeAthenaClient` con columnas
  `station_id`/`address`/`district`/`lat`/`lon`, verifica el `_nest_location`
  y que la tabla real (`aforos_peatones_bicicletas_por_estacion_modo_hora`)
  aparece en el SQL generado.
- `test_nodos.py::EstacionMedidaTests`: construcción del nodo (`id`/`tipo`/
  `fuente`/`nombre` con `address`, y respaldo a `district` cuando `address`
  es `None`), caso sin `station_id` (→ `None`, no crashea), y deduplicación
  por `(station_id, mode, fecha, hora)` → un único nodo por `station_id`
  (dos horas del mismo `station_id`/`mode` colapsan a 1).

## Decisiones no obvias

- **Esquema plano (`lat`/`lon`), no anidado**: se verificó contra el job
  PySpark real desplegado y contra `glue.tf` antes de escribir el SQL, en
  vez de asumir el esquema anidado que sugería el enunciado (basado en
  `aggregate.py`, que es solo la referencia documental/de test de este
  dataset, no lo que corre en Glue) — ver sección de arriba.
- **Un único `GROUP BY station_id`, sin `mode`**: la identidad de nodo es
  el `station_id`, que ya es único por red (peatones vs. bicicletas usan
  prefijos de ID distintos) — agrupar también por `mode` generaría dos
  filas para el mismo punto físico si alguna vez una estación mide ambos
  modos con el mismo `station_id` (no ocurre hoy, pero el criterio de
  identidad de nodo no debe depender de esa casualidad).
- **El fix de partition projection se deja como código, no aplicado**:
  coherente con la restricción explícita del enunciado (no `terraform
  apply`) y con el criterio ya establecido en `NEXT_STEPS.md` (Prioridad 1)
  de no tocar Terraform en caliente sin revisión humana — aunque este
  cambio concreto es pequeño y aislado (dos parámetros de dos tablas), se
  prefiere no romper esa disciplina para una tarea que no es la
  reconciliación general.

## Restricciones respetadas

- No se ha implementado la Fase B (`afluencia_estimada`) — queda para la
  tarea 088, tal como fija `doc/086`.
- No se ha usado ningún naming distinto a `tipo: "aforos_peatones_
  bicicletas"`.
- No se ha tocado `ingesta/capturas/afluencia_lugares_madrid.py` ni
  `populartimes`.
- No se ha cambiado el umbral de `PROXIMO_A` (300 m, tarea 070).
- No se ha ejecutado ningún `terraform apply`/`destroy` — el fix de
  partition projection queda como código, documentado, sin aplicar.
- La comprobación de drift se hizo antes de asumir que Gold tenía datos
  reales, tal como pedía el enunciado — y, al encontrar un problema
  real (aunque de otro tipo, no drift de código), se documentó en vez de
  continuar a ciegas asumiendo que la consulta encontraría filas.

## Relevante para tareas futuras

- **Bloqueo real, no completable sin aplicar Terraform**: `:EstacionMedida
  {tipo: "aforos_peatones_bicicletas"}` está completamente implementado y
  probado, pero con 0 nodos reales hasta que se aplique el fix de
  `projection.date.range`/`projection.fecha.range` ya escrito en
  `infra/terraform/glue.tf`. Aplicarlo (idealmente junto con la
  reconciliación de la Prioridad 1 de `NEXT_STEPS.md`) y relanzar
  `python3 -m grafo.cargar_grafo` es el siguiente paso antes de que la
  tarea 088 (Fase B, `afluencia_estimada`) tenga señal real que cruzar.
- Este mismo tipo de bug (partition projection calibrada para "casi tiempo
  real" aplicada a una fuente cuyo `measured_at` real es histórico) podría
  repetirse en cualquier dataset futuro cuya fuente original publique
  fechas no alineadas con la fecha de ingesta — merece la pena revisar el
  resto de datasets con el mismo patrón si aparece algún otro Gold
  "vacío" sin causa diagnosticada (p. ej. sería la primera pregunta a
  hacerse sobre `aparcamientos`, hoy marcado como "sin diagnosticar" en
  `NEXT_STEPS.md`).
- La comprobación de drift de código (comparar el MD5 embebido en la key de
  S3 del script desplegado contra `md5sum` del fichero local) es un patrón
  barato y reutilizable para verificar, sin `terraform plan` completo (que
  hoy falla por falta de `codebuild:BatchGetProjects`, ver `NEXT_STEPS.md`),
  si el código de un job Glue concreto está al día con `main`.
