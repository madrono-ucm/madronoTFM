# 043 — Grafo urbano en Neo4j: decisión, esquema e infraestructura (sin aplicar)

## Qué se implementó

Primera pieza del grafo urbano en Neo4j que describe la memoria (apartado
5.2), sobre lugares/estaciones de medida/conexiones de transporte. A
diferencia de Kafka (tarea 042, ya decidido con el usuario), aquí la decisión
seguía abierta. **Alcance de esta tarea: investigar, decidir con criterio,
escribir el esquema inicial y documentar — sin crear ninguna instancia real
ni cargar ningún dato.**

## Decisión: Neo4j AuraDB Free, no autogestionado en EC2

Investigadas en vivo las condiciones vigentes (agosto 2026) del tier gratuito
de AuraDB: gratis para siempre (no un trial), sin tarjeta de crédito, pausa
automática a los 3 días de inactividad (reversible con un clic/llamada a la
API), borrado solo tras 90 días pausada, snapshots manuales bajo demanda
(sin backup automático programado), y un límite de tamaño con **discrepancia
real entre fuentes oficiales de Neo4j** (200k nodos/400k relaciones según la
FAQ, 50k/175k según otras páginas de producto — documentado explícitamente,
sin resolver a ciegas).

Se eligió **AuraDB Free** frente a autogestionar en EC2 porque, a diferencia
de Kafka (donde el equivalente gestionado más barato, MSK, tiene un suelo
real de ~$75/mes y no existe tier gratuito), aquí la opción gestionada **es
literalmente gratis**, y el volumen real de entidades del proyecto (21
distritos, ~131 barrios, unos pocos miles de puntos de tráfico/EMT/BiciMAD/
estaciones sumados entre todos los tipos de nodo) queda muy por debajo de
ambas cifras del límite documentado, incluso en el escenario más
conservador. Autogestionar habría costado ~$15-20/mes (instancia +EBS,
estimación análoga a la de Kafka en doc/042) más el mantenimiento
(parcheo, backups a construir desde cero) que AuraDB Free resuelve sin
coste. La pausa por inactividad a los 3 días se acepta como fricción menor
para un proyecto de TFM con actividad intermitente, reversible sin pérdida
de datos. Detalle completo de la comparación, con tabla y fuentes citadas,
en `infra/neo4j/README.md`.

## Alta de AuraDB Free: bloqueo manual documentado (mismo patrón que EMT/AEMET/CAMS)

Crear la instancia real requiere entrar en la consola web de Neo4j Aura
(<https://console.neo4j.io>) y pulsar "Create instance" — un paso interactivo
en navegador que no se puede completar desde este pipeline sin supervisión
humana, de la misma naturaleza que los bloqueos ya documentados de EMT
(doc/003), AEMET (doc/018) y CAMS (doc/019). Se documenta el proceso completo
de alta (4 pasos) en `infra/neo4j/README.md`, junto con las variables de
entorno que necesitaría el proyecto para conectarse
(`NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE`, sin
hardcodear nada). No se ha añadido ningún parámetro SSM placeholder en
`infra/terraform/` para estas variables porque, a diferencia de
`AEMET_API_KEY`/`CAMS_ADS_API_KEY`, todavía no existe ningún proceso de carga
(Lambda/Glue) que las vaya a consumir — se documenta como el paso a dar
cuando exista ese proceso, no antes.

## Esquema inicial del grafo (código versionado, sin ejecutar)

`infra/neo4j/schema/schema.cypher`: constraints de unicidad, índices de
propiedad e índices espaciales (`POINT INDEX`, característica nativa de
Cypher, no depende de APOC) para 4 tipos de nodo:

- `:Distrito`, `:Barrio` (jerarquía administrativa, de `barrios_distritos_madrid`, doc/010).
- `:Lugar` (POIs, aparcamientos, cines, grandes recintos — un único label con
  `tipo` como discriminador, no un label por dataset).
- `:EstacionMedida` (tráfico, calidad del aire, ruido — solo identidad/
  ubicación, **sin duplicar series temporales**, que siguen en Gold/Athena).
- `:ParadaTransporte` (EMT, BiciMAD, CRTM).

Y 4 tipos de relación documentados como contrato (Neo4j no permite forzar el
tipo de una relación con un constraint): `PERTENECE_A` (Barrio→Distrito),
`UBICADO_EN` (point-in-polygon contra Barrio, a calcular por el futuro ETL),
`PROXIMO_A` (proximidad genérica entre cualquier par de nodos con ubicación,
con `distancia_m`), `CONECTADO_CON` (adyacencia real de la red de transporte,
con `modo`/`linea`, lo que hace de `ParadaTransporte` un grafo navegable).

No se ha ejecutado `schema.cypher` contra ninguna instancia (no existe
ninguna real todavía) ni se ha cargado ningún dato de ejemplo — es esquema
puro, tal como pedían las restricciones de la tarea.

## Sin ningún fichero `.tf` nuevo

Al elegir AuraDB Free (SaaS externo a AWS, sin coste) no hay ninguna
infraestructura AWS que aprovisionar para el propio Neo4j — a diferencia de
si se hubiera elegido autogestionado en EC2, que sí habría necesitado
`infra/terraform/neo4j.tf` con el mismo criterio de security group/rol IAM de
acceso mínimo que la tarea 042 aplicó a Kafka. `infra/terraform/README.md` se
actualizó con una nota explicando esta ausencia deliberada, para que no
parezca un olvido en una revisión futura.

## Restricciones respetadas

- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales (no aplica: no se creó ningún fichero `.tf` para Neo4j).
- No se ha creado ninguna instancia real de AuraDB (bloqueada en un paso
  manual de consola, documentado igual que EMT/AEMET/CAMS) ni se ha
  capturado ninguna credencial real en ningún fichero commiteado.
- No se ha cargado ningún dato real ni de ejemplo en ningún grafo — ETL
  Gold → Neo4j queda fuera de alcance de esta tarea.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- Primer paso real pendiente: que un humano complete el alta de AuraDB Free
  y fije las 3-4 variables de entorno en un gestor de secretos — mismo
  bloqueo pendiente que AEMET/CAMS (docs 018/019), documentado en
  `infra/neo4j/README.md`.
- El proceso de carga Gold → Neo4j (fuera de alcance aquí) es candidato
  natural para extender el patrón de `procesamiento/silver_gold/` (doc/041):
  un módulo que calcule `UBICADO_EN`/`PROXIMO_A`/`CONECTADO_CON` desde Gold y
  haga `MERGE` contra Neo4j vía el driver oficial `neo4j` (PyPI, Python puro).
  Es también el momento de añadir los parámetros SSM de las credenciales de
  Neo4j que esta tarea, a propósito, no creó todavía.
- Verificar en la consola real de Aura, en el momento del alta, cuál de las
  dos cifras de límite de tamaño documentadas (200k/400k vs 50k/175k) es la
  vigente — discrepancia real entre páginas oficiales de Neo4j, sin resolver
  en esta tarea por falta de acceso a una instancia real.
- Si el grafo se acercara algún día al límite real del tier Free o
  necesitara alta disponibilidad/backup automático, la vía de escape
  documentada es AuraDB Professional (de pago, mismo proveedor, sin
  migración de esquema) antes que plantear autogestionar en EC2.
