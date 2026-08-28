# FIL-01 — Fix `aemet_prevision` silver→gold (fallo en producción)

## Síntoma

El job `madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold` fallaba en su
última ejecución (28/8):

```
An error occurred while calling o160.parquet. Failed to delete key: aemet_prevision_por_municipio_leadtime
```

`bronze-to-silver` del mismo dataset iba bien; la mitad de `aemet_avisos`
(otra tabla Gold del mismo job) también. Solo fallaba la escritura de
`aemet_prevision_por_municipio_leadtime`.

## Causa raíz — hueco de IAM, no del código Spark

`aemet_prevision` es **el único dataset del patrón** que escribe Gold con
`mode("overwrite")` (`procesamiento/silver_gold/aemet_prevision_avisos/
glue_silver_to_gold.py:132`). Es deliberado: su clave de negocio
`(municipio_code, leadtime_days)` no lleva fecha, así que cada ejecución
recalcula la tabla entera; con `append` se duplicaría una fila por horizonte
cada día (ver el comentario en el propio script). El resto de datasets usan
`append`.

`overwrite` estático de Spark **borra el directorio destino antes de
reescribir**, lo que exige `s3:DeleteObject`. La sentencia IAM
`WriteGoldAemetPrevisionPorMunicipioLeadtime` de
`infra/terraform/glue.tf` se había copiado del patrón `append` y solo tenía
`s3:PutObject` / `s3:AbortMultipartUpload` / `s3:ListMultipartUploadParts`.
Sobre un Gold vacío no había nada que borrar y el job "pasaba"; al acumular
objetos, el `delete` empezó a fallar.

## Arreglo

`infra/terraform/glue.tf`: añadido `s3:DeleteObject` a esa sentencia,
acotado a los dos recursos ya listados
(`gold/aemet_prevision_por_municipio_leadtime/*` + el marcador `_$folder$`),
con un comentario explicando por qué solo este dataset lo necesita.

`terraform apply -target=aws_iam_policy.glue_aemet_prevision_avisos_data_access`:
`0 added, 1 changed, 0 destroyed`.

## Verificación (28/8)

- `aws glue start-job-run` de `...-silver-to-gold` → **`SUCCEEDED`** (68 s,
  sin error).
- Athena: `SELECT count(*), max(processed_at) FROM
  aemet_prevision_por_municipio_leadtime` → 4 filas (1 municipio × 4 buckets
  de `leadtime_days`), `processed_at = 2026-08-28T14:55:30` (fresco, antes
  obsoleto).

## Nota

"Solo 1 `municipio_code`" es una limitación conocida y aparte: el productor
`aemet_prevision_avisos.py` captura la previsión de un único municipio
(Madrid), no un bug de este job.
