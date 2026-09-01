---
kind: vic-eval
title: "Evaluación técnica ronda 7 — verificación independiente del terraform apply de FIL_16/FIL_17 + re-congelación"
owner: Claude (QA)
status: pending
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-7.md`](../doc/PLAN-EVALUACION-TECNICA-7.md).
**Solo lectura contra AWS** (profile `madrono`, ver
`.claude/.../memory/madrono-access.md` / `infra/OPERACION.md`). Ningún
`terraform apply`, ningún `aws` mutante, ningún cambio de código.

## Por qué

El 2026-09-01 una sesión interactiva ejecutó `terraform apply -target`
para:
- **`FIL_17`** — `aws_iam_policy.ingestion_lambda_secrets` + attachment +
  los 16 `aws_lambda_function.producer` (env `SECRETO` → `SECRETO_SSM_PATH`).
- **`FIL_16`** — parcial: `aws_cloudwatch_event_rule.glue_job_failed`
  creada; el topic SNS + policy + target fallaron por falta de permisos
  SNS en `madrono-terraform-deployer` (aceptado por el usuario, no es
  pendiente).
- **Pipeline**: `pipeline_enabled` `false`→`true` (aplicar) →
  verificación → `true`→`false` (re-aplicar). Ventana abierta ~24 min.

El `apply` fue **acotado con `-target`** para excluir el stack de Kafka
(deliberadamente sin aplicar) y un rebuild de la layer Lambda (drift
pre-existente de `ingesta/requirements.txt`). Hay que confirmar de forma
independiente que el resultado es correcto y que **no se coló nada más**.

## Alcance — verificar contra AWS real, en el momento del QA

Correr los comandos y pegar la salida real (no reciclar la de la sesión
del 2026-09-01).

1. **`FIL_17` — cero secretos en claro**: `aws lambda
   get-function-configuration` de `madrono-tfm-dev-aemet_prevision_avisos`,
   `-bluesky_menciones`, `-cams_calidad_aire`, `-transporte_publico_emt`
   → `Environment.Variables` debe ser **solo** `BRONZE_BASE_PATH` +
   `*_SSM_PATH`. Ningún valor de credencial.
2. **`FIL_17` — mínimo privilegio**: `aws iam get-policy-version` de
   `madrono-tfm-dev-ingestion-lambda-secrets` → `Action` = solo
   `ssm:GetParameter`, `Resource` = exactamente los **6 ARNs** de
   `/madrono-tfm/dev/secrets/*` (emt-client-id, emt-pass-key,
   bluesky-identifier, bluesky-app-password, aemet-api-key,
   cams-ads-api-key), **sin comodines**. Confirmar que está adjunta a
   `madrono-tfm-dev-ingestion-role`.
3. **`FIL_17` — la ruta de código correcta**: `grep` en los 4 módulos
   productores (`ingesta/capturas/**`) que el `CaptureConfig.from_env`
   usa `secretos.get_secret("X")`, no `os.environ["X"]` directo.
4. **Pipeline congelado de verdad**: `aws scheduler list-schedules` →
   los ~23 `madrono-tfm-dev-*` con `State=DISABLED` (contar, no muestrear).
   `aws glue get-triggers` → los `scheduled-bronze-to-silver` /
   `conditional-silver-to-gold` con `State=DEACTIVATED`. `terraform plan`
   acotado a `aws_scheduler_schedule.producer` + los 5 grupos de
   `aws_glue_trigger` → **`No changes`**.
5. **`FIL_16` parcial y coherente**: `aws events describe-rule
   madrono-tfm-dev-glue-job-failed` → `State=ENABLED`, patrón
   `{FAILED,TIMEOUT,ERROR}` sobre `Glue Job State Change`. `aws events
   list-targets-by-rule` → **`Targets: []`**. `aws sns list-topics` → **no
   existe** `madrono-tfm-dev-alertas-pipeline`. Confirmar que `doc/FIL-16`
   lo documenta como aceptado (no como pendiente).
6. **Cero drift colateral**: `terraform plan` completo (sin `-target`).
   Debe salir **exactamente**: Kafka ×5 (add), SNS ×3 (add, bloqueado
   IAM), `aws_s3_object.layer_build_source` (replace) +
   `aws_codebuild_project.lambda_dependencies_layer` (update) — y **nada
   más**. En particular confirmar que `aws_iam_policy.scheduler_invoke_lambda`
   ya **no** aparece (fue un recompute transitorio "known after apply"
   durante el `apply` del 2026-09-01; debe haber quedado estable).
7. **`terraform fmt -check -recursive` + `terraform validate`** limpios.
8. **Coste de la ventana**: contar los objetos Bronze escritos entre
   ~21:19 y ~21:43 UTC del 2026-09-01 (`aws s3 ls --recursive` sobre
   `s3://madrono-tfm-dev-bronze-.../*/fecha=2026-09-01/hora=21/` o
   CloudWatch de las Lambda). Cuantificar (esperado: el `invoke` manual de
   `cams_calidad_aire` = 1 fichero, + como mucho 1-2 ticks horarios).
9. **`FIL_40`/`FIL_41` de paso**: los 12 productores sin secreto también
   subieron `source_code_hash`. Confirmar que el hash desplegado
   corresponde al `.zip` que produce el repo en `HEAD` (build local del
   paquete y comparar `sha256`), no a algo inesperado.

## Criterios de aceptación

- Los 9 puntos verificados con comando + salida reales del momento del QA.
- Verdicto explícito por punto: correcto / desviación menor / problema
  real (→ `FIL_56`+).
- Informe en `doc/VIC-33-eval-fil16-17-terraform.md`.
- Cero cambios aplicados (código o infra).

## Restricciones

- Solo lectura. Nada de `terraform apply` ni `aws` mutante.
- Si algún comando `aws` lo bloquea el clasificador de auto-mode: anotarlo
  y seguir con el resto; no buscar rodeos.
