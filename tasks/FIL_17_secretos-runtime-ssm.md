---
kind: fil
title: "Seguridad: leer secretos de SSM en runtime, no inyectarlos como env en claro"
owner: Filippos (interactive)
status: done
allow_infra_apply: true
created_at: "2026-08-30"
resolved_at: "2026-08-30"
depends_on: []
---

## Resolución (2026-08-30) — código aplicado, `terraform apply` pendiente

1. `ingesta/capturas/secretos.py` — `get_secret(name)`: si
   `<name>_SSM_PATH` está en el entorno → `ssm:GetParameter --with-decryption`
   cacheado por cold start; si no, fallback a `os.environ[name]` (tests /
   CLI local intactos); si ninguno, `None`. Error de SSM con path presente
   se propaga.
2. `lambda.tf`: el `merge` del `environment` inyecta ahora
   `"${name}_SSM_PATH" => aws_ssm_parameter.secrets[name].name` (el path),
   nunca `.value`.
3. IAM: `aws_iam_policy.ingestion_lambda_secrets` — `ssm:GetParameter`
   acotado a los 6 ARNs de `local.secrets` (sin comodines). Añadido al
   `depends_on` de `aws_lambda_function.producer`. `kms:Decrypt` no hace
   falta (clave `alias/aws/ssm` gestionada por AWS).
4. 4 módulos adaptados (`transporte_publico_madrid`, `bluesky_menciones_madrid`,
   `aemet_prevision_avisos`, `cams_calidad_aire_madrid`):
   `os.environ.get("X")` → `secretos.get_secret("X")` sólo para los 5
   secretos.
5. `ingesta/tests/test_secretos.py` (6) + suite `ingesta/` (309) en verde;
   `terraform validate` + `fmt -check` OK.

**`terraform apply` pendiente** (pipeline congelado, mismo criterio que
`FIL_16`): pasos de `apply -target` + verificación
(`get-function-configuration` sin secretos en claro + `lambda invoke`) en
`doc/FIL-17-...md`. Los valores reales ya están en los parámetros SSM.

## Contexto

`infra/terraform/lambda.tf` (`aws_ssm_parameter.secrets` + `secret_env`)
crea placeholders SSM `SecureString` pero luego **inyecta el valor real como
variable de entorno en claro** de la Lambda (visible en la consola / en
`get-function-configuration`). Afecta a `AEMET_API_KEY`, `EMT_CLIENT_ID`,
`EMT_PASS_KEY`, `CAMS_ADS_API_KEY` y `BLUESKY_IDENTIFIER`/
`BLUESKY_APP_PASSWORD` (añadidos al arreglar `bluesky`). El rol de ingesta
(`aws_iam_role.ingestion`) no tiene `ssm:GetParameter`.

## Objetivo

Que las Lambda de productores obtengan sus secretos con `ssm:GetParameter`
`--with-decryption` **en el handler** (cacheado en el `init` del contenedor),
en vez de recibirlos como env en claro. Higiene de seguridad estándar que
un revisor técnico mirará.

## Alcance

1. Un helper compartido `ingesta/capturas/secretos.py` — `get_secret(name)`:
   lee `os.environ` para el **path SSM** (no el valor) y hace un único
   `ssm.get_parameter(WithDecryption=True)` por cold start, cacheado.
2. `lambda.tf`: en vez de `{ name => aws_ssm_parameter.secrets[name].value }`
   inyectar `{ "${name}_SSM_PATH" => aws_ssm_parameter.secrets[name].name }`.
3. IAM: sentencia `ssm:GetParameter` en `aws_iam_role.ingestion` **acotada
   a los ARNs concretos** de `local.secrets` (mínimo privilegio) +
   `kms:Decrypt` sobre la clave del parámetro si aplica.
4. Adaptar los ~5 módulos de productor que hoy leen `os.environ["X"]`
   directamente a `secretos.get_secret("X")`.
5. `terraform apply -target` de las Lambda + roles; verificar que cada
   productor afectado invoca OK (con el pipeline congelado, invocación
   manual `aws lambda invoke`).

## Criterios de aceptación

- 0 secretos reales en `Environment.Variables` de las Lambda
  (`get-function-configuration` sólo muestra `*_SSM_PATH` y `BRONZE_BASE_PATH`).
- Cada productor afectado invoca correctamente leyendo de SSM.
- Tests del helper (mock de `boto3`). `doc/FIL-17-...md`.

## Restricciones

- Sin rotación automática (queda para §7.5).
- `terraform apply` tras revisión humana.

## Nota de prioridad (Claude QA, `VIC_18`, 30/8)

Verificado con `terraform plan` agregado (no solo el `-target` acotado del
PR original): el `apply` de este ticket **sigue pendiente** —
`aws_iam_policy.ingestion_lambda_secrets` aparece como "to add" y las 16
`aws_lambda_function.producer` como "to change" en un plan fresco de hoy.
A diferencia de `FIL_16` (seguro de dejar sin aplicar mientras la ingesta
está congelada — no hay nada que alertar), **este es un fix de
seguridad**: mientras no se aplique, las 16 Lambda en la cuenta real de
AWS siguen exponiendo sus credenciales en claro vía
`aws lambda get-function-configuration`, independientemente de que la
ingesta esté parada. Recomendado aplicar esto **antes** de reanudar la
ingesta, no como parte del mismo paso — son dos decisiones independientes.
Detalle completo en [`doc/VIC-18-eval-terraform-v2.md`](../doc/VIC-18-eval-terraform-v2.md).
