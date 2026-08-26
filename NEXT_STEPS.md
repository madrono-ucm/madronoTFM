# Plan de cierre — hacia el 17 de septiembre de 2026

Roadmap priorizado, escrito el 25/8/2026 tras la revisión de arquitectura
de las tareas 083-084 (ver [`PROGRESS.md`](PROGRESS.md) y
[`PLATFORM_SCHEMA.md`](PLATFORM_SCHEMA.md)). Quedan **~3.5 semanas** hasta
la entrega. Prioridades ordenadas por urgencia real, no por orden de
aparición en el repositorio — la número 1 es más urgente que Google Maps lo
fue nunca.

No sustituye al reparto por pista de [`PLAN.md`](PLAN.md#reparto-sin-conflictos)
— cada ítem indica a qué pista pertenece (Sistema / Memoria / Ambos).

## Prioridad 1 — Reconciliar el drift de Terraform (Sistema)

**Por qué es la prioridad más alta**: descubierto el 25/8
(`doc/083-investigacion-google-maps-arquitectura.md`) — el código
Glue/Lambda desplegado en AWS puede no coincidir con `main` (48 objetos de
código desactualizados en el `terraform plan` sin acotar). Esto significa
que **no se puede confiar en que las correcciones ya fusionadas estén
realmente en ejecución** — cualquier verificación futura contra datos
reales hereda esta duda hasta que se resuelva.

1. ~~Añadir `codebuild:BatchGetProjects` al rol `madrono-terraform-deployer`~~
   — **hecho, fuera de este repo, antes de la tarea 088**: el rol real
   (`madrono-terraform-deployerEC2`) no está gestionado por el código
   Terraform de este proyecto (es el rol de instancia EC2 creado a mano en
   el bootstrap de la tarea 014), así que no hay ningún `.tf` que tocar; el
   permiso ya aparece concedido en AWS vía la managed policy
   `AWSCodeBuildAdminAccess` (ver `doc/088-terraform-drift-plan-sin-aplicar.md`,
   Hallazgos 1 y 2). `terraform plan` sin acotar ya completa limpio.
2. **Hecho (tarea 088)**: `terraform plan` sin acotar generado y volcado
   íntegro en `doc/088-terraform-drift-plan-sin-aplicar.md`, con la
   categorización por secciones — **pendiente la revisión humana** de ese
   documento antes de aplicar nada. Resultado real: `5 to add, 15 to
   change, 0 to destroy` (mucho menor que el `53/61/65` de `doc/083` — los
   48 `aws_s3_object.glue_script_*` de aquella sesión ya no aparecen, el
   código Glue desplegado ya coincide con `main`; solo quedan 14
   redespliegues de código Lambda y los 5 recursos de Kafka ya conocidos).
3. **Pendiente**: tras la revisión humana del punto 2, una tarea nueva
   (creada aparte, patrón de dos tareas de `tasks/README.md`) aplica y
   vuelve a verificar en vivo (`aws lambda list-functions`, `aws glue
   get-jobs`, etc.) que el estado post-apply coincide con lo esperado.
4. Documentar en `doc/` el resultado de la tarea 3, igual que cualquier
   otra tarea.

**Advertencia para quien lo ejecute**: `terraform plan -destroy
-target=...` sobre un solo dataset puede arrastrar, por políticas IAM
compartidas, la planificación de destruir **todos** los productores
Lambda — probado el 25/8, no usar `-destroy -target` sin entender el grafo
de dependencias primero.

## Prioridad 2 — Tablas Gold rotas o inalcanzables, causas distintas (Sistema)

| Dataset | Síntoma | Causa | Dónde está documentado |
|---|---|---|---|
| `aparcamientos` | ~~Job `SUCCEEDED`, 0 filas escritas~~ **Resuelto** | Efecto colateral no documentado de la reescritura de lectura incremental (tareas 072/075) — ya no tenía el bug. Verificado con Athena real: 601 filas/día hasta hoy | `doc/090` |
| `cartelera_cines_estrenos` | ~~Job falla (`AnalysisException`)~~ **Resuelto** | Causa real más profunda que "Silver vacío": sin escritor programado de sesiones (solo `sweep_premieres`), la puerta de calidad rechazaba el 100% de los lotes. Añadido `sweep_showtimes`/`event.tipo=="sesiones"` + schedule Terraform; de paso, arreglado un bug real (`Column 'fecha' does not exist`) presente también en `agenda_eventos` (rompiendo producción desde el 08-23) y `bluesky_menciones` | `doc/090` |
| `afluencia_lugares` | Ya no es prioridad — ver tarea 086 | Bloqueado por Google Maps, sustituido | `doc/012`, `doc/083` |
| `aforos_peatones_bicicletas` | Athena devuelve 0 filas pese a que el Parquet real existe en S3 | `projection.date.range`/`projection.fecha.range` del catálogo (`"2026-08-01,NOW+1DAY"`) más estrecho que el `measured_at` real de la fuente (`2024-06-30`, fuente municipal descontinuada desde entonces, confirmado contra `datos.madrid.es`) — partición invisible por fórmula, no por falta de dato. Fix ya escrito en `infra/terraform/glue.tf` (rango ampliado a `"2024-01-01,NOW+1DAY"`), sin aplicar. Su `glue_silver_to_gold.py` también tenía el mismo bug de `fecha` que `cartelera_cines_estrenos` — ya corregido (tarea 090), aunque no verificable en vivo hasta que la fuente vuelva a publicar | `doc/087`, `doc/090` |

Ya no queda ninguna tabla Gold rota sin diagnosticar. Solo sigue pendiente
aplicar el fix de partition projection de `aforos_peatones_bicicletas`
(junto con la Prioridad 1, o antes si se aísla con cuidado) y relanzar
`grafo/cargar_grafo.py`; aun así, no vuelve a ser señal *en vivo* (la
fuente sigue descontinuada) — solo desbloquea el histórico real 2019-2024
para análisis/ML, `afluencia_estimada` (tarea 089) ya no depende de ella.
La tarea 090 dejó además un drift deliberado de Terraform (4 objetos S3 de
script Glue + el zip compartido `procesamiento_source`, ver `doc/090`) que
la Prioridad 1 debe absorber en su reconciliación.

## Prioridad 3 — ~~Implementar la tarea 086 (afluencia por grafo)~~ Hecho, rediseñada (Sistema)

**Hecho (tarea 089), con un diseño distinto al original de esta prioridad**:
la especificación original de la tarea 086 usaba `aforos_peatones_
bicicletas` como señal primaria (proxy real de peatones) — descartada tras
la tarea 087, que confirmó que esa fuente municipal está descontinuada
desde 2024-06-30 (ver `doc/087`). `afluencia_estimada` (tarea 089, ya real
y verificada en vivo) combina en su lugar tráfico + ruido + BiciMAD +
calidad del aire vía el grafo Neo4j (mismo patrón que `trafico_cercano`,
tarea 081) — ver `asistente/README.md`. No depende de la Prioridad 2.

## Prioridad 4 — ~~Resto de tools del asistente~~ Completada (Sistema)

`asistente/README.md` ya documenta el patrón (task 079: una tool de
extremo a extremo por tarea, no varias a la vez). **Las 6 `tools`
originales del esqueleto de la tarea 044 ya tienen lógica real** — no
queda ninguna con `NotImplementedError`:

- ~~`opciones_movilidad`~~ **Hecho (tarea 096)** — simplificación
  deliberada: sin routing real por calles (no existe ningún grafo
  transitable, `CONECTADO_CON` de la tarea 071 solo conecta paradas a lo
  largo de una línea CRTM), describe condiciones de tráfico/BiciMAD/EMT
  cerca de origen y destino por separado, `duracion_estimada_min` queda
  siempre en `None`. Verificado en vivo (`GET /opciones-movilidad`) —
  confirma también la cobertura muy limitada de EMT (fila de abajo:
  "sin datos" en ambos extremos para "Retiro"→"Sol"), ver `doc/096`
- ~~`disponibilidad_aparcamiento`~~ **Hecho (tarea 090)** — real, vía Athena
  directo (una sola tabla, sin grafo), verificado en vivo
  (`GET /disponibilidad-aparcamiento`), ver `doc/090`
- ~~`eventos_cercanos`~~ **Hecho (tarea 095)** — resuelve el lugar contra el
  grafo y filtra por distancia real contra **Silver** de `agenda_eventos`
  (Gold agrega por categoría/distrito/fecha, sin lat/lon por evento;
  `agenda_recintos_madrid` queda fuera, sin pipeline Silver/Gold propio
  todavía), verificado en vivo (`GET /eventos-cercanos`) — encontró y
  corrigió dos bugs reales (columna de partición `fecha` vs `date`, y
  deduplicación por `event_id`), ver `doc/095`
- ~~Persistir `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` como parámetros
  SSM `SecureString`~~ **Ya existen** (confirmado en la tarea 095,
  `/madrono-tfm/dev/secrets/neo4j-*`) — el gap de la tarea 043 se cerró en
  algún momento entre la 081 y la 095, sin documentarlo aquí. Sigue
  pendiente repetir con ellas la verificación completa de `trafico_cercano`/
  `afluencia_estimada` contra Neo4j real (la 081 solo pudo verificar la
  mitad de Athena/Gold), ver `asistente/README.md`.

## Prioridad 5 — CI mínima (Sistema, recomendado no bloqueante)

No existe `.github/workflows/` — nada corre los tests existentes
automáticamente ni habría detectado el drift de la Prioridad 1 antes de
que lo hiciera una sesión manual. Una CI mínima (tests de
`ingesta/`/`procesamiento/`/`grafo/`/`asistente/`/`herramientas/` +
`terraform validate`/`terraform plan` de solo lectura en cada PR) es barata
de montar y da la "posibilidad de review y QA" automática que complementa
la revisión humana de PRs ya existente.

## Prioridad 6 — Memoria (Memoria, y Ambos para §5-§7)

`PLAN.md` ya tiene el reparto exacto por sección
([tabla en PLAN.md](PLAN.md#memoria--reparto-por-sección)) — no se
duplica aquí. Dos añadidos de esta sesión:

- §5 Arquitectura: usar `PLATFORM_SCHEMA.md` como fuente adicional (ya
  verificado contra la cuenta real, no solo contra `doc/`).
- §6.8 Ética/legal: la sección "zona gris académica" de `doc/012` sigue
  siendo contenido válido — el hallazgo de la tarea 083 (Google Maps exige
  facturación incluso en el nivel gratuito) es un dato nuevo y verificado
  que refuerza, no invalida, esa discusión.
- §7.4 Limitaciones: la decisión editorial pendiente en `PLAN.md`
  (bloqueador 3) debería incorporar también el drift de Terraform y las 3
  tablas Gold rotas como limitaciones reales del sistema a fecha de
  entrega, si no se llegan a resolver todas antes del 17/9.

## Prioridad 7 — Gaps menores, sin bloquear nada (Sistema)

- `transporte_publico_emt` Gold solo tiene 1 `stop_id` real distinto
  (`grafo/README.md`) — investigar si es un límite de la fuente EMT o un
  bug de captura.
- `grafo/README.md` sigue diciendo "no existe ninguna instancia Neo4j
  real" pese a que la tarea 080 cargó una — actualizar cuando se toque ese
  directorio por cualquier otro motivo.
- Visibilidad de coste: dar de alta `ce:GetCostAndUsage` sigue pendiente
  (bloqueado antes por el clasificador de seguridad del entorno, `doc/078`)
  — revisar si merece reintentarse antes del cierre.

## Cómo usar este documento

Actualízalo según se cierre cada prioridad (tachar o mover a
`PROGRESS.md` con fecha). No repite lo que ya vive en `PLAN.md` (reparto,
bloqueadores del equipo) — se centra en **qué falta técnicamente y en qué
orden**, con el porqué de cada orden.
