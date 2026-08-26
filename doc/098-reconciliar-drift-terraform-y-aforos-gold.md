# 098 — Reconciliar el drift de Terraform (Prioridad 1) y desbloquear el Gold de aforos (Prioridad 2)

## Contexto

`NEXT_STEPS.md` llevaba desde el 25/8 marcando esto como la prioridad más
alta: el código Glue/Lambda desplegado en AWS podía no coincidir con
`main`, y el plan real capturado en `doc/093` (10 to add, 55 to change, 5
to destroy) llevaba pendiente de revisión humana y `apply` desde entonces.
Retomado interactivamente tras la auditoría en vivo de esta sesión.

## Bloqueo real encontrado antes de poder planificar nada

`terraform plan` desde este entorno (identidad `madrono-terraform-deployer`,
usuario IAM local, no la instancia EC2 que usaron sesiones anteriores)
fallaba con:

```
AccessDeniedException: User: .../madrono-terraform-deployer is not
authorized to perform: codebuild:BatchGetProjects on resource:
.../madrono-tfm-dev-lambda-dependencies-layer
```

`NEXT_STEPS.md` ya documentaba que este permiso se había concedido, pero
**a una identidad distinta**: el rol de instancia `madrono-terraform-
deployerEC2` de la EC2 desde la que se ejecutó `doc/093`, no el usuario IAM
`madrono-terraform-deployer` usado en este entorno local. Sin ese permiso,
`terraform plan` no podía refrescar el estado de
`aws_codebuild_project.lambda_dependencies_layer`, lo que en cascada
producía un plan **incorrecto e inflado** (55 to add / 64 to change / 50 to
destroy, incluyendo recursos sin relación aparente) en vez de un error
claro.

**Arreglo** (con aprobación explícita del usuario, quien lo aplicó a mano
en la consola de IAM tras que el clasificador de seguridad del entorno
bloqueara automatizarlo): política inline `terraform-lambda-layer-
codebuild` en el usuario `madrono-terraform-deployer`, con permisos
acotados al ARN exacto de ese proyecto de CodeBuild (`BatchGetProjects`,
`CreateProject`, `UpdateProject`, `DeleteProject`, `BatchGetBuilds`,
`StartBuild`, `ListBuildsForProject`) — no la política gestionada
`AWSCodeBuildAdminAccess` completa (más amplia de lo necesario, y además
bloqueada por la cuota de 10 políticas gestionadas por usuario, ya al
límite).

## El plan real, tras arreglar el permiso: mucho más grande de lo esperado, pero explicable

Con el permiso corregido, `terraform plan` completó sin errores:
**55 to add, 65 to change, 50 to destroy** — bastante más que los 10/55/5
de `doc/093` (25/8). Verificado con detalle línea a línea antes de tocar
nada real:

- **50 "must be replaced"**: todos `aws_s3_object` de scripts de Glue
  (`glue-scripts/<script>-<hash-md5>.py`, la clave S3 incluye un hash del
  contenido). Como se han fusionado muchas correcciones a `main` desde el
  último `apply` real (incluida la propia tarea 090 de esta sesión, con
  sobrescrituras directas a S3 fuera de Terraform para 4 scripts), casi
  todos los scripts tienen ahora un hash distinto al que Terraform tenía en
  estado → "replace", no "update", porque la clave completa cambia.
  Verificado que cada reemplazo va emparejado, en el mismo plan, con la
  actualización del `aws_glue_job` correspondiente (`command.script_location`
  y `default_arguments."--extra-py-files"` apuntando a la nueva clave) — sin
  ninguna ventana donde un job apunte a un script ya borrado.
- **65 "update in-place"**: 13 funciones Lambda (nuevo `source_code_hash`,
  mismo código empaquetado con las correcciones ya fusionadas), el resto de
  `aws_glue_job` (mismo motivo que arriba), el proyecto de CodeBuild
  (metadata menor), y las **2 tablas de `aforos_peatones_bicicletas`**
  (Prioridad 2, ver abajo). Una política IAM (`scheduler_invoke_lambda`)
  aparecía como "recomputada" por completo (`-> (known after apply)`) por
  depender de atributos de recursos en actualización — verificado que el
  contenido semántico (los 14 ARNs de Lambda con permiso de invocación) no
  cambiaba.
- **5 "to add"**: la infraestructura de Kafka (`aws_instance.kafka` +
  seguridad/IAM), de la tarea 042 — **deliberadamente sin aplicar nunca**,
  documentado así en `doc/088`/`doc/093`. Aplicarlo habría significado
  levantar una instancia EC2 real sin que nadie lo hubiera pedido.

**Cero destrucciones reales**: verificado explícitamente (`grep "will be
destroyed"` sobre el plan completo → 0 resultados puros); el "50 to
destroy" del resumen es la mitad-destrucción de los 50 pares de reemplazo
de scripts ya descritos arriba, no una eliminación de datos ni de
infraestructura en uso.

## Excluir Kafka de un `apply` sin `-exclude` (no soportado en esta versión de Terraform)

Terraform 1.15 no tiene `-exclude` en `plan`/`apply`. En vez de editar
`kafka.tf` (arriesgado, cambia código trackeado) se generó la lista de los
329 recursos **ya existentes en el state real** (`terraform state list`,
menos `data.*`) y se repitió el `plan` con esos 329 como `-target`
explícitos — como Kafka no está en el state y nada de lo targeteado
depende de él, el plan resultante es idéntico al plan completo menos
exactamente los 5 recursos de Kafka (verificado con un `diff` línea a línea
entre ambos listados de recursos antes de aplicar nada).

## Aplicado

`terraform apply` del plan acotado (con aprobación explícita del usuario,
el clasificador de seguridad del entorno bloquea `apply` sin ella cada
vez): **50 added, 64 changed, 50 destroyed**, sin errores. Un
`terraform plan` posterior sin `-target` confirma el estado deseado: **5 to
add** (solo Kafka, tal como se pretendía), **0 to change, 0 to destroy**.

## Verificación en vivo (no solo `terraform apply` en verde)

```
aws glue get-job — script_location apunta ya a la nueva clave S3 con hash
aws lambda get-function trafico — CodeSha256 nuevo, LastModified de hoy
aws glue get-table aforos_peatones_bicicletas (Silver) —
  projection.fecha.range = "2024-01-01,NOW+1DAY" (antes "2026-08-01,...")
```

**Prioridad 2 (Gold de `aforos_peatones_bicicletas`) — antes 0 filas, ahora
real:**

```sql
SELECT count(*) FROM aforos_peatones_bicicletas          -- Silver: 1971
SELECT count(*) FROM aforos_peatones_bicicletas_por_estacion_modo_hora  -- Gold: 1971
```

Sin necesidad de ningún `MSCK REPAIR` ni recarga: la partición por
proyección (`partition projection`) de Athena se calcula en el momento de
la consulta, así que ampliar el rango en el catálogo de Glue fue
suficiente para que el Parquet histórico ya existente en S3 (2019-2024,
fuente municipal descontinuada desde 2024-06-30, ver `doc/087`) se
volviera visible de inmediato.

## Qué queda fuera de esta tarea

- La infraestructura de Kafka (tarea 042) sigue deliberadamente sin
  aplicar — no se ha tocado.
- `afluencia_estimada` (tarea 089) ya no depende de
  `aforos_peatones_bicicletas`, así que este desbloqueo no cambia ninguna
  señal *en vivo* del asistente — solo habilita análisis/ML sobre el
  histórico 2019-2024 ya real y accesible.
- No se ha relanzado `grafo/cargar_grafo.py`: los nodos de aforos que
  entrarían al grafo (tarea 087) siguen siendo trabajo de otra tarea si se
  decide usarlos — este fix solo restaura el acceso a través de Athena.

## Relevante para tareas futuras

- Cualquier sesión que ejecute Terraform localmente (no desde la EC2
  original) debe verificar primero si su identidad IAM tiene los mismos
  permisos que `madrono-terraform-deployerEC2` — no asumir que "ya se
  concedió" sin comprobar contra la identidad real en uso
  (`aws sts get-caller-identity`).
- Un plan de Terraform con números muy distintos a la última captura
  documentada no implica necesariamente drift nuevo real — puede ser un
  plan incompleto/erróneo por un permiso faltante. Verificar que el plan
  termine sin errores antes de comparar cifras.
- `terraform plan`/`apply` sin `-exclude` (no disponible en esta versión)
  puede acotarse de forma segura a "todo lo que ya está en `state`" vía
  `terraform state list` + `-target` repetido, cuando lo que se quiere
  excluir es precisamente infraestructura que nunca se ha creado.
