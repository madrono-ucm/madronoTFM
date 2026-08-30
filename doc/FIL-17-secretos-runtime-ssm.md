# FIL-17 — Secretos leídos de SSM en runtime, no inyectados en claro

## El problema

`infra/terraform/lambda.tf` creaba parámetros SSM `SecureString` para las
credenciales pero luego inyectaba **el valor real** como variable de entorno
de la Lambda:

```hcl
{ for name in each.value.secret_env : name => aws_ssm_parameter.secrets[name].value }
```

Cualquiera con `lambda:GetFunctionConfiguration` veía `AEMET_API_KEY`,
`EMT_CLIENT_ID`, `EMT_PASS_KEY`, `CAMS_ADS_API_KEY`,
`BLUESKY_IDENTIFIER`/`BLUESKY_APP_PASSWORD` en claro. Un revisor técnico lo
marca a la primera.

## La solución

### 1. Helper `ingesta/capturas/secretos.py`

`get_secret("AEMET_API_KEY")`:

1. Si `AEMET_API_KEY_SSM_PATH` está en el entorno → `ssm:GetParameter`
   `--with-decryption` sobre ese path, **cacheado por path** (una sola
   llamada por *cold start* del contenedor).
2. Si no → `os.environ.get("AEMET_API_KEY")` (tests, CLI local y cualquier
   despliegue que aún inyecte el valor directo siguen funcionando).
3. Ninguno → `None`.

Un error de SSM cuando el path SÍ está configurado **se propaga** (no
degrada a "sin credencial" en silencio).

### 2. `lambda.tf`: se inyecta el path, no el valor

```hcl
{ for name in each.value.secret_env : "${name}_SSM_PATH" => aws_ssm_parameter.secrets[name].name }
```

### 3. IAM de mínimo privilegio

`aws_iam_policy.ingestion_lambda_secrets`: `ssm:GetParameter` acotado a
`[for s in aws_ssm_parameter.secrets : s.arn]` — los 6 ARNs concretos, sin
`ssm:*` ni comodines de path. `kms:Decrypt` no hace falta explícito: los
parámetros usan `alias/aws/ssm` (clave gestionada por AWS), que autoriza el
descifrado vía el propio servicio SSM en la misma cuenta.

### 4. Productores adaptados (4 módulos)

| Módulo | Secretos |
|---|---|
| `transporte_publico_madrid` | `EMT_CLIENT_ID`, `EMT_PASS_KEY` |
| `bluesky_menciones_madrid` | `BLUESKY_IDENTIFIER`, `BLUESKY_APP_PASSWORD` |
| `aemet_prevision_avisos` | `AEMET_API_KEY` |
| `cams_calidad_aire_madrid` | `CAMS_ADS_API_KEY` |

Cambio mínimo: `os.environ.get("X", "")` → `secretos.get_secret("X") or ""`
en el `CaptureConfig.from_env` de cada uno. El resto de variables de
configuración (URLs, códigos de municipio…) siguen como env normales.

## Verificación

- `ingesta/tests/test_secretos.py` (6): lee de SSM con path, cachea por cold
  start, fallback a var directa, prioridad del path, `None` sin ninguno,
  propagación de error. Los 4 tests de productor afectados (+ toda la suite
  `ingesta/`, 309) siguen en verde: el fallback a `os.environ` mantiene el
  comportamiento en los tests que fijan la var directamente.
- `terraform validate` + `fmt -check` OK.

## Estado: aplicado en el código, `terraform apply` pendiente

Igual que `FIL_16`: el pipeline está congelado (`pipeline_enabled=false`),
las Lambda no se ejecutan. Al reanudar la ingesta, antes o junto al
`apply` general:

```bash
cd infra/terraform
AWS_PROFILE=madrono terraform apply \
  -target=aws_iam_policy.ingestion_lambda_secrets \
  -target=aws_iam_role_policy_attachment.ingestion_lambda_secrets \
  -target=aws_lambda_function.producer
# comprobar que ya no hay secretos en claro:
aws lambda get-function-configuration --function-name madrono-tfm-dev-aemet-prevision-avisos \
  --query 'Environment.Variables'   # -> sólo BRONZE_BASE_PATH + *_SSM_PATH
# e invocar un productor afectado:
aws lambda invoke --function-name madrono-tfm-dev-cams-calidad-aire /dev/stdout
```

Los valores reales ya están en los parámetros SSM (fijados a mano fuera de
git, `ignore_changes = [value]`); no hay que volver a ponerlos.

## Fuera de alcance (§7.5)

Rotación automática de credenciales, Secrets Manager (SSM `SecureString`
basta para este volumen), cifrado con CMK propia.
