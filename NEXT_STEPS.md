# Plan de cierre — hacia el 17 de septiembre de 2026

Roadmap priorizado, escrito el 25/8/2026 tras la revisión de arquitectura
de las tareas 083-084 (ver [`PROGRESS.md`](PROGRESS.md) y
[`PLATFORM_SCHEMA.md`](PLATFORM_SCHEMA.md)). Quedan **~3.5 semanas** hasta
la entrega. Prioridades ordenadas por urgencia real, no por orden de
aparición en el repositorio — la número 1 es más urgente que Google Maps lo
fue nunca.

No sustituye al reparto por pista de [`PLAN.md`](PLAN.md#reparto-sin-conflictos)
— cada ítem indica a qué pista pertenece (Sistema / Memoria / Ambos).

## Prioridad 1 — ~~Reconciliar el drift de Terraform~~ Hecho (Sistema)

**Hecho (tarea 098)**: el plan real (recapturado, `10 to add, 55 to
change, 5 to destroy` según `doc/093` había subido a `55/65/50` por más
trabajo fusionado entre medias) se aplicó completo salvo la infraestructura
de Kafka (tarea 042, deliberadamente excluida vía `-target` sobre los 329
recursos ya en `state`, no vía `-exclude` — no soportado en esta versión de
Terraform). `terraform apply`: **50 added, 64 changed, 50 destroyed**, sin
errores. Un `terraform plan` posterior sin acotar confirma el estado
deseado: solo Kafka pendiente (`5 to add, 0 to change, 0 to destroy`).

Bloqueo real encontrado y resuelto en el camino: el usuario IAM local
(`madrono-terraform-deployer`) no tenía el permiso `codebuild:
BatchGetProjects` que sí tenía el rol de instancia EC2
(`madrono-terraform-deployerEC2`) usado por sesiones anteriores — sin él,
`terraform plan` fallaba en cascada y mostraba cifras infladas/incorrectas
en vez de un error claro. Arreglado con una política inline acotada al
ARN exacto del proyecto de CodeBuild (no la managed policy completa,
bloqueada además por la cuota de 10 políticas/usuario). Ver `doc/098` para
el detalle completo, incluida la verificación línea a línea de cada uno de
los ~170 cambios antes de aplicar nada.

## Prioridad 2 — ~~Tablas Gold rotas o inalcanzables~~ Hecho (Sistema)

| Dataset | Síntoma | Causa | Dónde está documentado |
|---|---|---|---|
| `aparcamientos` | ~~Job `SUCCEEDED`, 0 filas escritas~~ **Resuelto** | Efecto colateral no documentado de la reescritura de lectura incremental (tareas 072/075) — ya no tenía el bug. Verificado con Athena real: 601 filas/día hasta hoy | `doc/090` |
| `cartelera_cines_estrenos` | ~~Job falla (`AnalysisException`)~~ **Resuelto** | Causa real más profunda que "Silver vacío": sin escritor programado de sesiones (solo `sweep_premieres`), la puerta de calidad rechazaba el 100% de los lotes. Añadido `sweep_showtimes`/`event.tipo=="sesiones"` + schedule Terraform; de paso, arreglado un bug real (`Column 'fecha' does not exist`) presente también en `agenda_eventos` (rompiendo producción desde el 08-23) y `bluesky_menciones` | `doc/090` |
| `afluencia_lugares` | Ya no es prioridad — ver tarea 086 | Bloqueado por Google Maps, sustituido | `doc/012`, `doc/083` |
| `aforos_peatones_bicicletas` | ~~Athena devuelve 0 filas pese a que el Parquet real existe en S3~~ **Resuelto (tarea 098)** | `projection.date.range`/`projection.fecha.range` ampliado de `"2026-08-01,NOW+1DAY"` a `"2024-01-01,NOW+1DAY"`, aplicado de verdad. Verificado con Athena real tras el `apply`, sin ningún `MSCK REPAIR`: **1971 filas** en Silver y en Gold (antes 0) | `doc/087`, `doc/090`, `doc/098` |

Ya no queda ninguna tabla Gold rota ni bloqueada. `aforos_peatones_
bicicletas` sigue sin ser señal *en vivo* (la fuente municipal está
descontinuada desde 2024-06-30) — el desbloqueo da acceso real al
histórico 2019-2024 para análisis/ML; `afluencia_estimada` (tarea 089) no
dependía de ella. Pendiente, si se decide usarlo: relanzar
`grafo/cargar_grafo.py` para que los nodos de aforos entren también al
grafo (tarea 087) — fuera del alcance de la 098, que solo restauraba el
acceso vía Athena.

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

## Prioridad 5 — ~~CI mínima~~ Hecho, parcial (Sistema)

**Hecho (tarea 097)**: `.github/workflows/ci.yml`, dos jobs en cada PR/push
a `main` — `tests` (841 tests reales de `ingesta/`/`procesamiento/`/
`grafo/`/`asistente/`/`herramientas/`, ninguno necesita credenciales) y
`terraform` (`fmt -check` + `validate`, sin backend remoto —
`init -backend=false`, deliberadamente sin necesitar credenciales AWS como
secreto de este repositorio). De paso corrigió el nit de formato real que
`doc/090`/`doc/093` ya habían dejado en `lambda.tf` (bloqueaba
`fmt -check`) y 3 tests con `read_text()` sin `encoding="utf-8"` explícito
(fallaban en Windows, nunca en Linux -- por eso no se habían visto en CI
hasta ahora, que no existía).

**Sigue pendiente, fuera de esta tarea**: `terraform plan` de solo lectura
en cada PR -- necesita credenciales AWS reales como secreto del
repositorio (recomendado: rol OIDC de solo lectura, no claves estáticas),
una decisión que le corresponde a quien administra el repositorio en
GitHub, no a esta tarea.

**QA (tarea 101)**: la CI corre y suele estar en verde, pero hoy no
bloquea ningún merge real -- `main` no tiene branch protection
(`gh api .../branches/main/protection` → 404) y las tareas `force: true`
fusionan su PR (`merge_pr()`, `tasks/scripts/gh_git.py:164`) sin esperar en
absoluto a que los checks de CI terminen. `doc/101-...md` documenta las dos
recomendaciones (activar branch protection exigiendo los checks `tests` +
`terraform`, y hacer que `merge_pr()` espere a los checks antes de
fusionar) con el comando/diseño ya listos para aplicar -- pendientes de
aprobación humana explícita antes de ejecutarse, ninguno aplicado todavía.

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
