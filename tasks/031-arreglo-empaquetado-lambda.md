---
id: 31
slug: arreglo-empaquetado-lambda
title: Arreglar el empaquetado del .zip de Lambda (falta el paquete ingesta/ de nivel
  superior)
status: in_progress
force: true
allow_infra_apply: true
branch: task/031-arreglo-empaquetado-lambda
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T21:39:17+00:00'
updated_at: '2026-08-14T21:40:44.922323+00:00'
started_at: '2026-08-14T21:40:44.922300+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 030 (`terraform apply` de las 14 Lambdas) verificó con una invocación
manual real que **las funciones fallan al arrancar**, y diagnosticó la causa raíz
sin corregirla (fuera de su alcance):

```
Runtime.ImportModuleError: Unable to import module 'ingesta.capturas.trafico_madrid': No module named 'ingesta'
```

`data.archive_file.ingesta_source` en `infra/terraform/lambda.tf` usa
`source_dir = "${path.module}/../../ingesta"`, lo que empaqueta el **contenido**
de `ingesta/` en la raíz del `.zip` (`capturas/`, `bronze.py`... sueltos) en vez de
preservar `ingesta/` como carpeta de nivel superior — pero el `handler` de cada
función (`ingesta.capturas.<módulo>.lambda_handler`) necesita que `ingesta` sea un
paquete importable desde la raíz. Confirmado en vivo por la 030 con
`unzip -l build/ingesta_source.zip` y con `aws s3 ls` (vacío) sobre el bucket
Bronze tras la invocación fallida.

**Excepción de alcance** (`allow_infra_apply: true`): tienes permiso para ejecutar
`terraform apply` sobre este cambio concreto (solo afecta al `filename`/
`source_code_hash` de las 14 funciones ya existentes, Terraform las actualiza
in-place, no crea ni destruye recursos) — nada más.

## Objetivo

Corregir el empaquetado para que `ingesta/` exista como carpeta de nivel superior
dentro del `.zip`, reaplicar, y verificar con una invocación manual real que ahora
sí se llega a ejecutar el código del productor (aunque probablemente falle después
por la falta de la Lambda Layer de dependencias — ver más abajo, eso NO es el
alcance de esta tarea).

## Alcance concreto

1. Corrige `data.archive_file.ingesta_source` (o la estructura que sea necesaria)
   en `infra/terraform/lambda.tf` para que el `.zip` resultante contenga
   `ingesta/__init__.py`, `ingesta/capturas/...`, etc., con `ingesta/` como
   prefijo — verifica con `unzip -l` sobre el `.zip` generado antes de aplicar
   nada, no lo des por hecho.
2. `terraform plan`: confirma que el único cambio es el `source_code_hash`/`filename`
   de las 14 `aws_lambda_function` (in-place, sin recrear ni destruir nada). Si el
   plan mostrara algo más, para y documenta en vez de aplicar.
3. `terraform apply -auto-approve`.
4. Invoca manualmente (`aws lambda invoke`) las mismas dos funciones que probó la
   tarea 030 (`aforos_peatones_bicicletas`, `cartelera_cines_estrenos`) y compara
   el error. Es esperable que **ahora fallen por otra causa** (falta de `requests`
   u otras dependencias de terceros, ya documentado como pendiente por la tarea
   029/030) — eso confirmaría que este arreglo concreto funcionó, aunque las
   Lambdas sigan sin funcionar de extremo a extremo todavía.
5. Documenta en `doc/031-arreglo-empaquetado-lambda.md` el antes/después exacto
   del error de cada invocación de prueba.

## Restricciones

- Alcance limitado a este bug de empaquetado. NO intentes resolver también la
  falta de la Lambda Layer de dependencias de terceros — es una decisión de
  herramienta (Docker/CodeBuild/GitHub Actions) pendiente de que el humano la
  tome, no algo que decidir dentro de esta tarea.
- NO ejecutes `terraform destroy`.
- No modifiques nada del código de `ingesta/` en sí — el problema es de
  empaquetado en Terraform, no del código Python.

## Criterios de aceptación

- El `.zip` desplegado contiene `ingesta/` como paquete de nivel superior
  (verificado con `unzip -l`).
- `terraform apply` completado sin error, solo actualizando las 14 funciones
  in-place.
- La invocación manual de prueba ya no falla por `No module named 'ingesta'` (puede
  seguir fallando por dependencias de terceros — eso es esperado y no es un fallo
  de esta tarea, documéntalo si ocurre).
