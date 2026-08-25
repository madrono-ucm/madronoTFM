# Plan de equipo — Madroño TFM

Documento vivo de coordinación entre **Filippos Dorezi** y **Víctor Huaman**
hasta la entrega del **17 de septiembre de 2026**. Se actualiza cada semana
(ver [Estado semanal](#estado-semanal)); el reparto de trabajo
(ver [Reparto sin conflictos](#reparto-sin-conflictos)) se revisa solo si
cambia de forma sustancial.

No sustituye a `tasks/README.md` (cómo funciona la cola del agente
autónomo) ni a `doc/README.md` (documentación técnica acumulada, tarea a
tarea) — los complementa: aquí vive la coordinación humana entre los dos;
allí, el detalle técnico de cada pieza. [`PROGRESS.md`](PROGRESS.md) añade
una bitácora de sesiones de ingeniería interactiva (no del agente),
[`PLATFORM_SCHEMA.md`](PLATFORM_SCHEMA.md) el inventario de plataformas y
[`NEXT_STEPS.md`](NEXT_STEPS.md) el plan priorizado hacia el cierre.

## Resumen a 23 de agosto

| | |
|---|---|
| Fuentes de datos implementadas | 21 (14 en producción continua) |
| Datasets Silver/Gold en producción | 14 |
| Tareas del agente completadas y fusionadas | 78 |
| Credenciales reales obtenidas | EMT, AEMET, CAMS, Neo4j AuraDB Free |
| Credenciales pendientes | ninguna — Google Maps descartado el 25/8, ver bloqueador 2 |
| Bloqueadores críticos | ninguno — Neo4j resuelto el 24/8 |

La serie de incidentes de coste/duplicados en Silver/Gold (tareas
[`072`](tasks/done/072-arreglo-lectura-incremental-glue.md)–[`077`](tasks/done/077-limpieza-duplicados-grupo-diario-resto.md))
está cerrada por completo: los 14 datasets procesan solo datos nuevos por
ejecución y no quedan duplicados conocidos.

**La memoria (`documents/Memoria_TFM FV.docx`) sigue fechada en junio 2026,
sin tocar desde el 11 de agosto** — describe una arquitectura (Kafka +
Flink, Delta Lake, MLflow/Evidently/ONNX, Power BI) que en varios puntos ya
no coincide con lo construido. Antes de escribir más memoria hace falta
alinear ambas cosas — ver [Reparto sin conflictos](#reparto-sin-conflictos).

## Bloqueadores

Solo vosotros podéis desbloquear esto — nada de lo demás avanza sin ello:

1. ~~Alta de Neo4j AuraDB Free~~ — **resuelto y grafo cargado el 24/8.**
   Instancia real creada, credenciales en SSM (mismo patrón que
   EMT/AEMET/CAMS). Grafo completo cargado y verificado con Cypher real:
   9327 nodos (21 Distrito, 131 Barrio, 4738 EstacionMedida, 4056
   ParadaTransporte, 381 Lugar) y 41031 relaciones (`PERTENECE_A`,
   `UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`) — ver
   [`doc/080-cargar-grafo-neo4j-real.md`](doc/080-cargar-grafo-neo4j-real.md).
   **Corrección 25/8**: las 4 credenciales se habían guardado por error en
   `eu-south-2` (esta EC2 cae ahí sin `--region` explícito, bug ya
   conocido del proyecto) en vez de `eu-west-1`, donde vive el resto de
   secretos — la tarea 081 detectó correctamente que no las encontraba en
   `eu-west-1`. Recreadas en `eu-west-1`, verificadas, y borradas las
   copias de `eu-south-2`. **Al guardar cualquier secreto nuevo en SSM,
   usad siempre `--region eu-west-1` explícito.**
2. ~~Clave de Google Maps Platform~~ — **descartado el 25/8, no bloqueador.**
   Verificado a nivel de código (`doc/083-investigacion-google-maps-arquitectura.md`)
   que la librería `populartimes` exige una llamada de pago a la API
   oficial de Google *antes* de poder hacer scraping, sin forma de
   evitarlo — no es un bloqueador de credencial pendiente, es una
   dependencia que este proyecto ha decidido no asumir (coste 0). Se
   sustituye por una señal de afluencia basada en el grafo Neo4j sobre
   `aforos_peatones_bicicletas` (gratis, ya en producción) — especificada
   en la tarea 086 y desglosada en tareas de implementación por debajo (ver
   Pista Sistema) — ver
   [`doc/012-captura-afluencia-lugares-madrid.md`](doc/012-captura-afluencia-lugares-madrid.md)
   para el contexto original y por qué OSM tampoco serviría aquí (solo
   geodatos estáticos, sin ninguna señal de afluencia/popularidad en vivo).
3. **Decisión editorial**: cómo se documenta en la memoria (§7.4
   Limitaciones) el alcance recortado de las fases 3–5 frente al plan
   original — antes de que la Pista Memoria llegue a esa sección (semana
   del 7 sep).

## Reparto sin conflictos

El reparto es por **área del repositorio**, no por tarea suelta, para que
los dos podáis trabajar en paralelo toda la semana sin pisaros commits. Cada
pista es dueña de sus carpetas de principio a fin; si algo cruza de pista,
se avisa en el chat del equipo antes de tocarlo.

| Carpeta / fichero | Pista dueña | Notas |
|---|---|---|
| `infra/`, `procesamiento/`, `ingesta/`, `herramientas/` | **Sistema** | Cola del agente autónomo — ver más abajo |
| `grafo/` | **Sistema** | Código ya escrito; falta instancia real (bloqueador 1) |
| `asistente/` | **Sistema** | Esqueleto ya escrito; falta lógica real |
| `tasks/`, `doc/` | **Sistema** | Los genera la cola del agente — ver [Cola del agente](#cola-del-agente-sin-colisiones-de-número) |
| `documents/Memoria_TFM FV.docx` | **Memoria** | Ver reparto por sección abajo |
| `PLAN.md` (este fichero) | Ambos | Markdown plano — git lo fusiona sin conflicto salvo que los dos editéis la misma línea a la vez |

Al ser un `.docx` binario, **no se puede fusionar con git si los dos lo
editáis a la vez sin coordinaros** — usad Word Online/OneDrive (o pasadlo a
Google Docs mientras se escribe) para coedición en tiempo real, o
turnaos por sección y avisad en el chat al soltar el turno.

### Memoria — reparto por sección

Cada uno escribe la sección que corresponde a lo que ha construido o
validado — así el reparto de la memoria seguirá el mismo criterio que el
del código, sin que nadie tenga que escribir sobre una parte que no conoce
de primera mano.

| Sección | Contenido | Fuente técnica (`doc/`) |
|---|---|---|
| §5 Arquitectura | Reescribir con la pila real (Lambda/EventBridge, Glue+Athena, no Kafka/Delta) | [`doc/001`](doc/001-infraestructura-aws-terraform.md)–[`doc/029`](doc/029-terraform-lambda-eventbridge-plan.md), [`doc/041`](doc/041-piloto-silver-gold-trafico.md) |
| §6.1–6.4 Fuentes, preparación, flujos | Las 21 fuentes, Bronze→Silver→Gold, hora de Madrid | [`doc/002`](doc/002-captura-datos-trafico-madrid.md)–[`doc/024`](doc/024-desbloquear-transporte-publico-emt.md), [`doc/034`](doc/034-bronzewriter-hora-madrid.md)–[`doc/040`](doc/040-arreglo-timeout-aforos.md) |
| §6.5 Orquestación | Glue Triggers nativos, cadencia por dataset | [`doc/064`](doc/064-diseno-scheduling-silver-gold.md), [`doc/065`](doc/065-aplicar-scheduling-silver-gold.md) |
| §6.6 Almacenamiento y consulta | Athena + Partition Projection sobre el catálogo de Glue | [`doc/066`](doc/066-consulta-athena-silver-gold.md), [`doc/068`](doc/068-athena-partition-projection.md) |
| §6.7 Explotación | Grafo + asistente (cuando avancen) | [`doc/043`](doc/043-grafo-neo4j.md), [`doc/044`](doc/044-esqueleto-asistente-fastapi-mcp.md) |
| §6.8 Ética/legal | Ya escrita en el plan original, revisar si sigue vigente | — |
| §7 Resultados, métricas, limitaciones | Con datos reales del sistema (78 tareas, incidente de duplicados como caso de validación) | Todo `doc/072`–[`doc/077`](doc/077-limpieza-duplicados-grupo-diario-resto.md) |

### Cola del agente — sin colisiones de número

`tasks/NNN-slug.md` exige un número de 3 dígitos único y secuencial — es la
única forma de romper la cola si los dos añadís una tarea el mismo día sin
avisaros. Protocolo:

1. **Antes de crear una tarea nueva, `git pull` primero.**
2. El siguiente número libre está siempre en **este documento** (ver abajo)
   — no lo calcules mirando `tasks/done/`, puede haber cambiado desde tu
   último pull.
3. Al crear la tarea, sube en el mismo commit el número siguiente
   actualizado aquí. Si los dos hacéis push a la vez, `git push` fallará
   para el segundo — es lo esperado, no un error real: haced `git pull
   --rebase` y volved a intentarlo con el número correcto.

**Próximo número libre: `087`** (083-086 consumidas el 25/8: investigación
Google Maps/arquitectura, esquema de plataformas, plan de cierre, spec de
afluencia por grafo — ver `PROGRESS.md`).

Nota sobre el orden: las tareas sin bloqueo se numeran y encolan ya; las
bloqueadas por credenciales se numeran **cuando llegan**, no antes, para no
reservarles un hueco que fuerce a esperar a toda la cola (es estrictamente
secuencial, ver `tasks/README.md`). Así se numeró `079` antes que `080`
pese a estar en orden inverso de creación en este documento.

### Pista Sistema

- [x] **[`079-asistente-tool-calidad-aire`](tasks/079-asistente-tool-calidad-aire.md)**
  — en cola. Primera `tool` real del asistente (`calidad_aire`, contra
  `gold.calidad_aire_por_estacion_contaminante_hora` vía Athena), de
  extremo a extremo: MCP montado en FastAPI, respuesta trazable a los
  datos. Alcance deliberadamente acotado a una sola tool — las otras 4 son
  tareas de seguimiento.
- [x] **[`080-cargar-grafo-neo4j-real`](tasks/done/080-cargar-grafo-neo4j-real.md)**
  — **completada.** Grafo cargado y verificado en la instancia real
  (9327 nodos, 41031 relaciones, ver `doc/080-...md`). Incluyó un backfill
  puntual a Bronze real de 3 datasets de referencia estática que nunca se
  habían subido (`barrios_distritos_madrid`, `poi_madrid`,
  `crtm_red_transporte_madrid`) — sin ellos, el grafo se quedaba sin
  `Distrito`/`Barrio`/`PERTENECE_A`/`UBICADO_EN`/`CONECTADO_CON`.
- [ ] **Clave de Google Maps** (número pendiente de asignar) — bloqueada
  por la clave. Guardar en SSM, aplicar vía Terraform igual que
  EMT/AEMET/CAMS (ver [`doc/018`](doc/018-captura-aemet-prevision-avisos.md)
  como referencia del patrón), verificar que `afluencia_lugares` deja de
  devolver `is_mock: true`.
- [x] **[`081-asistente-tool-trafico-cercano-grafo`](tasks/done/081-asistente-tool-trafico-cercano-grafo.md)**
  — **completada** (mitad Athena/Gold verificada contra datos reales; la
  mitad Neo4j no pudo verificarse — ver hallazgo abajo).
- [x] **[`082-verificar-trafico-cercano-neo4j-real`](tasks/082-verificar-trafico-cercano-neo4j-real.md)**
  — en cola. Verifica `trafico_cercano` contra Neo4j real, ahora que el bug
  de región de abajo está corregido.
- [ ] **[`083-grafo-enriquecimiento-poi-osm`](tasks/083-grafo-enriquecimiento-poi-osm.md)**
  — en cola. Enriquece `:Lugar` con etiquetas de OpenStreetMap (Overpass
  API, gratis, sin key) por proximidad — geodatos de lugar, no afluencia
  (OSM no tiene ningún dato de popularidad/tiempo real).
- [ ] **[`084-grafo-nodos-aforos-neo4j-real`](tasks/084-grafo-nodos-aforos-neo4j-real.md)**
  — en cola. Añade `:EstacionMedida {tipo: "aforo"}` (conteos reales de
  peatones/bicicletas, ya en Gold desde la tarea 054) al grafo y recarga la
  instancia real. Paso previo a `085`.
- [ ] **[`085-asistente-tool-afluencia-prevista-aforos`](tasks/085-asistente-tool-afluencia-prevista-aforos.md)**
  — en cola, depende de `084`. Implementa `afluencia_prevista` sobre
  `aforos_peatones_bicicletas` en vez de Google/`populartimes` — quita el
  bloqueo de la clave de Google Maps para esta tool sin esperar la
  credencial.
- [ ] **Asistente: resto de tools** (`disponibilidad_aparcamiento`,
  `eventos_cercanos`, `opciones_movilidad`; `afluencia_prevista` ya no
  bloqueada por Google Maps — rediseñada como señal basada en grafo, ver
  la especificación de la tarea 086) — sin bloqueo, se pueden ir encolando
  una a una según el mismo patrón que `079`.
- [ ] Revisar la herramienta de coste (`herramientas/costes/`, tarea
  [`078`](doc/078-desglose-costes-estimador-presupuesto.md)) una vez por
  semana durante la sincronización — es la forma más rápida de detectar
  otro incidente como el de las tareas 072–077 antes de que crezca.

### Pista Memoria

Ver el reparto por sección de arriba. Como referencia de alcance: la
memoria actual tiene ~19.000 caracteres (166 párrafos no vacíos) — es un
documento de planificación, no un borrador de resultados; la sección 7
(Resultados y conclusiones) está prácticamente vacía de contenido real y es
la que más trabajo nuevo necesita.

## Estado semanal

Formato para cada entrada semanal (añadir una nueva sección arriba de la
más antigua, o al final — decidid un orden y mantenedlo):

```
### Semana del DD–DD mes

**Sistema** — qué se cerró / en qué se sigue / qué está bloqueado
**Memoria** — qué sección se cerró / en qué se sigue
**Bloqueadores activos** — lista corta, o "ninguno"
**Para la semana que viene** — 2–3 objetivos concretos
```

---

### Semana del 24–30 de agosto

**Sistema** — Serie de limpieza de duplicados (072–077) cerrada el 23/8.
`079-asistente-tool-calidad-aire` completada: primera `tool` real del
asistente, contra Athena. **Alta de Neo4j resuelta el 24/8, grafo urbano
cargado y verificado** (9327 nodos, 41031 relaciones — `doc/080-...md`).
`081-asistente-tool-trafico-cercano-grafo` completada (primera tool que
cruza grafo + Athena), pero reveló un bug real: las credenciales de Neo4j
se habían guardado en la región de AWS equivocada (`eu-south-2` en vez de
`eu-west-1`) — corregido el 25/8, `082` en cola para verificar la tool
contra la instancia real ahora que está accesible. De paso, revisando la
factura real de AWS: arreglados dos grupos de logs de Glue sin retención
(~1.78 GB acumulados sin límite) — fijado a 14 días. Solo queda la clave
de Google Maps como bloqueador de credenciales.

**Memoria** — Sin empezar todavía; el documento actual es el de
planificación original (junio 2026).

**Bloqueadores activos** — ninguno.

**25/8 (sesión de arquitectura, fuera del ciclo normal de tareas)** —
investigación de Google Maps + revisión de arquitectura: descartado
Google Maps definitivamente (verificado a nivel de código que no puede dar
datos reales a coste 0, no es un bloqueador de credencial), sustituido por
una señal de afluencia basada en grafo (tarea 086, spec). Se descubrió
además que el estado de Terraform ha derivado de `main` (código
Glue/Lambda desplegado desactualizado respecto al repositorio) — nuevo
bloqueador a reconciliar, ver `NEXT_STEPS.md`. Detalle completo en
`PROGRESS.md` y `doc/083-investigacion-google-maps-arquitectura.md`.

**Para la semana que viene**
- [x] Resolver el alta de Neo4j (bloqueador crítico) — resuelto 24/8
- [x] Crear y encolar `079-asistente-tool-calidad-aire` — completada
- [x] Cargar y verificar el grafo real (`080`) — completada
- [x] Crear y encolar `081-asistente-tool-trafico-cercano-grafo` — completada
- [x] Corregir la región de las credenciales de Neo4j en SSM (25/8)
- [x] Crear y encolar `082-verificar-trafico-cercano-neo4j-real`
- [x] Descartar Google Maps y diseñar su sustituto (25/8, tarea 083/086)
- [ ] Reconciliar el drift de Terraform detectado el 25/8 (ver `NEXT_STEPS.md`)
- [ ] Empezar a reescribir §5 de la memoria con la arquitectura real
