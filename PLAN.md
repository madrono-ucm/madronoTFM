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
| Fuentes de datos implementadas | 24 (14 en producción continua, 3 nuevas del 25/8 solo en Ingesta — ver `doc/090-...md`) |
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

0. **URGENTE (29/8, activo ahora): 37 de 48 jobs de Glue (77 %) fallan en
   `LAUNCH ERROR`** — la librería compartida `procesamiento.zip` a la que
   apuntan no existe en S3 (varias generaciones distintas del fichero,
   `terraform apply` parciales previos dejaron jobs "anclados" a hashes ya
   borrados). Al menos 28 horas de Bronze→Silver roto para tráfico,
   bicimad, transporte_publico_emt, meteorologia, calidad_aire y
   aparcamientos — 6 de los 16 "productores en producción continua" que
   describe la memoria. **Plan de reconciliación ya generado y verificado
   como seguro** (sin destrucciones sueltas) — ver
   [`FIL_09`](tasks/FIL_09_reparar-glue-libreria-compartida.md) y el plan
   completo en
   [`doc/FIL-09-terraform-plan-glue-libreria-compartida.md`](doc/FIL-09-terraform-plan-glue-libreria-compartida.md).
   Movido de la cola numerada (`tasks/done/106-...md`, redirigida) a la
   pista interactiva porque necesita un `terraform apply` real revisado y
   aprobado por un humano antes de ejecutarse (mismo criterio que las
   tareas 098/100). **Actualización (29/8 tarde)**: el código ya mejoró
   (key estable para `procesamiento.zip`, PR #175, evita que esto vuelva a
   pasar) pero **sigue sin aplicarse** — plan regenerado sobre ese commit,
   misma magnitud y sigue seguro. **Solo falta la aprobación humana para
   el `apply`.**
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

**Próximo número libre: `107`** (106 consumida el 29/8, **URGENTE** — ver
Bloqueadores. 105 consumida el 29/8 por una auditoría
de QA del reentrenamiento nocturno — ver Pista Sistema. 104 consumida el
29/8 por una auditoría
de QA del disco de la EC2 — ver Pista Sistema. 103 consumida el 29/8 por
una auditoría
de QA del track de ML — ver Pista Sistema. 101/102 consumidas el 27/8 por una
auditoría de QA de la tarea 097 — ver Pista Sistema. 100 consumida el 27/8
por una auditoría de
QA de la tarea 098 — ver Pista Sistema. Nota: "099" se usó como etiqueta de
un commit de CI suelto (`09da5eb`) sin crear nunca `tasks/099-*.md`, así
que ese número no tiene fichero propio — se salta para evitar confusión,
no se reutiliza. 095/096 consumidas el 26/8: resto de
tools del asistente (`eventos_cercanos`, `opciones_movilidad`). 097
consumida el 26/8: CI mínima (Prioridad 5 de `NEXT_STEPS.md`). 098
consumida el 26/8: reconciliación real del drift de Terraform (Prioridad 1)
y desbloqueo del Gold de aforos (Prioridad 2) — ver Pista Sistema. Un fix
de CI posterior el mismo día (referenciado como "tarea 099" en el mensaje
de commit) no llegó a crear `tasks/099-...md` ni `doc/099-...md` — de ahí
que `099` siga siendo el próximo número realmente libre, no `100`. 094
consumida el 26/8 por la misma pasada de QA — ver Pista Sistema. 091
consumida el 26/8: `disponibilidad_aparcamiento`, ver
`tasks/done/091-...md`. 092/093 consumidas el 26/8 por una pasada de QA
independiente — ver Pista Sistema. 090 consumida el 25/8: rastreo de nuevos
datasets de `datos.madrid.es` y tres productores nuevos, ver
`doc/090-nuevas-fuentes-parques-ser-emt-incidencias.md`. 083-086 consumidas el 25/8: investigación
Google Maps/arquitectura, esquema de plataformas, plan de cierre, spec de
afluencia por grafo — ver `PROGRESS.md`. 087/089 son la implementación de
esa spec, tomados en la misma sesión al detectar la colisión de números
con una cola de tareas paralela que ya había encolado su propio `083`-`085`
antes de esta sesión de arquitectura — ver la nota junto a `083` en Pista
Sistema. `088` se insertó después, ahead of `089`, para la Prioridad 1 de
`NEXT_STEPS.md` — plan de reconciliación de Terraform, sin aplicar nada).

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
- [x] ~~Clave de Google Maps~~ — **descartado el 25/8** (tarea 083, ver
  Bloqueadores arriba): no se persigue esta credencial, se sustituye por
  una señal basada en grafo (tareas `086`/`087`/`088`).
- [x] **[`081-asistente-tool-trafico-cercano-grafo`](tasks/done/081-asistente-tool-trafico-cercano-grafo.md)**
  — **completada** (mitad Athena/Gold verificada contra datos reales; la
  mitad Neo4j no pudo verificarse — ver hallazgo abajo).
- [x] **[`082-verificar-trafico-cercano-neo4j-real`](tasks/082-verificar-trafico-cercano-neo4j-real.md)**
  — en cola. Verifica `trafico_cercano` contra Neo4j real, ahora que el bug
  de región de abajo está corregido.
- [x] **[`083-investigacion-google-maps-arquitectura`](tasks/done/083-investigacion-google-maps-arquitectura.md)**
  — **completada** (sesión interactiva, PR #127). Descarta Google Maps a
  nivel de código (coste 0 imposible) y descubre drift de Terraform — ver
  `doc/083-...md`, `PROGRESS.md`, `NEXT_STEPS.md` (Prioridad 1).
- [x] **[`084-esquema-plataformas`](tasks/done/084-esquema-plataformas.md)**
  — **completada** (PR #128). `PLATFORM_SCHEMA.md`, inventario verificado
  contra la cuenta AWS real.
- [x] **[`085-plan-cierre-tfm`](tasks/done/085-plan-cierre-tfm.md)**
  — **completada** (PR #129). `NEXT_STEPS.md`, roadmap priorizado hacia el
  17 de septiembre.
- [x] **[`086-afluencia-estimada-grafo`](tasks/done/086-afluencia-estimada-grafo.md)**
  — **completada, solo especificación** (PR #130). Diseña `afluencia_estimada`
  (Fase A grafo + Fase B tool) — implementada por `087`/`088`.
- [x] **[`083-grafo-enriquecimiento-poi-osm`](tasks/done/083-grafo-enriquecimiento-poi-osm.md)**
  — **completada** (demonio, PR #131). **Número duplicado a propósito, no
  renumerado**: se encoló antes de detectar la colisión con la tarea `083`
  de arriba (mismo número, contenido distinto, sesiones distintas); para
  cuando el demonio abrió el PR, el código ya citaba "tarea 083" en
  docstrings/comentarios/tests a lo largo de `grafo/`/`ingesta/` —
  renumerar habría significado reescribir todas esas referencias sin
  ningún beneficio real. Enriquece `:Lugar` con etiquetas de OpenStreetMap
  (Overpass API, gratis, sin key) por proximidad (≤30m) — geodatos de
  lugar, no afluencia. Verificado en vivo contra Overpass real (6 POIs
  reales commiteados como muestra); no se ha recargado la instancia real de
  Neo4j con este enriquecimiento todavía.
- [x] **[`087-grafo-aforos-peatones-bicicletas-neo4j-real`](tasks/done/087-grafo-aforos-peatones-bicicletas-neo4j-real.md)**
  — **completada, código y tests solamente — sin PR** (el demonio se quedó
  parado a mitad de tarea sin llegar a comitear nada, ver el hallazgo junto
  a `083`; se retomó de forma interactiva). Fase A de la especificación
  `086`: añade `:EstacionMedida {tipo: "aforos_peatones_bicicletas"}` al
  pipeline del grafo (código en `main`, 93 tests en verde). **No verificado
  contra Athena real ni recargado en la instancia real de Neo4j** — la
  sesión que lo implementó no tenía credenciales AWS/Neo4j en su entorno
  (ver `doc/087-...md`). Queda como paso pendiente explícito antes de que
  `089` pueda verificarse de extremo a extremo.
- [ ] **[`088-terraform-drift-plan-sin-aplicar`](tasks/088-terraform-drift-plan-sin-aplicar.md)**
  — en cola, insertada por delante de `089` a petición del usuario.
  Prioridad 1 de `NEXT_STEPS.md`: produce el `terraform plan` completo del
  drift descubierto en la tarea `083` (48 objetos de código Glue/Lambda
  desactualizados) para revisión humana — **deliberadamente solo la mitad
  "plan" del patrón de dos tareas** (`allow_infra_apply: false`, no aplica
  nada). La mitad "apply" es una tarea aparte, a crear solo después de que
  un humano revise este plan.
- [x] **[`089-asistente-tool-afluencia-estimada`](tasks/done/089-asistente-tool-afluencia-estimada.md)**
  — **completada** (sesión interactiva, el demonio se quedó sin sesión a
  mitad de tarea -- ver `doc/089-...md`). Implementa `afluencia_estimada`
  combinando tráfico + ruido + BiciMAD + calidad del aire (no
  `aforos_peatones_bicicletas`, descontinuado -- tarea 087) vía el grafo.
  Verificada de extremo a extremo contra Neo4j/Athena reales (23 estaciones
  de tráfico, 3 de BiciMAD, 1 de ruido y 1 de calidad del aire encontradas
  cerca de "Plaza de España", datos reales combinados). El bloqueador de la
  clave de Google Maps queda completamente cerrado: ninguna tool del
  asistente depende ya de él. 39 tests en verde.
- [x] **[`090-nuevas-fuentes-parques-ser-emt-incidencias`](doc/090-nuevas-fuentes-parques-ser-emt-incidencias.md)**
  — **completada** (sesión interactiva, a petición del usuario: rastreo de
  109+10 datasets de `datos.madrid.es` cruzados contra los productores ya
  existentes). Tres productores nuevos, solo Ingesta (sin Silver/Gold ni
  Terraform): `parques_jardines_madrid.py` (llena el hueco de "paseo por
  el parque"), `ser_calles_madrid.py` (aparcamiento en calle, posible vía
  para desbloquear `disponibilidad_aparcamiento`), `emt_incidencias_madrid.py`
  (feed RSS real en vivo, señal para `opciones_movilidad`). Dos candidatos
  de "alta prioridad" del rastreo inicial (ocupación de líneas EMT,
  campañas de aforos) resultaron ser datos anuales al verificarlos, no en
  vivo — descartados, ver `doc/090-...md`.
- [ ] **Asistente: resto de tools** (`eventos_cercanos`,
  `opciones_movilidad`) — sin bloqueo, se pueden ir encolando una a una
  según el mismo patrón que `079` (`disponibilidad_aparcamiento` ya
  completada, ver `tasks/done/091-...md`).
- [ ] **[`092-terraform-fileset-excluir-pycache`](tasks/092-terraform-fileset-excluir-pycache.md)**
  — QA (26/8): `terraform plan`/`apply` crashea con un error de codificación
  si existe `__pycache__/` local bajo `ingesta/` (el `fileset` de
  `lambda.tf` no lo excluye, solo excluye `tests/`/`capturas/samples/`).
  Reproducido en vivo. Riesgo real para quien ejecute el "apply" de la
  Prioridad 1 de `NEXT_STEPS.md` si antes ha corrido los tests localmente.
- [ ] **[`093-recapturar-plan-drift-terraform-real`](tasks/093-recapturar-plan-drift-terraform-real.md)**
  — QA (26/8): el plan de `doc/088` (`5 to add, 15 to change, 0 to
  destroy`) está obsoleto — el `terraform plan` real de hoy da
  `10 to add, 55 to change, 5 to destroy` (cascada de los 4 scripts Glue +
  el zip compartido que la tarea 090 desplegó manualmente a S3). El equipo
  no debe crear la tarea de "apply" de la Prioridad 1 sobre el número
  antiguo.
- [ ] **[`094-recargar-grafo-osm-aforos-instancia-real`](tasks/094-recargar-grafo-osm-aforos-instancia-real.md)**
  — QA (26/8): verificado con Cypher real que la instancia real de Neo4j
  sigue sin el enriquecimiento OSM de la tarea `083` (0 `:Lugar` con campos
  OSM) ni los nodos de aforos de la tarea `087` (conteo de
  `EstacionMedida` sin cambios desde `080`) — ambos documentados como
  pendientes en sus respectivos `doc/`, pero sin ningún ticket accionable
  hasta ahora.
- [x] **[`095-asistente-eventos-cercanos`](tasks/done/095-asistente-eventos-cercanos.md)**
  — **completada** (PR #139). Resuelve el lugar contra el grafo y filtra
  por distancia real contra Silver de `agenda_eventos`; corrigió dos bugs
  reales (columna de partición `fecha` vs `date`, deduplicación por
  `event_id`) — ver `doc/095-...md`.
- [x] **[`096-asistente-opciones-movilidad`](tasks/done/096-asistente-opciones-movilidad.md)**
  — **completada** (PR #141). Última de las 6 `tools` originales del
  esqueleto de la tarea 044 — ya ninguna tiene `NotImplementedError`.
  Simplificación deliberada: sin routing real por calles,
  `duracion_estimada_min` queda en `None` — ver `doc/096-...md`.
- [x] **[`097-ci-minima`](tasks/done/097-ci-minima.md)** — **completada**
  (PR #142). `.github/workflows/ci.yml`: job `tests` (841 tests reales,
  sin credenciales) + job `terraform` (`fmt -check` + `validate`, sin
  backend remoto) en cada PR/push a `main` — Prioridad 5 de
  `NEXT_STEPS.md`, hecha parcial (falta `terraform plan` real, necesita
  credenciales AWS como secreto del repo, decisión de quien administra
  GitHub) — ver `doc/097-...md`. Un fix de seguimiento el mismo día quitó
  una referencia a un `procesamiento/requirements.txt` que nunca existió
  (PR #145), sin `tasks/`/`doc/` propios.
- [x] **[`098-reconciliar-drift-terraform-y-aforos-gold`](tasks/done/098-reconciliar-drift-terraform-y-aforos-gold.md)**
  — **completada** (sesión interactiva, PR #144). Prioridades 1 y 2 de
  `NEXT_STEPS.md` cerradas: `terraform apply` real (50 added, 64 changed,
  50 destroyed, Kafka excluido a propósito) tras resolver un permiso IAM
  (`codebuild:BatchGetProjects`) que faltaba en el usuario local; Gold de
  `aforos_peatones_bicicletas` desbloqueado ampliando la partition
  projection de fechas (1971 filas verificadas en Athena real, antes 0) —
  ver `doc/098-...md`. Ya no queda ninguna tabla Gold rota ni bloqueada.
- [x] **[`100-normalizar-eol-terraform-file-hash`](tasks/done/100-normalizar-eol-terraform-file-hash.md)**
  — **completada** (PR #147). QA (27/8), auditoría de la tarea 098: el
  `terraform plan` seguía mostrando `55/64/50` (add/change/destroy) desde
  esta EC2 pese al `apply` ya hecho — **no era un `apply` incompleto ni una
  regresión**, verificado byte a byte que los 4 scripts de la tarea 090 (y
  el resto) estaban desplegados con el contenido correcto, solo con
  finales de línea `CRLF` (el entorno donde se ejecutó el `apply` real
  normalizaba a `CRLF`; esta EC2 usa `LF`, el repo no tenía
  `.gitattributes`). Añadido `.gitattributes` forzando `LF`.
- [x] **[`101-ci-no-bloquea-nada-force-y-sin-proteccion`](tasks/done/101-ci-no-bloquea-nada-force-y-sin-proteccion.md)**
  — **completada** (PR #148). QA (27/8), auditoría de la tarea 097: la CI
  corre y suele estar en verde, pero no bloqueaba ningún merge real —
  `main` sin branch protection, `force: true` fusionaba sin esperar a los
  checks. Decisión tomada el 28/8 (ver `NEXT_STEPS.md` §"Estado a 28/8",
  decisión 6): **se deja como está** hasta el cierre, documentado como
  limitación real en §7.4 de la memoria (`VIC_06`).
- [x] **[`102-completar-fix-encoding-read-text-tests`](tasks/done/102-completar-fix-encoding-read-text-tests.md)**
  — **completada**. Hallazgo menor de la misma auditoría: 2 ficheros más
  (7 llamadas) con el mismo bug de `read_text()` sin `encoding="utf-8"`
  que la tarea 097 no había cubierto del todo — arreglado.
- [x] **[`103-modelado-ci-y-dependencia-sistema-libgomp`](tasks/done/103-modelado-ci-y-dependencia-sistema-libgomp.md)**
  — **completada**. QA (29/8), verificando si `VIC_05` podía avanzar:
  `ML_02`/`ML_03` (Tier 1) confirmados **realmente completos** (tests en
  verde tras instalar `libgomp1`, que faltaba en esta EC2 y hacía fallar
  LightGBM; métricas reales verosímiles en
  `modelado/evaluation/artifacts/`) — el `status: pending` del
  front-matter estaba simplemente desactualizado, corregido a `done`.
  `modelado/` no estaba en la CI (tarea 097) — arreglado: verificado con
  `gh run list` que la CI corre `modelado/` en verde en cada push/PR
  desde entonces.
- [ ] **[`104-ec2-root-volume-al-limite`](tasks/104-ec2-root-volume-al-limite.md)**
  — QA (29/8): `df -h /` de esta EC2 al 95% (375M libres de 6,7G) — ya
  causó un fallo real (`pip install` con `Disk quota exceeded`) durante
  esta sesión. El stack de ML (`torch`/`lightgbm`/`mlflow`/`onnx`, 934M
  en `~/.local`) pesa mucho más que cuando se aprovisionó la instancia.
  Con `ML_10` corriendo un `cron` de reentrenamiento nocturno en la misma
  instancia, el riesgo ya no es puntual. Propone redimensionar el volumen
  EBS (requiere aprobación, coste marginal) o, como mitigación inmediata
  sin coste, limpieza rutinaria de cachés.
- [ ] **[`105-desplegar-cron-reentrenamiento-nocturno`](tasks/105-desplegar-cron-reentrenamiento-nocturno.md)**
  — QA (29/8): el reentrenamiento nocturno de `ML_10` está construido y
  verificado a mano, pero el `cron.d` real **nunca se instaló**
  (verificado: `/etc/cron.d/` sin él, sin crontab de `ubuntu`) — su
  propio `doc/ML-10` ya lo admitía como "paso de despliegue pendiente".
  Corregida la redacción de la memoria (§5.5/§7.4, decía que ya estaba
  programado) para no sobreclamar; el ticket es para desplegarlo de
  verdad, con aprobación explícita (cron con credenciales AWS recurrente
  y sin supervisión).
- [ ] Revisar la herramienta de coste (`herramientas/costes/`, tarea
  [`078`](doc/078-desglose-costes-estimador-presupuesto.md)) una vez por
  semana durante la sincronización — es la forma más rápida de detectar
  otro incidente como el de las tareas 072–077 antes de que crezca.

### Pista Memoria

Ver el reparto por sección de arriba, y `tasks/VIC_00_README.md` /
`tasks/VIKT_00_README.md` para el detalle ticket a ticket (fuera de la
cola del demonio). **Estado 29/8: los 7 tickets `VIC_*` y los 4 `VIKT_*`
están completos.** `VIKT_*` es una segunda pasada de QA + actualización,
hecha tras aterrizar `ML_04`–`ML_10` (que `VIC_*` no llegó a ver):
`VIKT_01` reconcilió toda la memoria contra el repo real (14
discrepancias, ninguna de dato inventado) y `VIKT_02`–`VIKT_04`
las cerraron — siete tools del asistente (no seis), MLOps real
(MLflow/Evidently/ONNX/reentrenamiento nocturno), Tabla 3 con los números
consolidados de `ML_08`, backtest incremental real en §7.4, y un Anexo C
de reproducibilidad. §1–§7.5 de la memoria reflejan ya la arquitectura y
los resultados reales, sin Kafka/Flink/Delta/Power BI/streaming
presentados como entregados en
ningún sitio fuera de §5.3 (justificación del descarte) y §7.5 (futuras
líneas). La memoria ya no necesita una pasada de "poner al día", solo
revisión editorial humana y las ampliaciones que decida el equipo
(ablaciones de la decisión 8, cuadernos de `ML_08` cuando existan).

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

**26/8** — Cerradas las 6 `tools` originales del esqueleto del asistente:
`095-asistente-eventos-cercanos` y `096-asistente-opciones-movilidad`
completadas, ninguna `tool` tiene ya `NotImplementedError` (Prioridad 4 de
`NEXT_STEPS.md`, completa). `097-ci-minima` añade
`.github/workflows/ci.yml` (tests + `terraform fmt`/`validate` en cada PR,
Prioridad 5, parcial — falta `terraform plan` real con credenciales de
repo). `098-reconciliar-drift-terraform-y-aforos-gold` cierra las
Prioridades 1 y 2: `terraform apply` real aplicado (50 added, 64 changed,
50 destroyed, Kafka excluido a propósito) tras resolver un permiso IAM
que faltaba en el usuario local, y Gold de `aforos_peatones_bicicletas`
desbloqueado (1971 filas verificadas en Athena real, antes 0). Ya no queda
ninguna tabla Gold rota ni bloqueada, ni bloqueador de infraestructura
activo — ver `NEXT_STEPS.md` y `doc/098-...md`. Solo quedan pendientes los
gaps menores de Prioridad 7 y el arranque de la Pista Memoria.

**27–28/8** — QA de las tareas 097/098/100 (tickets `101`/`102`, CI sin
poder de bloqueo real — ver `doc/101`). El 28/8, sesión de arquitectura:
chequeo de salud de todas las fuentes reales + decisión de que el
**modelado ML es el elemento central del TFM** — reparto reorganizado en
tres pistas fuera de la cola del demonio: `FIL_*` (fundación de datos,
Filippos), `VIC_*` (memoria, Víctor) y `ML_*` (a crear). Detalle completo
en `NEXT_STEPS.md` §"Estado a 28/8". La mayoría de `FIL_01`–`FIL_08` ya
cerrada (PRs #150–155).

**29/8** — Los 7 tickets `VIC_*` completados (ver Pista Memoria arriba).
De paso, verificando si `VIC_05` podía avanzar, se confirmó
independientemente que `ML_02`/`ML_03` (Tier 1) estaban realmente
terminados (front-matter desactualizado, corregido) y se encontró que
`modelado/` no tiene cobertura de CI (ticket `103`). Decisión tomada al
escribir `VIC_05`: las ablaciones de §7.3 ("decisión 8" de
`NEXT_STEPS.md`) se descartan para esta entrega por tiempo — recomendado
revisar esta decisión con el equipo si aparece margen antes del 17/9.
Más tarde el mismo día aterrizaron `ML_04`–`ML_10` (PRs #159–#168), así
que se creó una segunda tanda de tickets (`VIKT_01`–`VIKT_04`) para
reconciliar la memoria otra vez: `VIKT_01` (QA de solo lectura) encontró
14 discrepancias, ninguna de dato inventado, y `VIKT_02`–`VIKT_04` las
cerraron — siete tools del asistente, MLOps real (MLflow/Evidently/ONNX/
reentrenamiento nocturno vía cron), Tabla 3 con los números consolidados
de `ML_08`, backtest incremental real en §7.4 y un Anexo C de
reproducibilidad. Los 11 tickets de memoria (`VIC_*` + `VIKT_*`) quedan
completos.

**Para la semana que viene**
- [x] Resolver el alta de Neo4j (bloqueador crítico) — resuelto 24/8
- [x] Crear y encolar `079-asistente-tool-calidad-aire` — completada
- [x] Cargar y verificar el grafo real (`080`) — completada
- [x] Crear y encolar `081-asistente-tool-trafico-cercano-grafo` — completada
- [x] Corregir la región de las credenciales de Neo4j en SSM (25/8)
- [x] Crear y encolar `082-verificar-trafico-cercano-neo4j-real`
- [x] Descartar Google Maps y diseñar su sustituto (25/8, tarea 083/086)
- [x] Reconciliar el drift de Terraform detectado el 25/8 (26/8, tarea 098
  — ver `NEXT_STEPS.md`)
- [x] Empezar a reescribir §5 de la memoria con la arquitectura real —
  completada y ampliada a **toda la memoria** (29/8, `VIC_01`–`VIC_07`,
  los 7 tickets cerrados)
- [x] Crear los tickets numerados de ML (`modelado/`, Tier 0–4) —
  `ML_01`–`ML_06` creados y en su mayoría cerrados (ver `NEXT_STEPS.md`)
- [ ] Resolver/revisar la decisión 8 (ablaciones de §7.3) con el equipo
  si hay margen antes del cierre — de momento descartadas, documentado en
  `VIC_05`
- [ ] Cerrar `modelado/` en la CI (ticket `103`)
