# Plan de equipo — Madroño TFM

Documento vivo de coordinación entre **Filippos Dorezi** y **Víctor Huaman**
hasta la entrega del **17 de septiembre de 2026**. Se actualiza cada semana
(ver [Estado semanal](#estado-semanal)); el reparto de trabajo
(ver [Reparto sin conflictos](#reparto-sin-conflictos)) se revisa solo si
cambia de forma sustancial.

No sustituye a `tasks/README.md` (cómo funciona la cola del agente
autónomo) ni a `doc/README.md` (documentación técnica acumulada, tarea a
tarea) — los complementa: aquí vive la coordinación humana entre los dos;
allí, el detalle técnico de cada pieza.

## Resumen a 23 de agosto

| | |
|---|---|
| Fuentes de datos implementadas | 21 (14 en producción continua) |
| Datasets Silver/Gold en producción | 14 |
| Tareas del agente completadas y fusionadas | 78 |
| Credenciales reales obtenidas | EMT, AEMET, CAMS, Neo4j AuraDB Free |
| Credenciales pendientes | Google Maps |
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

1. ~~Alta de Neo4j AuraDB Free~~ — **resuelto el 24/8.** Instancia real
   creada, credenciales guardadas en SSM (`SecureString`, mismo patrón que
   EMT/AEMET/CAMS) y conexión verificada con una consulta Cypher real
   (`RETURN 1`, base de datos vacía, 0 nodos). Carga real de datos ya
   encolada — ver [`080-cargar-grafo-neo4j-real`](tasks/080-cargar-grafo-neo4j-real.md).
2. **Clave de Google Maps Platform** (`console.cloud.google.com/google/maps-apis/credentials`,
   habilitar Places API). Único bloqueador de credenciales que queda —
   ver [`doc/012-captura-afluencia-lugares-madrid.md`](doc/012-captura-afluencia-lugares-madrid.md).
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

**Próximo número libre: `081`**

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
- [x] **[`080-cargar-grafo-neo4j-real`](tasks/080-cargar-grafo-neo4j-real.md)**
  — en cola. Bloqueador de Neo4j resuelto (ver arriba): ejecuta
  `grafo/cargar_grafo.py` (tareas 067-071) contra la instancia real,
  credenciales leídas de SSM en tiempo de ejecución, verificado con Cypher
  que los 4 tipos de nodo y las 4 relaciones están cargados. `force: false`
  (primera carga real).
- [ ] **Clave de Google Maps** (número pendiente de asignar) — bloqueada
  por la clave. Guardar en SSM, aplicar vía Terraform igual que
  EMT/AEMET/CAMS (ver [`doc/018`](doc/018-captura-aemet-prevision-avisos.md)
  como referencia del patrón), verificar que `afluencia_lugares` deja de
  devolver `is_mock: true`.
- [ ] **Asistente: tool con cruce vía grafo** (número pendiente) — depende
  de que `080` termine y se fusione. Preguntas que cruzan datasets (p. ej.
  "¿hay tráfico cerca de este evento?").
- [ ] **Asistente: resto de tools** (`disponibilidad_aparcamiento`,
  `eventos_cercanos`, `opciones_movilidad`; `afluencia_prevista` bloqueada
  hasta Google Maps) — sin bloqueo salvo la indicada, se pueden ir
  encolando una a una según el mismo patrón que `079`.
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

**Sistema** — Serie de limpieza de duplicados (072–077) cerrada por
completo el 23/8. `079-asistente-tool-calidad-aire` en cola. **Alta de
Neo4j resuelta el 24/8**: instancia AuraDB Free real creada, credenciales
en SSM, conexión verificada con Cypher real — `080-cargar-grafo-neo4j-real`
creada y en cola. Solo queda la clave de Google Maps como bloqueador de
credenciales.

**Memoria** — Sin empezar todavía; el documento actual es el de
planificación original (junio 2026).

**Bloqueadores activos** — Clave de Google Maps.

**Para la semana que viene**
- [x] Resolver el alta de Neo4j (bloqueador crítico) — resuelto 24/8
- [x] Crear y encolar `079-asistente-tool-calidad-aire`
- [x] Crear y encolar `080-cargar-grafo-neo4j-real`
- [ ] Conseguir la clave de Google Maps
- [ ] Empezar a reescribir §5 de la memoria con la arquitectura real
