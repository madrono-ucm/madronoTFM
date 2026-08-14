---
id: 33
slug: conectar-lambda-layer-verificar
title: Conectar la Lambda Layer a las 14 funciones y verificar escritura real en Bronze
status: in_progress
force: false
allow_infra_apply: true
branch: task/033-conectar-lambda-layer-verificar
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T21:41:18+00:00'
updated_at: '2026-08-14T22:06:31.585634+00:00'
started_at: '2026-08-14T22:06:31.585611+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Última pieza de la migración a producción de la ingesta. La tarea 032 publicó una
Lambda Layer con las dependencias de terceros; la 031 arregló el empaquetado del
código propio. Esta tarea conecta ambas cosas a las 14 funciones y confirma, por
fin, que el pipeline completo escribe datos reales en Bronze.

**`force: false` deliberado**: en cuanto esta tarea aplique y verifique, las 20
invocaciones programadas empezarán a escribir datos de verdad en el bucket Bronze
de forma continua — es el punto real de arranque de la producción de datos, no solo
de infraestructura vacía. Prefiero fusionar este PR a mano tras ver la
verificación, no que se fusione solo.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para `terraform
apply` sobre este cambio (fija `lambda_dependencies_layer_arn` y actualiza las 14
funciones in-place) y para invocar Lambdas manualmente. Nada más.

## Objetivo

Fijar `lambda_dependencies_layer_arn` al ARN publicado por la tarea 032, aplicar, y
verificar con al menos 2-3 invocaciones manuales reales que los datos llegan a
Bronze.

## Alcance concreto

1. Lee el ARN de la Layer del resumen de `doc/032-lambda-layer-codebuild.md` y
   fíjalo en `terraform.tfvars` (`lambda_dependencies_layer_arn = "..."`).
2. `terraform plan`: confirma que el único cambio es añadir la Layer a las 14
   funciones (in-place, sin recrear ni destruir nada). Si mostrara algo más, para
   y documenta.
3. `terraform apply -auto-approve`.
4. Invoca manualmente (`aws lambda invoke`) al menos 2-3 funciones de distinta
   naturaleza (p.ej. una simple como `aforos_peatones_bicicletas`, una con más
   dependencias como `cartelera_cines_estrenos` si usa `beautifulsoup4`, y una que
   necesite credenciales reales como `bicimad` o `trafico`) y confirma con
   `aws s3 ls s3://madrono-tfm-dev-bronze-222234418587/ --recursive` que aparecen
   objetos nuevos tras cada invocación.
5. Si alguna función concreta sigue fallando (p.ej. por credenciales de
   AEMET/CAMS que nunca se llegaron a obtener, ver tareas 018/019), documenta cuál
   y por qué en `doc/033-conectar-lambda-layer-verificar.md` — no es necesariamente
   un fallo de esta tarea si el motivo es un bloqueo ya conocido de antes, pero
   debe quedar explícito qué funciona de extremo a extremo y qué no todavía.

## Restricciones

- NO ejecutes `terraform destroy`.
- NO modifiques el código de `ingesta/` en esta tarea — si algo falla por código
  (no por la Layer ni por credenciales), documenta el problema en vez de
  arreglarlo aquí; sería una tarea de seguimiento aparte.

## Criterios de aceptación

- Las 14 funciones tienen la Layer adjunta (verificado con `aws lambda
  get-function-configuration`).
- Al menos 2-3 invocaciones manuales de funciones distintas confirman escritura
  real y nueva en el bucket Bronze.
- `doc/033-conectar-lambda-layer-verificar.md` documenta, función por función, cuál
  quedó verificada funcionando de extremo a extremo y cuál no (con el motivo si
  aplica).
