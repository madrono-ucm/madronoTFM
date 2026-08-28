# Operación — cómo aplicar y verificar infraestructura y datos

Runbook operativo del proyecto: cómo alcanzar AWS / Neo4j / Terraform desde
una sesión de trabajo, cómo desplegar un productor nuevo de principio a fin,
y las trampas conocidas del entorno. Complementa `infra/terraform/README.md`
(que documenta el *código* Terraform) con el *cómo se ejecuta*.

`infra/terraform/README.md` dice "este código no se ha aplicado" — **está
obsoleto**: la infra real se aplicó en la tarea 098 (`terraform apply`: 50
added / 64 changed / 50 destroyed). Lo único deliberadamente sin aplicar es
Kafka (`kafka.tf`).

## Credenciales y accesos

### AWS

| | |
|---|---|
| Perfil | **`madrono`** (`~/.aws/credentials`; también como líneas `aws configure set` en `.claude/settings.local.json`) |
| Cuenta | `222234418587` |
| Usuario IAM | `madrono-terraform-deployer` |
| Región | `eu-west-1` (siempre explícita — esta máquina/EC2 cae en `eu-south-2` sin `--region`) |

```bash
export AWS_PROFILE=madrono AWS_DEFAULT_REGION=eu-west-1
aws sts get-caller-identity          # comprobación
```

Huecos IAM conocidos del usuario `madrono-terraform-deployer`:
`codebuild:ListProjects` denegado; `codebuild:BatchGetProjects` se añadió
como política inline acotada al ARN del proyecto de la Lambda Layer
(`doc/098`). El rol de instancia EC2 `madrono-terraform-deployerEC2` que usa
el demonio es más amplio.

### Neo4j (AuraDB Free, instancia real)

Credenciales en SSM Parameter Store, `eu-west-1`, `SecureString`:

```bash
MSYS_NO_PATHCONV=1 aws ssm get-parameter --name /madrono-tfm/dev/secrets/neo4j-uri      --with-decryption --query Parameter.Value --output text
#   ... -username   -password   -database   (mismo patrón)
```

`grafo/cargar_grafo.py` lee las variables de entorno `NEO4J_URI`,
`NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. Una recarga completa
tarda 20–50 min contra el free tier (todo `MERGE` idempotente — interrumpir
el cliente no corrompe nada).

### Terraform

Backend remoto ya inicializado (`infra/terraform/.terraform/`):

| | |
|---|---|
| State | S3 `madrono-tfm-terraform-state`, key `infra/lakehouse/terraform.tfstate` |
| Locks | DynamoDB `madrono-tfm-terraform-locks` |
| Config | `infra/terraform/backend.hcl` (no se commitea) |

```bash
cd infra/terraform
AWS_PROFILE=madrono terraform plan
AWS_PROFILE=madrono terraform apply                       # o con -target=...
```

Usa `-target=<recurso>` cuando `terraform plan` muestre drift no relacionado
con tu cambio (p. ej. otras tareas fusionadas entre medias).

### CodeBuild — Lambda Layer de dependencias

`infra/terraform/lambda_layer_build.tf`:

- Proyecto CodeBuild: `madrono-tfm-dev-lambda-dependencies-layer`
- Rol IAM: `madrono-tfm-dev-lambda-layer-codebuild-role`
- Política: `madrono-tfm-dev-lambda-layer-codebuild-policy`

Construye la layer desde `ingesta/requirements.txt` sobre
`aws/codebuild/amazonlinux-x86_64-lambda-standard:python3.13`. Flujo de dos
`apply` (ver `doc/032`): 1) `apply` crea proyecto + rol; 2)
`aws codebuild start-build --project-name madrono-tfm-dev-lambda-dependencies-layer`;
3) segundo `apply` crea `aws_lambda_layer_version`. Solo hace falta rehacerlo
si cambian las dependencias de `ingesta/requirements.txt`.

## Desplegar un productor nuevo de principio a fin

Patrón para `FIL_03`/`FIL_04`/`FIL_05` (y cualquier fuente futura). Copia el
bloque del dataset más reciente y parecido (`bluesky_menciones`,
`agenda_eventos`) como plantilla.

1. **Código de captura** (`ingesta/capturas/<mod>.py`): `DATASET_NAME`,
   `capture_all(config) -> list[dict]`, `lambda_handler(event, context)` que
   escribe con `BronzeWriter`. Tests en `ingesta/tests/test_lambda_handlers.py`
   (reutilizan `_run_handler_writing_records`).
2. **Silver/Gold** (`procesamiento/silver_gold/<dataset>/`):
   `glue_bronze_to_silver.py`, `glue_silver_to_gold.py`, `aggregate.py`
   (fuente de verdad documental/de test del esquema Gold), `ge_suite.py`
   (puerta de calidad Great Expectations).
3. **Terraform**:
   - `lambda.tf`: entrada en `local.producers` (`module`, `dataset`) y en
     `local.schedules` (cadencia — horaria para señales vivas, semanal para
     referencia).
   - `glue.tf`: bloque completo del dataset — objetos S3 de scripts, rol IAM
     + política de acceso a datos acotada por prefijo
     (`bronze/<ds>/*`, `silver/<ds>/*`, `gold/<tabla>/*`,
     `_quality_reports/<ds>/*`, y los marcadores `_$folder$`), los 2 jobs de
     Glue, y las tablas del catálogo.
     - **Si el job escribe Gold con `mode("overwrite")`** (clave de negocio
       sin fecha, recálculo completo), la política necesita `s3:DeleteObject`
       sobre el prefijo Gold — el patrón `append` no. Solo `aemet_prevision`
       usa `overwrite` hoy (ver `FIL_01`).
   - `glue_scheduling.tf`: trigger `SCHEDULED` de `bronze-to-silver` +
     trigger `CONDITIONAL` de `silver-to-gold`.
   - `athena.tf`: tabla del catálogo con Partition Projection; el
     `projection.<col>.range` **debe** arrancar amplio (`2024-01-01` o
     `2026-08-01`), nunca una ventana estrecha de 14 días (bug real de la
     tarea 098 con `aforos`).
4. **Aplicar y verificar**:
   ```bash
   cd infra/terraform && AWS_PROFILE=madrono terraform plan   # revisar CADA cambio
   AWS_PROFILE=madrono terraform apply -target=...             # acotado al dataset
   AWS_PROFILE=madrono aws lambda invoke --function-name madrono-tfm-dev-<ds> --region eu-west-1 /tmp/out.json
   AWS_PROFILE=madrono aws glue start-job-run --job-name madrono-tfm-dev-<ds>-bronze-to-silver --region eu-west-1
   AWS_PROFILE=madrono aws glue start-job-run --job-name madrono-tfm-dev-<ds>-silver-to-gold --region eu-west-1
   # Athena: SELECT count(*), max(processed_at) FROM <tabla_gold>
   ```
5. `terraform plan` limpio después (solo Kafka pendiente).
6. `doc/` con el resultado real (conteos, no tests).

## Comandos de verificación útiles

```bash
export AWS_PROFILE=madrono AWS_DEFAULT_REGION=eu-west-1 MSYS_NO_PATHCONV=1

# Salud de todos los jobs de Glue (última ejecución)
aws glue get-job-runs --job-name <job> --max-items 1 \
  --query "JobRuns[0].[JobRunState,StartedOn,ErrorMessage]" --output text

# Schedules de EventBridge Scheduler
aws scheduler list-schedules --query "Schedules[].[Name,State]" --output text

# Frescura de Bronze de un dataset
aws s3api list-objects-v2 --bucket madrono-tfm-dev-bronze-222234418587 \
  --prefix "<ds>/" --query "sort_by(Contents,&LastModified)[-1].[LastModified,Key]" --output text

# Athena (rápido, vía el helper de grafo/extract)
python -c "import sys;sys.path.insert(0,'.');from grafo.extract import run_athena_query,GOLD_DATABASE;print(run_athena_query('SELECT count(*) n FROM <tabla>',GOLD_DATABASE))"
```

## Trampas del entorno

- **Git Bash destroza los argumentos que empiezan por `/`** (nombres de
  parámetros SSM, algunos ARNs) — antepón
  `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'` a esos comandos.
- `aws ... --query` con `list-objects-v2` aplica el query **por página** —
  varias filas de salida en un prefijo de >1000 objetos es un artefacto de
  paginación, no varios "último objeto".
- El repo tiene `.gitattributes` forzando `LF`; Git avisa "CRLF will be
  replaced" al hacer commit — inofensivo (tarea 100).
- Guardar cualquier secreto nuevo en SSM: **siempre `--region eu-west-1`
  explícito** (el resto de secretos vive ahí; sin `--region` esta EC2 escribe
  en `eu-south-2`, bug ya conocido — `doc/082`).

## Qué puede bloquear una sesión de Claude Code

`terraform apply` y los comandos `aws` mutadores chocan con el clasificador
de "auto mode" salvo que una regla de `.claude/settings.local.json` los
permita explícitamente. Reglas actuales relevantes en `permissions.allow`:
`terraform fmt/validate/init -backend=false`, `aws sts *`, `aws ssm *`,
`aws configure *`. Para desbloquear `apply` / `glue start-job-run` /
`lambda invoke` / `codebuild start-build` hay que añadir la regla
correspondiente (o ejecutar el comando a mano fuera de la sesión).
