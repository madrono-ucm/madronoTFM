# 092 — QA: `terraform plan`/`apply` crashea si existe `__pycache__` local en `ingesta/`

## Causa raíz

`infra/terraform/lambda.tf`, local `ingesta_source_files` (usado por
`data.archive_file.ingesta_source` para empaquetar el .zip de las 14
Lambdas de ingesta), filtraba el resultado de `fileset(ingesta_source_root,
"**")` excluyendo solo `tests/` y `capturas/samples/`. No excluía
`__pycache__/` ni `.pyc`/`.pyo`. Ese directorio está en `.gitignore` (nunca
se commitea), pero lo genera cualquier ejecución local de
`python3 -m unittest` sobre `ingesta/` — algo rutinario antes de tocar
Terraform. `file(...)` sobre un `.pyc` (binario) falla porque no es UTF-8
válido.

## Reproducción (antes del fix)

1. `python3 -m unittest discover -s ingesta -p "test_*.py"` → genera
   `ingesta/__pycache__/`, `ingesta/tests/__pycache__/`,
   `ingesta/capturas/__pycache__/` reales (297 tests, todos en verde).
2. `terraform init -backend-config=backend.hcl` (backend S3 real, cuenta
   AWS de este proyecto) + `terraform plan` →

   ```
   Error: Error in function call
     on lambda.tf line 361, in data "archive_file" "ingesta_source":
     361:       content  = file("${local.ingesta_source_root}/${source.value}")
     source.value is "__pycache__/__init__.cpython-314.pyc"
   Call to function "file" failed: contents of
   "./../../ingesta/__pycache__/__init__.cpython-314.pyc" are not valid
   UTF-8; use the filebase64 function...
   ```

   Mismo error para cada `.pyc` generado — confirma el hallazgo de QA tal
   cual estaba descrito en el ticket.

## Fix

Se añaden tres condiciones al filtro existente (`strcontains`/`endswith`,
disponibles desde Terraform 1.5; `versions.tf` exige `>= 1.7.0`, instalado
1.15.8):

```hcl
if !startswith(f, "tests/") && !startswith(f, "capturas/samples/") &&
   !strcontains(f, "__pycache__/") && !endswith(f, ".pyc") && !endswith(f, ".pyo")
```

`strcontains(f, "__pycache__/")` cubre `__pycache__/` en cualquier nivel de
profundidad (`capturas/__pycache__/...`, no solo en la raíz); `.pyc`/`.pyo`
sueltos (por si existiera bytecode fuera de un `__pycache__/`, caso
infrecuente pero cubierto por Python) se excluyen aparte por extensión.

## Verificación

- Con `__pycache__` presente: `terraform plan` ya no falla — mismo
  `Plan: 10 to add, 55 to change, 5 to destroy` que sin `__pycache__`
  (drift ya documentado y aceptado, `doc/088`/`doc/090`, no relacionado con
  esta tarea).
- Checkout limpio (sin `__pycache__`): se comparó el plan completo
  (`terraform plan -no-color`, filtrando las líneas de progreso
  `Refreshing state...`/`Reading...`/`Read complete after ...s elapsed`,
  no deterministas por el orden de refresco asíncrono) generado con el
  código **antes** del fix contra el generado **después** del fix, mismo
  árbol limpio, mismo `terraform init` — resultado idéntico línea a línea
  (única diferencia real: una línea `Still reading... [Xs elapsed]` de
  progreso, por timing). Confirma que el fix no introduce ningún cambio en
  `aws_s3_object.procesamiento_source` ni en ninguna `aws_lambda_function`
  cuando no hay `__pycache__` que excluir.
- `terraform validate`: `Success!`.

Todo verificado con AWS real (cuenta `222234418587`, `eu-west-1`, rol
`madrono-terraform-deployerEC2` ya asumido en este entorno) y backend S3
real; ningún `terraform apply` — solo `plan`/`validate`, según el alcance
de esta tarea (igual que la tarea 088). `backend.hcl`/`terraform.tfvars`/
`.terraform/`/`.terraform.lock.hcl`/`build/` creados solo para esta
verificación, todos gitignored, borrados al terminar.

## Restricciones respetadas

- Solo se toca el filtro de `ingesta_source_files` en
  `infra/terraform/lambda.tf`.
- No se ha aplicado ningún cambio de infraestructura (`terraform apply`).
- No se ha tocado el drift documentado en `doc/088` (sigue pendiente de
  una recaptura/aplicación aparte).

## Relevante para tareas futuras

- Cualquier sesión que vaya a ejecutar `terraform plan`/`apply` tras haber
  corrido los tests de `ingesta/` ya no necesita limpiar `__pycache__` a
  mano primero.
- `infra/terraform/glue.tf` empaqueta `procesamiento/` con el mismo patrón
  exacto (`fileset` + `file()` por fichero, `data.archive_file
  "procesamiento_source"`), pero su filtro (`local.procesamiento_source_files`,
  línea ~41) ya excluía `__pycache__` (`!strcontains(f, "__pycache__")`)
  desde antes de esta tarea — no comparte el bug, no ha hecho falta
  tocarlo. Si se añade un tercer paquete empaquetado así en el futuro,
  replicar el filtro de `ingesta_source_files` (o el de
  `procesamiento_source_files`) desde el principio.
