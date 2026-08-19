# 065 — Aplicar el scheduling de Silver/Gold en producción y verificar un disparo real

## Qué se ha aplicado en AWS (región `eu-west-1`, cuenta `222234418587`)

Los 28 `aws_glue_trigger` diseñados (sin aplicar) en la tarea 064
(`infra/terraform/glue_scheduling.tf`) — 14 `SCHEDULED` (Bronze→Silver) + 14
`CONDITIONAL` (Silver→Gold, predicado: el Bronze→Silver correspondiente en
`SUCCEEDED`) — están creados y `ACTIVATED` en AWS real, uno por cada
combinación dataset×etapa de los 14 datasets del pipeline. Confirmado con
`aws glue get-triggers` (28 triggers, todos `State: ACTIVATED`).

### Cómo se aplicó: `terraform apply` targeted no era viable, se usó boto3 + `terraform import`

`terraform plan -target=aws_glue_trigger....` (necesario para no tocar
`lambda.tf`/`kafka.tf`, con deriva no relacionada ya documentada en tareas
anteriores) arrastraba, como dependencia transitiva, un cambio real y no
relacionado con esta tarea: el zip de `procesamiento/` en
`aws_s3_object.procesamiento_source` estaba desactualizado frente al código
commiteado en `main` (su hash MD5 cambió, `archive_file` lo detecta por
contenido) y por tanto los 14 `aws_glue_job` Bronze→Silver mostraban un
cambio pendiente en `--extra-py-files`. Terraform 1.15 no tiene `-exclude`
(solo `-target`), y `-target` sobre cualquier trigger arrastra el job Glue
completo del que depende (incluido ese cambio no relacionado) — no hay forma
de aplicar solo el trigger sin aplicar también esa deriva ajena al alcance
de esta tarea.

Para no tocar esa deriva (fuera de alcance, no descrita por el prompt), se
crearon los 28 triggers directamente con `boto3`/`glue.create_trigger`
replicando exactamente los atributos que generaba el plan de Terraform
(`Name`, `Type`, `Schedule`, `Actions`, `Predicate` con `Logical=AND` y
`LogicalOperator=EQUALS` por condición, `StartOnCreation=true`, y los tags
`Environment/ManagedBy/Project` que aplicaría el `default_tags` del
provider) y después se importaron los 28 recursos a state con
`terraform import` (uno a uno; cada import tarda 1-2 min por el tamaño ya
grande del state remoto en S3, ~10-15 min en total). Verificado después con
`terraform plan -target=...` sobre los 4 recursos de triggers: sin este
cambio residual, el único diff mostrado son los mismos 14+1 recursos ajenos
(`aws_glue_job`/`aws_s3_object.procesamiento_source`) ya presentes antes de
esta tarea — **no se ha tocado ni aplicado esa deriva**, sigue pendiente de
una tarea futura que reconcilie explícitamente el paquete `procesamiento/`
desplegado en S3 con el código de `main`.

### Ajuste de código necesario: `lifecycle { ignore_changes = [start_on_creation] }`

`start_on_creation` es un argumento de solo escritura: la API de Glue
(`GetTrigger`) no lo devuelve, así que tras `terraform import` el state no
puede refrescarlo y quedaba en `false` (valor por defecto), mostrando un
diff perpetuo `+ start_on_creation = true` en `terraform plan` aunque los 28
triggers reales ya estén `ACTIVATED`. Se ha añadido
`lifecycle { ignore_changes = [start_on_creation] }` a los 4 bloques
`resource "aws_glue_trigger"` de `glue_scheduling.tf` para que el plan
targeted quede limpio (confirmado: `terraform plan -target=<los 4 recursos
de trigger>` ya no muestra ningún cambio en los propios triggers, solo la
deriva ajena de `procesamiento_source`/`aws_glue_job` ya descrita arriba).

## Verificación end-to-end forzada (3 datasets representativos)

Se forzó el disparo con `aws glue start-trigger` sobre el trigger
`SCHEDULED` de 3 datasets: `meteorologia` (grupo horario), `ruido` (grupo
diario) y `aemet_prevision_avisos` (estructura de dos pares Gold en un solo
job).

| Dataset | Job Bronze→Silver forzado | Run ID | Resultado |
|---|---|---|---|
| `meteorologia` | `madrono-tfm-dev-meteorologia-bronze-to-silver` | `jr_129d9f840a86ac738ae8bb4867d53e8a912947d56aa050b2dde41e6e3ef05b8d` | `SUCCEEDED` |
| `ruido` | `madrono-tfm-dev-ruido-bronze-to-silver` | `jr_f8d743b0d74b2b986a6dd93d79b7fc9709458a2fc02f5c2e7e8b9f35951b3dd3` | `SUCCEEDED` |
| `aemet_prevision_avisos` | `madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver` | `jr_063e0d47d013ca09cc4c500c91619150ff87e7813adb95637785d64335dafd9c` | `SUCCEEDED` |

Los 3 jobs Bronze→Silver forzados terminaron con éxito.

### Hallazgo: el trigger `CONDITIONAL` no encadenó automáticamente Silver→Gold en la ventana observada

Tras confirmar el éxito de los 3 jobs Bronze→Silver (hacia las 23:37-23:38
UTC), se comprobó repetidamente durante los minutos siguientes (hasta
~23:41 UTC, ventana de observación de unos 5 minutos) el último `job-run` de
cada job Silver→Gold correspondiente
(`aws glue get-job-runs --job-name ... --max-results 1`): en los 3 casos el
run más reciente seguía siendo una ejecución **anterior a esta sesión**
(`ruido`: 2026-08-19T22:37, ya visto en la tarea 062; `meteorologia`:
2026-08-16T15:17; `aemet_prevision_avisos`: 2026-08-19T22:59, de la
verificación manual de la tarea 063) — ninguno con `TriggerName` asociado
(todas esas ejecuciones previas fueron lanzadas a mano con
`start-job-run`, no por un trigger). Es decir: **en la ventana de
observación de esta sesión, el trigger `CONDITIONAL` no lanzó una nueva
ejecución de Silver→Gold** pese a que su predicado (`Bronze→Silver en
SUCCEEDED`) se cumplió y el trigger está `ACTIVATED` con el predicado
correcto (`aws glue get-trigger` confirma `Logical: AND`,
`Conditions: [{JobName: ..., LogicalOperator: EQUALS, State: SUCCEEDED}]`).

**No se ha depurado más allá de esta comprobación** (instrucción explícita
de la tarea: documentar, no depurar indefinidamente) por el límite de tiempo
de la sesión. Posibles causas no descartadas, para una tarea de
seguimiento: (a) la documentación de AWS Glue indica que la evaluación de
triggers `CONDITIONAL` puede tardar varios minutos en dispararse tras el
evento observado (no instantáneo), por lo que es posible que el disparo
llegara después del cierre de esta sesión — recomendado para la tarea de
seguimiento: comprobar `aws glue get-job-runs` sobre los 3 jobs Silver→Gold
sin forzar nada, más tarde; (b) que un trigger creado vía `create_trigger`
(boto3) en vez de a través del flujo nativo de un evento de scheduling de
Glue no reciba el mismo evento interno de cambio de estado que
dispara la evaluación del predicado — no confirmado, y de ser así afectaría
solo a la forma de aplicación de esta tarea (boto3 + import), no al diseño
en sí, ya que el mismo trigger disparado por su propio cron `SCHEDULED`
(sin intervención manual) debería generar el evento nativo sin este
problema.

## Los 28 triggers: confirmados creados y `ACTIVATED`

Confirmado con una única llamada `aws glue get-triggers` (28/28,
`State: ACTIVATED` en todos):

**Grupo horario (6 datasets × 2 triggers = 12)**: `trafico`,
`transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
`meteorologia` — cada uno con su `-scheduled-bronze-to-silver` y
`-conditional-silver-to-gold`.

**Grupo diario (8 datasets × 2 triggers = 16)**: `ruido`,
`cartelera_cines_estrenos`, `agenda_eventos`, `bluesky_menciones`,
`aemet_prevision_avisos`, `cams_calidad_aire`, `afluencia_lugares`,
`aforos_peatones_bicicletas` — mismo patrón de dos triggers cada uno.

De estos 14 datasets, 3 (`meteorologia`, `ruido`, `aemet_prevision_avisos`)
tienen verificado el disparo real forzado de su Bronze→Silver (ver tabla
arriba); el resto (11) se han confirmado solo como creados/`ACTIVATED` vía
`aws glue get-trigger`/`get-triggers`, sin forzar su disparo.

## Restricciones respetadas

- No se ha ejecutado `terraform destroy`.
- No se ha tocado `infra/terraform/lambda.tf` ni la ingesta Bronze — la
  deriva de `lambda.tf`/`kafka.tf` visible en `terraform plan` sin
  `-target` sigue sin aplicarse, igual que en tareas anteriores.
- No se ha aplicado la deriva no relacionada del zip de `procesamiento/`
  en `aws_s3_object.procesamiento_source` ni los 14 `aws_glue_job`
  Bronze→Silver que dependen de él — descubierta como efecto colateral de
  `-target`, documentada arriba, deliberadamente evitada con el enfoque
  boto3+import para no exceder el alcance descrito por esta tarea.
- El comportamiento inesperado del trigger `CONDITIONAL` (no observado
  disparar Silver→Gold en la ventana de esta sesión) se documenta como
  hallazgo, no se ha intentado depurar más allá de la comprobación descrita.
- `backend.hcl` (copia local de `backend.hcl.example`, cubierta por
  `.gitignore`) y los artefactos de `terraform init`/`plan`
  (`.terraform/`, `.terraform.lock.hcl`, `build/`, ficheros `tfplan*`) se
  eliminan al terminar la sesión — no se commitea nada de esto.

## Relevante para tareas futuras

- **Verificar sin forzar nada** si los 3 triggers `CONDITIONAL` de
  `meteorologia`/`ruido`/`aemet_prevision_avisos` dispararon Silver→Gold
  después del cierre de esta sesión (`aws glue get-job-runs --job-name
  madrono-tfm-dev-<dataset>-silver-to-gold --max-results 1`, comprobar si
  `StartedOn` es posterior a esta sesión y si `TriggerName` está poblado).
  Si sí dispararon con retraso, el diseño es correcto y solo hacía falta
  más margen de espera del que permitió el presupuesto de esta sesión. Si
  no, hace falta investigar por qué un trigger `CONDITIONAL` creado por
  boto3 (en vez de por el flujo nativo `terraform apply`) no reacciona al
  evento de finalización del job vigilado — y, si se confirma, sería
  necesario recrear esos triggers (o los 28) a través de un `terraform
  apply` real una vez resuelta la deriva del zip de `procesamiento/`
  documentada arriba, en vez de mantenerlos como creados por boto3 +
  importados.
  automatización de scheduling.
- Antes de asumir que `terraform plan -target=<recurso>` sobre un recurso
  aparentemente aislado (como un `aws_glue_trigger` que solo referencia
  `.name` de un job) no arrastra nada más: Terraform incluye el plan
  completo de cualquier dependencia transitiva con cambios pendientes, no
  solo el atributo específico referenciado — en esta tarea eso convirtió
  una aplicación "solo triggers" en una aplicación que también habría
  tocado 14 `aws_glue_job` y reemplazado un `aws_s3_object`, fuera del
  alcance descrito. Cuando eso ocurra y el resto del diff sea código
  legítimo pero fuera de alcance, crear el recurso nuevo directamente vía
  API (boto3/CLI) e importarlo a `terraform import` es una alternativa
  viable para no arrastrar esa deriva ajena al `apply`.
- El zip `procesamiento/` desplegado en S3
  (`aws_s3_object.procesamiento_source`) sigue desactualizado frente al
  código de `main` — sigue pendiente desde antes de esta tarea (no
  introducido por ella) y bloquea cualquier `terraform apply` limpio que
  toque los 14 `aws_glue_job` Bronze→Silver o el propio objeto S3. Una
  tarea de seguimiento debería aplicarlo explícitamente (fuera del alcance
  de esta tarea, que solo cubre los triggers).
