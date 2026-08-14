# 031 — Arreglar el empaquetado del .zip de Lambda (falta el paquete `ingesta/` de nivel superior)

## Qué se implementó

La tarea 030 diagnosticó, con una invocación real (`aws lambda invoke`), que las 14
funciones Lambda desplegadas fallaban al arrancar con
`Runtime.ImportModuleError: No module named 'ingesta'`. Causa raíz: en
`infra/terraform/lambda.tf`, `data.archive_file.ingesta_source` usaba
`source_dir = "${path.module}/../../ingesta"`, lo que empaqueta el **contenido**
de `ingesta/` en la raíz del `.zip` en vez del directorio `ingesta/` en sí, pero el
`handler` de cada función (`ingesta.capturas.<módulo>.lambda_handler`) necesita que
`ingesta` sea un paquete importable desde la raíz del `.zip`.

Esta tarea corrige el empaquetado y reaplica en AWS.

## Cambio de código

En `infra/terraform/lambda.tf`, se sustituyó `source_dir`/`excludes` por una lista
explícita de ficheros (`local.ingesta_source_files`, vía `fileset()` sobre
`ingesta/`, excluyendo `tests/` y `capturas/samples/` — mismo criterio de exclusión
que antes) y un bloque `dynamic "source"` en `data.archive_file.ingesta_source`, uno
por fichero, con `filename = "ingesta/<ruta-relativa>"` y `content = file(...)`. Esto
fuerza a que `ingesta/` exista como carpeta de nivel superior dentro del `.zip`,
sin recurrir a un `null_resource`/`local-exec` que copie ficheros a un directorio de
staging (evita depender de herramientas de shell externas y mantiene el cambio
puramente declarativo en Terraform). Se verificó que los ficheros restantes tras las
exclusiones (`.py`, `.md`, `.txt`) son todos texto plano — `file()` no soporta
binarios, y los únicos binarios de `ingesta/` (`tests/fixtures/*.nc`, etc.) ya
quedaban excluidos por `tests/`.

Verificación local del `.zip` generado, **antes** de aplicar nada:

```
$ unzip -l build/ingesta_source.zip
   176574  ingesta/README.md
        0  ingesta/__init__.py
        0  ingesta/capturas/__init__.py
    28534  ingesta/capturas/aemet_prevision_avisos.py
    ... (25 ficheros en total, todos bajo ingesta/)
```

Y una prueba de importación local (fuera de Lambda, solo para confirmar el layout
del `.zip`):

```
$ cd /tmp/lambda_test && unzip -q .../ingesta_source.zip
$ python3 -c "import ingesta.capturas.aforos_peatones_bicicletas_madrid as m; print(hasattr(m, 'lambda_handler'))"
True
```

## `terraform plan` antes de aplicar

```
Plan: 0 to add, 15 to change, 0 to destroy.
```

Los 15 cambios fueron:
- Los **14** `aws_lambda_function.producer[*]` in-place (`source_code_hash` y
  `filename` nuevos por el `.zip` reconstruido; nada de `id`, `arn`, `role`,
  `handler`, `runtime`, etc. cambió).
- `aws_iam_policy.scheduler_invoke_lambda` in-place. Este 15º cambio **no lo
  introduce el arreglo de empaquetado**: `data.aws_iam_policy_document.scheduler_invoke_lambda`
  construye su JSON iterando `[for fn in aws_lambda_function.producer : fn.arn]`, y
  como las 14 funciones tienen un cambio in-place pendiente, Terraform no puede
  garantizar en fase de `plan` que sus ARNs no cambien (aunque en la práctica un
  `update-function-code` nunca cambia el ARN de una función Lambda existente), así
  que marca la política dependiente como recalculable en `apply` — se muestra como
  "will be updated in-place" con el valor completo sustituido por
  `(known after apply)`. Es un efecto colateral esperado y documentado del cambio
  autorizado (actualizar las 14 funciones), no una modificación independiente: tras
  el `apply`, el contenido de la política es idéntico (mismos 14 ARNs, misma acción
  `lambda:InvokeFunction`), confirmado con un segundo `terraform apply` inmediato
  que reportó `0 added, 0 changed, 0 destroyed`.

No se detectó ningún `will be created` ni `will be destroyed` en el plan — se
procedió a aplicar tal como pedía el criterio de aceptación.

## `terraform apply`

```
terraform apply -var-file=terraform.tfvars -auto-approve
```

Completado sin error. Un segundo `apply` inmediatamente después confirmó
`0 added, 0 changed, 0 destroyed`, es decir, el estado converge y no hay drift
residual.

Región: `eu-west-1`. Cuenta AWS: `222234418587`. Recursos afectados: los mismos 14
`aws_lambda_function` ya existentes desde la tarea 030 (mismos nombres, mismos
ARNs) — ninguno se creó ni se destruyó — más una actualización in-place (con
contenido idéntico) de la política IAM `madrono-tfm-dev-scheduler-invoke-lambda`.

## Verificación con invocación manual real (antes/después)

Se invocaron las mismas dos funciones que probó la tarea 030:

| Función | Error tarea 030 (antes) | Error tarea 031 (después) |
|---|---|---|
| `madrono-tfm-dev-aforos_peatones_bicicletas` | `Runtime.ImportModuleError: No module named 'ingesta'` | `Runtime.ImportModuleError: No module named 'requests'` |
| `madrono-tfm-dev-cartelera_cines_estrenos` | `Runtime.ImportModuleError: No module named 'ingesta'` | `Runtime.ImportModuleError: No module named 'requests'` |

El paquete `ingesta` ahora se importa correctamente (el error ya no es sobre
`ingesta`, sino sobre `requests`, una dependencia de terceros de
`ingesta/requirements.txt`). Esto confirma que el arreglo de empaquetado de esta
tarea funciona: el runtime llega a ejecutar `ingesta/capturas/<módulo>.py` y falla
en su primer `import` de una librería de terceros — exactamente el fallo
**siguiente**, ya diagnosticado y documentado como pendiente por las tareas
029/030 (falta la Lambda Layer de dependencias), **no** un fallo nuevo introducido
por esta tarea.

Confirmado también que `s3://madrono-tfm-dev-bronze-222234418587/` sigue vacío
tras ambas invocaciones (`aws s3 ls --recursive` sin resultados) — coherente con
que el fallo sigue ocurriendo antes de instanciar `BronzeWriter`.

## Restricciones respetadas

- **No se ha ejecutado `terraform destroy`** en ningún momento.
- **No se ha modificado el código de `ingesta/`** — el cambio es puramente de
  empaquetado en `infra/terraform/lambda.tf`.
- **No se ha intentado resolver la falta de la Lambda Layer de dependencias de
  terceros** (`requests`, `beautifulsoup4`, `netCDF4`, `populartimes`, etc.) — sigue
  fuera de alcance, tal como pedía el enunciado; el error `No module named
  'requests'` observado tras el arreglo es la confirmación esperada de que ese
  problema (distinto y ya documentado) sigue pendiente, no algo que esta tarea deba
  resolver.
- **No se ha dejado nada programado** (cron, systemd timer, bucle) en esta EC2. No
  se ha instalado ninguna dependencia de terceros ni construido ninguna Lambda
  Layer real — el único artefacto local (`build/ingesta_source.zip`, ~550 KB de
  código fuente puro, ver tabla de `unzip -l` arriba) se generó en
  `infra/terraform/build/` (gitignored) y se eliminó al terminar la tarea, junto con
  `backend.hcl`, `terraform.tfvars`, `.terraform/` y `.terraform.lock.hcl`
  (regenerados a partir de sus `.example`, igual que en las tareas 029/030).
- El alcance del `apply` se limitó exactamente a lo que describía el prompt de esta
  tarea: actualizar el código de las 14 funciones ya existentes in-place. No se creó
  ni se destruyó ningún recurso.

## Relevante para tareas futuras

- **Sigue siendo el mismo bloqueante ya documentado por las tareas 029/030**: falta
  construir y desplegar la Lambda Layer real con `ingesta/requirements.txt`
  (`requests`, `beautifulsoup4`, `cdsapi`, `netCDF4`, `populartimes`) en un entorno
  compatible con el runtime de Lambda (Docker/manylinux, no esta EC2), subirla como
  `aws_lambda_layer_version` y fijar su ARN en `terraform.tfvars` vía
  `lambda_dependencies_layer_arn`. Hasta que eso exista, **las 14 funciones seguirán
  fallando** en su primer disparo programado real, ahora en el `import` de la
  primera dependencia de terceros que use cada módulo (`requests` es la más común,
  pero no la única — p. ej. `cams_calidad_aire_madrid.py` probablemente falle en
  `import cdsapi` o `netCDF4` en vez de/además de `requests`).
- Los 5 parámetros SSM siguen con el valor placeholder
  `CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM` (sin cambios en esta tarea) — sigue
  pendiente fijarlos a mano fuera de Terraform antes de un despliegue funcional
  real.
- Si una tarea futura vuelve a tocar `data.archive_file.ingesta_source`, tener en
  cuenta que ahora depende de `local.ingesta_source_files` (vía `fileset()`) en vez
  de `source_dir`/`excludes`: añadir un nuevo directorio a excluir (además de
  `tests/` y `capturas/samples/`) requiere añadir una condición `startswith(...)`
  más en esa lista, no una entrada en un argumento `excludes`. Si en el futuro
  `ingesta/` incorpora ficheros binarios fuera de `tests/`/`capturas/samples/`,
  `file()` fallará al leerlos (no soporta binarios) — en ese caso haría falta
  cambiar el bloque `source` para usar `filebase64`/`source_content_filename` según
  corresponda al tipo de fichero.
