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

1. Añadir `codebuild:BatchGetProjects` al rol `madrono-terraform-deployer`
   (bloquea hoy que `terraform plan` sin acotar termine limpio).
2. Ejecutar `terraform plan` sin acotar, revisarlo **sección por sección
   con un humano** (no aplicar a ciegas) — confirmar que cada cambio es
   esperado (redepliegue de código a la última versión de `main`) y no
   oculta nada más.
3. Aplicar. Volver a verificar con las mismas comprobaciones en vivo usadas
   en la sesión del 25/8 (`aws lambda list-functions`, `aws glue get-jobs`,
   etc.) que el estado post-apply coincide con lo esperado.
4. Documentar en `doc/` el resultado, igual que cualquier otra tarea.

**Advertencia para quien lo ejecute**: `terraform plan -destroy
-target=...` sobre un solo dataset puede arrastrar, por políticas IAM
compartidas, la planificación de destruir **todos** los productores
Lambda — probado el 25/8, no usar `-destroy -target` sin entender el grafo
de dependencias primero.

## Prioridad 2 — Tablas Gold rotas o inalcanzables, causas distintas (Sistema)

| Dataset | Síntoma | Causa | Dónde está documentado |
|---|---|---|---|
| `aparcamientos` | Job `SUCCEEDED`, 0 filas escritas | **Sin diagnosticar** | `doc/052` |
| `cartelera_cines_estrenos` | Job falla (`AnalysisException`) | Silver vacío (0 filas pasan el filtro de calidad) + lectura sin schema explícito | `doc/063` |
| `afluencia_lugares` | Ya no es prioridad — ver tarea 086 | Bloqueado por Google Maps, sustituido | `doc/012`, `doc/083` |
| `aforos_peatones_bicicletas` | Athena devuelve 0 filas pese a que el Parquet real existe en S3 | `projection.date.range`/`projection.fecha.range` del catálogo (`"2026-08-01,NOW+1DAY"`) es más estrecho que el `measured_at` real de la fuente (`2024-06-30`) -- partición invisible por fórmula, no por falta de dato. Fix ya escrito en `infra/terraform/glue.tf` (rango ampliado a `"2024-01-01,NOW+1DAY"`), sin aplicar | `doc/087` |

`aparcamientos` sigue siendo la más urgente de las dos sin diagnosticar
(job "exitoso" que no escribe nada, sin pista real de la causa): la tarea
086 (afluencia por grafo) quiere usar su ocupación como señal secundaria, y
hoy no puede porque su Gold está vacío. `aforos_peatones_bicicletas` ya
tiene diagnóstico y fix escritos (tarea 087) -- solo falta aplicar el
cambio de Terraform (junto con la Prioridad 1, o antes si se aísla con
cuidado) y relanzar `grafo/cargar_grafo.py`.

## Prioridad 3 — Implementar la tarea 086 (afluencia por grafo) (Sistema)

Especificación ya escrita (ver `tasks/086-afluencia-estimada-grafo.md`,
PR pendiente) — sustituye la señal de Google Maps por una compuesta sobre
`aforos_peatones_bicicletas` (proxy real de peatones) + `bicimad`/`trafico`
como señales secundarias + `agenda_eventos` como indicador anticipado, vía
el grafo Neo4j (mismo patrón que `trafico_cercano`, tarea 081). Depende de
la Prioridad 2 (`aparcamientos`) solo si se quiere esa señal desde el
principio — puede implementarse sin ella y añadirla después.

## Prioridad 4 — Resto de tools del asistente (Sistema)

`asistente/README.md` ya documenta el patrón (task 079: una tool de
extremo a extremo por tarea, no varias a la vez):

- `opciones_movilidad` (cruza `trafico`+EMT+BiciMAD)
- `disponibilidad_aparcamiento` (depende de la Prioridad 2)
- `eventos_cercanos` (`agenda_eventos`+`agenda_recintos`)
- Persistir `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD` como parámetros
  SSM `SecureString` (gap documentado desde la tarea 043, causó un bloqueo
  real en la verificación de la tarea 081) — hacerlo junto con cualquiera
  de estas tools evita que se repita.

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
