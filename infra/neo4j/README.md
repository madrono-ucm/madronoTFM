# Grafo urbano en Neo4j — tarea 043

La memoria del TFM (apartado 5.2) describe un grafo urbano en Neo4j construido
sobre la capa Gold del lakehouse: lugares, estaciones de medida y conexiones de
transporte, modelados como nodos y relaciones para consultas de proximidad y
conectividad que un modelo relacional/tabular (Athena sobre Gold) expresa mal
o de forma cara (p.ej. "estaciones de calidad del aire a menos de 300m de un
parque", "ruta con menos trasbordos entre dos paradas"). A diferencia de Kafka
(tarea 042, ya decidido de antemano por el usuario), aquí la decisión seguía
abierta. **Esta tarea la resuelve y deja la infraestructura/esquema
correspondiente escritos, sin aplicar ni cargar nada real.**

## Decisión: Neo4j AuraDB Free, no autogestionado en EC2

Se elige **AuraDB Free** (SaaS gestionado por Neo4j, tier gratuito) en vez de
un Neo4j autogestionado en una EC2 dedicada. Resumen de la comparación (detalle
de cada punto más abajo):

| | AuraDB Free | Autogestionado en EC2 |
|---|---|---|
| Coste mensual | **$0**, para siempre (no es un trial con caducidad) | ~$15-20/mes (instancia + EBS, estimación análoga a la de Kafka en doc/042) |
| Tarjeta de crédito para el alta | No requerida | N/A (coste ya sale de la cuenta AWS del proyecto) |
| Mantenimiento (parcheo, versión de Neo4j) | A cargo de Neo4j | A cargo del proyecto |
| Backups | Snapshots manuales bajo demanda, retenidos 90 días, exportables; **sin backup automático programado** en el tier Free | Ninguno por defecto — habría que construirlo (script + cron/Lambda + S3), trabajo adicional no trivial |
| Alta disponibilidad | Ninguna (instancia única, igual que EC2) | Ninguna con un solo nodo (mismo límite que Kafka en doc/042) |
| Límites de tamaño | 200k nodos / 400k relaciones (ver discrepancia de fuentes más abajo) — o 50k/175k según la página más conservadora | Sin límite salvo el hardware de la instancia |
| Pausa por inactividad | Se pausa a los 3 días sin actividad; se reanuda con un clic/llamada a la API; se borra si sigue pausada 90 días | No aplica (la instancia sigue encendida y facturando mientras exista) |
| Acceso programático | Bolt/`neo4j+s://` estándar, mismos drivers oficiales que cualquier Neo4j — sin restricción para uso automatizado/headless | Igual, más el trabajo de asegurar la instancia (security group, SSM) |

**Por qué pesa más el coste y el mantenimiento que el límite de tamaño**: el
grafo de este proyecto es, por diseño, un grafo de *entidades* (distritos,
barrios, lugares, estaciones, paradas de transporte) con sus relaciones
espaciales — no un grafo de *medidas* (las series temporales de tráfico/aire/
ruido siguen en Gold/Athena, fuera de Neo4j, ver el esquema más abajo). Los
volúmenes reales de entidades de Madrid son pequeños comparados con cualquiera
de los dos límites documentados del tier Free:

- 21 distritos, ~131 barrios (doc/010).
- Puntos de tráfico: cientos (doc/002 documenta miles de mediciones por
  captura, pero el número de **puntos de medida distintos**, que es lo que
  sería un nodo aquí, es de un orden mucho menor — la capa Gold de tráfico
  agrega por `point_id`, doc/041).
- Paradas EMT: del orden de 4.000-4.500 en toda la red de Madrid.
- Estaciones BiciMAD: unas 600.
- Estaciones de calidad del aire/ruido: unas pocas decenas cada una.
- POIs turísticos, aparcamientos, cines, grandes recintos: cientos, no miles.

Incluso sumando todos los tipos de nodo con generosidad, el proyecto se queda
muy por debajo de 50k nodos — el límite más conservador de los dos que
documenta Neo4j (ver "Discrepancia de fuentes" abajo) — y las relaciones
(proximidad + conectividad de transporte) crecen de forma acotada respecto a
los nodos, no de forma combinatoria. No hay ningún escenario realista de este
proyecto en el que el límite del tier Free sea el factor limitante frente al
coste/mantenimiento de una EC2 dedicada.

**Pausa por inactividad**: es el único riesgo real de AuraDB Free frente a
autogestionado, y se acepta conscientemente. Este es un proyecto de TFM con
actividad intermitente (no un servicio en producción con tráfico continuo);
una base de datos que se pausa a los 3 días sin uso y se reanuda con un clic o
una llamada a la API de gestión de Aura (sin pérdida de datos, solo un pausado
reversible) es una fricción menor comparada con mantener una EC2 encendida
24/7 (~$15-20/mes) solo para evitarla. El borrado solo ocurre tras 90 días
*pausada* sin reanudar — un margen amplio para un proyecto activo.

**Backups**: el tier Free no ofrece backup automático programado, solo
snapshots manuales bajo demanda (retenidos 90 días, exportables como fichero
`.backup`/`.dump`). Es una limitación real, pero equivalente en la práctica a
lo que tendría un Neo4j autogestionado en EC2 sin trabajo adicional (ahí
tampoco hay backup automático por defecto: habría que construirlo). Y, sobre
todo, **Neo4j en este proyecto no es la fuente de verdad de los datos** —
Gold en S3 (versionado, con lifecycle propio, ver doc/001) lo es; el grafo se
reconstruye desde Gold por el futuro proceso de carga (ver "Qué falta para
cargar datos reales" abajo), así que perder el contenido de Neo4j sería
recuperable sin backups propios, a diferencia de Bronze/Gold.

### Discrepancia de fuentes sobre los límites exactos

Al investigar las condiciones vigentes (agosto de 2026), se encontró una
discrepancia real entre dos páginas oficiales de Neo4j: la
[FAQ de AuraDB](https://neo4j.com/cloud/platform/aura-graph-database/faq/)
cita 200k nodos / 400k relaciones para el tier Free, mientras que otras
páginas de producto citan 50k nodos / 175k relaciones. No se ha podido
contrastar cuál es la vigente ahora mismo contra la consola real de Aura (no
hay una instancia creada todavía, ver bloqueo de alta abajo). Para esta
decisión el número exacto es irrelevante — como se argumenta arriba, el
proyecto se queda muy por debajo de ambos límites incluso en el escenario más
conservador — pero conviene verificarlo en la consola de Aura en el momento
del alta real, no dar por buena ninguna de las dos cifras a ciegas.

### Por qué esta decisión es la contraria a la de Kafka (doc/042), y por qué eso es coherente

Kafka se autogestionó en EC2 precisamente **por coste**: el equivalente
gestionado más barato (MSK) tiene un suelo de coste real de ~$75/mes incluso
en su configuración mínima — no existe un tier gratuito de MSK utilizable para
este proyecto. Con Neo4j la comparación es la inversa: AuraDB Free es
**literalmente gratis**, no solo "más barato" que autogestionar. El criterio
de decisión (coste mínimo, apartado 5.4 de la memoria) es el mismo en ambos
casos; lo que cambia es qué opción lo cumple mejor en cada caso.

## Alta de AuraDB Free: paso manual bloqueado en este entorno

Crear una instancia de AuraDB Free requiere entrar en la
[consola de Neo4j Aura](https://console.neo4j.io) con una cuenta (email o
SSO), sin tarjeta de crédito, y pulsar "Create instance" — un paso interactivo
en un navegador que **no se puede completar desde este pipeline sin
supervisión humana**, de la misma naturaleza que el alta de EMT (doc/003), de
AEMET (doc/018) o de CAMS (doc/019): no es un CAPTCHA ni una verificación de
email en este caso, es simplemente una acción de consola web que exige una
sesión de usuario real. Se documenta aquí como bloqueo explícito, igual que en
esas tareas, en vez de intentar rodearlo.

**Lo que hace falta, cuando alguien complete el alta:**

1. Entrar en <https://console.neo4j.io>, crear una cuenta si no existe una ya.
2. "Create instance" → tipo **AuraDB Free** → región (elegir una cercana a
   `eu-west-1`, donde vive el resto de la infraestructura AWS del proyecto —
   Aura no garantiza colocar Free en la misma nube/región que AWS, es un
   servicio SaaS independiente de AWS).
3. Aura genera y muestra **una sola vez** el usuario (`neo4j` por defecto) y
   la contraseña inicial, junto con el URI de conexión
   (`neo4j+s://<id>.databases.neo4j.io`). Guardarlos en un gestor de secretos
   — **nunca en un fichero de este repositorio**.
4. Ejecutar el esquema inicial contra la instancia ya creada:
   ```bash
   cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" \
     -f infra/neo4j/schema/schema.cypher
   ```

Ninguno de estos 4 pasos se completó en la tarea 043 (esta), cuando se
escribió lo de arriba — no existía instancia, ni credencial, ni dato.

**Actualización (28/8): los 4 pasos están hechos.** La instancia AuraDB Free
real se creó en la tarea 080; las credenciales viven en SSM
(`/madrono-tfm/dev/secrets/neo4j-*`, `eu-west-1` — confirmado en la tarea
095); el esquema (`schema.cypher`) se aplicó el 26/8 (tarea 094, ver
"Esquema inicial del grafo" abajo); y `grafo/cargar_grafo.py` ha cargado el
grafo completo tres veces (tareas 080/087/094). Los párrafos siguientes
sobre "cómo se conectaría" y "no existe ningún proceso de carga" describen
el estado de la tarea 043 y ya no son vigentes — se conservan como
histórico del diseño.

## Cómo se conectaría el proyecto (variables de entorno, sin hardcodear nada)

Mismo patrón que el resto de credenciales del proyecto (`AEMET_API_KEY`,
`CAMS_ADS_API_KEY`, `EMT_CLIENT_ID`/`EMT_PASS_KEY`, ver `ingesta/README.md`):
variables de entorno, nunca valores hardcodeados en código ni commiteados.

| Variable | Descripción |
|---|---|
| `NEO4J_URI` | URI de conexión Bolt, p.ej. `neo4j+s://<id>.databases.neo4j.io` |
| `NEO4J_USERNAME` | Usuario (`neo4j` por defecto en una instancia Aura recién creada) |
| `NEO4J_PASSWORD` | Contraseña generada por Aura al crear la instancia (o rotada después) |
| `NEO4J_DATABASE` | Nombre de la base de datos dentro de la instancia (`neo4j` por defecto; AuraDB Free solo permite una) |

No se ha añadido ningún parámetro SSM placeholder en `infra/terraform/` para
estas variables (a diferencia de `AEMET_API_KEY`/`CAMS_ADS_API_KEY`, que sí
tienen su placeholder en `lambda.tf`): esos placeholders existen porque ya hay
una función Lambda real que los consume como variable de entorno
(`local.producers[*].secret_env`). Todavía no existe ningún proceso de carga
Gold → Neo4j (depende de que la agregación por barrio/distrito de la tarea
041 se extienda a más datasets, fuera de alcance de esta tarea) que vaya a
leer estas variables, así que añadir el parámetro SSM ahora sería
infraestructura sin ningún consumidor. Cuando se implemente ese proceso de
carga (Lambda, Glue job, o script manual), es el momento de añadir
`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` como parámetros SSM
`SecureString` con el mismo patrón que las credenciales ya existentes.

## Esquema inicial del grafo

Definido como código versionado en
[`infra/neo4j/schema/schema.cypher`](schema/schema.cypher): constraints de
unicidad, índices de propiedad e índices espaciales (`POINT INDEX`) para
cuatro tipos de nodo, más el contrato documentado (en comentarios, ya que
Neo4j no permite forzar el "tipo" de una relación con un constraint) de los
tipos de relación. No carga ningún dato, solo declara el esquema.

**Aplicado contra la instancia real el 26/8 (tarea 094)** -- quedó
pendiente desde que se creó la instancia (tarea 080) hasta que un QA
posterior lo detectó: sin los constraints `..._id_unique`, cada
`MERGE (n:Label {id: $id})`/`MATCH (a {id: ...})` de `grafo/cypher.py` hacía
un escaneo completo sin índice sobre miles de nodos existentes -- probado
en vivo, un `python3 -m grafo.cargar_grafo` real quedó colgado **3 horas**
(96s de CPU real sobre 3h de reloj, la propia consulta `PROXIMO_A`
confirmada como cuello de botella con `SHOW TRANSACTIONS`) antes de
aplicar el esquema; el mismo recargue completo tras aplicarlo tardó unos
20 minutos (dominado por el cómputo de `relaciones.ubicado_en`, point-in-
polygon en Python puro contra ~131 barrios por cada uno de ~9000 nodos, no
por la base de datos). Ver `doc/094-recargar-grafo-osm-aforos-instancia-
real.md` para el detalle completo.

### Tipos de nodo

| Label | Qué representa | Dataset(s) Gold de origen |
|---|---|---|
| `:Distrito` | Los 21 distritos administrativos de Madrid | `barrios_distritos_madrid` (doc/010) |
| `:Barrio` | Los ~131 barrios, cada uno perteneciente a un distrito | `barrios_distritos_madrid` (doc/010) |
| `:Lugar` | Sitio de interés con ubicación fija: POI turístico, aparcamiento, cine, gran recinto... (`tipo` distingue el subtipo) | `poi_madrid` (doc/011), `aparcamientos_madrid` (doc/005), `cartelera_cines_madrid` (doc/023), `agenda_grandes_recintos_madrid` (doc/022) |
| `:EstacionMedida` | Punto fijo de medición: tráfico, calidad del aire, ruido (`tipo` distingue cuál). Solo identidad/ubicación — las series temporales de medidas siguen en Gold/Athena, no se duplican en Neo4j | `trafico_madrid` (doc/002), `calidad_aire_madrid` (doc/006), `ruido_madrid` (doc/007) |
| `:ParadaTransporte` | Nodo de la red de transporte: parada EMT, estación BiciMAD, parada/estación CRTM (metro, cercanías...) | `transporte_publico_emt` (doc/003), `bicimad` (doc/004), `crtm_red_transporte` (doc/021) |

### Tipos de relación

| Relación | Entre | Propiedades | Significado |
|---|---|---|---|
| `PERTENECE_A` | `(:Barrio)->(:Distrito)` | — | Jerarquía administrativa |
| `UBICADO_EN` | `(:Lugar\|:EstacionMedida\|:ParadaTransporte)->(:Barrio)` | — | El barrio que contiene el punto (point-in-polygon, calculado por el futuro ETL) |
| `PROXIMO_A` | Cualquier par de nodos con `ubicacion` | `distancia_m` | Proximidad espacial por debajo de un umbral (a decidir por el ETL que la genere) |
| `CONECTADO_CON` | `(:ParadaTransporte)->(:ParadaTransporte)` | `modo`, `linea` | Adyacencia real de la red de transporte (paradas consecutivas de una línea) — es lo que hace de `ParadaTransporte` un grafo navegable, no solo puntos con proximidad |

Decisiones de diseño explicadas con más detalle como comentarios en el propio
`schema.cypher` (por qué un solo label `:Lugar` en vez de uno por dataset, por
qué `EstacionMedida` no guarda medidas, por qué `PROXIMO_A` es genérico entre
tipos de nodo). Resumen de las más relevantes:

- **`EstacionMedida` no almacena series temporales.** El grafo modela
  identidad y relaciones espaciales; las medidas (valores de tráfico/aire/
  ruido en el tiempo) siguen viviendo en Gold, consultables vía Athena/BI. Un
  proceso de análisis combinaría ambos: Neo4j para "qué estaciones están
  cerca de este barrio", Gold para "qué midió esa estación la semana pasada".
- **Un único label `:Lugar` para POIs/aparcamientos/cines/recintos**, con
  `tipo` como discriminador, en vez de un label por dataset. Todos comparten
  el mismo patrón de relaciones (`UBICADO_EN`, `PROXIMO_A`); separarlos en
  labels distintos solo complicaría las consultas de "qué hay cerca de aquí"
  sin aportar nada que `tipo` no dé ya — mismo principio de no crear
  abstracciones que el resto del proyecto ya sigue.
- **`PROXIMO_A` es genérico** entre cualquier combinación de tipos de nodo
  con ubicación (Lugar↔Lugar, EstacionMedida↔Lugar, ParadaTransporte↔Lugar...)
  en vez de una relación específica por combinación, porque la semántica
  ("estos dos puntos están cerca") no depende de qué tipos sean.
- **La agregación por barrio/distrito, deliberadamente pendiente de esta
  tarea** (ver doc/041, "la agregación por distrito... queda deliberadamente
  pendiente de la tarea 043"): este esquema define `UBICADO_EN` como la
  relación que resuelve exactamente ese punto-en-polígono, pero no la
  calcula — eso es trabajo del futuro proceso de carga Gold → Neo4j, no de
  esta tarea (que es solo esquema/infraestructura, sin ETL).

## Qué no se ha hecho en esta tarea

- No se ha creado ninguna instancia de AuraDB Free real (bloqueada en un paso
  manual de consola, ver arriba) ni ninguna EC2 en AWS.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales — no hay, de hecho, ningún fichero `.tf` nuevo en esta tarea: al
  elegir AuraDB Free (SaaS externo a AWS) no hay infraestructura AWS que
  aprovisionar para el propio Neo4j (a diferencia de si se hubiera elegido
  autogestionado en EC2, que sí habría necesitado `infra/terraform/neo4j.tf`).
- No se ha ejecutado `schema.cypher` contra ninguna instancia real.
- No se ha cargado ningún dato real ni de ejemplo en ningún grafo — ETL
  Gold → Neo4j queda fuera de alcance, depende de que la agregación por
  barrio/distrito exista en Gold para más datasets que solo tráfico (doc/041).
- No se ha capturado ninguna credencial real en ningún fichero commiteado.

## Relevante para tareas futuras

- El primer paso real hacia un grafo funcionando es que un humano complete el
  alta de la instancia AuraDB Free (paso 1-3 de "Alta de AuraDB Free" arriba)
  y fije `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` en un gestor de
  secretos — igual que sigue pendiente el alta de AEMET/CAMS (doc/018/019).
- Antes de dar por buena la elección de región de Aura, conviene medir la
  latencia real Aura↔AWS `eu-west-1` si el proceso de carga corre desde
  Lambda/Glue en esa región — Aura Free no permite elegir explícitamente
  "misma región que mi cuenta AWS" del mismo modo que MSK/RDS, así que la
  región más cercana disponible en el momento del alta puede no ser
  exactamente `eu-west-1`.
- El proceso de carga Gold → Neo4j (fuera de alcance de esta tarea) es el
  candidato natural para extender el patrón de `procesamiento/silver_gold/`
  (doc/041): un nuevo módulo que lea Gold (parquet en S3), calcule
  `UBICADO_EN` (point-in-polygon contra `barrios_distritos_madrid`) y
  `PROXIMO_A`/`CONECTADO_CON`, y haga `MERGE` contra Neo4j vía el driver
  oficial (`neo4j` en PyPI, Python puro, sin fricción de empaquetado nativo).
- Si en el futuro el grafo se acerca al límite real del tier Free (verificar
  cuál de las dos cifras documentadas es la vigente, ver "Discrepancia de
  fuentes" arriba) o necesita alta disponibilidad/backup automático, la vía
  de escape es AuraDB Professional (de pago, mismo proveedor, sin migración
  de esquema) antes que plantear autogestionar en EC2 — evita repetir el
  trabajo de mantenimiento que esta decisión evitó desde el principio.
- Verificar en la consola real de Aura, en el momento del alta, los límites
  exactos vigentes (200k/400k nodos-relaciones según la FAQ, 50k/175k según
  otras páginas de producto) — no se ha podido resolver esta discrepancia sin
  acceso a una instancia real.

## Fuentes consultadas

- [Neo4j AuraDB — Frequently Asked Questions](https://neo4j.com/cloud/platform/aura-graph-database/faq/)
  (límites de tamaño del tier Free, pausa por inactividad a los 3 días,
  borrado a los 90 días pausada, sin tarjeta de crédito requerida).
- [Neo4j Aura — Backup, export, restore, and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)
  y [How Do Backups Work in Neo4j Aura?](https://aura.support.neo4j.com/hc/en-us/articles/360037560093-How-Do-Backups-Work-in-Neo4j-Aura-)
  (snapshots bajo demanda en el tier Free, retención de 90 días, sin backup
  automático programado en Free).
- [AWS blog — "Create Amazon MSK clusters with T3 brokers for less than
  $2.50/day"](https://aws.amazon.com/blogs/big-data/create-amazon-msk-clusters-with-t3-brokers-for-less-than-2-50-a-day/)
  y `doc/042-kafka-autogestionado.md` (estimación de coste de EC2
  autogestionado usada aquí por analogía, mismo tipo de instancia mínima
  viable para un piloto de un solo nodo).
