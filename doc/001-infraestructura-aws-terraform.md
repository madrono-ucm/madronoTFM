# 001 — Infraestructura base en AWS (Terraform)

## Qué se implementó

Proyecto Terraform completo en `infra/terraform/` con el andamiaje base del
lakehouse medallón para la Fase 1 (Ingesta) del TFM:

- `versions.tf`: fija Terraform `>= 1.7.0, < 2.0.0` y el provider `aws` `~> 5.0`;
  declara (sin rellenar) el backend remoto `s3`.
- `variables.tf`: región, nombre/entorno de proyecto, capas del medallón,
  parámetros de ciclo de vida y principals de confianza del rol de ingesta.
- `main.tf`: provider, 3 buckets S3 (`bronze`/`silver`/`gold`, uno por capa),
  versionado, cifrado SSE-S3, bloqueo de acceso público, política de ciclo de
  vida, bucket policy que exige TLS, y un rol/policy IAM de ingesta con
  permisos de solo-escritura sobre Bronze.
- `outputs.tf`: nombres/ARNs de los buckets y ARN del rol/policy de ingesta.
- `README.md`: explica cada recurso, el paso 0 manual (crear a mano el bucket
  de estado + tabla DynamoDB de lock, con comandos `aws` documentados pero no
  ejecutados), cómo se correría `terraform init/plan/apply` manualmente, y —
  el punto más importante— la lista concreta de acciones IAM (S3, IAM,
  DynamoDB, STS) que necesita la identidad que ejecute `apply`, con un
  ejemplo de policy JSON.
- `backend.hcl.example` y `terraform.tfvars.example`: plantillas para el
  backend y las variables reales, que no se commitean.
- `.gitignore` propio en `infra/terraform/` (`*.tfstate*`, `.terraform/`,
  `*.tfvars`, `backend.hcl`) y ampliación equivalente del `.gitignore` raíz.

**No se ha ejecutado ningún `terraform`/`aws` con efectos reales** — solo se
ha escrito y documentado el código, tal y como pedía la tarea.

## Decisiones de diseño (por qué)

- **Región `eu-west-1` (Irlanda)** por defecto en vez de `eu-south-2` (España):
  más madurez de servicios y precios generalmente más bajos en la UE; no hay
  (por ahora) un requisito legal de residencia estricta en España. Es una
  variable, así que cambiarlo es trivial si ese requisito aparece más
  adelante.
- **Un bucket S3 por capa** (Bronze/Silver/Gold) en vez de un único bucket con
  prefijos: simplifica y hace más seguras las políticas IAM de mínimo
  privilegio (el rol de ingesta referencia el ARN completo del bucket Bronze,
  sin depender de una `Condition` de prefijo bien escrita), y permite que cada
  capa evolucione su ciclo de vida/cifrado de forma independiente. El coste de
  tener 3 buckets en vez de 1 es cero en S3.
- **Ciclo de vida asimétrico entre versión actual y no-actual**: la versión
  actual pasa a Standard-IA (barata pero consultable al instante) y nunca a
  Glacier, porque se espera consultar el lakehouse (sobre todo Gold) bajo
  demanda vía Athena/BI y Glacier introduce latencia de recuperación
  inaceptable para eso. Las versiones no-actuales (historial de versionado)
  sí van a Glacier y se expiran, porque no se esperan consultar.
- **Rol de ingesta confiado por defecto a `lambda.amazonaws.com`**: encaja con
  el principio de coste mínimo (sin servidores en reposo) como patrón por
  defecto para los futuros productores de datos; es configurable
  (`ingestion_trusted_services`/`ingestion_trusted_arns`) para cuando se
  decida la implementación real de ingesta.
- **Backend S3 + DynamoDB** con bucket/tabla creados a mano como paso 0 (no
  se pueden crear con el mismo Terraform que los usa) — documentado con
  comandos concretos en el README, no ejecutados.
- Fuera de alcance deliberadamente: MSK/Kafka u otros servicios gestionados
  caros — se evaluará en una tarea posterior una vez validado este andamiaje
  base, en línea con el principio de coste mínimo del proyecto.

## Relevante para tareas futuras

- El rol de ingesta (`aws_iam_role.ingestion` / `ingestion_bronze_write`
  policy) solo permite escribir en Bronze. Cualquier tarea que implemente un
  productor de datos real (scraper, Lambda...) debe usar este rol y, si el
  servicio no es Lambda, añadir su service principal o ARN a
  `ingestion_trusted_services`/`ingestion_trusted_arns` en `variables.tf`.
- No existe todavía infraestructura de cómputo/procesado (Glue, EMR, Athena,
  etc.) ni catálogo de datos — este ticket es solo el almacenamiento base y el
  rol de escritura de Bronze.
- El bucket de estado remoto y la tabla de lock de Terraform **no existen
  todavía en AWS**: alguien con permisos debe ejecutar el "paso 0" del README
  antes de poder hacer el primer `terraform init` de este proyecto.

## Bug del demonio encontrado y arreglado en esta misma tarea

Al procesar esta tarea se detectó que `tasks/scripts/agent_loop.py` tenía un bug de
condición de carrera que hizo que **esta misma tarea 001 se reprocesara y fusionara
por duplicado 21 veces** antes de arreglarse (ver el historial de `main`: 21 commits
"feat(infra): andamiaje base Terraform del lakehouse en AWS (#N)" con contenido
idéntico). Causa: en `_run_task_attempt`, con `force: true`, el código fusionaba el PR
(`gh_git.merge_pr`, que avanza `origin/main` en GitHub) **antes** de comitear y pushear
el bookkeeping (`status: in_review`, `pr_number`) del propio clon local del demonio.
Ese push llegaba tarde, contra un `origin/main` ya adelantado por el propio merge, y
`git push` lo rechazaba (`! [rejected] ... fetch first`). El error se registraba en el
heartbeat pero no detenía el demonio, así que en el siguiente ciclo la tarea seguía
viéndose con `status: in_progress` y `pr_number: null` (el último bookkeeping que sí
se había guardado) — el demonio la trataba como "in_progress recuperada tras un
crash" y la volvía a ejecutar entera desde cero, indefinidamente.

Arreglo: en `_run_task_attempt` se movió el `_save(...)` que persiste
`status: in_review` / `pr_number` a **antes** del `gh_git.merge_pr(...)`, no después.
Así el push de bookkeeping siempre se hace contra un `origin/main` que todavía no ha
avanzado por el propio merge (el PR aún no se ha fusionado en ese punto), y solo
entonces se dispara el merge. En el siguiente ciclo, `_handle_in_review` ve
correctamente el PR como `MERGED` y mueve la tarea a `tasks/done/` una única vez.

No se han limpiado a mano los 21 merges duplicados ya fusionados en `main` (reescribir
el historial sería más disruptivo que dejarlos); el contenido de todos ellos es
idéntico al de este PR, así que no hay divergencia de código que resolver, solo ruido
en el historial de commits.
