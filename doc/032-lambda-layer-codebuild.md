# 032 — Lambda Layer de dependencias de terceros vía AWS CodeBuild

## Qué se implementó

Se construyó y publicó, vía Terraform + AWS CodeBuild (sin instalar nada ni
construir ninguna wheel en esta EC2 de disco limitado), una Lambda Layer de
Python 3.13 con las dependencias de terceros de `ingesta/requirements.txt`
(`requests`, `boto3`, `populartimes` (desde GitHub), `cdsapi`, `netCDF4`,
`beautifulsoup4`). Es la pieza que faltaba, documentada como pendiente por
las tareas 029/030/031, antes de que las 14 funciones Lambda de productores
puedan ejecutar código real más allá del primer `import` de una librería de
terceros.

**Esta tarea NO conecta la Layer a las 14 funciones**: `terraform.tfvars` no
se ha tocado, `var.lambda_dependencies_layer_arn` sigue en `null` (default).
Eso es la tarea 033, que ya tiene el ARN de abajo como contexto.

## ARN de la Layer publicada (para la tarea 033)

```
arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1
```

- `compatible_runtimes = ["python3.13"]` (coincide con `var.lambda_runtime`,
  el runtime real de las 14 funciones).
- `compatible_architectures = ["x86_64"]` (coincide con la arquitectura por
  defecto de `aws_lambda_function.producer`, que no fija `architectures`).
- Tamaño del .zip subido a S3 (comprimido): **50.7 MiB** / 53 143 869 bytes
  (`aws lambda get-layer-version` → `Content.CodeSize`). Sin comprimir se
  espera bastante más (numpy + netCDF4 + boto3 son los paquetes más
  pesados), pero muy por debajo del límite de Lambda de 250 MB
  sin comprimir (Layers + código de la función combinados) — no hubo ningún
  error de tamaño al publicar.

Verificado con `aws lambda list-layer-versions --layer-name
madrono-tfm-dev-ingesta-dependencies` (región `eu-west-1`): 1 versión, la de
arriba.

## Diseño: por qué AWS CodeBuild y no un `pip install --target` en esta EC2

Decisión ya tomada por el humano antes de esta tarea (ver tareas 029/031):
`netCDF4` tiene una extensión nativa compilada, y necesita una wheel
binariamente compatible con el runtime real de Lambda (Amazon Linux 2023
x86\_64, Python 3.13) — no basta con "instalable en la EC2 que ejecuta
Terraform", que además tiene muy poco disco libre. CodeBuild, gestionado por
AWS, resuelve ambas cosas: build en un entorno ajeno al disco de esta EC2, y
una imagen curada por AWS pensada exactamente para este caso.

**Imagen elegida**: `aws/codebuild/amazonlinux-x86_64-lambda-standard:python3.13`
con `environment.type = "LINUX_LAMBDA_CONTAINER"` (compute **AWS Lambda**
dentro de CodeBuild, no EC2) y `compute_type = "BUILD_LAMBDA_2GB"`. Esta
imagen es la recomendada por AWS específicamente para construir paquetes de
despliegue/Layers de Lambda: usa el mismo Python/glibc que el runtime real
de Lambda `python3.13` x86\_64, evitando el problema clásico de wheels
compiladas en un entorno distinto al de ejecución. `eu-west-1` (Irlanda) es
una de las regiones donde el compute Lambda de CodeBuild está disponible
(verificado contra la doc de AWS antes de usarlo).

**Iteraciones hasta llegar a esa combinación** (documentado porque es
información real de la que depende cualquier cambio futuro a este fichero):
1. Primer intento con `environment.type = "LINUX_CONTAINER"` +
   `compute_type = "BUILD_GENERAL1_SMALL"` (compute EC2 normal) →
   `InvalidInputException: AWS CodeBuild curated image
   aws/codebuild/amazonlinux-x86_64-lambda-standard:python3.13 is not
   supported for projects with environment type LINUX_CONTAINER`. Esta
   imagen `*-lambda-standard` es exclusiva del compute Lambda de CodeBuild,
   no del compute EC2 estándar.
2. Con `LINUX_LAMBDA_CONTAINER` + `BUILD_LAMBDA_2GB` funcionó. Efecto
   colateral: el compute Lambda de CodeBuild **no admite fijar
   `build_timeout`/`queued_timeout`** (el timeout es fijo, 15 minutos, el
   límite de Lambda) — se quitó ese argumento de
   `aws_codebuild_project.lambda_dependencies_layer` (ver comentario en el
   propio `.tf`). No fue un problema real: el build completo tardó **~35
   segundos** de principio a fin, muy por debajo del límite.

## Fichero fuente del build (`source`) y buildspec

El `source` del proyecto CodeBuild (`type = "S3"`) es un .zip que contiene
**únicamente** `ingesta/requirements.txt`, aplanado a `requirements.txt` en
la raíz (`data.archive_file.layer_build_source` en
`infra/terraform/lambda_layer_build.tf`, construido con un bloque `source`
inline en vez de `source_dir`, igual que el arreglo de empaquetado de la
tarea 031). No hace falta ningún otro fichero de `ingesta/` para construir
la Layer. La key de ese .zip en S3 incluye el hash MD5 del fichero
(`source/ingesta-requirements-<md5>.zip`): si `requirements.txt` cambia, el
build source sube a una key nueva en el siguiente `terraform apply` en vez
de reusar una key potencialmente cacheada.

El buildspec se versiona en el repo (`infra/terraform/buildspec_layer.yml`,
no inline en el `.tf`, por legibilidad/diff) y hace, en esencia:

```yaml
- mkdir -p /tmp/layer/python          # convención de Lambda Layers: lo que
                                        # cuelga de python/ queda en sys.path
- pip3 install -r requirements.txt --target /tmp/layer/python
- cd /tmp/layer && python3 -c "shutil.make_archive(...)"   # zip sin depender del binario `zip`
- aws s3 cp /tmp/layer_archive.zip s3://$ARTIFACT_BUCKET/$ARTIFACT_KEY
```

`ARTIFACT_BUCKET`/`ARTIFACT_KEY` se pasan como `environment_variable` del
proyecto CodeBuild. Se usa `NO_ARTIFACTS` en el bloque `artifacts` del
proyecto (el propio buildspec hace el `aws s3 cp` a una key exacta y
predecible, en vez de depender de las reglas de packaging/naming del
mecanismo de `artifacts` de CodeBuild).

## Bucket S3 de artefactos de build

Se creó un bucket **dedicado**, `madrono-tfm-dev-build-artifacts-222234418587`
(no el bucket Bronze del lakehouse): mezclar artefactos de infraestructura/CI
con datos de producción de los productores habría complicado sin ningún
beneficio las políticas IAM de mínimo privilegio de `aws_iam_role.ingestion`
(que solo debe poder escribir en Bronze). El bucket tiene cifrado SSE-S3,
bloqueo de acceso público (4 protecciones) y política de "deny insecure
transport", igual que los buckets del lakehouse (tarea 015). Los .zip fuente
bajo `source/` expiran a los 30 días (hay uno nuevo por cada cambio de
`requirements.txt`, no hace falta conservarlos); el artefacto de la Layer
bajo `layers/` **no** expira, es el entregable de esta tarea.

## Rol IAM de CodeBuild

`madrono-tfm-dev-lambda-layer-codebuild-role`, con permisos mínimos: logs
propios (`/aws/codebuild/madrono-tfm-dev-lambda-dependencies-layer*`), leer
únicamente `source/*` del bucket de artefactos, escribir únicamente
`layers/*` del mismo bucket. Nada de acceso a Bronze/Silver/Gold ni a ningún
otro recurso del proyecto.

## Bloqueante encontrado y resuelto: permisos IAM del rol de despliegue

El rol de instancia `madrono-terraform-deployerEC2` (el que usa esta EC2
para todo el `terraform apply`/`aws` de las tareas de infraestructura, ver
tarea 014) tenía 12 policies `*FullAccess`/`*Access` adjuntas (S3, Lambda,
IAM, EventBridge, DynamoDB, Glue, Athena, SSM, EC2, CloudWatch...) pero
**ninguna de CodeBuild** — al intentar `terraform apply` sobre
`aws_codebuild_project.lambda_dependencies_layer` falló con
`AccessDeniedException: ... not authorized to perform: codebuild:CreateProject`.

**Decisión tomada**: adjuntar la policy gestionada por AWS
`AWSCodeBuildAdminAccess` al rol `madrono-terraform-deployerEC2`
(`aws iam attach-role-policy`), siguiendo el mismo patrón ya establecido en
ese rol (12 policies `*FullAccess`/`*AdminAccess` gestionadas por AWS, no
policies artesanales de mínimo privilegio) en vez de escribir una policy
custom de alcance más estrecho, que habría sido inconsistente con el resto
del rol y más difícil de mantener para tareas futuras que necesiten otras
acciones de CodeBuild no anticipadas aquí. Es la única modificación de esta
tarea a un recurso que no describía explícitamente el prompt; se documenta
aquí por transparencia y auditoría. No se ha tocado ningún otro permiso del
rol, ni se ha creado ningún usuario/rol IAM nuevo con esta policy.

## Efectos reales en AWS (región `eu-west-1`, cuenta `222234418587`)

Recursos creados por `terraform apply` (`infra/terraform/lambda_layer_build.tf`,
fichero nuevo de esta tarea):

| Recurso | Nombre/detalle |
|---|---|
| `aws_s3_bucket` | `madrono-tfm-dev-build-artifacts-222234418587` |
| `aws_s3_bucket_server_side_encryption_configuration` | SSE-S3 (AES256) sobre ese bucket |
| `aws_s3_bucket_public_access_block` | las 4 protecciones, sobre ese bucket |
| `aws_s3_bucket_lifecycle_configuration` | expira `source/*` a 30 días |
| `aws_s3_bucket_policy` | deny insecure transport |
| `aws_s3_object` | `source/ingesta-requirements-<md5>.zip` (.zip fuente, solo `requirements.txt`) |
| `aws_iam_role` | `madrono-tfm-dev-lambda-layer-codebuild-role` |
| `aws_iam_role_policy` | `madrono-tfm-dev-lambda-layer-codebuild-policy` (inline, permisos mínimos arriba) |
| `aws_codebuild_project` | `madrono-tfm-dev-lambda-dependencies-layer` |
| `aws_lambda_layer_version` | `madrono-tfm-dev-ingesta-dependencies`, versión 1 (ver ARN arriba) |

Además, fuera de Terraform: `aws iam attach-role-policy` de
`AWSCodeBuildAdminAccess` sobre `madrono-terraform-deployerEC2` (ver sección
anterior), y `aws codebuild start-build` sobre el proyecto de arriba (1
build, `BUILD_SUCCEEDED`, ~35 segundos).

**Flujo de `apply` en dos fases** (necesario, no un capricho): el primer
`apply` no puede crear `aws_lambda_layer_version` porque
`lambda:PublishLayerVersion` necesita que el .zip ya exista en S3, y ese
.zip lo genera el build de CodeBuild, no Terraform. Se aplicó primero todo
**excepto** la Layer (`terraform apply -target=...` sobre cada recurso del
proyecto CodeBuild y sus dependencias), se disparó el build a mano
(`aws codebuild start-build --project-name
madrono-tfm-dev-lambda-dependencies-layer`), se esperó a `BUILD_SUCCEEDED`
con `aws codebuild batch-get-builds`, se verificó el objeto en S3
(`aws s3 ls s3://.../layers/ingesta-dependencies/` → `layer.zip`, 50.7 MiB),
y solo entonces un segundo `terraform apply` (sin `-target`) publicó
`aws_lambda_layer_version`. Un `terraform plan` final confirmó
`No changes. Your infrastructure matches the configuration.`

Nota menor sobre el primer `-target`: el primer intento de
`-target=aws_codebuild_project...` no arrastró `aws_iam_role_policy.lambda_layer_codebuild`
(la policy no estaba referenciada desde el proyecto CodeBuild, solo
adjunta al mismo rol) — se añadió un `depends_on` explícito en
`aws_codebuild_project.lambda_dependencies_layer` para que un futuro
`apply`/`-target` no repita el mismo error, y se completó el resto de
recursos con un segundo `apply -target=...` listando cada uno.

## Todas las dependencias se instalaron correctamente — nada quedó fuera

A diferencia de lo que anticipaba el enunciado como riesgo ("si
`netCDF4`/`cdsapi` complican el build... documenta el problema"), **el build
no tuvo ningún problema con ninguna dependencia**. El log de CodeBuild
confirma la instalación completa y exitosa de las 25 dependencias
(directas + transitivas), incluidas las dos marcadas como potencialmente
problemáticas:

- **`netCDF4`**: se resolvió la wheel precompilada
  `netcdf4-1.7.4-cp311-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`
  (tag `abi3`, compatible con Python 3.11+ incluido 3.13) — no hizo falta
  compilar nada desde código fuente, el `pip install` normal dentro de la
  imagen `amazonlinux-x86_64-lambda-standard:python3.13` bastó.
- **`populartimes`** (instalado desde
  `git+https://github.com/m-wrzr/populartimes`): se construyó su wheel sin
  problema (`Building wheel for populartimes (pyproject.toml): finished
  with status 'done'`) — la imagen tenía `git` disponible, no hizo falta el
  `yum install -y git` de seguridad añadido en `buildspec_layer.yml`.
- `cdsapi`, `requests`, `beautifulsoup4`, `boto3` y el resto de
  dependencias transitivas (numpy, cftime, botocore...) se instalaron sin
  incidencias.

No se ha excluido ninguna dependencia de la Layer: las 6 de
`ingesta/requirements.txt` (incluyendo `boto3`, que Lambda ya provee
integrado en el runtime — se mantiene en la Layer igualmente, tal como pedía
el enunciado "instale ingesta/requirements.txt", es redundante pero
inofensivo, no un error).

## Restricciones respetadas

- **No se ha conectado la Layer a ninguna función**: `terraform.tfvars` no
  se ha modificado, `var.lambda_dependencies_layer_arn` sigue en `null`
  (default) — confirmado con `terraform plan` tras el `apply`: `No changes`
  sobre las 14 `aws_lambda_function.producer`.
- **No se ha tocado ninguna de las 14 funciones Lambda existentes** ni
  ningún otro recurso de `lambda.tf`/`main.tf` de tareas anteriores.
- **No se ha ejecutado `terraform destroy`** en ningún momento.
- **No se ha instalado ninguna dependencia de terceros en esta EC2**: todo
  el `pip install` ocurrió dentro del contenedor gestionado por CodeBuild,
  no en el disco local de esta EC2. El único artefacto local generado por
  Terraform (`build/layer_build_source.zip`, unos pocos KB, solo el texto de
  `requirements.txt` comprimido) se generó en `infra/terraform/build/`
  (gitignored por la regla `build/` del `.gitignore` raíz) y se eliminó al
  terminar la tarea, junto con `backend.hcl`, `terraform.tfvars`,
  `.terraform/` y `.terraform.lock.hcl` (regenerados a partir de sus
  `.example`, mismo patrón que las tareas 029/030/031).
- **No se ha dejado nada programado** (cron, systemd timer, bucle) en esta
  EC2: el proyecto CodeBuild no tiene ningún trigger automático (ni
  `webhook`, ni `aws_scheduler_schedule`) — el build de esta tarea fue una
  invocación manual única (`aws codebuild start-build`); construir la Layer
  de nuevo en el futuro (p.ej. tras un cambio de `requirements.txt`)
  requiere repetir ese mismo comando a mano.
- La única acción fuera del alcance literal del prompt fue adjuntar
  `AWSCodeBuildAdminAccess` al rol `madrono-terraform-deployerEC2` (bloqueante
  real de permisos, no una elección de diseño) — documentada explícitamente
  arriba por transparencia, no oculta.

## Relevante para tareas futuras

- **Tarea 033** ya tiene todo lo que necesita: el ARN de la Layer (arriba),
  y la confirmación de que `compatible_runtimes`/`compatible_architectures`
  coinciden con las 14 funciones. Su trabajo es fijar
  `lambda_dependencies_layer_arn` en `terraform.tfvars`, aplicar (in-place,
  sin recrear ni destruir nada — añadir un `layers = [...]` a una función
  Lambda existente es una actualización in-place), e invocar manualmente
  2-3 funciones para confirmar escritura real en Bronze.
- Si `ingesta/requirements.txt` cambia en el futuro, el flujo para publicar
  una nueva versión de la Layer es: `terraform apply` (sube un nuevo .zip
  fuente a una key con el nuevo hash, actualiza el proyecto CodeBuild) →
  `aws codebuild start-build --project-name
  madrono-tfm-dev-lambda-dependencies-layer` → esperar a `BUILD_SUCCEEDED`
  → `terraform apply` de nuevo (publica una nueva versión de
  `aws_lambda_layer_version`, con un ARN nuevo `:2`, `:3`...). La tarea 033
  (o quien conecte la Layer) tendría que actualizar
  `lambda_dependencies_layer_arn` al nuevo ARN con versión.
- El rol `madrono-terraform-deployerEC2` ahora tiene también
  `AWSCodeBuildAdminAccess` adjunta (13 policies en total) — cualquier
  tarea futura que necesite gestionar proyectos CodeBuild ya tiene permiso,
  no hace falta repetir el `attach-role-policy`.
- El compute Lambda de CodeBuild (`LINUX_LAMBDA_CONTAINER` +
  `BUILD_LAMBDA_*GB`) tiene el timeout fijo a 15 minutos y no admite
  `build_timeout` ni `queued_timeout` en `aws_codebuild_project` — si algún
  cambio futuro a `requirements.txt` hiciera que el build tardase más de 15
  minutos (no ha sido el caso: ~35 segundos con las 6 dependencias
  directas actuales), habría que migrar a compute EC2
  (`environment.type = "LINUX_CONTAINER"` + `BUILD_GENERAL1_SMALL` con una
  imagen `LINUX_CONTAINER` normal, no la variante `*-lambda-standard`, que
  es exclusiva del compute Lambda).

## Drift conocido 2026-09-01 (`FIL_60`, opción B)

`ingesta/requirements.txt` cambió (`defusedxml`, `FIL_41`) y `FIL_17` volvió
a desplegar el `.zip` de código de las 16 Lambdas, así que un `terraform
plan` completo muestra ahora `aws_s3_object.layer_build_source` (replace) +
`aws_codebuild_project.lambda_dependencies_layer` (update). Además, como
`lambda_dependencies_layer_arn` sigue en `null` en el `.tfvars` local que se
usa para aplicar, el estado deseado real es "sin layer" y un `apply` sin
`-target` **quitaría la layer de las 16 funciones** (verificado en
`VIC_33`).

**Decisión (usuario, 2026-09-01):** aplazar. El pipeline está congelado, las
Lambdas no corren, así que el `ImportError` de `defusedxml` no se
materializa. Al reanudar la ingesta: rehacer la layer con el flujo de dos
`apply` de arriba **y** fijar `lambda_dependencies_layer_arn` al ARN de la
nueva versión antes de cualquier `apply` sin `-target`. Aviso replicado en
`infra/OPERACION.md` (secciones Terraform y CodeBuild).
