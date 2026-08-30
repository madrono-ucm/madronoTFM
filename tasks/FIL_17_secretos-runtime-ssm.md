---
kind: fil
title: "Seguridad: leer secretos de SSM en runtime, no inyectarlos como env en claro"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
created_at: "2026-08-30"
depends_on: []
---

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
