# 030 — Aplicar el despliegue de Lambda + EventBridge Scheduler (`terraform apply`)

## Qué se implementó

Esta tarea aplica en AWS el Terraform que la tarea 029 dejó escrito y
planificado en `infra/terraform/lambda.tf` (14 `aws_lambda_function.producer`
+ 20 `aws_scheduler_schedule.producer` + recursos IAM/CloudWatch/SSM
asociados). No hay cambios de código: **ningún fichero `.tf` se ha tocado en
esta tarea**. El único entregable de código es este documento;
`backend.hcl`, `terraform.tfvars`, `.terraform/` y `build/ingesta_source.zip`
se regeneraron a partir de sus `.example` (gitignored, no commiteados, sin
ajustar ningún valor) y se han eliminado del disco al terminar.

## Pasos ejecutados

```bash
cd infra/terraform
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan -var-file=terraform.tfvars    # comprobación: ¿sigue igual que en la tarea 029?
terraform apply -var-file=terraform.tfvars -auto-approve
```

`terraform init` se completó sin error (mismo warning no bloqueante de
`dynamodb_table` deprecado que en las tareas 014/015/029). El `plan` de
comprobación dio exactamente **`Plan: 58 to add, 0 to change, 0 to destroy`**,
idéntico al ya revisado en `doc/029-terraform-lambda-eventbridge-plan.md`
(mismos 58 recursos, mismo `source_code_hash` del .zip de código fuente), así
que se procedió a aplicar sin modificar nada, tal como pedía el enunciado.

## Resultado del `apply`

**`Apply complete! Resources: 58 added, 0 changed, 0 destroyed.`** Sin
errores, sin recursos a medio crear, una sola pasada.

Región: **`eu-west-1`**. Cuenta AWS: **`222234418587`**.

## Recursos reales creados en AWS

| Tipo | Cantidad | Detalle |
|---|---|---|
| `aws_lambda_function` | 14 | `madrono-tfm-dev-<clave>` (ver tabla completa abajo) |
| `aws_scheduler_schedule` | 20 | `madrono-tfm-dev-<clave-schedule>` |
| `aws_cloudwatch_log_group` | 14 | `/aws/lambda/madrono-tfm-dev-<clave>`, retención 14 días |
| `aws_ssm_parameter` (`SecureString`) | 5 | `/madrono-tfm/dev/secrets/{aemet-api-key,cams-ads-api-key,emt-client-id,emt-pass-key,google-maps-api-key}`, valor placeholder `CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM` |
| `aws_iam_role` | 1 | `madrono-tfm-dev-scheduler-role` (`arn:aws:iam::222234418587:role/madrono-tfm-dev-scheduler-role`) |
| `aws_iam_policy` | 2 | `madrono-tfm-dev-ingestion-lambda-logs`, `madrono-tfm-dev-scheduler-invoke-lambda` |
| `aws_iam_role_policy_attachment` | 2 | logs → rol de ingesta existente; invoke → rol de scheduler nuevo |

14 funciones Lambda (nombre = `madrono-tfm-dev-<clave>`):
`trafico`, `transporte_publico_emt`, `bicimad`, `aparcamientos`,
`calidad_aire`, `meteorologia`, `ruido`, `afluencia_lugares`,
`aforos_peatones_bicicletas`, `bluesky_menciones`, `agenda_eventos`,
`aemet_prevision_avisos`, `cams_calidad_aire`, `cartelera_cines_estrenos`.

20 schedules (nombre = `madrono-tfm-dev-<clave-schedule>`):
`aemet_avisos_{0800,1100,1800,2350}`, `aemet_prevision_{0700,1400}`,
`afluencia_lugares`, `aforos_peatones_bicicletas`, `agenda_eventos`,
`aparcamientos`, `bicimad`, `bluesky_menciones`, `calidad_aire`,
`cams_{0715_utc,0900_utc}`, `cartelera_cines_estrenos`, `emt_llegadas`,
`meteorologia`, `ruido`, `trafico`.

## Verificación con `aws` CLI directo (no solo la salida de Terraform)

- **`aws lambda get-function --function-name <nombre>`** en las 14 funciones
  → las 14 existen, `Configuration.State = Active` en las 14 (comprobado con
  un bucle sobre las 14 claves de `local.producers`).
- **`aws scheduler get-schedule --name <nombre>`** en los 20 schedules → los
  20 existen, `State = ENABLED` en los 20 (comprobado con un bucle sobre las
  20 claves de `local.schedules`).
- **`aws ssm describe-parameters`** con filtro por prefijo
  `/madrono-tfm/dev/secrets/` → los 5 parámetros existen.
- **`aws logs describe-log-groups`** con prefijo
  `/aws/lambda/madrono-tfm-dev-` → 14 log groups (uno por función).
- **`aws iam get-role --role-name madrono-tfm-dev-scheduler-role`** → existe,
  ARN `arn:aws:iam::222234418587:role/madrono-tfm-dev-scheduler-role`.

Todo lo anterior confirma que el estado real en AWS coincide con lo que
Terraform reporta.

## Invocación manual de prueba: **FALLA** (bug de empaquetado, no relacionado con las dependencias de terceros)

Se invocaron manualmente (`aws lambda invoke`) dos de las funciones de menor
riesgo/frecuencia (`aforos_peatones_bicicletas`, mensual, y
`cartelera_cines_estrenos`, diaria), sin esperar al primer disparo
programado, tal como pedía el enunciado. **Las dos fallan**, con el mismo
error:

```
{"errorMessage": "Unable to import module 'ingesta.capturas.aforos_peatones_bicicletas_madrid': No module named 'ingesta'",
 "errorType": "Runtime.ImportModuleError", "requestId": "", "stackTrace": []}
```

```
{"errorMessage": "Unable to import module 'ingesta.capturas.cartelera_cines_madrid': No module named 'ingesta'",
 "errorType": "Runtime.ImportModuleError", "requestId": "", "stackTrace": []}
```

**Causa raíz identificada** (solo diagnóstico, no se ha corregido — fuera de
alcance de esta tarea): `data.archive_file.ingesta_source` en
`infra/terraform/lambda.tf` usa `source_dir = "${path.module}/../../ingesta"`,
lo que empaqueta el **contenido** de `ingesta/` directamente en la raíz del
.zip (`__init__.py`, `capturas/`, `bronze.py`, ... en la raíz — confirmado
con `unzip -l build/ingesta_source.zip`), en vez de preservar el propio
directorio `ingesta/` como prefijo dentro del .zip. El `handler` de cada
función (p. ej. `ingesta.capturas.aforos_peatones_bicicletas_madrid.lambda_handler`)
asume que existe un paquete `ingesta` de nivel superior importable, que no
existe con este empaquetado — el runtime falla en la fase de `init`, **antes**
de que se ejecute una sola línea del código del productor (antes incluso de
llegar al `import requests` que documentaba la tarea 029 como limitación
conocida por falta de layer de dependencias). Es un fallo distinto y previo
al de la layer: aunque hubiera una layer con `requests`/`beautifulsoup4`/etc.
ya instalada, la importación seguiría fallando por esta causa.

**Confirmación de que no se escribió nada en Bronze**: `aws s3 ls
s3://madrono-tfm-dev-bronze-222234418587/ --recursive` (antes y después de
ambas invocaciones) devuelve **vacío** — coherente con que el fallo ocurre en
`Runtime.ImportModuleError` durante la fase `init`, antes de que
`BronzeWriter` llegue a instanciarse.

Como pedía el enunciado ante un fallo de la invocación de prueba: se
documenta el error exacto y su causa raíz, **no se ha intentado arreglarlo**
modificando `lambda.tf` ni ningún otro fichero — eso queda como tarea de
seguimiento explícita (ver abajo). Por la misma causa, es de esperar que
**las 14 funciones fallen de la misma manera** en su primer disparo
programado real (no solo las 2 probadas), ya que las 14 comparten el mismo
.zip y el mismo patrón de `handler` con prefijo `ingesta.`.

## Confirmación explícita

El `apply` terminó **sin error** y coincidió exactamente con el plan ya
revisado en la tarea 029 (58 to add, 0 to change, 0 to destroy). No se
ejecutó `terraform destroy` en ningún momento. No se modificó ningún fichero
`.tf`. Los 58 recursos existen y están activos/habilitados en AWS, verificado
con `aws` CLI directo, no solo con la salida de Terraform. **La invocación
manual de prueba no confirma una escritura real en Bronze** — al contrario
que el criterio de aceptación esperado, ambas invocaciones de prueba
fallaron por el bug de empaquetado descrito arriba, documentado aquí en
detalle en vez de corregido, conforme a las restricciones explícitas del
enunciado ("no seas la que soluciona el problema... eso sería una tarea de
seguimiento").

## Relevante para tareas futuras

- **Bloqueante inmediato, antes del primer disparo programado real**:
  corregir el empaquetado de `data.archive_file.ingesta_source` en
  `infra/terraform/lambda.tf` para que el .zip contenga un directorio
  `ingesta/` de nivel superior (p. ej. usando la opción de `archive_file`
  para anidar el contenido bajo un prefijo, o restructurando el `source_dir`
  con un paso de copia previo a `ingesta/ingesta/...`), y volver a aplicar
  (`terraform apply`, sin destruir nada — el cambio solo afecta al
  `filename`/`source_code_hash` de las 14 funciones, que Terraform
  actualizará in place). Sin este arreglo, **las 20 invocaciones
  programadas fallarán** desde el primer disparo (la más próxima, según
  las cadencias de la tarea 029, sería `bicimad`/`trafico`/`emt_llegadas`
  a los pocos minutos de este `apply`, luego `aparcamientos` a los 15
  minutos, etc.) — puramente en la fase de `import`, sin coste de ejecución
  real más allá de la invocación en sí (facturación mínima, milisegundos).
- **Sigue pendiente, tal como documentó la tarea 029** (no cambia con esta
  tarea): la Lambda Layer real con `ingesta/requirements.txt`
  (`requests`, `beautifulsoup4`, `cdsapi`, `netCDF4`, `populartimes`) sigue
  sin construirse ni desplegarse (`layers = []` en las 14 funciones,
  `var.lambda_dependencies_layer_arn` sigue en `null`). Aunque se corrija el
  bug de empaquetado de arriba, las funciones seguirán fallando (esta vez en
  `import requests` u otro paquete de terceros, ya dentro de
  `ingesta/capturas/<módulo>.py`) hasta que exista esa layer. Ambos arreglos
  son independientes y ambos son necesarios antes de un despliegue
  funcional real.
- Los 5 parámetros SSM (`terraform output secret_ssm_parameter_names`) siguen
  con el valor placeholder `CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM`; las 4
  funciones que los necesitan (`transporte_publico_emt`, `afluencia_lugares`,
  `aemet_prevision_avisos`, `cams_calidad_aire`) tampoco funcionarían
  correctamente todavía aunque se arreglasen los dos bloqueantes anteriores,
  hasta que alguien fije los valores reales a mano
  (`aws ssm put-parameter --name <nombre> --value <credencial real> --type
  SecureString --overwrite`).
- Dado que `force` es `false` en esta tarea (a propósito, según el
  enunciado), el PR de esta tarea **no se fusiona solo**: un humano debe
  revisar este documento (en particular la sección de la invocación fallida)
  antes de fusionar — con el estado actual, fusionar no supone ningún riesgo
  operativo nuevo más allá del ya asumido (los schedules ya están `ENABLED`
  en AWS independientemente de si el PR se fusiona o no, ya que el `apply`
  ya se ejecutó contra la cuenta real), pero si conviene que quien revise
  decida si complementa este PR con el arreglo de empaquetado antes o
  después de fusionar.
- No se ha tocado ni recreado ningún recurso del lakehouse (tarea 015) ni
  ningún fichero `.tf`: el `plan` de comprobación confirmó `0 to change`
  sobre ellos antes de aplicar.
