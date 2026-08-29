# FIL-10 — Plan de Terraform para aplicar la key estable de los 48 `glue_script_*` (tarea 107)

**Tarea deliberadamente de solo lectura hasta este punto** — el código
(`infra/terraform/glue.tf`) ya está mergeado en `main` (tarea 107, commit
`7a97133`), validado (`terraform fmt`/`validate` limpios) y con este plan
generado en modo lectura. **No se ha aplicado nada.** Sigue el patrón de dos
pasos de `tasks/README.md`: este documento es el "plan" para revisión; la
ejecución del `apply` requiere aprobación humana explícita antes de
lanzarse, mismo criterio que `FIL_09`/tareas 098/100.

## Resumen ejecutivo

- Extiende a los 48 `aws_s3_object.glue_script_*` el mismo fix de key
  estable que `FIL_09`/PR #175 aplicó a `procesamiento_source` tras el
  incidente de la tarea 106 (37/48 jobs de Glue rotos >28h por una key con
  hash borrada). Cada `glue_script_*` tiene exactamente un consumidor (su
  `aws_glue_job` correspondiente) que congela la key resuelta en su propio
  estado — mismo riesgo estructural, acotado a 1 job por incidente en vez
  de 37, pero repetido 48 veces. Detalle completo del análisis (incluido
  por qué `layer_build_source`, el otro *follow-up* que dejó anotado
  `FIL_09`, **no** comparte este riesgo y se descarta a propósito) en
  [`doc/107-glue-scripts-key-estable.md`](../doc/107-glue-scripts-key-estable.md).
- **No es urgente**: a diferencia de `FIL_09`, hoy no hay ningún job roto.
  Es una mejora preventiva para que este incidente no se repita en los
  scripts individuales.
- Plan verificado como seguro: **48 to add, 67 to change, 48 to destroy**
  (Kafka excluido a propósito, nunca aplicado). Verificado con `grep` que
  **no hay ninguna destrucción suelta** — los 48 `destroy` son la mitad-baja
  de los 48 pares `must be replaced` (key con hash → key estable,
  `create_before_destroy` en efecto en los 48, símbolo `+/-`, nunca
  `-/+`). Los 67 `change` son los `aws_glue_job.*` correspondientes
  actualizando su `script_location` a la key estable (in-place, sin
  *replace*) más dependientes indirectos (`aws_codebuild_project`,
  `aws_iam_policy.scheduler_invoke_lambda`) y drift preexistente no
  relacionado (`aws_lambda_function.producer[*]`, por trabajo de otras
  sesiones sobre el paquete compartido de Lambda).

## Recomendación

1. Que un humano revise este documento (resumen de arriba, y
   `doc/107-glue-scripts-key-estable.md` para el análisis completo,
   incluido por qué `layer_build_source` queda fuera).
2. Aprobar explícitamente la ejecución del `apply` — sin prisa, no hay
   nada roto hoy; puede esperar a un hueco de revisión tranquilo.
3. Tras el `apply`, verificar en vivo (no solo el código de salida):
   - `aws glue get-jobs` — los 48 `script_location`/`--extra-py-files`
     relevantes apuntan a keys sin hash (`glue-scripts/<nombre>.py`).
   - Lanzar o esperar al siguiente disparo programado de un par de jobs
     al azar, confirmar `SUCCEEDED`.
4. Documentar el resultado como una sección nueva al final de
   `doc/107-glue-scripts-key-estable.md` (no crear un `doc/` nuevo) y
   marcar esta ficha como resuelta.

## Cómo se generó este plan (reproducible)

```bash
cd infra/terraform
find ../../ingesta ../../procesamiento -iname "__pycache__" -type d -exec rm -rf {} +
export TF_PLUGIN_CACHE_DIR=/tmp/tf-plugin-cache   # poco disco en esta EC2, ver ticket 104
terraform init -input=false -backend-config=backend.hcl -reconfigure
TARGETS=$(terraform state list | grep -v '^data\.' | sed "s/^/-target='/;s/$/'/" | tr '\n' ' ')
eval "terraform plan -input=false -no-color $TARGETS"
```

## Plan completo, íntegro, sin acotar (salvo la exclusión de Kafka)

```

Warning: Deprecated Parameter

The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile"
instead.
data.archive_file.layer_build_source: Reading...
data.archive_file.layer_build_source: Read complete after 0s [id=a065adf344096385bd82b718b14ee9b9b05429f5]
data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role: Reading...
aws_cloudwatch_log_group.glue_shared["logs-v2"]: Refreshing state... [id=/aws-glue/jobs/logs-v2]
aws_ssm_parameter.secrets["BLUESKY_APP_PASSWORD"]: Refreshing state... [id=/madrono-tfm/dev/secrets/bluesky-app-password]
aws_glue_catalog_database.silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver]
aws_cloudwatch_log_group.glue_shared["output"]: Refreshing state... [id=/aws-glue/jobs/output]
aws_cloudwatch_log_group.glue_shared["error"]: Refreshing state... [id=/aws-glue/jobs/error]
aws_cloudwatch_log_group.producer["cartelera_cines_estrenos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-cartelera_cines_estrenos]
data.aws_caller_identity.current: Reading...
data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_cartelera_cines_estrenos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-cartelera-cines-estrenos]
data.aws_caller_identity.current: Read complete after 0s [id=222234418587]
aws_cloudwatch_log_group.glue_bluesky_menciones: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-bluesky-menciones]
data.archive_file.ingesta_source: Reading...
aws_cloudwatch_log_group.glue_cams_calidad_aire: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-cams-calidad-aire]
aws_cloudwatch_log_group.glue_aparcamientos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aparcamientos]
aws_cloudwatch_log_group.glue_trafico: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-trafico]
aws_cloudwatch_log_group.glue_aemet_prevision_avisos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aemet-prevision-avisos]
aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aforos-peatones-bicicletas]
aws_ssm_parameter.secrets["BLUESKY_IDENTIFIER"]: Refreshing state... [id=/madrono-tfm/dev/secrets/bluesky-identifier]
aws_ssm_parameter.secrets["CAMS_ADS_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/cams-ads-api-key]
aws_ssm_parameter.secrets["EMT_CLIENT_ID"]: Refreshing state... [id=/madrono-tfm/dev/secrets/emt-client-id]
aws_ssm_parameter.secrets["EMT_PASS_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/emt-pass-key]
aws_ssm_parameter.secrets["AEMET_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/aemet-api-key]
aws_cloudwatch_log_group.glue_ruido: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-ruido]
aws_cloudwatch_log_group.glue_meteorologia: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-meteorologia]
aws_cloudwatch_log_group.glue_transporte_publico_emt: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-transporte-publico-emt]
data.archive_file.procesamiento_source: Reading...
aws_cloudwatch_log_group.glue_afluencia_lugares: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-afluencia-lugares]
aws_cloudwatch_log_group.producer["bicimad"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-bicimad]
aws_cloudwatch_log_group.producer["ruido"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-ruido]
aws_cloudwatch_log_group.producer["emt_incidencias"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-emt_incidencias]
aws_cloudwatch_log_group.producer["calidad_aire"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-calidad_aire]
aws_cloudwatch_log_group.producer["meteorologia"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-meteorologia]
aws_cloudwatch_log_group.producer["agenda_eventos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-agenda_eventos]
aws_cloudwatch_log_group.producer["parques_jardines"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-parques_jardines]
aws_cloudwatch_log_group.producer["aemet_prevision_avisos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aemet_prevision_avisos]
aws_cloudwatch_log_group.producer["trafico"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-trafico]
aws_cloudwatch_log_group.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aforos_peatones_bicicletas]
aws_cloudwatch_log_group.producer["bluesky_menciones"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-bluesky_menciones]
aws_cloudwatch_log_group.producer["cams_calidad_aire"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-cams_calidad_aire]
aws_cloudwatch_log_group.producer["ser_calles"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-ser_calles]
aws_cloudwatch_log_group.producer["transporte_publico_emt"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-transporte_publico_emt]
aws_cloudwatch_log_group.producer["aparcamientos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aparcamientos]
data.aws_iam_policy_document.ingestion_assume_role: Reading...
data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role: Reading...
data.aws_iam_policy_document.ingestion_assume_role: Read complete after 0s [id=2690255455]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_afluencia_lugares_assume_role: Reading...
data.aws_iam_policy_document.lambda_layer_codebuild_assume_role: Reading...
data.aws_iam_policy_document.glue_afluencia_lugares_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_agenda_eventos_assume_role: Reading...
data.aws_iam_policy_document.lambda_layer_codebuild_assume_role: Read complete after 0s [id=1229436035]
data.aws_iam_policy_document.glue_agenda_eventos_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_agenda_eventos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-agenda-eventos]
data.aws_iam_policy_document.glue_ruido_assume_role: Reading...
aws_cloudwatch_log_group.glue_bicimad: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-bicimad]
data.aws_iam_policy_document.glue_meteorologia_assume_role: Reading...
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role: Reading...
data.aws_iam_policy_document.glue_ruido_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_meteorologia_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_calidad_aire_assume_role: Reading...
data.aws_iam_policy_document.glue_bicimad_assume_role: Reading...
data.aws_iam_policy_document.scheduler_assume_role: Reading...
data.aws_iam_policy_document.glue_bicimad_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_calidad_aire_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.scheduler_assume_role: Read complete after 0s [id=52247394]
data.aws_iam_policy_document.glue_aparcamientos_assume_role: Reading...
data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role: Reading...
aws_glue_catalog_database.gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold]
data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role: Reading...
data.aws_iam_policy_document.glue_bluesky_menciones_assume_role: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_aparcamientos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_trafico_assume_role: Reading...
aws_cloudwatch_log_group.glue_calidad_aire: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-calidad-aire]
aws_iam_role.glue_cams_calidad_aire: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role]
data.aws_iam_policy_document.glue_bluesky_menciones_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_trafico_assume_role: Read complete after 0s [id=2681768870]
aws_s3_bucket.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
data.aws_iam_policy_document.athena_query_assume_role: Reading...
aws_s3_bucket.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
data.aws_iam_policy_document.athena_query_assume_role: Read complete after 0s [id=337710939]
aws_iam_role.glue_afluencia_lugares: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role]
aws_iam_role.ingestion: Refreshing state... [id=madrono-tfm-dev-ingestion-role]
aws_iam_role.glue_aemet_prevision_avisos: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role]
aws_iam_role.lambda_layer_codebuild: Refreshing state... [id=madrono-tfm-dev-lambda-layer-codebuild-role]
aws_iam_role.glue_agenda_eventos: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role]
aws_iam_role.glue_ruido: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role]
aws_iam_role.glue_cartelera_cines_estrenos: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role]
aws_iam_role.glue_meteorologia: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role]
aws_iam_role.glue_calidad_aire: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role]
aws_iam_role.glue_bicimad: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role]
data.aws_iam_policy_document.ingestion_lambda_logs: Reading...
aws_iam_role.scheduler: Refreshing state... [id=madrono-tfm-dev-scheduler-role]
aws_iam_role.glue_transporte_publico_emt: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role]
data.aws_iam_policy_document.ingestion_lambda_logs: Read complete after 0s [id=2241953021]
aws_iam_role.glue_aforos_peatones_bicicletas: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role]
aws_iam_role.glue_aparcamientos: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role]
aws_iam_role.glue_bluesky_menciones: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role]
aws_iam_role.glue_trafico: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role]
aws_s3_bucket.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_iam_role.athena_query: Refreshing state... [id=madrono-tfm-dev-athena-query-role]
aws_s3_bucket.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_athena_workgroup.silver_gold: Refreshing state... [id=madrono-tfm-dev-silver-gold]
aws_s3_bucket_server_side_encryption_configuration.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_s3_bucket_public_access_block.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
data.aws_iam_policy_document.athena_results_bucket_policy: Reading...
data.aws_iam_policy_document.athena_results_bucket_policy: Read complete after 0s [id=3728792540]
aws_s3_bucket_lifecycle_configuration.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_iam_role_policy_attachment.glue_afluencia_lugares_service_role: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role-20260817225242316200000006]
aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup_gold: Refreshing state... [id=glue-scripts/cams_calidad_aire_backfill_dedup_gold-fa45e88fe2d37635cc6240ef327383ff.py]
aws_lambda_layer_version.ingesta_dependencies: Refreshing state... [id=arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1]
aws_s3_object.glue_script_afluencia_lugares_silver_to_gold: Refreshing state... [id=glue-scripts/afluencia_lugares_estimada-818054b226fcfb9227d13b69da7397f3.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_backfill_dedup-bfb76e782afee2c5956f548a34da0b18.py]
aws_s3_object.layer_build_source: Refreshing state... [id=source/ingesta-requirements-65d5d59fef3021bc0831a29454145c7b.zip]
aws_s3_object.glue_script_ruido_bronze_to_silver: Refreshing state... [id=glue-scripts/ruido_bronze_to_silver-57461bb981d80490227ccb4922409ef9.py]
aws_s3_object.glue_script_meteorologia_bronze_to_silver: Refreshing state... [id=glue-scripts/meteorologia_bronze_to_silver-3fcf5c38a2dd24e79206eb53af97348a.py]
aws_s3_object.glue_script_transporte_publico_emt_bronze_to_silver: Refreshing state... [id=glue-scripts/transporte_publico_emt_bronze_to_silver-5b3c3602b3f60bf9ff3ef5cfe1c8d6a9.py]
aws_s3_object.glue_script_agenda_eventos_backfill_dedup: Refreshing state... [id=glue-scripts/agenda_eventos_backfill_dedup-ebb7fb05697677064a5b18ee492aca9e.py]
aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup: Refreshing state... [id=glue-scripts/cams_calidad_aire_backfill_dedup-69f636c9df5c3880b98dff5bf4088421.py]
aws_s3_object.glue_script_aparcamientos_backfill_dedup: Refreshing state... [id=glue-scripts/aparcamientos_backfill_dedup-0040b8ac53f09f609005c2ad2aac464f.py]
data.archive_file.ingesta_source: Read complete after 3s [id=12ad18563270873bdfd7ab50cc89f7a02cf85c49]
aws_s3_object.glue_script_bronze_to_silver: Refreshing state... [id=glue-scripts/trafico_bronze_to_silver-ae01fdf48416d1e59a499e725af5eeb4.py]
aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold: Refreshing state... [id=glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py]
aws_s3_object.glue_script_meteorologia_backfill_dedup_gold: Refreshing state... [id=glue-scripts/meteorologia_backfill_dedup_gold-cb6dc670fef14d383aaa366eb184d811.py]
aws_s3_object.glue_script_silver_to_gold: Refreshing state... [id=glue-scripts/trafico_silver_to_gold-1884fa42b9e7b491c226ccb77bb38a49.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_bronze_to_silver: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d8325aae3ee77630cfc0f6612c30323e.py]
aws_s3_object.glue_script_ruido_backfill_dedup: Refreshing state... [id=glue-scripts/ruido_backfill_dedup-2cf7215ae11978fc12206039bba3aece.py]
aws_s3_object.glue_script_agenda_eventos_backfill_dedup_gold: Refreshing state... [id=glue-scripts/agenda_eventos_backfill_dedup_gold-c417e4a5711e3fcb2d416cc0f05f3290.py]
aws_s3_object.glue_script_cartelera_cines_estrenos_bronze_to_silver: Refreshing state... [id=glue-scripts/cartelera_cines_estrenos_bronze_to_silver-77e98d1cd921c208bf5ffaa29d284e32.py]
aws_s3_bucket_public_access_block.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_object.glue_script_calidad_aire_silver_to_gold: Refreshing state... [id=glue-scripts/calidad_aire_silver_to_gold-8333a2c7125ffd86e09976ae4db5114d.py]
aws_s3_object.glue_script_bicimad_bronze_to_silver: Refreshing state... [id=glue-scripts/bicimad_bronze_to_silver-cd282dfb63915ca6f80b2ccbd8143809.py]
aws_s3_object.glue_script_bluesky_menciones_silver_to_gold: Refreshing state... [id=glue-scripts/bluesky_menciones_silver_to_gold-8c43f4a9df541e2eea43a8456514dc10.py]
aws_s3_object.glue_script_agenda_eventos_bronze_to_silver: Refreshing state... [id=glue-scripts/agenda_eventos_bronze_to_silver-75c29ecd15eb33bf665840234bcf5cc8.py]
aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup: Refreshing state... [id=glue-scripts/transporte_publico_emt_backfill_dedup-961447ee3174a4e4ef33f1b6e006affa.py]
aws_s3_object.glue_script_bicimad_backfill_dedup_gold: Refreshing state... [id=glue-scripts/bicimad_backfill_dedup_gold-0eb546a683ffaa467741ed1fa47a2abb.py]
aws_s3_object.glue_script_meteorologia_backfill_dedup: Refreshing state... [id=glue-scripts/meteorologia_backfill_dedup-1fa9eaae33ade611f68b64e9ac2dffc0.py]
aws_s3_object.glue_script_calidad_aire_backfill_dedup: Refreshing state... [id=glue-scripts/calidad_aire_backfill_dedup-6d44949bc6077a4ec6bba66eff619e0e.py]
aws_s3_object.glue_script_bicimad_silver_to_gold: Refreshing state... [id=glue-scripts/bicimad_silver_to_gold-dd61f49fdef5e187adf9e3b2cb0bcd68.py]
aws_s3_object.glue_script_cams_calidad_aire_silver_to_gold: Refreshing state... [id=glue-scripts/cams_calidad_aire_silver_to_gold-f83d74685a5a4d930a50993f848d2a01.py]
aws_s3_object.glue_script_calidad_aire_backfill_dedup_gold: Refreshing state... [id=glue-scripts/calidad_aire_backfill_dedup_gold-879b3165bb85419fae5a2b8078c723d0.py]
aws_iam_role_policy_attachment.glue_aemet_prevision_avisos_service_role: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role-20260817225242271000000004]
aws_s3_object.glue_script_aparcamientos_silver_to_gold: Refreshing state... [id=glue-scripts/aparcamientos_silver_to_gold-b55a4a1d69d1eadf50394eb93b034fd8.py]
data.aws_iam_policy_document.build_artifacts_bucket_policy: Reading...
aws_s3_object.glue_script_bluesky_menciones_backfill_dedup: Refreshing state... [id=glue-scripts/bluesky_menciones_backfill_dedup-d20c9b44b3da1387c2a6a1d6fd6a5090.py]
aws_s3_object.glue_script_bluesky_menciones_bronze_to_silver: Refreshing state... [id=glue-scripts/bluesky_menciones_bronze_to_silver-e2d8897c5d4760401b16893568ac32ee.py]
data.aws_iam_policy_document.build_artifacts_bucket_policy: Read complete after 0s [id=1312249984]
aws_s3_object.glue_script_ruido_backfill_dedup_gold: Refreshing state... [id=glue-scripts/ruido_backfill_dedup_gold-db9317465c5f82d4c56c9faae1e83723.py]
aws_s3_object.glue_script_bluesky_menciones_backfill_dedup_gold: Refreshing state... [id=glue-scripts/bluesky_menciones_backfill_dedup_gold-9cfe45ea7aef30a0f20892f1bdaccb0a.py]
aws_s3_object.glue_script_aparcamientos_bronze_to_silver: Refreshing state... [id=glue-scripts/aparcamientos_bronze_to_silver-4c9fe8e66729a98c520c97a0aa10f630.py]
aws_s3_object.glue_script_aemet_prevision_avisos_bronze_to_silver: Refreshing state... [id=glue-scripts/aemet_prevision_avisos_bronze_to_silver-d7b98621b0e2b5a6d5d4c70119146f34.py]
aws_s3_object.glue_script_cams_calidad_aire_bronze_to_silver: Refreshing state... [id=glue-scripts/cams_calidad_aire_bronze_to_silver-9211d3802eca398bfda830e10b7b8ef2.py]
aws_s3_object.glue_script_ruido_silver_to_gold: Refreshing state... [id=glue-scripts/ruido_silver_to_gold-77502f7109487420c57b7e41102616e3.py]
aws_s3_bucket_server_side_encryption_configuration.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_bucket_lifecycle_configuration.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup_gold: Refreshing state... [id=glue-scripts/transporte_publico_emt_backfill_dedup_gold-318da358079d2d12e5b8c55e656eb079.py]
aws_s3_object.glue_script_aparcamientos_backfill_dedup_gold: Refreshing state... [id=glue-scripts/aparcamientos_backfill_dedup_gold-7f4c18ec21a262d4a6e788348e492c3f.py]
data.aws_iam_policy_document.lambda_layer_codebuild: Reading...
aws_s3_object.glue_script_agenda_eventos_silver_to_gold: Refreshing state... [id=glue-scripts/agenda_eventos_silver_to_gold-4d854fda4df74abc055b9eba9af92b0f.py]
aws_s3_object.glue_script_afluencia_lugares_bronze_to_silver: Refreshing state... [id=glue-scripts/afluencia_lugares_bronze_to_silver-2299183b4c60edf1e2539fc00a59ccc5.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_silver_to_gold-a7df88f8aa89cea895c3e594ff738600.py]
aws_s3_object.glue_script_meteorologia_silver_to_gold: Refreshing state... [id=glue-scripts/meteorologia_silver_to_gold-4fb287e094c6f4dd3cb17585cbde692e.py]
data.aws_iam_policy_document.lambda_layer_codebuild: Read complete after 1s [id=2269842593]
aws_s3_object.glue_script_transporte_publico_emt_silver_to_gold: Refreshing state... [id=glue-scripts/transporte_publico_emt_silver_to_gold-7cd0d472adb8dfd5d48cc79dfad6acdb.py]
aws_s3_object.glue_script_calidad_aire_bronze_to_silver: Refreshing state... [id=glue-scripts/calidad_aire_bronze_to_silver-4eb1972a460e5e10ae7df4a3315f52d4.py]
aws_s3_object.glue_script_aemet_prevision_avisos_silver_to_gold: Refreshing state... [id=glue-scripts/aemet_prevision_avisos_silver_to_gold-e203db858089238019b642eb9b9f6a23.py]
aws_s3_object.glue_script_bicimad_backfill_dedup: Refreshing state... [id=glue-scripts/bicimad_backfill_dedup-4a3264e9732202731f31d5974bbe9017.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup_gold: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-7c312ea88152d382dd1e02b82a549a7c.py]
aws_iam_role_policy_attachment.glue_cams_calidad_aire_service_role: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role-20260817225242109200000002]
aws_iam_role_policy_attachment.glue_agenda_eventos_service_role: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role-20260817225242339700000007]
aws_iam_policy.ingestion_lambda_logs: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-lambda-logs]
aws_iam_role_policy_attachment.glue_calidad_aire_service_role: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role-20260816075639813800000006]
aws_iam_role_policy_attachment.glue_cartelera_cines_estrenos_service_role: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role-2026081722524271480000000b]
aws_iam_role_policy_attachment.glue_bicimad_service_role: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role-20260816075639036000000002]
aws_iam_role_policy_attachment.glue_meteorologia_service_role: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role-20260816075639015600000001]
aws_iam_role_policy_attachment.glue_ruido_service_role: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role-20260817225242315200000005]
aws_iam_role_policy_attachment.glue_aforos_peatones_bicicletas_service_role: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role-20260817225242176000000003]
aws_iam_role_policy_attachment.glue_transporte_publico_emt_service_role: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role-20260816075639707000000005]
aws_iam_role_policy_attachment.glue_aparcamientos_service_role: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role-20260816075639434100000004]
aws_iam_role_policy_attachment.glue_bluesky_menciones_service_role: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role-20260817225241998700000001]
aws_s3_bucket_policy.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_iam_role_policy_attachment.glue_trafico_service_role: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role-20260816075639044000000003]
data.aws_iam_policy_document.athena_query: Reading...
aws_glue_job.cams_calidad_aire_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-gold-backfill-dedup]
data.aws_iam_policy_document.glue_aparcamientos_data_access: Reading...
data.aws_iam_policy_document.athena_query: Read complete after 0s [id=1764529612]
data.aws_iam_policy_document.glue_meteorologia_data_access: Reading...
data.aws_iam_policy_document.glue_aparcamientos_data_access: Read complete after 0s [id=3918684311]
data.aws_iam_policy_document.glue_bluesky_menciones_data_access: Reading...
data.aws_iam_policy_document.glue_bluesky_menciones_data_access: Read complete after 0s [id=3016547089]
data.aws_iam_policy_document.glue_transporte_publico_emt_data_access: Reading...
data.aws_iam_policy_document.glue_ruido_data_access: Reading...
data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access: Reading...
data.aws_iam_policy_document.glue_meteorologia_data_access: Read complete after 0s [id=1660976330]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access: Reading...
aws_glue_catalog_table.afluencia_lugares_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:afluencia_lugares_por_lugar_fecha_hora]
data.aws_iam_policy_document.glue_ruido_data_access: Read complete after 0s [id=3942754620]
aws_glue_catalog_table.cams_calidad_aire_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:cams_calidad_aire_por_contaminante_fecha_validez]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access: Read complete after 0s [id=3244402974]
data.aws_iam_policy_document.glue_transporte_publico_emt_data_access: Read complete after 0s [id=1469263382]
data.aws_iam_policy_document.glue_agenda_eventos_data_access: Reading...
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access: Read complete after 0s [id=3258002293]
aws_glue_catalog_table.aemet_prevision_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aemet_prevision_por_municipio_leadtime]
aws_glue_catalog_table.transporte_publico_emt_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:transporte_publico_emt_por_parada_hora]
aws_glue_catalog_table.calidad_aire_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:calidad_aire_por_estacion_contaminante_hora]
data.aws_iam_policy_document.glue_agenda_eventos_data_access: Read complete after 0s [id=2233283693]
aws_glue_catalog_table.aforos_peatones_bicicletas_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aforos_peatones_bicicletas_por_estacion_modo_hora]
aws_glue_catalog_table.meteorologia_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:meteorologia_por_estacion_magnitud_hora]
aws_glue_catalog_table.aemet_avisos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aemet_avisos_por_zona_fecha_nivel]
data.aws_iam_policy_document.glue_cams_calidad_aire_data_access: Reading...
data.aws_iam_policy_document.glue_cams_calidad_aire_data_access: Read complete after 0s [id=3873881262]
aws_glue_catalog_table.bicimad_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:bicimad_por_estacion_hora]
aws_glue_catalog_table.aparcamientos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aparcamientos]
aws_glue_catalog_table.aemet_prevision_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aemet_prevision]
aws_glue_catalog_table.calidad_aire_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:calidad_aire]
data.aws_iam_policy_document.glue_calidad_aire_data_access: Reading...
aws_glue_catalog_table.transporte_publico_emt_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:transporte_publico_emt]
aws_glue_catalog_table.agenda_eventos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:agenda_eventos]
data.aws_iam_policy_document.glue_calidad_aire_data_access: Read complete after 0s [id=3442098839]
aws_glue_catalog_table.aforos_peatones_bicicletas_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aforos_peatones_bicicletas]
aws_glue_catalog_table.aemet_avisos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aemet_avisos]
aws_glue_catalog_table.meteorologia_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:meteorologia]
aws_glue_catalog_table.bicimad_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:bicimad]
aws_glue_catalog_table.ruido_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:ruido_por_estacion_periodo_fecha]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_glue_catalog_table.afluencia_lugares_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:afluencia_lugares]
aws_glue_catalog_table.trafico_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:trafico_por_punto_hora]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_glue_catalog_table.cams_calidad_aire_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:cams_calidad_aire]
data.aws_iam_policy_document.glue_trafico_data_access: Reading...
aws_glue_catalog_table.aparcamientos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aparcamientos_por_parking_hora]
data.aws_iam_policy_document.ingestion_bronze_write: Reading...
data.aws_iam_policy_document.glue_trafico_data_access: Read complete after 0s [id=3067492418]
data.aws_iam_policy_document.bucket_policy["bronze"]: Reading...
data.aws_iam_policy_document.bucket_policy["bronze"]: Read complete after 0s [id=42177744]
data.aws_iam_policy_document.ingestion_bronze_write: Read complete after 0s [id=175239690]
aws_s3_bucket_versioning.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.aws_iam_policy_document.bucket_policy["gold"]: Reading...
data.aws_iam_policy_document.bucket_policy["silver"]: Reading...
data.aws_iam_policy_document.bucket_policy["silver"]: Read complete after 0s [id=168412883]
aws_s3_bucket_versioning.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
data.aws_iam_policy_document.bucket_policy["gold"]: Read complete after 0s [id=1014628649]
aws_s3_bucket_versioning.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_glue_catalog_table.trafico_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:trafico]
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access: Read complete after 1s [id=2497092921]
aws_glue_catalog_table.cartelera_cines_estrenos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:cartelera_cines_estrenos]
aws_s3_bucket_public_access_block.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.aws_iam_policy_document.glue_afluencia_lugares_data_access: Reading...
data.aws_iam_policy_document.glue_afluencia_lugares_data_access: Read complete after 0s [id=827917947]
aws_s3_bucket_public_access_block.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_public_access_block.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_glue_catalog_table.agenda_eventos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:agenda_eventos_por_categoria_distrito_fecha]
aws_glue_catalog_table.bluesky_menciones_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:bluesky_menciones_por_termino_modo_hora]
aws_glue_catalog_table.bluesky_menciones_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:bluesky_menciones]
aws_glue_catalog_table.ruido_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:ruido]
data.aws_iam_policy_document.glue_bicimad_data_access: Reading...
data.aws_iam_policy_document.glue_bicimad_data_access: Read complete after 0s [id=2467033104]
aws_glue_catalog_table.cartelera_cines_estrenos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:cartelera_cines_estrenos_por_pelicula_cine_fecha]
aws_glue_job.meteorologia_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-meteorologia-gold-backfill-dedup]
aws_glue_job.agenda_eventos_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-gold-backfill-dedup]
aws_glue_job.bicimad_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bicimad-gold-backfill-dedup]
aws_s3_bucket_policy.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_glue_job.bluesky_menciones_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-gold-backfill-dedup]
aws_glue_job.calidad_aire_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-calidad-aire-gold-backfill-dedup]
aws_glue_job.ruido_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-ruido-gold-backfill-dedup]
aws_iam_role_policy.lambda_layer_codebuild: Refreshing state... [id=madrono-tfm-dev-lambda-layer-codebuild-role:madrono-tfm-dev-lambda-layer-codebuild-policy]
aws_glue_job.transporte_publico_emt_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-gold-backfill-dedup]
aws_glue_job.aparcamientos_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aparcamientos-gold-backfill-dedup]
aws_glue_job.aforos_peatones_bicicletas_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-gold-backfill-dedup]
aws_iam_policy.athena_query: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-athena-query]
aws_iam_role_policy_attachment.ingestion_lambda_logs: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260814212955875100000001]
aws_iam_policy.glue_aparcamientos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aparcamientos-data-access]
aws_iam_policy.glue_bluesky_menciones_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-bluesky-menciones-data-access]
aws_iam_policy.glue_meteorologia_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-meteorologia-data-access]
aws_iam_policy.glue_ruido_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ruido-data-access]
aws_iam_policy.glue_aemet_prevision_avisos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aemet-prevision-avisos-data-access]
aws_iam_policy.glue_transporte_publico_emt_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-transporte-publico-emt-data-access]
aws_iam_policy.glue_cartelera_cines_estrenos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-cartelera-cines-estrenos-data-access]
aws_iam_policy.glue_agenda_eventos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-agenda-eventos-data-access]
aws_iam_policy.glue_cams_calidad_aire_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-cams-calidad-aire-data-access]
aws_iam_policy.glue_calidad_aire_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-calidad-aire-data-access]
aws_iam_policy.glue_trafico_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-trafico-data-access]
aws_iam_policy.ingestion_bronze_write: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-bronze-write]
aws_s3_bucket_policy.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_policy.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_policy.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_iam_policy.glue_aforos_peatones_bicicletas_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aforos-peatones-bicicletas-data-access]
aws_iam_policy.glue_afluencia_lugares_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-afluencia-lugares-data-access]
aws_iam_policy.glue_bicimad_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-bicimad-data-access]
aws_lambda_function.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos_peatones_bicicletas]
aws_codebuild_project.lambda_dependencies_layer: Refreshing state... [id=arn:aws:codebuild:eu-west-1:222234418587:project/madrono-tfm-dev-lambda-dependencies-layer]
aws_lambda_function.producer["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido]
aws_lambda_function.producer["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky_menciones]
aws_lambda_function.producer["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad]
aws_lambda_function.producer["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia]
aws_lambda_function.producer["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico]
aws_lambda_function.producer["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad_aire]
aws_lambda_function.producer["emt_incidencias"]: Refreshing state... [id=madrono-tfm-dev-emt_incidencias]
aws_lambda_function.producer["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte_publico_emt]
data.archive_file.procesamiento_source: Still reading... [00m10s elapsed]
aws_lambda_function.producer["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet_prevision_avisos]
aws_lambda_function.producer["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda_eventos]
aws_lambda_function.producer["ser_calles"]: Refreshing state... [id=madrono-tfm-dev-ser_calles]
aws_lambda_function.producer["parques_jardines"]: Refreshing state... [id=madrono-tfm-dev-parques_jardines]
aws_lambda_function.producer["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos]
aws_lambda_function.producer["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams_calidad_aire]
aws_lambda_function.producer["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera_cines_estrenos]
data.archive_file.procesamiento_source: Read complete after 11s [id=ae8c8f673275334b6e3c720d48940d7399264c78]
aws_iam_role_policy_attachment.glue_aparcamientos_data_access: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role-20260816075639899700000008]
aws_iam_role_policy_attachment.athena_query: Refreshing state... [id=madrono-tfm-dev-athena-query-role-20260820014319117700000001]
aws_iam_role_policy_attachment.glue_meteorologia_data_access: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role-2026081607564030390000000c]
aws_iam_role_policy_attachment.glue_bluesky_menciones_data_access: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role-2026081722524272500000000d]
aws_iam_role_policy_attachment.glue_aemet_prevision_avisos_data_access: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role-20260817225242985500000010]
aws_iam_role_policy_attachment.glue_ruido_data_access: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role-20260817225242694700000008]
aws_iam_role_policy_attachment.glue_transporte_publico_emt_data_access: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role-2026081607564024520000000b]
aws_iam_role_policy_attachment.glue_cartelera_cines_estrenos_data_access: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role-2026081722524271210000000a]
aws_s3_bucket_lifecycle_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_lifecycle_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_lifecycle_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_iam_role_policy_attachment.glue_agenda_eventos_data_access: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role-2026081722524290960000000f]
aws_iam_role_policy_attachment.glue_cams_calidad_aire_data_access: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role-2026081722524272170000000c]
aws_iam_role_policy_attachment.glue_trafico_data_access: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role-2026081607564002340000000a]
aws_iam_role_policy_attachment.glue_calidad_aire_data_access: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role-20260816075639853300000007]
aws_iam_role_policy_attachment.ingestion_bronze_write: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260813160151981500000001]
aws_iam_role_policy_attachment.glue_aforos_peatones_bicicletas_data_access: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role-20260817225242712100000009]
aws_iam_role_policy_attachment.glue_afluencia_lugares_data_access: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role-2026081722524275410000000e]
aws_iam_role_policy_attachment.glue_bicimad_data_access: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role-20260816075639983400000009]
aws_scheduler_schedule.producer["aparcamientos"]: Refreshing state... [id=default/madrono-tfm-dev-aparcamientos]
aws_scheduler_schedule.producer["aemet_prevision_1400"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_prevision_1400]
aws_scheduler_schedule.producer["cams_0715_utc"]: Refreshing state... [id=default/madrono-tfm-dev-cams_0715_utc]
aws_scheduler_schedule.producer["bluesky_menciones"]: Refreshing state... [id=default/madrono-tfm-dev-bluesky_menciones]
aws_scheduler_schedule.producer["emt_llegadas"]: Refreshing state... [id=default/madrono-tfm-dev-emt_llegadas]
aws_scheduler_schedule.producer["aemet_avisos_0800"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_0800]
aws_scheduler_schedule.producer["parques_jardines"]: Refreshing state... [id=default/madrono-tfm-dev-parques_jardines]
aws_scheduler_schedule.producer["ser_calles"]: Refreshing state... [id=default/madrono-tfm-dev-ser_calles]
aws_scheduler_schedule.producer["aemet_avisos_1100"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_1100]
aws_scheduler_schedule.producer["aemet_avisos_1800"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_1800]
aws_scheduler_schedule.producer["aemet_prevision_0700"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_prevision_0700]
aws_scheduler_schedule.producer["emt_incidencias"]: Refreshing state... [id=default/madrono-tfm-dev-emt_incidencias]
aws_scheduler_schedule.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=default/madrono-tfm-dev-aforos_peatones_bicicletas]
aws_scheduler_schedule.producer["aemet_avisos_2350"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_2350]
aws_scheduler_schedule.producer["bicimad"]: Refreshing state... [id=default/madrono-tfm-dev-bicimad]
aws_scheduler_schedule.producer["cams_0900_utc"]: Refreshing state... [id=default/madrono-tfm-dev-cams_0900_utc]
aws_scheduler_schedule.producer["agenda_eventos"]: Refreshing state... [id=default/madrono-tfm-dev-agenda_eventos]
aws_scheduler_schedule.producer["calidad_aire"]: Refreshing state... [id=default/madrono-tfm-dev-calidad_aire]
aws_scheduler_schedule.producer["meteorologia"]: Refreshing state... [id=default/madrono-tfm-dev-meteorologia]
aws_scheduler_schedule.producer["trafico"]: Refreshing state... [id=default/madrono-tfm-dev-trafico]
aws_scheduler_schedule.producer["ruido"]: Refreshing state... [id=default/madrono-tfm-dev-ruido]
aws_scheduler_schedule.producer["cartelera_cines_estrenos"]: Refreshing state... [id=default/madrono-tfm-dev-cartelera_cines_estrenos]
aws_scheduler_schedule.producer["cartelera_cines_estrenos_sesiones"]: Refreshing state... [id=default/madrono-tfm-dev-cartelera_cines_estrenos_sesiones]
aws_iam_policy.scheduler_invoke_lambda: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-scheduler-invoke-lambda]
aws_s3_object.procesamiento_source: Refreshing state... [id=glue-libs/procesamiento.zip]
aws_iam_role_policy_attachment.scheduler_invoke_lambda: Refreshing state... [id=madrono-tfm-dev-scheduler-role-20260814213123137400000002]
aws_glue_job.afluencia_lugares_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-silver-to-gold]
aws_glue_job.aforos_peatones_bicicletas_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold]
aws_glue_job.meteorologia_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-meteorologia-silver-to-gold]
aws_glue_job.calidad_aire_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-calidad-aire-bronze-to-silver]
aws_glue_job.aemet_prevision_avisos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold]
aws_glue_job.afluencia_lugares_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-bronze-to-silver]
aws_glue_job.bluesky_menciones_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-silver-to-gold]
aws_glue_job.bicimad_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bicimad-silver-backfill-dedup]
aws_glue_job.cams_calidad_aire_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-bronze-to-silver]
aws_glue_job.transporte_publico_emt_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-silver-to-gold]
aws_glue_job.aforos_peatones_bicicletas_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup]
aws_glue_job.agenda_eventos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-silver-to-gold]
aws_glue_job.aemet_prevision_avisos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver]
aws_glue_job.bluesky_menciones_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-bronze-to-silver]
aws_glue_job.aparcamientos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aparcamientos-bronze-to-silver]
aws_glue_job.bicimad_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-bicimad-silver-to-gold]
aws_glue_job.agenda_eventos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-bronze-to-silver]
aws_glue_job.cartelera_cines_estrenos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver]
aws_glue_job.ruido_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-ruido-silver-to-gold]
aws_glue_job.bicimad_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-bicimad-bronze-to-silver]
aws_glue_job.transporte_publico_emt_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup]
aws_glue_job.aforos_peatones_bicicletas_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver]
aws_glue_job.trafico_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-trafico-silver-to-gold]
aws_glue_job.bluesky_menciones_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup]
aws_glue_job.meteorologia_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-meteorologia-silver-backfill-dedup]
aws_glue_job.transporte_publico_emt_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-bronze-to-silver]
aws_glue_job.ruido_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-ruido-silver-backfill-dedup]
aws_glue_job.trafico_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-trafico-bronze-to-silver]
aws_glue_job.cartelera_cines_estrenos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold]
aws_glue_job.agenda_eventos_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-silver-backfill-dedup]
aws_glue_job.cams_calidad_aire_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup]
aws_glue_job.aparcamientos_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aparcamientos-silver-backfill-dedup]
aws_glue_job.cams_calidad_aire_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-silver-to-gold]
aws_glue_job.aparcamientos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aparcamientos-silver-to-gold]
aws_glue_job.calidad_aire_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-calidad-aire-silver-backfill-dedup]
aws_glue_job.meteorologia_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-meteorologia-bronze-to-silver]
aws_glue_job.calidad_aire_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-calidad-aire-silver-to-gold]
aws_glue_trigger.afluencia_lugares_estimada: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-scheduled-estimada]
aws_glue_job.ruido_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-ruido-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad-aire-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad-scheduled-bronze-to-silver]
aws_glue_trigger.conditional_silver_to_gold_daily["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad-aire-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad-conditional-silver-to-gold]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  ~ update in-place
+/- create replacement and then destroy
 <= read (data resources)

Terraform will perform the following actions:

  # data.aws_iam_policy_document.scheduler_invoke_lambda will be read during apply
  # (depends on a resource or a module with changes pending)
 <= data "aws_iam_policy_document" "scheduler_invoke_lambda" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "lambda:InvokeFunction",
            ]
          + effect    = "Allow"
          + resources = [
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aemet_prevision_avisos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aforos_peatones_bicicletas",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-agenda_eventos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aparcamientos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bicimad",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bluesky_menciones",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-calidad_aire",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cams_calidad_aire",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cartelera_cines_estrenos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-emt_incidencias",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-meteorologia",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-parques_jardines",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-ruido",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-ser_calles",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-trafico",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-transporte_publico_emt",
            ]
          + sid       = "InvokeProducerLambdas"
        }
    }

  # aws_codebuild_project.lambda_dependencies_layer will be updated in-place
  ~ resource "aws_codebuild_project" "lambda_dependencies_layer" {
        id                     = "arn:aws:codebuild:eu-west-1:222234418587:project/madrono-tfm-dev-lambda-dependencies-layer"
        name                   = "madrono-tfm-dev-lambda-dependencies-layer"
        tags                   = {}
        # (14 unchanged attributes hidden)

      ~ source {
          ~ buildspec           = <<-EOT
              - version: 0.2
              + version: 0.2
              - 
              + 
              - # Tarea 032: construye una Lambda Layer de Python 3.13 con las dependencias
              + # Tarea 032: construye una Lambda Layer de Python 3.13 con las dependencias
              - # de terceros de ingesta/requirements.txt (requests, boto3, populartimes,
              + # de terceros de ingesta/requirements.txt (requests, boto3, populartimes,
              - # cdsapi, netCDF4, beautifulsoup4). Se ejecuta en la imagen CodeBuild
              + # cdsapi, netCDF4, beautifulsoup4). Se ejecuta en la imagen CodeBuild
              - # gestionada por AWS "amazonlinux-x86_64-lambda-standard:python3.13"
              + # gestionada por AWS "amazonlinux-x86_64-lambda-standard:python3.13"
              - # (ver aws_codebuild_project.lambda_dependencies_layer en
              + # (ver aws_codebuild_project.lambda_dependencies_layer en
              - # lambda_layer_build.tf), que usa el mismo Python/glibc que el runtime real
              + # lambda_layer_build.tf), que usa el mismo Python/glibc que el runtime real
              - # de Lambda python3.13 x86_64 -- necesario para que paquetes con extensiones
              + # de Lambda python3.13 x86_64 -- necesario para que paquetes con extensiones
              - # nativas (netCDF4) resuelvan una wheel binariamente compatible con Lambda,
              + # nativas (netCDF4) resuelvan una wheel binariamente compatible con Lambda,
              - # no solo "instalable en la imagen de build".
              + # no solo "instalable en la imagen de build".
              - #
              + #
              - # El "source" de este proyecto CodeBuild (ver aws_s3_object.layer_build_source)
              + # El "source" de este proyecto CodeBuild (ver aws_s3_object.layer_build_source)
              - # es un .zip que contiene únicamente ingesta/requirements.txt, aplanado a
              + # es un .zip que contiene únicamente ingesta/requirements.txt, aplanado a
              - # "requirements.txt" en la raíz -- de ahí que aquí se referencie sin el
              + # "requirements.txt" en la raíz -- de ahí que aquí se referencie sin el
              - # prefijo "ingesta/".
              + # prefijo "ingesta/".
              - 
              + 
              - phases:
              + phases:
              -   install:
              +   install:
              -     commands:
              +     commands:
              -       - python3 --version
              +       - python3 --version
              -       - command -v git >/dev/null 2>&1 || yum install -y git
              +       - command -v git >/dev/null 2>&1 || yum install -y git
              -       - pip3 install --upgrade pip
              +       - pip3 install --upgrade pip
              -   build:
              +   build:
              -     commands:
              +     commands:
              -       - mkdir -p /tmp/layer/python
              +       - mkdir -p /tmp/layer/python
              -       - pip3 install -r requirements.txt --target /tmp/layer/python
              +       - pip3 install -r requirements.txt --target /tmp/layer/python
              -   post_build:
              +   post_build:
              -     commands:
              +     commands:
              -       - cd /tmp/layer && python3 -c "import shutil; shutil.make_archive('/tmp/layer_archive', 'zip', '.')"
              +       - cd /tmp/layer && python3 -c "import shutil; shutil.make_archive('/tmp/layer_archive', 'zip', '.')"
                      - aws s3 cp /tmp/layer_archive.zip "s3://${ARTIFACT_BUCKET}/${ARTIFACT_KEY}"
            EOT
            # (5 unchanged attributes hidden)
        }

        # (4 unchanged blocks hidden)
    }

  # aws_glue_job.aemet_prevision_avisos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "aemet_prevision_avisos_bronze_to_silver" {
        id                        = "madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver"
        name                      = "madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aemet_prevision_avisos_bronze_to_silver-d7b98621b0e2b5a6d5d4c70119146f34.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aemet_prevision_avisos_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aemet_prevision_avisos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "aemet_prevision_avisos_silver_to_gold" {
        id                        = "madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold"
        name                      = "madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aemet_prevision_avisos_silver_to_gold-e203db858089238019b642eb9b9f6a23.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aemet_prevision_avisos_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.afluencia_lugares_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "afluencia_lugares_bronze_to_silver" {
        id                        = "madrono-tfm-dev-afluencia-lugares-bronze-to-silver"
        name                      = "madrono-tfm-dev-afluencia-lugares-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/afluencia_lugares_bronze_to_silver-2299183b4c60edf1e2539fc00a59ccc5.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/afluencia_lugares_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.afluencia_lugares_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "afluencia_lugares_silver_to_gold" {
        id                        = "madrono-tfm-dev-afluencia-lugares-silver-to-gold"
        name                      = "madrono-tfm-dev-afluencia-lugares-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/afluencia_lugares_estimada-818054b226fcfb9227d13b69da7397f3.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/afluencia_lugares_estimada.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_bronze_to_silver" {
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d8325aae3ee77630cfc0f6612c30323e.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-7c312ea88152d382dd1e02b82a549a7c.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_backfill_dedup-bfb76e782afee2c5956f548a34da0b18.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_silver_to_gold" {
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_silver_to_gold-a7df88f8aa89cea895c3e594ff738600.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.agenda_eventos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_bronze_to_silver" {
        id                        = "madrono-tfm-dev-agenda-eventos-bronze-to-silver"
        name                      = "madrono-tfm-dev-agenda-eventos-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_bronze_to_silver-75c29ecd15eb33bf665840234bcf5cc8.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.agenda_eventos_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-agenda-eventos-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-agenda-eventos-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_backfill_dedup_gold-c417e4a5711e3fcb2d416cc0f05f3290.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.agenda_eventos_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-agenda-eventos-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-agenda-eventos-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_backfill_dedup-ebb7fb05697677064a5b18ee492aca9e.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.agenda_eventos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_silver_to_gold" {
        id                        = "madrono-tfm-dev-agenda-eventos-silver-to-gold"
        name                      = "madrono-tfm-dev-agenda-eventos-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_silver_to_gold-4d854fda4df74abc055b9eba9af92b0f.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aparcamientos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_bronze_to_silver" {
        id                        = "madrono-tfm-dev-aparcamientos-bronze-to-silver"
        name                      = "madrono-tfm-dev-aparcamientos-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_bronze_to_silver-4c9fe8e66729a98c520c97a0aa10f630.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aparcamientos_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-aparcamientos-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-aparcamientos-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_backfill_dedup_gold-7f4c18ec21a262d4a6e788348e492c3f.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aparcamientos_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-aparcamientos-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-aparcamientos-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_backfill_dedup-0040b8ac53f09f609005c2ad2aac464f.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aparcamientos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_silver_to_gold" {
        id                        = "madrono-tfm-dev-aparcamientos-silver-to-gold"
        name                      = "madrono-tfm-dev-aparcamientos-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_silver_to_gold-b55a4a1d69d1eadf50394eb93b034fd8.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bicimad_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "bicimad_bronze_to_silver" {
        id                        = "madrono-tfm-dev-bicimad-bronze-to-silver"
        name                      = "madrono-tfm-dev-bicimad-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_bronze_to_silver-cd282dfb63915ca6f80b2ccbd8143809.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bicimad_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "bicimad_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-bicimad-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-bicimad-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_backfill_dedup_gold-0eb546a683ffaa467741ed1fa47a2abb.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bicimad_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "bicimad_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-bicimad-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-bicimad-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_backfill_dedup-4a3264e9732202731f31d5974bbe9017.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bicimad_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "bicimad_silver_to_gold" {
        id                        = "madrono-tfm-dev-bicimad-silver-to-gold"
        name                      = "madrono-tfm-dev-bicimad-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_silver_to_gold-dd61f49fdef5e187adf9e3b2cb0bcd68.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bluesky_menciones_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_bronze_to_silver" {
        id                        = "madrono-tfm-dev-bluesky-menciones-bronze-to-silver"
        name                      = "madrono-tfm-dev-bluesky-menciones-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_bronze_to_silver-e2d8897c5d4760401b16893568ac32ee.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bluesky_menciones_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-bluesky-menciones-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-bluesky-menciones-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_backfill_dedup_gold-9cfe45ea7aef30a0f20892f1bdaccb0a.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bluesky_menciones_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_backfill_dedup-d20c9b44b3da1387c2a6a1d6fd6a5090.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.bluesky_menciones_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_silver_to_gold" {
        id                        = "madrono-tfm-dev-bluesky-menciones-silver-to-gold"
        name                      = "madrono-tfm-dev-bluesky-menciones-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_silver_to_gold-8c43f4a9df541e2eea43a8456514dc10.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.calidad_aire_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_bronze_to_silver" {
        id                        = "madrono-tfm-dev-calidad-aire-bronze-to-silver"
        name                      = "madrono-tfm-dev-calidad-aire-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_bronze_to_silver-4eb1972a460e5e10ae7df4a3315f52d4.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.calidad_aire_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-calidad-aire-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-calidad-aire-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_backfill_dedup_gold-879b3165bb85419fae5a2b8078c723d0.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.calidad_aire_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-calidad-aire-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-calidad-aire-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_backfill_dedup-6d44949bc6077a4ec6bba66eff619e0e.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.calidad_aire_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_silver_to_gold" {
        id                        = "madrono-tfm-dev-calidad-aire-silver-to-gold"
        name                      = "madrono-tfm-dev-calidad-aire-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_silver_to_gold-8333a2c7125ffd86e09976ae4db5114d.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.cams_calidad_aire_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_bronze_to_silver" {
        id                        = "madrono-tfm-dev-cams-calidad-aire-bronze-to-silver"
        name                      = "madrono-tfm-dev-cams-calidad-aire-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_bronze_to_silver-9211d3802eca398bfda830e10b7b8ef2.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.cams_calidad_aire_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-cams-calidad-aire-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-cams-calidad-aire-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_backfill_dedup_gold-fa45e88fe2d37635cc6240ef327383ff.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.cams_calidad_aire_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_backfill_dedup-69f636c9df5c3880b98dff5bf4088421.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.cams_calidad_aire_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_silver_to_gold" {
        id                        = "madrono-tfm-dev-cams-calidad-aire-silver-to-gold"
        name                      = "madrono-tfm-dev-cams-calidad-aire-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_silver_to_gold-f83d74685a5a4d930a50993f848d2a01.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.cartelera_cines_estrenos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "cartelera_cines_estrenos_bronze_to_silver" {
        id                        = "madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver"
        name                      = "madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_bronze_to_silver-77e98d1cd921c208bf5ffaa29d284e32.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.cartelera_cines_estrenos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "cartelera_cines_estrenos_silver_to_gold" {
        id                        = "madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold"
        name                      = "madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.meteorologia_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_bronze_to_silver" {
        id                        = "madrono-tfm-dev-meteorologia-bronze-to-silver"
        name                      = "madrono-tfm-dev-meteorologia-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_bronze_to_silver-3fcf5c38a2dd24e79206eb53af97348a.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.meteorologia_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-meteorologia-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-meteorologia-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_backfill_dedup_gold-cb6dc670fef14d383aaa366eb184d811.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.meteorologia_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-meteorologia-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-meteorologia-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_backfill_dedup-1fa9eaae33ade611f68b64e9ac2dffc0.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.meteorologia_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_silver_to_gold" {
        id                        = "madrono-tfm-dev-meteorologia-silver-to-gold"
        name                      = "madrono-tfm-dev-meteorologia-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_silver_to_gold-4fb287e094c6f4dd3cb17585cbde692e.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.ruido_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "ruido_bronze_to_silver" {
        id                        = "madrono-tfm-dev-ruido-bronze-to-silver"
        name                      = "madrono-tfm-dev-ruido-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_bronze_to_silver-57461bb981d80490227ccb4922409ef9.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.ruido_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "ruido_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-ruido-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-ruido-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_backfill_dedup_gold-db9317465c5f82d4c56c9faae1e83723.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.ruido_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "ruido_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-ruido-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-ruido-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_backfill_dedup-2cf7215ae11978fc12206039bba3aece.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.ruido_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "ruido_silver_to_gold" {
        id                        = "madrono-tfm-dev-ruido-silver-to-gold"
        name                      = "madrono-tfm-dev-ruido-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_silver_to_gold-77502f7109487420c57b7e41102616e3.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.trafico_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "trafico_bronze_to_silver" {
        id                        = "madrono-tfm-dev-trafico-bronze-to-silver"
        name                      = "madrono-tfm-dev-trafico-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/trafico_bronze_to_silver-ae01fdf48416d1e59a499e725af5eeb4.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/trafico_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.trafico_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "trafico_silver_to_gold" {
        id                        = "madrono-tfm-dev-trafico-silver-to-gold"
        name                      = "madrono-tfm-dev-trafico-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/trafico_silver_to_gold-1884fa42b9e7b491c226ccb77bb38a49.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/trafico_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.transporte_publico_emt_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_bronze_to_silver" {
        id                        = "madrono-tfm-dev-transporte-publico-emt-bronze-to-silver"
        name                      = "madrono-tfm-dev-transporte-publico-emt-bronze-to-silver"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_bronze_to_silver-5b3c3602b3f60bf9ff3ef5cfe1c8d6a9.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_bronze_to_silver.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.transporte_publico_emt_gold_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_gold_backfill_dedup" {
        id                        = "madrono-tfm-dev-transporte-publico-emt-gold-backfill-dedup"
        name                      = "madrono-tfm-dev-transporte-publico-emt-gold-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_backfill_dedup_gold-318da358079d2d12e5b8c55e656eb079.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_backfill_dedup_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.transporte_publico_emt_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_silver_backfill_dedup" {
        id                        = "madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_backfill_dedup-961447ee3174a4e4ef33f1b6e006affa.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_backfill_dedup.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.transporte_publico_emt_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_silver_to_gold" {
        id                        = "madrono-tfm-dev-transporte-publico-emt-silver-to-gold"
        name                      = "madrono-tfm-dev-transporte-publico-emt-silver-to-gold"
        tags                      = {}
        # (17 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_silver_to_gold-7cd0d472adb8dfd5d48cc79dfad6acdb.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_silver_to_gold.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_iam_policy.scheduler_invoke_lambda will be updated in-place
  ~ resource "aws_iam_policy" "scheduler_invoke_lambda" {
        id               = "arn:aws:iam::222234418587:policy/madrono-tfm-dev-scheduler-invoke-lambda"
        name             = "madrono-tfm-dev-scheduler-invoke-lambda"
      ~ policy           = jsonencode(
            {
              - Statement = [
                  - {
                      - Action   = "lambda:InvokeFunction"
                      - Effect   = "Allow"
                      - Resource = [
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-transporte_publico_emt",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-trafico",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-ser_calles",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-ruido",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-parques_jardines",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-meteorologia",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-emt_incidencias",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cartelera_cines_estrenos",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cams_calidad_aire",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-calidad_aire",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bluesky_menciones",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bicimad",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aparcamientos",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-agenda_eventos",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aforos_peatones_bicicletas",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aemet_prevision_avisos",
                        ]
                      - Sid      = "InvokeProducerLambdas"
                    },
                ]
              - Version   = "2012-10-17"
            }
        ) -> (known after apply)
        tags             = {}
        # (7 unchanged attributes hidden)
    }

  # aws_lambda_function.producer["aemet_prevision_avisos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aemet_prevision_avisos"
      ~ last_modified                  = "2026-08-29T21:09:25.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["aforos_peatones_bicicletas"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aforos_peatones_bicicletas"
      ~ last_modified                  = "2026-08-29T21:10:25.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["agenda_eventos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-agenda_eventos"
      ~ last_modified                  = "2026-08-29T21:09:19.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["aparcamientos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aparcamientos"
      ~ last_modified                  = "2026-08-29T21:09:31.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["bicimad"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-bicimad"
      ~ last_modified                  = "2026-08-29T21:09:49.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["bluesky_menciones"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-bluesky_menciones"
      ~ last_modified                  = "2026-08-29T21:11:38.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["calidad_aire"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-calidad_aire"
      ~ last_modified                  = "2026-08-29T21:10:31.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["cams_calidad_aire"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-cams_calidad_aire"
      ~ last_modified                  = "2026-08-29T21:10:49.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["cartelera_cines_estrenos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-cartelera_cines_estrenos"
      ~ last_modified                  = "2026-08-29T21:09:55.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["emt_incidencias"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-emt_incidencias"
      ~ last_modified                  = "2026-08-29T21:09:37.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["meteorologia"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-meteorologia"
      ~ last_modified                  = "2026-08-29T21:10:01.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["parques_jardines"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-parques_jardines"
      ~ last_modified                  = "2026-08-29T21:10:43.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["ruido"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-ruido"
      ~ last_modified                  = "2026-08-29T21:10:19.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["ser_calles"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-ser_calles"
      ~ last_modified                  = "2026-08-29T21:09:43.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["trafico"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-trafico"
      ~ last_modified                  = "2026-08-29T21:10:38.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["transporte_publico_emt"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-transporte_publico_emt"
      ~ last_modified                  = "2026-08-29T21:10:08.000+0000" -> (known after apply)
      ~ layers                         = [
          - "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1",
        ]
      ~ source_code_hash               = "SmlGk4JpPu5fdKU72Chw9VJE/NWz2znL3UUCyl6lzK4=" -> "8MMtrNQgz7A94bXSdj+LmX8a3tQbIj2Yh6vLWdCVNhM="
        tags                           = {}
        # (26 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_s3_object.glue_script_aemet_prevision_avisos_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_aemet_prevision_avisos_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aemet_prevision_avisos_bronze_to_silver-d7b98621b0e2b5a6d5d4c70119146f34.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `aemet_prevision_avisos`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `aemet_prevision_avisos`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Un único job procesa **las dos** formas de dato (previsión y avisos, ver
          + Un único job procesa **las dos** formas de dato (previsión y avisos, ver
          - `transform.py`) porque comparten productor, credencial y cadencia de
          + `transform.py`) porque comparten productor, credencial y cadencia de
          - scheduling real (ver `ingesta/README.md`, "Cadencia real de publicación") --
          + scheduling real (ver `ingesta/README.md`, "Cadencia real de publicación") --
          - tal como pide el enunciado de esta tarea ("job de Glue x2": Bronze->Silver y
          + tal como pide el enunciado de esta tarea ("job de Glue x2": Bronze->Silver y
          - Silver->Gold, no cuatro jobs). Internamente son dos flujos Spark
          + Silver->Gold, no cuatro jobs). Internamente son dos flujos Spark
          - independientes (dos lecturas, dos `mapPartitions`, dos escrituras), cada uno
          + independientes (dos lecturas, dos `mapPartitions`, dos escrituras), cada uno
          - reutilizando `transform.bronze_to_silver_prevision`/
          + reutilizando `transform.bronze_to_silver_prevision`/
          - `transform.bronze_to_silver_avisos` tal cual -- este módulo solo es el
          + `transform.bronze_to_silver_avisos` tal cual -- este módulo solo es el
          - "pegamento" de Spark/Glue.
          + "pegamento" de Spark/Glue.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo). Se
          + `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo). Se
          - escriben dos informes por ejecución (uno por forma de dato), bajo el mismo
          + escriben dos informes por ejecución (uno por forma de dato), bajo el mismo
          - prefijo `quality_report_path`.
          + prefijo `quality_report_path`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_prevision_path` / `bronze_avisos_path`: prefijos S3 de origen,
          + - `bronze_prevision_path` / `bronze_avisos_path`: prefijos S3 de origen,
          -   p.ej. `s3://madrono-tfm-dev-bronze-222234418587/aemet_prevision/` /
          +   p.ej. `s3://madrono-tfm-dev-bronze-222234418587/aemet_prevision/` /
          -   `.../aemet_avisos/` -- dos prefijos reales y distintos, ver
          +   `.../aemet_avisos/` -- dos prefijos reales y distintos, ver
          -   `transform.py`, "Prefijos S3 reales de Bronze".
          +   `transform.py`, "Prefijos S3 reales de Bronze".
          - - `silver_prevision_path` / `silver_avisos_path`: prefijos S3 de destino.
          + - `silver_prevision_path` / `silver_avisos_path`: prefijos S3 de destino.
          - - `quality_report_path`: prefijo S3 donde se escriben los informes de
          + - `quality_report_path`: prefijo S3 donde se escriben los informes de
          -   validación de Great Expectations (dos JSON por ejecución del job, uno por
          +   validación de Great Expectations (dos JSON por ejecución del job, uno por
          -   forma de dato).
          +   forma de dato).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType
          + from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.aemet_prevision_avisos.ge_suite import (
          + from procesamiento.silver_gold.aemet_prevision_avisos.ge_suite import (
          -     run_avisos_quality_report,
          +     run_avisos_quality_report,
          -     run_prevision_quality_report,
          +     run_prevision_quality_report,
          - )
          + )
          - from procesamiento.silver_gold.aemet_prevision_avisos.transform import (
          + from procesamiento.silver_gold.aemet_prevision_avisos.transform import (
          -     bronze_to_silver_avisos,
          +     bronze_to_silver_avisos,
          -     bronze_to_silver_prevision,
          +     bronze_to_silver_prevision,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - SILVER_PREVISION_SCHEMA = StructType(
          + SILVER_PREVISION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("municipio_code", StringType(), False),
          +         StructField("municipio_code", StringType(), False),
          -         StructField("municipio_name", StringType(), True),
          +         StructField("municipio_name", StringType(), True),
          -         StructField("province", StringType(), True),
          +         StructField("province", StringType(), True),
          -         StructField("elaborated_at", StringType(), True),
          +         StructField("elaborated_at", StringType(), True),
          -         StructField("valid_date", StringType(), False),
          +         StructField("valid_date", StringType(), False),
          -         StructField("sky_state", StringType(), True),
          +         StructField("sky_state", StringType(), True),
          -         StructField("sky_state_code", StringType(), True),
          +         StructField("sky_state_code", StringType(), True),
          -         StructField("precipitation_probability_pct", DoubleType(), True),
          +         StructField("precipitation_probability_pct", DoubleType(), True),
          -         StructField("temperature_max_c", DoubleType(), True),
          +         StructField("temperature_max_c", DoubleType(), True),
          -         StructField("temperature_min_c", DoubleType(), True),
          +         StructField("temperature_min_c", DoubleType(), True),
          -         StructField("thermal_sensation_max_c", DoubleType(), True),
          +         StructField("thermal_sensation_max_c", DoubleType(), True),
          -         StructField("thermal_sensation_min_c", DoubleType(), True),
          +         StructField("thermal_sensation_min_c", DoubleType(), True),
          -         StructField("humidity_max_pct", DoubleType(), True),
          +         StructField("humidity_max_pct", DoubleType(), True),
          -         StructField("humidity_min_pct", DoubleType(), True),
          +         StructField("humidity_min_pct", DoubleType(), True),
          -         StructField("wind_direction", StringType(), True),
          +         StructField("wind_direction", StringType(), True),
          -         StructField("wind_speed_kmh", DoubleType(), True),
          +         StructField("wind_speed_kmh", DoubleType(), True),
          -         StructField("wind_gust_max_kmh", DoubleType(), True),
          +         StructField("wind_gust_max_kmh", DoubleType(), True),
          -         StructField("uv_max", DoubleType(), True),
          +         StructField("uv_max", DoubleType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_AVISOS_SCHEMA = StructType(
          + SILVER_AVISOS_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("identifier", StringType(), False),
          +         StructField("identifier", StringType(), False),
          -         StructField("sent_at", StringType(), True),
          +         StructField("sent_at", StringType(), True),
          -         StructField("zone", StringType(), False),
          +         StructField("zone", StringType(), False),
          -         StructField("level", StringType(), False),
          +         StructField("level", StringType(), False),
          -         StructField("phenomenon", StringType(), False),
          +         StructField("phenomenon", StringType(), False),
          -         StructField("probability", StringType(), True),
          +         StructField("probability", StringType(), True),
          -         StructField("severity", StringType(), True),
          +         StructField("severity", StringType(), True),
          -         StructField("urgency", StringType(), True),
          +         StructField("urgency", StringType(), True),
          -         StructField("certainty", StringType(), True),
          +         StructField("certainty", StringType(), True),
          -         StructField("effective_from", StringType(), False),
          +         StructField("effective_from", StringType(), False),
          -         StructField("effective_until", StringType(), True),
          +         StructField("effective_until", StringType(), True),
          -         StructField("headline", StringType(), True),
          +         StructField("headline", StringType(), True),
          -         StructField("description", StringType(), True),
          +         StructField("description", StringType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_prevision_row(r: dict) -> Row:
          + def _to_silver_prevision_row(r: dict) -> Row:
          -     return Row(**{field.name: r[field.name] for field in SILVER_PREVISION_SCHEMA.fields})
          +     return Row(**{field.name: r[field.name] for field in SILVER_PREVISION_SCHEMA.fields})
          - 
          + 
          - 
          + 
          - def _to_silver_avisos_row(r: dict) -> Row:
          + def _to_silver_avisos_row(r: dict) -> Row:
          -     return Row(**{field.name: r[field.name] for field in SILVER_AVISOS_SCHEMA.fields})
          +     return Row(**{field.name: r[field.name] for field in SILVER_AVISOS_SCHEMA.fields})
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_prevision_partition(rows, processed_at_iso: str):
          + def _process_prevision_partition(rows, processed_at_iso: str):
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver_prevision(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver_prevision(bronze_records, processed_at)
          -     return [_to_silver_prevision_row(r) for r in silver_records]
          +     return [_to_silver_prevision_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _process_avisos_partition(rows, processed_at_iso: str):
          + def _process_avisos_partition(rows, processed_at_iso: str):
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver_avisos(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver_avisos(bronze_records, processed_at)
          -     return [_to_silver_avisos_row(r) for r in silver_records]
          +     return [_to_silver_avisos_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv,
          +         sys.argv,
          -         [
          +         [
          -             "JOB_NAME",
          +             "JOB_NAME",
          -             "bronze_prevision_path",
          +             "bronze_prevision_path",
          -             "bronze_avisos_path",
          +             "bronze_avisos_path",
          -             "silver_prevision_path",
          +             "silver_prevision_path",
          -             "silver_avisos_path",
          +             "silver_avisos_path",
          -             "quality_report_path",
          +             "quality_report_path",
          -         ],
          +         ],
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la partición Bronze de hoy (día
          +     # Lectura incremental (tarea 072): solo la partición Bronze de hoy (día
          -     # de ingestión; cadencia diaria, ver glue_scheduling.tf) de cada forma de
          +     # de ingestión; cadencia diaria, ver glue_scheduling.tf) de cada forma de
          -     # dato -- nunca la raíz completa, ver
          +     # dato -- nunca la raíz completa, ver
          -     # doc/072-arreglo-lectura-incremental-glue.md.
          +     # doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_prevision_partition_path = daily_partition_uri(args["bronze_prevision_path"], fecha)
          +     bronze_prevision_partition_path = daily_partition_uri(args["bronze_prevision_path"], fecha)
          -     bronze_avisos_partition_path = daily_partition_uri(args["bronze_avisos_path"], fecha)
          +     bronze_avisos_partition_path = daily_partition_uri(args["bronze_avisos_path"], fecha)
          -     s3_client = boto3.client("s3")
          +     s3_client = boto3.client("s3")
          -     # Previsión y avisos comparten productor/cadencia real (ver docstring del
          +     # Previsión y avisos comparten productor/cadencia real (ver docstring del
          -     # módulo): en la práctica llegan juntos cada día. Si un día concreto
          +     # módulo): en la práctica llegan juntos cada día. Si un día concreto
          -     # falta cualquiera de las dos, se salta esta ejecución entera (simple, se
          +     # falta cualquiera de las dos, se salta esta ejecución entera (simple, se
          -     # autocorrige al día siguiente) en vez de complicar el resto del job con
          +     # autocorrige al día siguiente) en vez de complicar el resto del job con
          -     # dos rutas de "falta una de las dos formas".
          +     # dos rutas de "falta una de las dos formas".
          -     if not partition_has_objects(s3_client, bronze_prevision_partition_path) or not partition_has_objects(
          +     if not partition_has_objects(s3_client, bronze_prevision_partition_path) or not partition_has_objects(
          -         s3_client, bronze_avisos_partition_path
          +         s3_client, bronze_avisos_partition_path
          -     ):
          +     ):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # --- Previsión --------------------------------------------------------
          +     # --- Previsión --------------------------------------------------------
          -     bronze_prevision_df = spark.read.option("multiLine", True).json(bronze_prevision_partition_path)
          +     bronze_prevision_df = spark.read.option("multiLine", True).json(bronze_prevision_partition_path)
          -     silver_prevision_rdd = bronze_prevision_df.rdd.mapPartitions(
          +     silver_prevision_rdd = bronze_prevision_df.rdd.mapPartitions(
          -         lambda rows: _process_prevision_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_prevision_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_prevision_df = spark.createDataFrame(silver_prevision_rdd, schema=SILVER_PREVISION_SCHEMA)
          +     silver_prevision_df = spark.createDataFrame(silver_prevision_rdd, schema=SILVER_PREVISION_SCHEMA)
          -     silver_prevision_df.cache()
          +     silver_prevision_df.cache()
          - 
          + 
          -     prevision_quality_report = run_prevision_quality_report(gx_context, silver_prevision_df)
          +     prevision_quality_report = run_prevision_quality_report(gx_context, silver_prevision_df)
          -     _write_quality_report(
          +     _write_quality_report(
          -         f"{args['quality_report_path'].rstrip('/')}/aemet_prevision_{processed_at:%Y%m%dT%H%M%S}.json",
          +         f"{args['quality_report_path'].rstrip('/')}/aemet_prevision_{processed_at:%Y%m%dT%H%M%S}.json",
          -         prevision_quality_report,
          +         prevision_quality_report,
          -     )
          +     )
          - 
          + 
          -     # Particiona solo por `fecha` (el día previsto, `valid_date`): la
          +     # Particiona solo por `fecha` (el día previsto, `valid_date`): la
          -     # previsión es diaria, sin resolución horaria real -- mismo criterio que
          +     # previsión es diaria, sin resolución horaria real -- mismo criterio que
          -     # `ruido`/`agenda_eventos`.
          +     # `ruido`/`agenda_eventos`.
          -     silver_prevision_df.withColumn("fecha", to_timestamp("valid_date")).withColumn(
          +     silver_prevision_df.withColumn("fecha", to_timestamp("valid_date")).withColumn(
          -         "fecha", date_format("fecha", "yyyy-MM-dd")
          +         "fecha", date_format("fecha", "yyyy-MM-dd")
          -     ).write.mode("append").partitionBy("fecha").parquet(args["silver_prevision_path"])
          +     ).write.mode("append").partitionBy("fecha").parquet(args["silver_prevision_path"])
          - 
          + 
          -     # --- Avisos -------------------------------------------------------------
          +     # --- Avisos -------------------------------------------------------------
          -     bronze_avisos_df = spark.read.option("multiLine", True).json(bronze_avisos_partition_path)
          +     bronze_avisos_df = spark.read.option("multiLine", True).json(bronze_avisos_partition_path)
          -     silver_avisos_rdd = bronze_avisos_df.rdd.mapPartitions(
          +     silver_avisos_rdd = bronze_avisos_df.rdd.mapPartitions(
          -         lambda rows: _process_avisos_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_avisos_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_avisos_df = spark.createDataFrame(silver_avisos_rdd, schema=SILVER_AVISOS_SCHEMA)
          +     silver_avisos_df = spark.createDataFrame(silver_avisos_rdd, schema=SILVER_AVISOS_SCHEMA)
          -     silver_avisos_df.cache()
          +     silver_avisos_df.cache()
          - 
          + 
          -     avisos_quality_report = run_avisos_quality_report(gx_context, silver_avisos_df)
          +     avisos_quality_report = run_avisos_quality_report(gx_context, silver_avisos_df)
          -     _write_quality_report(
          +     _write_quality_report(
          -         f"{args['quality_report_path'].rstrip('/')}/aemet_avisos_{processed_at:%Y%m%dT%H%M%S}.json",
          +         f"{args['quality_report_path'].rstrip('/')}/aemet_avisos_{processed_at:%Y%m%dT%H%M%S}.json",
          -         avisos_quality_report,
          +         avisos_quality_report,
          -     )
          +     )
          - 
          + 
          -     # Particiona por `fecha` = día de inicio de vigencia (`effective_from`),
          +     # Particiona por `fecha` = día de inicio de vigencia (`effective_from`),
          -     # no por `ingested_at` -- mismo criterio que `aggregate.py`.
          +     # no por `ingested_at` -- mismo criterio que `aggregate.py`.
          -     silver_avisos_df.withColumn("fecha", to_timestamp("effective_from")).withColumn(
          +     silver_avisos_df.withColumn("fecha", to_timestamp("effective_from")).withColumn(
          -         "fecha", date_format("fecha", "yyyy-MM-dd")
          +         "fecha", date_format("fecha", "yyyy-MM-dd")
          -     ).write.mode("append").partitionBy("fecha").parquet(args["silver_avisos_path"])
          +     ).write.mode("append").partitionBy("fecha").parquet(args["silver_avisos_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "d7b98621b0e2b5a6d5d4c70119146f34" -> "5874411ad6f28f158f685ce90841add5"
      ~ id                            = "glue-scripts/aemet_prevision_avisos_bronze_to_silver-d7b98621b0e2b5a6d5d4c70119146f34.py" -> (known after apply)
      ~ key                           = "glue-scripts/aemet_prevision_avisos_bronze_to_silver-d7b98621b0e2b5a6d5d4c70119146f34.py" -> "glue-scripts/aemet_prevision_avisos_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aemet_prevision_avisos_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_aemet_prevision_avisos_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aemet_prevision_avisos_silver_to_gold-e203db858089238019b642eb9b9f6a23.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `aemet_prevision_avisos`.
          + """Job de AWS Glue: Silver -> Gold del dataset `aemet_prevision_avisos`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - Un único job produce **las dos** tablas Gold (previsión por municipio y
          + Un único job produce **las dos** tablas Gold (previsión por municipio y
          - horizonte, avisos por zona/día/nivel), mismo motivo que
          + horizonte, avisos por zona/día/nivel), mismo motivo que
          - `glue_bronze_to_silver.py` ("job de Glue x2" pedido por el enunciado, no
          + `glue_bronze_to_silver.py` ("job de Glue x2" pedido por el enunciado, no
          - cuatro jobs).
          + cuatro jobs).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un cálculo fila a fila -- mismo
          + nativas de reduce distribuido de Spark, no un cálculo fila a fila -- mismo
          - motivo que el resto de datasets del patrón. `aggregate.py` sigue siendo la
          + motivo que el resto de datasets del patrón. `aggregate.py` sigue siendo la
          - fuente de verdad **documental y de test** de qué agrega Gold; las
          + fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente
          + expresiones de Spark de este job están escritas para producir exactamente
          - el mismo esquema de salida que
          + el mismo esquema de salida que
          - `aggregate.aggregate_prevision_silver_to_gold`/
          + `aggregate.aggregate_prevision_silver_to_gold`/
          - `aggregate.aggregate_avisos_silver_to_gold`; un cambio en uno debe
          + `aggregate.aggregate_avisos_silver_to_gold`; un cambio en uno debe
          - reflejarse en el otro.
          + reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_prevision_path` / `silver_avisos_path`: prefijos S3 de origen.
          + - `silver_prevision_path` / `silver_avisos_path`: prefijos S3 de origen.
          - - `gold_prevision_path` / `gold_avisos_path`: prefijos S3 de destino, p.ej.
          + - `gold_prevision_path` / `gold_avisos_path`: prefijos S3 de destino, p.ej.
          -   `.../aemet_prevision_por_municipio_leadtime/` /
          +   `.../aemet_prevision_por_municipio_leadtime/` /
          -   `.../aemet_avisos_por_zona_fecha_nivel/`.
          +   `.../aemet_avisos_por_zona_fecha_nivel/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          + from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv,
          +         sys.argv,
          -         [
          +         [
          -             "JOB_NAME",
          +             "JOB_NAME",
          -             "silver_prevision_path",
          +             "silver_prevision_path",
          -             "silver_avisos_path",
          +             "silver_avisos_path",
          -             "gold_prevision_path",
          +             "gold_prevision_path",
          -             "gold_avisos_path",
          +             "gold_avisos_path",
          -         ],
          +         ],
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
          -     # `to_timestamp`/`date_format`/`to_date` de mas abajo calcularian en UTC,
          +     # `to_timestamp`/`date_format`/`to_date` de mas abajo calcularian en UTC,
          -     # desalineado con `today()` (Python, Europe/Madrid).
          +     # desalineado con `today()` (Python, Europe/Madrid).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # --- Previsión: (municipio_code, leadtime_days) -------------------------
          +     # --- Previsión: (municipio_code, leadtime_days) -------------------------
          -     #
          +     #
          -     # A diferencia del resto del patrón (tarea 076), este flujo NO se puede
          +     # A diferencia del resto del patrón (tarea 076), este flujo NO se puede
          -     # acotar a la partición de Silver de hoy: `leadtime_days` (el horizonte,
          +     # acotar a la partición de Silver de hoy: `leadtime_days` (el horizonte,
          -     # p.ej. "mañana" = 1) agrupa a propósito previsiones de MUCHOS días de
          +     # p.ej. "mañana" = 1) agrupa a propósito previsiones de MUCHOS días de
          -     # calendario distintos capturadas en momentos distintos -- ver docstring
          +     # calendario distintos capturadas en momentos distintos -- ver docstring
          -     # de `aggregate.py`, "Un mismo leadtime_days agrupa previsiones de días
          +     # de `aggregate.py`, "Un mismo leadtime_days agrupa previsiones de días
          -     # de calendario distintos". La clave de negocio no incluye ninguna
          +     # de calendario distintos". La clave de negocio no incluye ninguna
          -     # fecha, así que cada ejecución necesita el histórico completo de Silver
          +     # fecha, así que cada ejecución necesita el histórico completo de Silver
          -     # para recalcular correctamente cada horizonte -- leer solo hoy dejaría
          +     # para recalcular correctamente cada horizonte -- leer solo hoy dejaría
          -     # cada bucket con una única captura en vez de con todo su histórico.
          +     # cada bucket con una única captura en vez de con todo su histórico.
          -     # El volumen de este dataset es pequeño (una previsión de 7 días para un
          +     # El volumen de este dataset es pequeño (una previsión de 7 días para un
          -     # único municipio, una vez al día -> unas 2500 filas/año), así que leer
          +     # único municipio, una vez al día -> unas 2500 filas/año), así que leer
          -     # todo el histórico sigue siendo barato incluso tras meses de
          +     # todo el histórico sigue siendo barato incluso tras meses de
          -     # acumulación: el problema real de coste que motivó esta serie de tareas
          +     # acumulación: el problema real de coste que motivó esta serie de tareas
          -     # (072-076) no aplica aquí igual que a `trafico`/`bicimad` (ingesta cada
          +     # (072-076) no aplica aquí igual que a `trafico`/`bicimad` (ingesta cada
          -     # pocos minutos). El problema real para ESTE dataset era otro: escribir
          +     # pocos minutos). El problema real para ESTE dataset era otro: escribir
          -     # con `mode("append")` duplicaba la fila de cada horizonte en cada
          +     # con `mode("append")` duplicaba la fila de cada horizonte en cada
          -     # ejecución (una fila más por (municipio_code, leadtime_days) cada día,
          +     # ejecución (una fila más por (municipio_code, leadtime_days) cada día,
          -     # creciendo sin límite) en vez de mantener una única fila por horizonte
          +     # creciendo sin límite) en vez de mantener una única fila por horizonte
          -     # -- se sustituye por `mode("overwrite")` (recálculo completo cada vez,
          +     # -- se sustituye por `mode("overwrite")` (recálculo completo cada vez,
          -     # sin acotar particiones -- Gold de previsión no está particionado por
          +     # sin acotar particiones -- Gold de previsión no está particionado por
          -     # fecha, ver docstring del módulo).
          +     # fecha, ver docstring del módulo).
          -     silver_prevision_df = spark.read.parquet(args["silver_prevision_path"])
          +     silver_prevision_df = spark.read.parquet(args["silver_prevision_path"])
          - 
          + 
          -     prevision_with_leadtime = silver_prevision_df.withColumn(
          +     prevision_with_leadtime = silver_prevision_df.withColumn(
          -         "leadtime_days",
          +         "leadtime_days",
          -         F.datediff(F.to_date("valid_date"), F.to_date("ingested_at")),
          +         F.datediff(F.to_date("valid_date"), F.to_date("ingested_at")),
          -     )
          +     )
          - 
          + 
          -     gold_prevision_df = (
          +     gold_prevision_df = (
          -         prevision_with_leadtime.groupBy("municipio_code", "leadtime_days")
          +         prevision_with_leadtime.groupBy("municipio_code", "leadtime_days")
          -         .agg(
          +         .agg(
          -             F.first("municipio_name", ignorenulls=True).alias("municipio_name"),
          +             F.first("municipio_name", ignorenulls=True).alias("municipio_name"),
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.avg("temperature_max_c").alias("avg_temperature_max_c"),
          +             F.avg("temperature_max_c").alias("avg_temperature_max_c"),
          -             F.max("temperature_max_c").alias("max_temperature_max_c"),
          +             F.max("temperature_max_c").alias("max_temperature_max_c"),
          -             F.avg("temperature_min_c").alias("avg_temperature_min_c"),
          +             F.avg("temperature_min_c").alias("avg_temperature_min_c"),
          -             F.min("temperature_min_c").alias("min_temperature_min_c"),
          +             F.min("temperature_min_c").alias("min_temperature_min_c"),
          -             F.avg("precipitation_probability_pct").alias("avg_precipitation_probability_pct"),
          +             F.avg("precipitation_probability_pct").alias("avg_precipitation_probability_pct"),
          -             F.max("precipitation_probability_pct").alias("max_precipitation_probability_pct"),
          +             F.max("precipitation_probability_pct").alias("max_precipitation_probability_pct"),
          -             F.min("valid_date").alias("first_valid_date"),
          +             F.min("valid_date").alias("first_valid_date"),
          -             F.max("valid_date").alias("last_valid_date"),
          +             F.max("valid_date").alias("last_valid_date"),
          -         )
          +         )
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es mucho más pequeño que Silver: particionar por `municipio_code`
          +     # Gold es mucho más pequeño que Silver: particionar por `municipio_code`
          -     # basta para podar particiones sin generar ficheros diminutos -- el
          +     # basta para podar particiones sin generar ficheros diminutos -- el
          -     # número de municipios/horizontes es reducido, a diferencia de
          +     # número de municipios/horizontes es reducido, a diferencia de
          -     # particionar por fecha (que aquí no tiene sentido: cada fila agrega
          +     # particionar por fecha (que aquí no tiene sentido: cada fila agrega
          -     # muchos días de calendario distintos, ver docstring de `aggregate.py`).
          +     # muchos días de calendario distintos, ver docstring de `aggregate.py`).
          -     # `mode("overwrite")` (no `"append"`, ver comentario arriba): cada
          +     # `mode("overwrite")` (no `"append"`, ver comentario arriba): cada
          -     # ejecución sustituye Gold entero por el recálculo completo, en vez de
          +     # ejecución sustituye Gold entero por el recálculo completo, en vez de
          -     # acumular una fila nueva por horizonte cada día.
          +     # acumular una fila nueva por horizonte cada día.
          -     gold_prevision_df.write.mode("overwrite").partitionBy("municipio_code").parquet(args["gold_prevision_path"])
          +     gold_prevision_df.write.mode("overwrite").partitionBy("municipio_code").parquet(args["gold_prevision_path"])
          - 
          + 
          -     # --- Avisos: (zone, fecha, level) ---------------------------------------
          +     # --- Avisos: (zone, fecha, level) ---------------------------------------
          -     #
          +     #
          -     # A diferencia de previsión, la clave de negocio de avisos SÍ incluye
          +     # A diferencia de previsión, la clave de negocio de avisos SÍ incluye
          -     # `fecha` (día de `effective_from`) -- mismo patrón que el resto del
          +     # `fecha` (día de `effective_from`) -- mismo patrón que el resto del
          -     # grupo diario (tarea 076): se lee solo la partición de Silver `fecha=hoy`
          +     # grupo diario (tarea 076): se lee solo la partición de Silver `fecha=hoy`
          -     # (el mismo `effective_from` que ya particiona físicamente Silver, ver
          +     # (el mismo `effective_from` que ya particiona físicamente Silver, ver
          -     # glue_bronze_to_silver.py), nunca la raíz completa.
          +     # glue_bronze_to_silver.py), nunca la raíz completa.
          -     fecha_avisos = today(processed_at)
          +     fecha_avisos = today(processed_at)
          -     silver_avisos_partition_path = daily_partition_uri(args["silver_avisos_path"], fecha_avisos)
          +     silver_avisos_partition_path = daily_partition_uri(args["silver_avisos_path"], fecha_avisos)
          -     if partition_has_objects(boto3.client("s3"), silver_avisos_partition_path):
          +     if partition_has_objects(boto3.client("s3"), silver_avisos_partition_path):
          -         silver_avisos_df = spark.read.parquet(silver_avisos_partition_path)
          +         silver_avisos_df = spark.read.parquet(silver_avisos_partition_path)
          - 
          + 
          -         avisos_with_fecha = silver_avisos_df.withColumn(
          +         avisos_with_fecha = silver_avisos_df.withColumn(
          -             "fecha", F.date_format(F.to_timestamp("effective_from"), "yyyy-MM-dd")
          +             "fecha", F.date_format(F.to_timestamp("effective_from"), "yyyy-MM-dd")
          -         )
          +         )
          - 
          + 
          -         gold_avisos_df = (
          +         gold_avisos_df = (
          -             avisos_with_fecha.groupBy("zone", "fecha", "level")
          +             avisos_with_fecha.groupBy("zone", "fecha", "level")
          -             .agg(
          +             .agg(
          -                 F.count(F.lit(1)).alias("samples_count"),
          +                 F.count(F.lit(1)).alias("samples_count"),
          -                 F.countDistinct("identifier").alias("alerts_count"),
          +                 F.countDistinct("identifier").alias("alerts_count"),
          -                 F.sort_array(F.collect_set("phenomenon")).alias("phenomena"),
          +                 F.sort_array(F.collect_set("phenomenon")).alias("phenomena"),
          -                 F.min("effective_from").alias("first_effective_from"),
          +                 F.min("effective_from").alias("first_effective_from"),
          -                 F.max("effective_until").alias("last_effective_until"),
          +                 F.max("effective_until").alias("last_effective_until"),
          -             )
          +             )
          -             .withColumn("schema_version", F.lit(1))
          +             .withColumn("schema_version", F.lit(1))
          -             .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +             .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -         )
          +         )
          - 
          + 
          -         gold_avisos_df.write.mode("append").partitionBy("fecha").parquet(args["gold_avisos_path"])
          +         gold_avisos_df.write.mode("append").partitionBy("fecha").parquet(args["gold_avisos_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "e203db858089238019b642eb9b9f6a23" -> "735e6a4f6938be2c1d4d15ce74735529"
      ~ id                            = "glue-scripts/aemet_prevision_avisos_silver_to_gold-e203db858089238019b642eb9b9f6a23.py" -> (known after apply)
      ~ key                           = "glue-scripts/aemet_prevision_avisos_silver_to_gold-e203db858089238019b642eb9b9f6a23.py" -> "glue-scripts/aemet_prevision_avisos_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_afluencia_lugares_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_afluencia_lugares_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/afluencia_lugares_bronze_to_silver-2299183b4c60edf1e2539fc00a59ccc5.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `afluencia_lugares`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `afluencia_lugares`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          - añadir las columnas auxiliares que necesita `ge_suite.py` (ver
          + añadir las columnas auxiliares que necesita `ge_suite.py` (ver
          - `_with_typical_by_hour_range_columns`) y escribir el resultado.
          + `_with_typical_by_hour_range_columns`) y escribir el resultado.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita).
          + `saveAsTextFile` necesita).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/afluencia_lugares_patron_tipico/`
          +   `s3://madrono-tfm-dev-bronze-222234418587/afluencia_lugares_patron_tipico/`
          -   (nombre real del dataset Bronze que escribe
          +   (nombre real del dataset Bronze que escribe
          -   `ingesta/capturas/afluencia_lugares_madrid.py::DATASET_NAME`, distinto del
          +   `ingesta/capturas/afluencia_lugares_madrid.py::DATASET_NAME`, distinto del
          -   nombre `afluencia_lugares` usado en Silver/Gold -- corregido en la tarea
          +   nombre `afluencia_lugares` usado en Silver/Gold -- corregido en la tarea
          -   061, ver doc/061).
          +   061, ver doc/061).
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/afluencia_lugares/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/afluencia_lugares/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     ArrayType,
          +     ArrayType,
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.afluencia_lugares.ge_suite import run_quality_report
          + from procesamiento.silver_gold.afluencia_lugares.ge_suite import run_quality_report
          - from procesamiento.silver_gold.afluencia_lugares.transform import WEEKDAY_KEYS_ES, bronze_to_silver
          + from procesamiento.silver_gold.afluencia_lugares.transform import WEEKDAY_KEYS_ES, bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - TYPICAL_BY_HOUR_SCHEMA = StructType(
          + TYPICAL_BY_HOUR_SCHEMA = StructType(
          -     [StructField(day, ArrayType(IntegerType()), True) for day in WEEKDAY_KEYS_ES]
          +     [StructField(day, ArrayType(IntegerType()), True) for day in WEEKDAY_KEYS_ES]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("place_id", StringType(), False),
          +         StructField("place_id", StringType(), False),
          -         StructField("name", StringType(), False),
          +         StructField("name", StringType(), False),
          -         StructField("query", StringType(), True),
          +         StructField("query", StringType(), True),
          -         StructField("address", StringType(), True),
          +         StructField("address", StringType(), True),
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("live_pct", IntegerType(), True),
          +         StructField("live_pct", IntegerType(), True),
          -         StructField("typical_by_hour", TYPICAL_BY_HOUR_SCHEMA, True),
          +         StructField("typical_by_hour", TYPICAL_BY_HOUR_SCHEMA, True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _typical_by_hour_row(typical_by_hour):
          + def _typical_by_hour_row(typical_by_hour):
          -     if not typical_by_hour:
          +     if not typical_by_hour:
          -         return None
          +         return None
          -     return Row(**{day: typical_by_hour.get(day) for day in WEEKDAY_KEYS_ES})
          +     return Row(**{day: typical_by_hour.get(day) for day in WEEKDAY_KEYS_ES})
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     row_dict = {
          +     row_dict = {
          -         field.name: silver_record[field.name] for field in SILVER_SCHEMA.fields if field.name != "typical_by_hour"
          +         field.name: silver_record[field.name] for field in SILVER_SCHEMA.fields if field.name != "typical_by_hour"
          -     }
          +     }
          -     row_dict["typical_by_hour"] = _typical_by_hour_row(silver_record.get("typical_by_hour"))
          +     row_dict["typical_by_hour"] = _typical_by_hour_row(silver_record.get("typical_by_hour"))
          -     return Row(**row_dict)
          +     return Row(**row_dict)
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _with_typical_by_hour_range_columns(silver_df):
          + def _with_typical_by_hour_range_columns(silver_df):
          -     """Añade las columnas auxiliares que `ge_suite.py` valida como `[0, 100]`.
          +     """Añade las columnas auxiliares que `ge_suite.py` valida como `[0, 100]`.
          - 
          + 
          -     GX no tiene una expectation nativa de "cada valor de cada array anidado
          +     GX no tiene una expectation nativa de "cada valor de cada array anidado
          -     de un struct está en un rango" (ver docstring de `ge_suite.py`); se
          +     de un struct está en un rango" (ver docstring de `ge_suite.py`); se
          -     aplanan aquí los 7 arrays del struct `typical_by_hour` (uno por día de
          +     aplanan aquí los 7 arrays del struct `typical_by_hour` (uno por día de
          -     la semana) y se calcula su mínimo/máximo. Un registro sin
          +     la semana) y se calcula su mínimo/máximo. Un registro sin
          -     `typical_by_hour` produce columnas auxiliares `null` (arrays vacíos tras
          +     `typical_by_hour` produce columnas auxiliares `null` (arrays vacíos tras
          -     el `coalesce`, `array_min`/`array_max` de un array vacío es `null` en
          +     el `coalesce`, `array_min`/`array_max` de un array vacío es `null` en
          -     Spark) -- GX ignora los `null` en `expect_column_values_to_be_between`
          +     Spark) -- GX ignora los `null` en `expect_column_values_to_be_between`
          -     por defecto.
          +     por defecto.
          -     """
          +     """
          -     day_arrays = [F.coalesce(F.col(f"typical_by_hour.{day}"), F.array()) for day in WEEKDAY_KEYS_ES]
          +     day_arrays = [F.coalesce(F.col(f"typical_by_hour.{day}"), F.array()) for day in WEEKDAY_KEYS_ES]
          -     all_values = F.flatten(F.array(*day_arrays))
          +     all_values = F.flatten(F.array(*day_arrays))
          -     return silver_df.withColumn("typical_by_hour_min_value", F.array_min(all_values)).withColumn(
          +     return silver_df.withColumn("typical_by_hour_min_value", F.array_min(all_values)).withColumn(
          -         "typical_by_hour_max_value", F.array_max(all_values)
          +         "typical_by_hour_max_value", F.array_max(all_values)
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(lambda rows: _process_partition(rows, processed_at.isoformat()))
          +     silver_rdd = bronze_df.rdd.mapPartitions(lambda rows: _process_partition(rows, processed_at.isoformat()))
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_typical_by_hour_range_columns(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_typical_by_hour_range_columns(silver_df))
          -     report_key = f"{args['quality_report_path'].rstrip('/')}/afluencia_lugares_{processed_at:%Y%m%dT%H%M%S}.json"
          +     report_key = f"{args['quality_report_path'].rstrip('/')}/afluencia_lugares_{processed_at:%Y%m%dT%H%M%S}.json"
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Particiona por el día/hora del instante de captura (`ingested_at`,
          +     # Particiona por el día/hora del instante de captura (`ingested_at`,
          -     # único timestamp de este dataset) -- mismo criterio que `trafico`.
          +     # único timestamp de este dataset) -- mismo criterio que `trafico`.
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(args["silver_path"])
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(args["silver_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "2299183b4c60edf1e2539fc00a59ccc5" -> "e019ce6127891d24af49cb253082177b"
      ~ id                            = "glue-scripts/afluencia_lugares_bronze_to_silver-2299183b4c60edf1e2539fc00a59ccc5.py" -> (known after apply)
      ~ key                           = "glue-scripts/afluencia_lugares_bronze_to_silver-2299183b4c60edf1e2539fc00a59ccc5.py" -> "glue-scripts/afluencia_lugares_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_afluencia_lugares_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_afluencia_lugares_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/afluencia_lugares_estimada-818054b226fcfb9227d13b69da7397f3.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ id                            = "glue-scripts/afluencia_lugares_estimada-818054b226fcfb9227d13b69da7397f3.py" -> (known after apply)
      ~ key                           = "glue-scripts/afluencia_lugares_estimada-818054b226fcfb9227d13b69da7397f3.py" -> "glue-scripts/afluencia_lugares_estimada.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (13 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_backfill_dedup-bfb76e782afee2c5956f548a34da0b18.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `aforos_peatones_bicicletas` (tarea 077, mismo patrón que
          + `aforos_peatones_bicicletas` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          - 
          + 
          - **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 054, arreglado en la tarea 076) lee solo la partición Bronze del día
          + (tarea 054, arreglado en la tarea 076) lee solo la partición Bronze del día
          - de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          + de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          - histórico", así que no sirve para reconstruir Silver desde cero. Este script
          + histórico", así que no sirve para reconstruir Silver desde cero. Este script
          - existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          + existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          - deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          + deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          - hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          + hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          - todo el histórico acumulado en vez de solo el día nuevo -- confirmado en esta
          + todo el histórico acumulado en vez de solo el día nuevo -- confirmado en esta
          - tarea con un análisis directo de los 144 ficheros parquet de Silver (la
          + tarea con un análisis directo de los 144 ficheros parquet de Silver (la
          - tabla de Glue Catalog tiene `partition projection` con rango `fecha` desde
          + tabla de Glue Catalog tiene `partition projection` con rango `fecha` desde
          - 2026-08-01, que excluye el dato real de 2024-06-29/06-30 -- Athena no sirve
          + 2026-08-01, que excluye el dato real de 2024-06-29/06-30 -- Athena no sirve
          - para verificar este dataset en concreto, ver `doc/077-...md`): `n=6` para el
          + para verificar este dataset en concreto, ver `doc/077-...md`): `n=6` para el
          - mismo (`station_id`, `mode`, `measured_at`) -- exactamente las 6 ejecuciones
          + mismo (`station_id`, `mode`, `measured_at`) -- exactamente las 6 ejecuciones
          - históricas que reescribieron el CSV completo de un año de golpe cada vez.
          + históricas que reescribieron el CSV completo de un año de golpe cada vez.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          + lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          - 
          + 
          - `(station_id, mode, measured_at)` es la clave natural del dataset (`mode`
          + `(station_id, mode, measured_at)` es la clave natural del dataset (`mode`
          - distingue las dos redes de estaciones -- peatones/bicicletas -- que
          + distingue las dos redes de estaciones -- peatones/bicicletas -- que
          - comparten el mismo campo `count`, ver docstring de `transform.py`, "parte de
          + comparten el mismo campo `count`, ver docstring de `transform.py`, "parte de
          - la clave natural de agregación en `aggregate.py`").
          + la clave natural de agregación en `aggregate.py`").
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          + de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          - `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          + `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/aforos_peatones_bicicletas/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/aforos_peatones_bicicletas/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.aforos_peatones_bicicletas.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.aforos_peatones_bicicletas.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - from procesamiento.silver_gold.aforos_peatones_bicicletas.ge_suite import run_quality_report
          + from procesamiento.silver_gold.aforos_peatones_bicicletas.ge_suite import run_quality_report
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez.
          +     # el histórico de Bronze de una vez.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: reprocesar el mismo CSV histórico
          +     # La deduplicación real que faltaba: reprocesar el mismo CSV histórico
          -     # completo en cada ejecución dejó hasta 6 copias de cada fila. Clave
          +     # completo en cada ejecución dejó hasta 6 copias de cada fila. Clave
          -     # natural: estación + red (peatones/bicicletas) + instante medido.
          +     # natural: estación + red (peatones/bicicletas) + instante medido.
          -     silver_df = silver_df.dropDuplicates(["station_id", "mode", "measured_at"])
          +     silver_df = silver_df.dropDuplicates(["station_id", "mode", "measured_at"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"aforos_peatones_bicicletas_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"aforos_peatones_bicicletas_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, derivado de
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, derivado de
          -     # `measured_at`), igual que el pipeline de producción.
          +     # `measured_at`), igual que el pipeline de producción.
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo.
          +     # prefijo de destino debe estar vacío antes de lanzarlo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "bfb76e782afee2c5956f548a34da0b18" -> "8dc97077e9a7b0d793edb42e68c8a090"
      ~ id                            = "glue-scripts/aforos_peatones_bicicletas_backfill_dedup-bfb76e782afee2c5956f548a34da0b18.py" -> (known after apply)
      ~ key                           = "glue-scripts/aforos_peatones_bicicletas_backfill_dedup-bfb76e782afee2c5956f548a34da0b18.py" -> "glue-scripts/aforos_peatones_bicicletas_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-7c312ea88152d382dd1e02b82a549a7c.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `aforos_peatones_bicicletas` (tarea 077, mismo patrón que
          + `aforos_peatones_bicicletas` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 054/076), que solo procesa la partición `fecha=hoy` de Silver. Este
          + tarea 054/076), que solo procesa la partición `fecha=hoy` de Silver. Este
          - job existe para recalcular Gold desde cero tras la reconstrucción
          + job existe para recalcular Gold desde cero tras la reconstrucción
          - deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          + deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          - histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
          + histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
          - Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          + Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          - schedule.
          + schedule.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver ya deduplicado -- lo que hace este job
          + `dropDuplicates`: parte de un Silver ya deduplicado -- lo que hace este job
          - es la misma agregación de producción de `glue_silver_to_gold.py`, solo que
          + es la misma agregación de producción de `glue_silver_to_gold.py`, solo que
          - sobre todo el histórico en vez de una única partición diaria, y escribiendo
          + sobre todo el histórico en vez de una única partición diaria, y escribiendo
          - con `overwrite` en vez de `append`.
          + con `overwrite` en vez de `append`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/aforos_peatones_bicicletas_por_estacion_modo_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/aforos_peatones_bicicletas_por_estacion_modo_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     silver_df = spark.read.parquet(args["silver_path"])
          +     silver_df = spark.read.parquet(args["silver_path"])
          - 
          + 
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "mode", "fecha", "hora")
          +         silver_df.groupBy("station_id", "mode", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("district_code", ignorenulls=True).alias("district_code"),
          +             F.first("district_code", ignorenulls=True).alias("district_code"),
          -             F.first("district", ignorenulls=True).alias("district"),
          +             F.first("district", ignorenulls=True).alias("district"),
          -             F.first("address", ignorenulls=True).alias("address"),
          +             F.first("address", ignorenulls=True).alias("address"),
          -             F.first("address_notes", ignorenulls=True).alias("address_notes"),
          +             F.first("address_notes", ignorenulls=True).alias("address_notes"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.sum("count").alias("total_count"),
          +             F.sum("count").alias("total_count"),
          -             F.avg("count").alias("avg_count"),
          +             F.avg("count").alias("avg_count"),
          -             F.max("count").alias("max_count"),
          +             F.max("count").alias("max_count"),
          -             F.min("count").alias("min_count"),
          +             F.min("count").alias("min_count"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo.
          +     # prefijo de destino debe estar vacío antes de lanzarlo.
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "7c312ea88152d382dd1e02b82a549a7c" -> "dedd44063c766e8475986650df404498"
      ~ id                            = "glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-7c312ea88152d382dd1e02b82a549a7c.py" -> (known after apply)
      ~ key                           = "glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-7c312ea88152d382dd1e02b82a549a7c.py" -> "glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aforos_peatones_bicicletas_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d8325aae3ee77630cfc0f6612c30323e.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `aforos_peatones_bicicletas`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `aforos_peatones_bicicletas`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          - y escribir el resultado.
          + y escribir el resultado.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          + `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/aforos_peatones_bicicletas/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/aforos_peatones_bicicletas/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.aforos_peatones_bicicletas.ge_suite import run_quality_report
          + from procesamiento.silver_gold.aforos_peatones_bicicletas.ge_suite import run_quality_report
          - from procesamiento.silver_gold.aforos_peatones_bicicletas.transform import bronze_to_silver
          + from procesamiento.silver_gold.aforos_peatones_bicicletas.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("station_id", StringType(), False),
          +         StructField("station_id", StringType(), False),
          -         StructField("mode", StringType(), False),
          +         StructField("mode", StringType(), False),
          -         StructField("count", IntegerType(), False),
          +         StructField("count", IntegerType(), False),
          -         StructField("measured_at", StringType(), False),
          +         StructField("measured_at", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("district_code", StringType(), True),
          +         StructField("district_code", StringType(), True),
          -         StructField("district", StringType(), True),
          +         StructField("district", StringType(), True),
          -         StructField("address", StringType(), True),
          +         StructField("address", StringType(), True),
          -         StructField("address_notes", StringType(), True),
          +         StructField("address_notes", StringType(), True),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         station_id=silver_record["station_id"],
          +         station_id=silver_record["station_id"],
          -         mode=silver_record["mode"],
          +         mode=silver_record["mode"],
          -         count=silver_record["count"],
          +         count=silver_record["count"],
          -         measured_at=silver_record["measured_at"],
          +         measured_at=silver_record["measured_at"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         district_code=silver_record["district_code"],
          +         district_code=silver_record["district_code"],
          -         district=silver_record["district"],
          +         district=silver_record["district"],
          -         address=silver_record["address"],
          +         address=silver_record["address"],
          -         address_notes=silver_record["address_notes"],
          +         address_notes=silver_record["address_notes"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"aforos_peatones_bicicletas_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"aforos_peatones_bicicletas_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          -     # para que un consumidor ya familiarizado con Bronze no tenga que
          +     # para que un consumidor ya familiarizado con Bronze no tenga que
          -     # aprender un esquema de partición distinto para Silver.
          +     # aprender un esquema de partición distinto para Silver.
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "d8325aae3ee77630cfc0f6612c30323e" -> "d037fa3c1d50aa6cdf1a4355e4af910b"
      ~ id                            = "glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d8325aae3ee77630cfc0f6612c30323e.py" -> (known after apply)
      ~ key                           = "glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d8325aae3ee77630cfc0f6612c30323e.py" -> "glue-scripts/aforos_peatones_bicicletas_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_silver_to_gold-a7df88f8aa89cea895c3e594ff738600.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `aforos_peatones_bicicletas`
          + """Job de AWS Glue: Silver -> Gold del dataset `aforos_peatones_bicicletas`
          - (conteo total/medio por estación, modo y hora).
          + (conteo total/medio por estación, modo y hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/aforos_peatones_bicicletas_por_estacion_modo_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/aforos_peatones_bicicletas_por_estacion_modo_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          + from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          -     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          +     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          -     # desalineado con `today()` (Python, Europe/Madrid).
          +     # desalineado con `today()` (Python, Europe/Madrid).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          +     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          -     # nunca la raiz completa del dataset -- mismo motivo de coste que
          +     # nunca la raiz completa del dataset -- mismo motivo de coste que
          -     # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio conteo
          +     # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio conteo
          -     # (`measured_at`, ver glue_bronze_to_silver.py), que coincide con el dia
          +     # (`measured_at`, ver glue_bronze_to_silver.py), que coincide con el dia
          -     # de ingestion para este dataset (conteos casi en tiempo real, sin
          +     # de ingestion para este dataset (conteos casi en tiempo real, sin
          -     # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
          +     # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
          -     # vez, el dia en que ese dia es "hoy".
          +     # vez, el dia en que ese dia es "hoy".
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          +     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `hora` sí se infiere como columna de partición física (es el nivel
          +     # `hora` sí se infiere como columna de partición física (es el nivel
          -     # inmediato bajo la ruta leída), pero `fecha` no -- al acotar la lectura
          +     # inmediato bajo la ruta leída), pero `fecha` no -- al acotar la lectura
          -     # a `fecha=<fecha>/` (tarea 076) esa partición queda fija en la propia
          +     # a `fecha=<fecha>/` (tarea 076) esa partición queda fija en la propia
          -     # ruta y Spark deja de exponerla como columna, igual que
          +     # ruta y Spark deja de exponerla como columna, igual que
          -     # `aparcamientos_silver_to_gold.py` (tarea 072). Se añade de vuelta con
          +     # `aparcamientos_silver_to_gold.py` (tarea 072). Se añade de vuelta con
          -     # el valor ya conocido en vez de asumir que Spark la habría inferido --
          +     # el valor ya conocido en vez de asumir que Spark la habría inferido --
          -     # mismo bug real que `cartelera_cines_estrenos_silver_to_gold.py`
          +     # mismo bug real que `cartelera_cines_estrenos_silver_to_gold.py`
          -     # (`AnalysisException: Column 'fecha' does not exist`), encontrado y
          +     # (`AnalysisException: Column 'fecha' does not exist`), encontrado y
          -     # corregido en la tarea 090 en los 3 jobs del patrón que lo tenían
          +     # corregido en la tarea 090 en los 3 jobs del patrón que lo tenían
          -     # latente; este en concreto no había fallado aún en producción porque la
          +     # latente; este en concreto no había fallado aún en producción porque la
          -     # fuente de `aforos_peatones_bicicletas` está descontinuada desde
          +     # fuente de `aforos_peatones_bicicletas` está descontinuada desde
          -     # 2026-06-30 (ver doc/087) y `partition_has_objects` nunca deja pasar
          +     # 2026-06-30 (ver doc/087) y `partition_has_objects` nunca deja pasar
          -     # ninguna ejecución real hasta aquí.
          +     # ninguna ejecución real hasta aquí.
          -     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          - 
          + 
          -     # `mode` entra en la clave de agrupación (mismo criterio que `pollutant`
          +     # `mode` entra en la clave de agrupación (mismo criterio que `pollutant`
          -     # en `calidad_aire`/`magnitude` en `meteorologia`): peatones y bicicletas
          +     # en `calidad_aire`/`magnitude` en `meteorologia`): peatones y bicicletas
          -     # se miden en redes de estaciones distintas, ver docstring de
          +     # se miden en redes de estaciones distintas, ver docstring de
          -     # `aggregate.py`.
          +     # `aggregate.py`.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "mode", "fecha", "hora")
          +         silver_df.groupBy("station_id", "mode", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("district_code", ignorenulls=True).alias("district_code"),
          +             F.first("district_code", ignorenulls=True).alias("district_code"),
          -             F.first("district", ignorenulls=True).alias("district"),
          +             F.first("district", ignorenulls=True).alias("district"),
          -             F.first("address", ignorenulls=True).alias("address"),
          +             F.first("address", ignorenulls=True).alias("address"),
          -             F.first("address_notes", ignorenulls=True).alias("address_notes"),
          +             F.first("address_notes", ignorenulls=True).alias("address_notes"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.sum("count").alias("total_count"),
          +             F.sum("count").alias("total_count"),
          -             F.avg("count").alias("avg_count"),
          +             F.avg("count").alias("avg_count"),
          -             F.max("count").alias("max_count"),
          +             F.max("count").alias("max_count"),
          -             F.min("count").alias("min_count"),
          +             F.min("count").alias("min_count"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # estación, modo y hora, no cada ~5 minutos): particionar solo por
          +     # estación, modo y hora, no cada ~5 minutos): particionar solo por
          -     # `date` es suficiente para podar particiones sin generar ficheros
          +     # `date` es suficiente para podar particiones sin generar ficheros
          -     # diminutos.
          +     # diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "a7df88f8aa89cea895c3e594ff738600" -> "98ae6a2fa1ca9fc05b6451aaffbd690b"
      ~ id                            = "glue-scripts/aforos_peatones_bicicletas_silver_to_gold-a7df88f8aa89cea895c3e594ff738600.py" -> (known after apply)
      ~ key                           = "glue-scripts/aforos_peatones_bicicletas_silver_to_gold-a7df88f8aa89cea895c3e594ff738600.py" -> "glue-scripts/aforos_peatones_bicicletas_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_agenda_eventos_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_agenda_eventos_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_backfill_dedup-ebb7fb05697677064a5b18ee492aca9e.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `agenda_eventos` (tarea 077, mismo patrón que
          + `agenda_eventos` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          - 
          + 
          - **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 056, arreglado en la tarea 076) lee solo la partición Bronze del día
          + (tarea 056, arreglado en la tarea 076) lee solo la partición Bronze del día
          - de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          + de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          - histórico", así que no sirve para reconstruir Silver desde cero. Este script
          + histórico", así que no sirve para reconstruir Silver desde cero. Este script
          - existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          + existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          - deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          + deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          - hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          + hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          - todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          + todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          - Athena real (`doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`):
          + Athena real (`doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`):
          - `n=56` para el mismo evento. Se lanza una sola vez a mano (`aws glue
          + `n=56` para el mismo evento. Se lanza una sola vez a mano (`aws glue
          - start-job-run`), nunca vía trigger ni schedule.
          + start-job-run`), nunca vía trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074, un
          + lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074, un
          - `overwrite` de Spark sobre un prefijo con miles de objetos preexistentes
          + `overwrite` de Spark sobre un prefijo con miles de objetos preexistentes
          - puede fallar de forma intermitente con `MultiObjectDeleteException` y abortar
          + puede fallar de forma intermitente con `MultiObjectDeleteException` y abortar
          - toda la escritura sin dejar nada nuevo escrito).
          + toda la escritura sin dejar nada nuevo escrito).
          - 
          + 
          - `event_id` es la clave natural imprescindible del dataset (ver docstring de
          + `event_id` es la clave natural imprescindible del dataset (ver docstring de
          - `transform.py`, "clave natural imprescindible para poder deduplicar
          + `transform.py`, "clave natural imprescindible para poder deduplicar
          - reingestas en `aggregate.py`") -- `dropDuplicates(["event_id"])` es la misma
          + reingestas en `aggregate.py`") -- `dropDuplicates(["event_id"])` es la misma
          - deduplicación que ya hace `aggregate.py` en tiempo de agregación, aplicada
          + deduplicación que ya hace `aggregate.py` en tiempo de agregación, aplicada
          - aquí a nivel de Silver para que no siga growing sin límite en cada
          + aquí a nivel de Silver para que no siga growing sin límite en cada
          - reingesta.
          + reingesta.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          + de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          - `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          + `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/agenda_eventos/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/agenda_eventos/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import substring
          + from pyspark.sql.functions import substring
          - 
          + 
          - from procesamiento.silver_gold.agenda_eventos.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.agenda_eventos.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - from procesamiento.silver_gold.agenda_eventos.ge_suite import run_quality_report
          + from procesamiento.silver_gold.agenda_eventos.ge_suite import run_quality_report
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el pipeline de producción (tarea 076/072): sin esto,
          +     # Mismo motivo que el pipeline de producción (tarea 076/072): sin esto,
          -     # `substring`/`date_format` calculan en el timezone de sesión por defecto
          +     # `substring`/`date_format` calculan en el timezone de sesión por defecto
          -     # de Spark (UTC en el runtime de Glue), desalineado con Europe/Madrid.
          +     # de Spark (UTC en el runtime de Glue), desalineado con Europe/Madrid.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          +     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa.
          +     # reconstrucción completa.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: reingestas repetidas del mismo
          +     # La deduplicación real que faltaba: reingestas repetidas del mismo
          -     # evento por el bug de lectura incremental. `event_id` es la clave
          +     # evento por el bug de lectura incremental. `event_id` es la clave
          -     # natural del dataset (ver docstring del módulo).
          +     # natural del dataset (ver docstring del módulo).
          -     silver_df = silver_df.dropDuplicates(["event_id"])
          +     silver_df = silver_df.dropDuplicates(["event_id"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"agenda_eventos_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"agenda_eventos_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (solo
          +     # Mismo esquema de partición que el pipeline de producción (solo
          -     # `fecha`, sin `hora` -- ver docstring de `glue_bronze_to_silver.py`).
          +     # `fecha`, sin `hora` -- ver docstring de `glue_bronze_to_silver.py`).
          -     silver_partitioned = silver_df.withColumn("fecha", substring("start_datetime", 1, 10))
          +     silver_partitioned = silver_df.withColumn("fecha", substring("start_datetime", 1, 10))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          +     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          -     # sustituto de ese borrado previo.
          +     # sustituto de ese borrado previo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha").parquet(args["silver_path"])
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha").parquet(args["silver_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "ebb7fb05697677064a5b18ee492aca9e" -> "406949108f74a212bfa3dd0a5f67acca"
      ~ id                            = "glue-scripts/agenda_eventos_backfill_dedup-ebb7fb05697677064a5b18ee492aca9e.py" -> (known after apply)
      ~ key                           = "glue-scripts/agenda_eventos_backfill_dedup-ebb7fb05697677064a5b18ee492aca9e.py" -> "glue-scripts/agenda_eventos_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_agenda_eventos_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_agenda_eventos_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_backfill_dedup_gold-c417e4a5711e3fcb2d416cc0f05f3290.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `agenda_eventos` (tarea 077, mismo patrón que
          + `agenda_eventos` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 056/076), que solo procesa la partición `fecha=hoy` de Silver. Este
          + tarea 056/076), que solo procesa la partición `fecha=hoy` de Silver. Este
          - job existe para recalcular Gold desde cero tras la reconstrucción
          + job existe para recalcular Gold desde cero tras la reconstrucción
          - deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          + deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          - histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
          + histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
          - Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          + Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          - schedule.
          + schedule.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que el propio backfill de Silver ya dejó
          + `dropDuplicates`: parte de un Silver que el propio backfill de Silver ya dejó
          - sin duplicados (`event_id` único) -- lo que hace este job es la misma
          + sin duplicados (`event_id` único) -- lo que hace este job es la misma
          - agregación de producción de `glue_silver_to_gold.py`, solo que sobre todo el
          + agregación de producción de `glue_silver_to_gold.py`, solo que sobre todo el
          - histórico en vez de una única partición diaria, y escribiendo con
          + histórico en vez de una única partición diaria, y escribiendo con
          - `overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
          + `overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
          - antes de lanzarlo, igual que Silver).
          + antes de lanzarlo, igual que Silver).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/agenda_eventos_por_categoria_distrito_fecha/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/agenda_eventos_por_categoria_distrito_fecha/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - UNKNOWN_CATEGORY = "__sin_categoria__"
          + UNKNOWN_CATEGORY = "__sin_categoria__"
          - UNKNOWN_DISTRICT = "__sin_distrito__"
          + UNKNOWN_DISTRICT = "__sin_distrito__"
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- exactamente lo que necesita una
          +     # el histórico de Silver de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa de Gold.
          +     # reconstrucción completa de Gold.
          -     silver_df = spark.read.parquet(args["silver_path"])
          +     silver_df = spark.read.parquet(args["silver_path"])
          - 
          + 
          -     normalized_df = silver_df.withColumn(
          +     normalized_df = silver_df.withColumn(
          -         "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
          +         "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
          -     ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))
          +     ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))
          - 
          + 
          -     # Misma agregación que el pipeline de producción
          +     # Misma agregación que el pipeline de producción
          -     # (`glue_silver_to_gold.py`): una fila por categoría/distrito/día.
          +     # (`glue_silver_to_gold.py`): una fila por categoría/distrito/día.
          -     gold_df = (
          +     gold_df = (
          -         normalized_df.groupBy("category_key", "district_key", "fecha")
          +         normalized_df.groupBy("category_key", "district_key", "fecha")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.countDistinct("event_id").alias("events_count"),
          +             F.countDistinct("event_id").alias("events_count"),
          -             F.countDistinct(F.when(F.col("free") == True, F.col("event_id"))).alias(  # noqa: E712
          +             F.countDistinct(F.when(F.col("free") == True, F.col("event_id"))).alias(  # noqa: E712
          -                 "free_events_count"
          +                 "free_events_count"
          -             ),
          +             ),
          -             F.sort_array(F.collect_set("source")).alias("sources"),
          +             F.sort_array(F.collect_set("source")).alias("sources"),
          -             F.min("start_datetime").alias("first_start_datetime"),
          +             F.min("start_datetime").alias("first_start_datetime"),
          -             F.max("start_datetime").alias("last_start_datetime"),
          +             F.max("start_datetime").alias("last_start_datetime"),
          -         )
          +         )
          -         .withColumnRenamed("category_key", "category")
          +         .withColumnRenamed("category_key", "category")
          -         .withColumnRenamed("district_key", "district")
          +         .withColumnRenamed("district_key", "district")
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          +     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          -     # que `glue_backfill_dedup.py` para Silver).
          +     # que `glue_backfill_dedup.py` para Silver).
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "c417e4a5711e3fcb2d416cc0f05f3290" -> "b4c8693ee116e2f50aee1b96fd7018c6"
      ~ id                            = "glue-scripts/agenda_eventos_backfill_dedup_gold-c417e4a5711e3fcb2d416cc0f05f3290.py" -> (known after apply)
      ~ key                           = "glue-scripts/agenda_eventos_backfill_dedup_gold-c417e4a5711e3fcb2d416cc0f05f3290.py" -> "glue-scripts/agenda_eventos_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_agenda_eventos_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_agenda_eventos_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_bronze_to_silver-75c29ecd15eb33bf665840234bcf5cc8.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `agenda_eventos`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `agenda_eventos`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          - y escribir el resultado.
          + y escribir el resultado.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          + `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          - 
          + 
          - Silver se particiona solo por `fecha` (derivada de `start_datetime`), sin
          + Silver se particiona solo por `fecha` (derivada de `start_datetime`), sin
          - `hora`: a diferencia del resto del patrón, una de las dos fuentes
          + `hora`: a diferencia del resto del patrón, una de las dos fuentes
          - (`agenda_turismo_esmadrid`) no publica ninguna hora en `start_datetime`
          + (`agenda_turismo_esmadrid`) no publica ninguna hora en `start_datetime`
          - (solo fecha, ver `transform.py`) -- forzar una `hora` inventada (p.ej.
          + (solo fecha, ver `transform.py`) -- forzar una `hora` inventada (p.ej.
          - "00" por defecto del parseo) sería engañoso, mismo criterio que ya aplicó
          + "00" por defecto del parseo) sería engañoso, mismo criterio que ya aplicó
          - `ruido` (tarea 053) para una fuente sin granularidad horaria. `fecha` se
          + `ruido` (tarea 053) para una fuente sin granularidad horaria. `fecha` se
          - deriva con `substring(start_datetime, 1, 10)` en vez de `to_date(...)`:
          + deriva con `substring(start_datetime, 1, 10)` en vez de `to_date(...)`:
          - ambos formatos de origen (`"2026-08-21T22:00:00"` del dataset municipal,
          + ambos formatos de origen (`"2026-08-21T22:00:00"` del dataset municipal,
          - `"2026-11-15"` de esMadrid) siempre empiezan por `YYYY-MM-DD`, así que un
          + `"2026-11-15"` de esMadrid) siempre empiezan por `YYYY-MM-DD`, así que un
          - recorte de texto es más simple y evita cualquier ambigüedad de parseo de
          + recorte de texto es más simple y evita cualquier ambigüedad de parseo de
          - fecha mixta en Spark.
          + fecha mixta en Spark.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/agenda_eventos/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/agenda_eventos/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.functions import substring
          + from pyspark.sql.functions import substring
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     BooleanType,
          +     BooleanType,
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.agenda_eventos.ge_suite import run_quality_report
          + from procesamiento.silver_gold.agenda_eventos.ge_suite import run_quality_report
          - from procesamiento.silver_gold.agenda_eventos.transform import bronze_to_silver
          + from procesamiento.silver_gold.agenda_eventos.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), False),
          +         StructField("source", StringType(), False),
          -         StructField("event_id", StringType(), False),
          +         StructField("event_id", StringType(), False),
          -         StructField("title", StringType(), False),
          +         StructField("title", StringType(), False),
          -         StructField("description", StringType(), True),
          +         StructField("description", StringType(), True),
          -         StructField("category", StringType(), True),
          +         StructField("category", StringType(), True),
          -         StructField("start_datetime", StringType(), False),
          +         StructField("start_datetime", StringType(), False),
          -         StructField("end_datetime", StringType(), True),
          +         StructField("end_datetime", StringType(), True),
          -         StructField("schedule_text", StringType(), True),
          +         StructField("schedule_text", StringType(), True),
          -         StructField("free", BooleanType(), True),
          +         StructField("free", BooleanType(), True),
          -         StructField("price_info", StringType(), True),
          +         StructField("price_info", StringType(), True),
          -         StructField("venue_name", StringType(), True),
          +         StructField("venue_name", StringType(), True),
          -         StructField("address", StringType(), True),
          +         StructField("address", StringType(), True),
          -         StructField("district", StringType(), True),
          +         StructField("district", StringType(), True),
          -         StructField("neighborhood", StringType(), True),
          +         StructField("neighborhood", StringType(), True),
          -         StructField("postal_code", StringType(), True),
          +         StructField("postal_code", StringType(), True),
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("url", StringType(), True),
          +         StructField("url", StringType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         event_id=silver_record["event_id"],
          +         event_id=silver_record["event_id"],
          -         title=silver_record["title"],
          +         title=silver_record["title"],
          -         description=silver_record["description"],
          +         description=silver_record["description"],
          -         category=silver_record["category"],
          +         category=silver_record["category"],
          -         start_datetime=silver_record["start_datetime"],
          +         start_datetime=silver_record["start_datetime"],
          -         end_datetime=silver_record["end_datetime"],
          +         end_datetime=silver_record["end_datetime"],
          -         schedule_text=silver_record["schedule_text"],
          +         schedule_text=silver_record["schedule_text"],
          -         free=silver_record["free"],
          +         free=silver_record["free"],
          -         price_info=silver_record["price_info"],
          +         price_info=silver_record["price_info"],
          -         venue_name=silver_record["venue_name"],
          +         venue_name=silver_record["venue_name"],
          -         address=silver_record["address"],
          +         address=silver_record["address"],
          -         district=silver_record["district"],
          +         district=silver_record["district"],
          -         neighborhood=silver_record["neighborhood"],
          +         neighborhood=silver_record["neighborhood"],
          -         postal_code=silver_record["postal_code"],
          +         postal_code=silver_record["postal_code"],
          -         lat=silver_record["lat"],
          +         lat=silver_record["lat"],
          -         lon=silver_record["lon"],
          +         lon=silver_record["lon"],
          -         url=silver_record["url"],
          +         url=silver_record["url"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"agenda_eventos_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"agenda_eventos_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Particiona solo por `fecha` (sin `hora`, ver docstring del módulo):
          +     # Particiona solo por `fecha` (sin `hora`, ver docstring del módulo):
          -     # una de las dos fuentes no publica hora de celebración.
          +     # una de las dos fuentes no publica hora de celebración.
          -     silver_partitioned = silver_df.withColumn("fecha", substring("start_datetime", 1, 10))
          +     silver_partitioned = silver_df.withColumn("fecha", substring("start_datetime", 1, 10))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha").parquet(args["silver_path"])
          +     silver_partitioned.write.mode("append").partitionBy("fecha").parquet(args["silver_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "75c29ecd15eb33bf665840234bcf5cc8" -> "e24cfdad3be04dfe065231b9643719c0"
      ~ id                            = "glue-scripts/agenda_eventos_bronze_to_silver-75c29ecd15eb33bf665840234bcf5cc8.py" -> (known after apply)
      ~ key                           = "glue-scripts/agenda_eventos_bronze_to_silver-75c29ecd15eb33bf665840234bcf5cc8.py" -> "glue-scripts/agenda_eventos_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_agenda_eventos_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_agenda_eventos_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_silver_to_gold-4d854fda4df74abc055b9eba9af92b0f.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `agenda_eventos` (número de
          + """Job de AWS Glue: Silver -> Gold del dataset `agenda_eventos` (número de
          - eventos por categoría, distrito y día de celebración).
          + eventos por categoría, distrito y día de celebración).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/agenda_eventos_por_categoria_distrito_fecha/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/agenda_eventos_por_categoria_distrito_fecha/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          + from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - UNKNOWN_CATEGORY = "__sin_categoria__"
          + UNKNOWN_CATEGORY = "__sin_categoria__"
          - UNKNOWN_DISTRICT = "__sin_distrito__"
          + UNKNOWN_DISTRICT = "__sin_distrito__"
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          -     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          +     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          -     # desalineado con `today()` (Python, Europe/Madrid).
          +     # desalineado con `today()` (Python, Europe/Madrid).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          +     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          -     # nunca la raiz completa del dataset -- mismo motivo de coste que
          +     # nunca la raiz completa del dataset -- mismo motivo de coste que
          -     # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio evento
          +     # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio evento
          -     # (`start_datetime`), que puede ser semanas/meses en el futuro respecto
          +     # (`start_datetime`), que puede ser semanas/meses en el futuro respecto
          -     # al dia de ingestion (agenda cultural real: eventos publicados con
          +     # al dia de ingestion (agenda cultural real: eventos publicados con
          -     # mucha antelacion, ver muestra real de `agenda_eventos_madrid_sample.json`
          +     # mucha antelacion, ver muestra real de `agenda_eventos_madrid_sample.json`
          -     # con fechas de fin hasta 2027) -- no la de ingestion. Silver es un
          +     # con fechas de fin hasta 2027) -- no la de ingestion. Silver es un
          -     # almacen persistente: cada particion `fecha=<dia>` recibe escrituras de
          +     # almacen persistente: cada particion `fecha=<dia>` recibe escrituras de
          -     # muchos dias de ingestion distintos mientras el evento sigue vigente en
          +     # muchos dias de ingestion distintos mientras el evento sigue vigente en
          -     # la fuente, pero esta lectura visita esa particion una unica vez, el
          +     # la fuente, pero esta lectura visita esa particion una unica vez, el
          -     # dia en que ese dia de calendario se convierte en "hoy" -- momento en
          +     # dia en que ese dia de calendario se convierte en "hoy" -- momento en
          -     # el que ya contiene todo lo que se llegó a capturar de ese evento.
          +     # el que ya contiene todo lo que se llegó a capturar de ese evento.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          +     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha` es columna de partición física de Silver (derivada de
          +     # `fecha` es columna de partición física de Silver (derivada de
          -     # `start_datetime`, ver glue_bronze_to_silver.py), pero al acotar la
          +     # `start_datetime`, ver glue_bronze_to_silver.py), pero al acotar la
          -     # lectura a una única partición `fecha=<fecha>/` (tarea 076) Spark deja
          +     # lectura a una única partición `fecha=<fecha>/` (tarea 076) Spark deja
          -     # de inferirla como columna -- esa partición queda fija en la propia
          +     # de inferirla como columna -- esa partición queda fija en la propia
          -     # ruta leída. Se añade de vuelta con el valor ya conocido -- bug real
          +     # ruta leída. Se añade de vuelta con el valor ya conocido -- bug real
          -     # (`AnalysisException: Column 'fecha' does not exist`) que llevaba
          +     # (`AnalysisException: Column 'fecha' does not exist`) que llevaba
          -     # fallando en producción todos los días desde el 2026-08-23 (ver
          +     # fallando en producción todos los días desde el 2026-08-23 (ver
          -     # historial real de `madrono-tfm-dev-agenda-eventos-silver-to-gold`),
          +     # historial real de `madrono-tfm-dev-agenda-eventos-silver-to-gold`),
          -     # encontrado y corregido en la tarea 090 junto con el mismo bug en
          +     # encontrado y corregido en la tarea 090 junto con el mismo bug en
          -     # `cartelera_cines_estrenos`/`aforos_peatones_bicicletas`.
          +     # `cartelera_cines_estrenos`/`aforos_peatones_bicicletas`.
          -     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          - 
          + 
          -     # `category`/`district` ausentes se agrupan bajo un sentinela en vez de
          +     # `category`/`district` ausentes se agrupan bajo un sentinela en vez de
          -     # descartarse -- mismo criterio que `aggregate.py` (ver docstring de ese
          +     # descartarse -- mismo criterio que `aggregate.py` (ver docstring de ese
          -     # módulo).
          +     # módulo).
          -     normalized_df = silver_df.withColumn(
          +     normalized_df = silver_df.withColumn(
          -         "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
          +         "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
          -     ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))
          +     ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))
          -     gold_df = (
          +     gold_df = (
          -         normalized_df.groupBy("category_key", "district_key", "fecha")
          +         normalized_df.groupBy("category_key", "district_key", "fecha")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.countDistinct("event_id").alias("events_count"),
          +             F.countDistinct("event_id").alias("events_count"),
          -             F.countDistinct(F.when(F.col("free") == True, F.col("event_id"))).alias(  # noqa: E712
          +             F.countDistinct(F.when(F.col("free") == True, F.col("event_id"))).alias(  # noqa: E712
          -                 "free_events_count"
          +                 "free_events_count"
          -             ),
          +             ),
          -             F.sort_array(F.collect_set("source")).alias("sources"),
          +             F.sort_array(F.collect_set("source")).alias("sources"),
          -             F.min("start_datetime").alias("first_start_datetime"),
          +             F.min("start_datetime").alias("first_start_datetime"),
          -             F.max("start_datetime").alias("last_start_datetime"),
          +             F.max("start_datetime").alias("last_start_datetime"),
          -         )
          +         )
          -         .withColumnRenamed("category_key", "category")
          +         .withColumnRenamed("category_key", "category")
          -         .withColumnRenamed("district_key", "district")
          +         .withColumnRenamed("district_key", "district")
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # categoría, distrito y día, no una por evento): particionar solo por
          +     # categoría, distrito y día, no una por evento): particionar solo por
          -     # `date` es suficiente para podar particiones sin generar ficheros
          +     # `date` es suficiente para podar particiones sin generar ficheros
          -     # diminutos.
          +     # diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "4d854fda4df74abc055b9eba9af92b0f" -> "7ed6c1455ead3aef19f9e40b96c23a51"
      ~ id                            = "glue-scripts/agenda_eventos_silver_to_gold-4d854fda4df74abc055b9eba9af92b0f.py" -> (known after apply)
      ~ key                           = "glue-scripts/agenda_eventos_silver_to_gold-4d854fda4df74abc055b9eba9af92b0f.py" -> "glue-scripts/agenda_eventos_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aparcamientos_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_aparcamientos_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_backfill_dedup-0040b8ac53f09f609005c2ad2aac464f.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `aparcamientos`.
          + `aparcamientos`.
          - 
          + 
          - **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 048, arreglado en la tarea 072) calcula internamente una única
          + (tarea 048, arreglado en la tarea 072) calcula internamente una única
          - hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          + hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          - un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          + un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          - reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          + reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          - TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          + TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          - confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          + confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          - que cada ejecución histórica del job de producción (antes del arreglo de la
          + que cada ejecución histórica del job de producción (antes del arreglo de la
          - tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          + tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          - deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          + deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          - verificado con una consulta Athena real sobre `(parking_id, measured_at)`
          + verificado con una consulta Athena real sobre `(parking_id, measured_at)`
          - antes de escribir este script. Se lanza una sola vez a mano (`aws glue
          + antes de escribir este script. Se lanza una sola vez a mano (`aws glue
          - start-job-run`), nunca vía trigger ni schedule.
          + start-job-run`), nunca vía trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          + lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          - tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          + tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          - sobrescribir un prefijo con miles de objetos preexistentes): este script
          + sobrescribir un prefijo con miles de objetos preexistentes): este script
          - escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          + escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          - de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          + de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          - con la reconstrucción.
          + con la reconstrucción.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción
          + de Spark/GX que ya usa el pipeline de producción
          - (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          + (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          - `_with_consistency_column`, `_write_quality_report`.
          + `_with_consistency_column`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/aparcamientos/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/aparcamientos/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import coalesce, date_format, lit, to_timestamp
          + from pyspark.sql.functions import coalesce, date_format, lit, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.aparcamientos.ge_suite import run_quality_report
          + from procesamiento.silver_gold.aparcamientos.ge_suite import run_quality_report
          - from procesamiento.silver_gold.aparcamientos.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.aparcamientos.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _with_consistency_column,
          +     _with_consistency_column,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          +     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          -     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          +     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          -     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          +     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          -     # con la hora de Madrid real de `measured_at`.
          +     # con la hora de Madrid real de `measured_at`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          +     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa.
          +     # reconstrucción completa.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          +     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          -     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          +     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          -     # registro repetido decenas de veces. Un par (parking_id, measured_at)
          +     # registro repetido decenas de veces. Un par (parking_id, measured_at)
          -     # identifica de forma única una medición real de ocupación. `measured_at`
          +     # identifica de forma única una medición real de ocupación. `measured_at`
          -     # puede ser nulo (ver transform.py); Spark trata NULL como igual a NULL
          +     # puede ser nulo (ver transform.py); Spark trata NULL como igual a NULL
          -     # en `dropDuplicates`, así que los registros sin medida compartida
          +     # en `dropDuplicates`, así que los registros sin medida compartida
          -     # también se deduplican entre sí por `parking_id`.
          +     # también se deduplican entre sí por `parking_id`.
          -     silver_df = silver_df.dropDuplicates(["parking_id", "measured_at"])
          +     silver_df = silver_df.dropDuplicates(["parking_id", "measured_at"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_consistency_column(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_consistency_column(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"aparcamientos_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"aparcamientos_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          +     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          -     # hora de Madrid; `__sin_medida__` para registros sin `measured_at`, ver
          +     # hora de Madrid; `__sin_medida__` para registros sin `measured_at`, ver
          -     # glue_bronze_to_silver.py).
          +     # glue_bronze_to_silver.py).
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha",
          +         "fecha",
          -         coalesce(date_format(to_timestamp("measured_at"), "yyyy-MM-dd"), lit("__sin_medida__")),
          +         coalesce(date_format(to_timestamp("measured_at"), "yyyy-MM-dd"), lit("__sin_medida__")),
          -     ).withColumn(
          +     ).withColumn(
          -         "hora",
          +         "hora",
          -         coalesce(date_format(to_timestamp("measured_at"), "HH"), lit("__sin_medida__")),
          +         coalesce(date_format(to_timestamp("measured_at"), "HH"), lit("__sin_medida__")),
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          +     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          -     # sustituto de ese borrado previo.
          +     # sustituto de ese borrado previo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "0040b8ac53f09f609005c2ad2aac464f" -> "d2f4134d5b53957b15e82d4bed24c7eb"
      ~ id                            = "glue-scripts/aparcamientos_backfill_dedup-0040b8ac53f09f609005c2ad2aac464f.py" -> (known after apply)
      ~ key                           = "glue-scripts/aparcamientos_backfill_dedup-0040b8ac53f09f609005c2ad2aac464f.py" -> "glue-scripts/aparcamientos_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aparcamientos_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_aparcamientos_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_backfill_dedup_gold-7f4c18ec21a262d4a6e788348e492c3f.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `aparcamientos`.
          + `aparcamientos`.
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 048/072), que solo procesa la partición horaria anterior a la
          + tarea 048/072), que solo procesa la partición horaria anterior a la
          - ejecución. Este job existe para recalcular Gold desde cero tras la
          + ejecución. Este job existe para recalcular Gold desde cero tras la
          - reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          + reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          - lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          + lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          - hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          + hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          - trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          + trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          + `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          - duplicados (`(parking_id, measured_at)` único) -- lo que hace este job es la
          + duplicados (`(parking_id, measured_at)` único) -- lo que hace este job es la
          - misma agregación de producción de `glue_silver_to_gold.py`, solo que sobre
          + misma agregación de producción de `glue_silver_to_gold.py`, solo que sobre
          - todo el histórico en vez de una única partición horaria, y escribiendo con
          + todo el histórico en vez de una única partición horaria, y escribiendo con
          - `overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
          + `overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
          - antes de lanzarlo, igual que Silver).
          + antes de lanzarlo, igual que Silver).
          - 
          + 
          - Filtra las filas de la partición `fecha=__sin_medida__` (registros sin
          + Filtra las filas de la partición `fecha=__sin_medida__` (registros sin
          - `measured_at`) antes de agregar -- mismo criterio que
          + `measured_at`) antes de agregar -- mismo criterio que
          - `glue_silver_to_gold.py`/`aggregate.aggregate_silver_to_gold`.
          + `glue_silver_to_gold.py`/`aggregate.aggregate_silver_to_gold`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/aparcamientos_por_parking_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/aparcamientos_por_parking_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          +     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          -     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          +     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          -     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          +     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- exactamente lo que necesita una
          +     # el histórico de Silver de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa de Gold. `measured_at` nulo (partición
          +     # reconstrucción completa de Gold. `measured_at` nulo (partición
          -     # `fecha=__sin_medida__`) no produce `fecha`/`hora` parseables y se
          +     # `fecha=__sin_medida__`) no produce `fecha`/`hora` parseables y se
          -     # filtra antes de agregar, igual que el pipeline de producción.
          +     # filtra antes de agregar, igual que el pipeline de producción.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(args["silver_path"])
          +         spark.read.parquet(args["silver_path"])
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -         .filter(F.col("measured_at").isNotNull())
          +         .filter(F.col("measured_at").isNotNull())
          -     )
          +     )
          - 
          + 
          -     # Misma agregación que el pipeline de producción
          +     # Misma agregación que el pipeline de producción
          -     # (`glue_silver_to_gold.py`): una fila por aparcamiento/fecha/hora.
          +     # (`glue_silver_to_gold.py`): una fila por aparcamiento/fecha/hora.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("parking_id", "fecha", "hora")
          +         silver_df.groupBy("parking_id", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("name", ignorenulls=True).alias("name"),
          +             F.first("name", ignorenulls=True).alias("name"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("free_spaces").alias("avg_free_spaces"),
          +             F.avg("free_spaces").alias("avg_free_spaces"),
          -             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          +             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          -             F.first("total_spaces", ignorenulls=True).alias("total_spaces"),
          +             F.first("total_spaces", ignorenulls=True).alias("total_spaces"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          +     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          -     # que `glue_backfill_dedup.py` para Silver).
          +     # que `glue_backfill_dedup.py` para Silver).
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "7f4c18ec21a262d4a6e788348e492c3f" -> "b03433c6e4e72c7e33e557790f1809b2"
      ~ id                            = "glue-scripts/aparcamientos_backfill_dedup_gold-7f4c18ec21a262d4a6e788348e492c3f.py" -> (known after apply)
      ~ key                           = "glue-scripts/aparcamientos_backfill_dedup_gold-7f4c18ec21a262d4a6e788348e492c3f.py" -> "glue-scripts/aparcamientos_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aparcamientos_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_aparcamientos_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_bronze_to_silver-4c9fe8e66729a98c520c97a0aa10f630.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `aparcamientos`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `aparcamientos`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          - añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
          + añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
          - `_with_consistency_column`) y escribir el resultado.
          + `_with_consistency_column`) y escribir el resultado.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/aparcamientos/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/aparcamientos/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - from procesamiento.silver_gold.aparcamientos.ge_suite import run_quality_report
          + from procesamiento.silver_gold.aparcamientos.ge_suite import run_quality_report
          - from procesamiento.silver_gold.aparcamientos.transform import bronze_to_silver
          + from procesamiento.silver_gold.aparcamientos.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("parking_id", StringType(), False),
          +         StructField("parking_id", StringType(), False),
          -         StructField("name", StringType(), True),
          +         StructField("name", StringType(), True),
          -         StructField("address", StringType(), True),
          +         StructField("address", StringType(), True),
          -         # `measured_at` es nullable a propósito (ocupación no compartida en
          +         # `measured_at` es nullable a propósito (ocupación no compartida en
          -         # tiempo real, ver transform.py) -- a diferencia del resto de
          +         # tiempo real, ver transform.py) -- a diferencia del resto de
          -         # datasets del patrón, donde es obligatorio.
          +         # datasets del patrón, donde es obligatorio.
          -         StructField("measured_at", StringType(), True),
          +         StructField("measured_at", StringType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("free_spaces", IntegerType(), True),
          +         StructField("free_spaces", IntegerType(), True),
          -         StructField("total_spaces", IntegerType(), True),
          +         StructField("total_spaces", IntegerType(), True),
          -         StructField("occupancy_ratio", DoubleType(), True),
          +         StructField("occupancy_ratio", DoubleType(), True),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         parking_id=silver_record["parking_id"],
          +         parking_id=silver_record["parking_id"],
          -         name=silver_record["name"],
          +         name=silver_record["name"],
          -         address=silver_record["address"],
          +         address=silver_record["address"],
          -         measured_at=silver_record["measured_at"],
          +         measured_at=silver_record["measured_at"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         free_spaces=silver_record["free_spaces"],
          +         free_spaces=silver_record["free_spaces"],
          -         total_spaces=silver_record["total_spaces"],
          +         total_spaces=silver_record["total_spaces"],
          -         occupancy_ratio=silver_record["occupancy_ratio"],
          +         occupancy_ratio=silver_record["occupancy_ratio"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _with_consistency_column(silver_df):
          + def _with_consistency_column(silver_df):
          -     """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.
          +     """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.
          - 
          + 
          -     GX no tiene una expectation nativa de "columna <= columna" (ver
          +     GX no tiene una expectation nativa de "columna <= columna" (ver
          -     docstring de `ge_suite.py`); se calcula aquí una vez, en Spark, en vez
          +     docstring de `ge_suite.py`); se calcula aquí una vez, en Spark, en vez
          -     de repetir la lógica de `transform.validate_record` como una expresión
          +     de repetir la lógica de `transform.validate_record` como una expresión
          -     de columnas separada. `free_spaces`/`total_spaces` pueden ser nulos (ver
          +     de columnas separada. `free_spaces`/`total_spaces` pueden ser nulos (ver
          -     `transform.py`): `coalesce(..., 0)` hace que un registro con cualquiera
          +     `transform.py`): `coalesce(..., 0)` hace que un registro con cualquiera
          -     de los dos ausentes dé `<= 0` (no viola la regla), igual que hace
          +     de los dos ausentes dé `<= 0` (no viola la regla), igual que hace
          -     `validate_record` (solo compara cuando ambos están presentes).
          +     `validate_record` (solo compara cuando ambos están presentes).
          -     """
          +     """
          -     return silver_df.withColumn(
          +     return silver_df.withColumn(
          -         "free_spaces_over_total_spaces",
          +         "free_spaces_over_total_spaces",
          -         F.coalesce(F.col("free_spaces"), F.lit(0)) - F.coalesce(F.col("total_spaces"), F.lit(1_000_000_000)),
          +         F.coalesce(F.col("free_spaces"), F.lit(0)) - F.coalesce(F.col("total_spaces"), F.lit(1_000_000_000)),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          +     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          -     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          +     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          -     # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
          +     # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
          -     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          +     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          -     # termina sin error pero nunca escribe la partición que espera Gold).
          +     # termina sin error pero nunca escribe la partición que espera Gold).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          +     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          -     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          +     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          -     # completo, que crecia sin limite y disparo el coste real de Glue
          +     # completo, que crecia sin limite y disparo el coste real de Glue
          -     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          +     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          +     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_consistency_column(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_consistency_column(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"aparcamientos_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"aparcamientos_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # `measured_at` puede ser nulo (ver transform.py): esas filas se
          +     # `measured_at` puede ser nulo (ver transform.py): esas filas se
          -     # particionan bajo `fecha=__sin_medida__/hora=__sin_medida__` en vez de
          +     # particionan bajo `fecha=__sin_medida__/hora=__sin_medida__` en vez de
          -     # perderse -- siguen siendo consultables (auditoría de cobertura), pero
          +     # perderse -- siguen siendo consultables (auditoría de cobertura), pero
          -     # `glue_silver_to_gold.py`/`aggregate.py` las excluyen de la agregación
          +     # `glue_silver_to_gold.py`/`aggregate.py` las excluyen de la agregación
          -     # horaria (no hay hora que asignarles, ver docstring de `aggregate.py`).
          +     # horaria (no hay hora que asignarles, ver docstring de `aggregate.py`).
          -     from pyspark.sql.functions import coalesce, date_format, lit, to_timestamp
          +     from pyspark.sql.functions import coalesce, date_format, lit, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha",
          +         "fecha",
          -         coalesce(date_format(to_timestamp("measured_at"), "yyyy-MM-dd"), lit("__sin_medida__")),
          +         coalesce(date_format(to_timestamp("measured_at"), "yyyy-MM-dd"), lit("__sin_medida__")),
          -     ).withColumn(
          +     ).withColumn(
          -         "hora",
          +         "hora",
          -         coalesce(date_format(to_timestamp("measured_at"), "HH"), lit("__sin_medida__")),
          +         coalesce(date_format(to_timestamp("measured_at"), "HH"), lit("__sin_medida__")),
          -     )
          +     )
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "4c9fe8e66729a98c520c97a0aa10f630" -> "90e5ef17131a899ea2f70fcff0bb1962"
      ~ id                            = "glue-scripts/aparcamientos_bronze_to_silver-4c9fe8e66729a98c520c97a0aa10f630.py" -> (known after apply)
      ~ key                           = "glue-scripts/aparcamientos_bronze_to_silver-4c9fe8e66729a98c520c97a0aa10f630.py" -> "glue-scripts/aparcamientos_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_aparcamientos_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_aparcamientos_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aparcamientos_silver_to_gold-b55a4a1d69d1eadf50394eb93b034fd8.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `aparcamientos` (ocupación media por aparcamiento/hora).
          + """Job de AWS Glue: Silver -> Gold del dataset `aparcamientos` (ocupación media por aparcamiento/hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Filtra las filas de la partición `fecha=__sin_medida__` (registros sin
          + Filtra las filas de la partición `fecha=__sin_medida__` (registros sin
          - `measured_at`, ver `glue_bronze_to_silver.py`) antes de agregar -- mismo
          + `measured_at`, ver `glue_bronze_to_silver.py`) antes de agregar -- mismo
          - criterio que `aggregate.aggregate_silver_to_gold` (excluye registros sin
          + criterio que `aggregate.aggregate_silver_to_gold` (excluye registros sin
          - `measured_at` parseable, ver docstring de ese módulo).
          + `measured_at` parseable, ver docstring de ese módulo).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/aparcamientos_por_parking_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/aparcamientos_por_parking_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          +     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          -     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          +     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          +     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha`/`hora` son columnas de partición de Silver (ver
          +     # `fecha`/`hora` son columnas de partición de Silver (ver
          -     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          +     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          -     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          +     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          -     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          +     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          -     # (`__sin_medida__` ya no puede aparecer: la partición leída es siempre
          +     # (`__sin_medida__` ya no puede aparecer: la partición leída es siempre
          -     # una fecha/hora real, ver docstring de glue_bronze_to_silver.py.)
          +     # una fecha/hora real, ver docstring de glue_bronze_to_silver.py.)
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(silver_partition_path)
          +         spark.read.parquet(silver_partition_path)
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          +     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          +     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
          +     # partition pruning si `silver_path` acota un rango de fechas concreto.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("parking_id", "fecha", "hora")
          +         silver_df.groupBy("parking_id", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("name", ignorenulls=True).alias("name"),
          +             F.first("name", ignorenulls=True).alias("name"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("free_spaces").alias("avg_free_spaces"),
          +             F.avg("free_spaces").alias("avg_free_spaces"),
          -             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          +             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          -             F.first("total_spaces", ignorenulls=True).alias("total_spaces"),
          +             F.first("total_spaces", ignorenulls=True).alias("total_spaces"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # aparcamiento y hora, no cada pocos minutos): particionar solo por
          +     # aparcamiento y hora, no cada pocos minutos): particionar solo por
          -     # `date` es suficiente para podar particiones sin generar ficheros
          +     # `date` es suficiente para podar particiones sin generar ficheros
          -     # diminutos.
          +     # diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "b55a4a1d69d1eadf50394eb93b034fd8" -> "ce49527d7c8d3dd98bcb65d2ca1b38ad"
      ~ id                            = "glue-scripts/aparcamientos_silver_to_gold-b55a4a1d69d1eadf50394eb93b034fd8.py" -> (known after apply)
      ~ key                           = "glue-scripts/aparcamientos_silver_to_gold-b55a4a1d69d1eadf50394eb93b034fd8.py" -> "glue-scripts/aparcamientos_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bicimad_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_bicimad_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_backfill_dedup-4a3264e9732202731f31d5974bbe9017.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de `bicimad`.
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de `bicimad`.
          - 
          + 
          - **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 041/047, arreglado en la tarea 072) calcula internamente una única
          + (tarea 041/047, arreglado en la tarea 072) calcula internamente una única
          - hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          + hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          - un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          + un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          - reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          + reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          - TODO el histórico de Bronze de una vez y deduplicar de verdad, tras varios
          + TODO el histórico de Bronze de una vez y deduplicar de verdad, tras varios
          - intentos previos de limpieza manual (borrado + relanzar el job de producción
          + intentos previos de limpieza manual (borrado + relanzar el job de producción
          - o compactar) que dejaron el dato en estados intermedios inconsistentes --
          + o compactar) que dejaron el dato en estados intermedios inconsistentes --
          - duplicados masivos (`n=6752` para una fila) y fechas con huecos. Ver
          + duplicados masivos (`n=6752` para una fila) y fechas con huecos. Ver
          - `doc/073-limpieza-duplicados-bicimad-lanzar.md` para el detalle de esos
          + `doc/073-limpieza-duplicados-bicimad-lanzar.md` para el detalle de esos
          - intentos. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          + intentos. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          - trigger ni schedule.
          + trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive`, ver doc/073): este
          + lanzarlo (borrado manual con `aws s3 rm --recursive`, ver doc/073): este
          - script escribe con `mode("overwrite")`, no `append` -- si el prefijo no
          + script escribe con `mode("overwrite")`, no `append` -- si el prefijo no
          - está vacío de antemano, el resultado seguiría mezclando el dato viejo (ya
          + está vacío de antemano, el resultado seguiría mezclando el dato viejo (ya
          - duplicado) con la reconstrucción.
          + duplicado) con la reconstrucción.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción
          + de Spark/GX que ya usa el pipeline de producción
          - (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          + (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          - `_with_consistency_columns`, `_write_quality_report`.
          + `_with_consistency_columns`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/bicimad/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/bicimad/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.bicimad.ge_suite import run_quality_report
          + from procesamiento.silver_gold.bicimad.ge_suite import run_quality_report
          - from procesamiento.silver_gold.bicimad.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.bicimad.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _with_consistency_columns,
          +     _with_consistency_columns,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          +     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          -     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          +     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          -     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          +     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          -     # con la hora de Madrid real de `measured_at`.
          +     # con la hora de Madrid real de `measured_at`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          +     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa.
          +     # reconstrucción completa.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: intentos previos dejaron registros
          +     # La deduplicación real que faltaba: intentos previos dejaron registros
          -     # repetidos miles de veces para la misma estación/instante. Un par
          +     # repetidos miles de veces para la misma estación/instante. Un par
          -     # (station_id, measured_at) identifica de forma única una medición real
          +     # (station_id, measured_at) identifica de forma única una medición real
          -     # del feed GBFS.
          +     # del feed GBFS.
          -     silver_df = silver_df.dropDuplicates(["station_id", "measured_at"])
          +     silver_df = silver_df.dropDuplicates(["station_id", "measured_at"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_consistency_columns(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_consistency_columns(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"bicimad_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"bicimad_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          +     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          -     # hora de Madrid).
          +     # hora de Madrid).
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          +     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          -     # sustituto de ese borrado previo.
          +     # sustituto de ese borrado previo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "4a3264e9732202731f31d5974bbe9017" -> "ed6e6af42559477339b933051cafe77b"
      ~ id                            = "glue-scripts/bicimad_backfill_dedup-4a3264e9732202731f31d5974bbe9017.py" -> (known after apply)
      ~ key                           = "glue-scripts/bicimad_backfill_dedup-4a3264e9732202731f31d5974bbe9017.py" -> "glue-scripts/bicimad_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bicimad_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_bicimad_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_backfill_dedup_gold-0eb546a683ffaa467741ed1fa47a2abb.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de `bicimad`.
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de `bicimad`.
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 047/072), que solo procesa la partición horaria anterior a la ejecución.
          + tarea 047/072), que solo procesa la partición horaria anterior a la ejecución.
          - Este job existe para recalcular Gold desde cero tras la reconstrucción
          + Este job existe para recalcular Gold desde cero tras la reconstrucción
          - deduplicada de Silver (`glue_backfill_dedup.py`, tarea 073): lee TODO el
          + deduplicada de Silver (`glue_backfill_dedup.py`, tarea 073): lee TODO el
          - histórico de Silver de una vez y agrega, en vez de una sola hora. Se lanza
          + histórico de Silver de una vez y agrega, en vez de una sola hora. Se lanza
          - una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          + una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          - schedule. Ver `doc/074-limpieza-duplicados-bicimad-verificar.md`.
          + schedule. Ver `doc/074-limpieza-duplicados-bicimad-verificar.md`.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que la propia tarea 073/074 ya dejó sin
          + `dropDuplicates`: parte de un Silver que la propia tarea 073/074 ya dejó sin
          - duplicados (`(station_id, measured_at)` único) -- lo que hace este job es la
          + duplicados (`(station_id, measured_at)` único) -- lo que hace este job es la
          - misma agregación de producción de `glue_silver_to_gold.py`, solo que sobre
          + misma agregación de producción de `glue_silver_to_gold.py`, solo que sobre
          - todo el histórico en vez de una única partición horaria, y escribiendo con
          + todo el histórico en vez de una única partición horaria, y escribiendo con
          - `overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
          + `overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
          - antes de lanzarlo, igual que Silver).
          + antes de lanzarlo, igual que Silver).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el resto de jobs de bicimad/trafico (tarea 072): sin
          +     # Mismo motivo que el resto de jobs de bicimad/trafico (tarea 072): sin
          -     # esto, `fecha`/`hora` se recalcularían en UTC (timezone de sesión por
          +     # esto, `fecha`/`hora` se recalcularían en UTC (timezone de sesión por
          -     # defecto de Spark en el runtime de Glue) en vez de Europe/Madrid.
          +     # defecto de Spark en el runtime de Glue) en vez de Europe/Madrid.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- exactamente lo que necesita una
          +     # el histórico de Silver de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa de Gold.
          +     # reconstrucción completa de Gold.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(args["silver_path"])
          +         spark.read.parquet(args["silver_path"])
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # Misma agregación que el pipeline de producción
          +     # Misma agregación que el pipeline de producción
          -     # (`glue_silver_to_gold.py`): una fila por estación/fecha/hora.
          +     # (`glue_silver_to_gold.py`): una fila por estación/fecha/hora.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "fecha", "hora")
          +         silver_df.groupBy("station_id", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("name", ignorenulls=True).alias("name"),
          +             F.first("name", ignorenulls=True).alias("name"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("bikes_available").alias("avg_bikes_available"),
          +             F.avg("bikes_available").alias("avg_bikes_available"),
          -             F.avg("bikes_disabled").alias("avg_bikes_disabled"),
          +             F.avg("bikes_disabled").alias("avg_bikes_disabled"),
          -             F.avg("docks_available").alias("avg_docks_available"),
          +             F.avg("docks_available").alias("avg_docks_available"),
          -             F.avg("docks_disabled").alias("avg_docks_disabled"),
          +             F.avg("docks_disabled").alias("avg_docks_disabled"),
          -             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          +             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          -             F.first("docks_total", ignorenulls=True).alias("docks_total"),
          +             F.first("docks_total", ignorenulls=True).alias("docks_total"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          +     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          -     # que `glue_backfill_dedup.py` para Silver).
          +     # que `glue_backfill_dedup.py` para Silver).
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "0eb546a683ffaa467741ed1fa47a2abb" -> "3cc7762735e125d2ba40c9a759900087"
      ~ id                            = "glue-scripts/bicimad_backfill_dedup_gold-0eb546a683ffaa467741ed1fa47a2abb.py" -> (known after apply)
      ~ key                           = "glue-scripts/bicimad_backfill_dedup_gold-0eb546a683ffaa467741ed1fa47a2abb.py" -> "glue-scripts/bicimad_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bicimad_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_bicimad_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_bronze_to_silver-cd282dfb63915ca6f80b2ccbd8143809.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `bicimad`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `bicimad`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que `trafico/glue_bronze_to_silver.py`
          + sin `terraform apply`, que `trafico/glue_bronze_to_silver.py`
          - (tarea 041)/`transporte_publico_emt/glue_bronze_to_silver.py` (tarea 046),
          + (tarea 041)/`transporte_publico_emt/glue_bronze_to_silver.py` (tarea 046),
          - ver `procesamiento/README.md`): este script asume el entorno de ejecución
          + ver `procesamiento/README.md`): este script asume el entorno de ejecución
          - real de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + real de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          - añadir las columnas auxiliares de consistencia que necesita `ge_suite.py`
          + añadir las columnas auxiliares de consistencia que necesita `ge_suite.py`
          - (ver `_with_consistency_columns`) y escribir el resultado.
          + (ver `_with_consistency_columns`) y escribir el resultado.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/bicimad/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/bicimad/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     BooleanType,
          +     BooleanType,
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - from procesamiento.silver_gold.bicimad.ge_suite import run_quality_report
          + from procesamiento.silver_gold.bicimad.ge_suite import run_quality_report
          - from procesamiento.silver_gold.bicimad.transform import bronze_to_silver
          + from procesamiento.silver_gold.bicimad.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("station_id", StringType(), False),
          +         StructField("station_id", StringType(), False),
          -         StructField("name", StringType(), True),
          +         StructField("name", StringType(), True),
          -         StructField("address", StringType(), True),
          +         StructField("address", StringType(), True),
          -         StructField("measured_at", StringType(), False),
          +         StructField("measured_at", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("bikes_available", IntegerType(), True),
          +         StructField("bikes_available", IntegerType(), True),
          -         StructField("bikes_disabled", IntegerType(), True),
          +         StructField("bikes_disabled", IntegerType(), True),
          -         StructField("docks_available", IntegerType(), True),
          +         StructField("docks_available", IntegerType(), True),
          -         StructField("docks_disabled", IntegerType(), True),
          +         StructField("docks_disabled", IntegerType(), True),
          -         StructField("docks_total", IntegerType(), True),
          +         StructField("docks_total", IntegerType(), True),
          -         StructField("status", StringType(), True),
          +         StructField("status", StringType(), True),
          -         StructField("is_renting", BooleanType(), True),
          +         StructField("is_renting", BooleanType(), True),
          -         StructField("is_returning", BooleanType(), True),
          +         StructField("is_returning", BooleanType(), True),
          -         StructField("occupancy_ratio", DoubleType(), True),
          +         StructField("occupancy_ratio", DoubleType(), True),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         station_id=silver_record["station_id"],
          +         station_id=silver_record["station_id"],
          -         name=silver_record["name"],
          +         name=silver_record["name"],
          -         address=silver_record["address"],
          +         address=silver_record["address"],
          -         measured_at=silver_record["measured_at"],
          +         measured_at=silver_record["measured_at"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         bikes_available=silver_record["bikes_available"],
          +         bikes_available=silver_record["bikes_available"],
          -         bikes_disabled=silver_record["bikes_disabled"],
          +         bikes_disabled=silver_record["bikes_disabled"],
          -         docks_available=silver_record["docks_available"],
          +         docks_available=silver_record["docks_available"],
          -         docks_disabled=silver_record["docks_disabled"],
          +         docks_disabled=silver_record["docks_disabled"],
          -         docks_total=silver_record["docks_total"],
          +         docks_total=silver_record["docks_total"],
          -         status=silver_record["status"],
          +         status=silver_record["status"],
          -         is_renting=silver_record["is_renting"],
          +         is_renting=silver_record["is_renting"],
          -         is_returning=silver_record["is_returning"],
          +         is_returning=silver_record["is_returning"],
          -         occupancy_ratio=silver_record["occupancy_ratio"],
          +         occupancy_ratio=silver_record["occupancy_ratio"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _with_consistency_columns(silver_df):
          + def _with_consistency_columns(silver_df):
          -     """Añade las columnas auxiliares que `ge_suite.py` valida como `<= 0`.
          +     """Añade las columnas auxiliares que `ge_suite.py` valida como `<= 0`.
          - 
          + 
          -     GX no tiene una expectation nativa de "suma de columnas <= otra
          +     GX no tiene una expectation nativa de "suma de columnas <= otra
          -     columna" (ver docstring de `ge_suite.py`); se calcula aquí una vez, en
          +     columna" (ver docstring de `ge_suite.py`); se calcula aquí una vez, en
          -     Spark, en vez de repetir la lógica de `transform.validate_record` como
          +     Spark, en vez de repetir la lógica de `transform.validate_record` como
          -     una expresión de columnas separada.
          +     una expresión de columnas separada.
          -     """
          +     """
          -     return silver_df.withColumn(
          +     return silver_df.withColumn(
          -         "bikes_over_capacity",
          +         "bikes_over_capacity",
          -         (F.coalesce(F.col("bikes_available"), F.lit(0)) + F.coalesce(F.col("bikes_disabled"), F.lit(0)))
          +         (F.coalesce(F.col("bikes_available"), F.lit(0)) + F.coalesce(F.col("bikes_disabled"), F.lit(0)))
          -         - F.col("docks_total"),
          +         - F.col("docks_total"),
          -     ).withColumn(
          +     ).withColumn(
          -         "docks_over_capacity",
          +         "docks_over_capacity",
          -         (F.coalesce(F.col("docks_available"), F.lit(0)) + F.coalesce(F.col("docks_disabled"), F.lit(0)))
          +         (F.coalesce(F.col("docks_available"), F.lit(0)) + F.coalesce(F.col("docks_disabled"), F.lit(0)))
          -         - F.col("docks_total"),
          +         - F.col("docks_total"),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Sin esto, `date_format(to_timestamp(...), "HH")` usa el timezone de
          +     # Sin esto, `date_format(to_timestamp(...), "HH")` usa el timezone de
          -     # sesión por defecto de Spark (UTC en el runtime de Glue) para calcular
          +     # sesión por defecto de Spark (UTC en el runtime de Glue) para calcular
          -     # `hora`, desalineado con `previous_hour()` (Europe/Madrid, igual que la
          +     # `hora`, desalineado con `previous_hour()` (Europe/Madrid, igual que la
          -     # partición real de Bronze) -- una fila medida a las 17:00+02:00 acababa
          +     # partición real de Bronze) -- una fila medida a las 17:00+02:00 acababa
          -     # escrita en `hora=15`, nunca en la partición que este mismo job acaba de
          +     # escrita en `hora=15`, nunca en la partición que este mismo job acaba de
          -     # leer de Bronze (tarea 072, bug encontrado al verificar con una
          +     # leer de Bronze (tarea 072, bug encontrado al verificar con una
          -     # ejecución real).
          +     # ejecución real).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          +     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          -     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          +     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          -     # completo, que crecia sin limite y disparo el coste real de Glue
          +     # completo, que crecia sin limite y disparo el coste real de Glue
          -     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          +     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          +     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_consistency_columns(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_consistency_columns(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"bicimad_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"bicimad_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          -     # para que un consumidor ya familiarizado con Bronze no tenga que
          +     # para que un consumidor ya familiarizado con Bronze no tenga que
          -     # aprender un esquema de partición distinto para Silver.
          +     # aprender un esquema de partición distinto para Silver.
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "cd282dfb63915ca6f80b2ccbd8143809" -> "44a29129cff7226b539da9071dd8f8b7"
      ~ id                            = "glue-scripts/bicimad_bronze_to_silver-cd282dfb63915ca6f80b2ccbd8143809.py" -> (known after apply)
      ~ key                           = "glue-scripts/bicimad_bronze_to_silver-cd282dfb63915ca6f80b2ccbd8143809.py" -> "glue-scripts/bicimad_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bicimad_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_bicimad_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bicimad_silver_to_gold-dd61f49fdef5e187adf9e3b2cb0bcd68.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `bicimad` (disponibilidad media por estación/hora).
          + """Job de AWS Glue: Silver -> Gold del dataset `bicimad` (disponibilidad media por estación/hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que `trafico/glue_silver_to_gold.py`/
          + mismo motivo que `trafico/glue_silver_to_gold.py`/
          - `transporte_publico_emt/glue_silver_to_gold.py`. `aggregate.py` sigue siendo
          + `transporte_publico_emt/glue_silver_to_gold.py`. `aggregate.py` sigue siendo
          - la fuente de verdad **documental y de test** de qué agrega Gold; las
          + la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que en glue_bronze_to_silver.py: sin esto, la `hora`
          +     # Mismo motivo que en glue_bronze_to_silver.py: sin esto, la `hora`
          -     # recalculada aquí desde `measured_at` usaría el timezone de sesión de
          +     # recalculada aquí desde `measured_at` usaría el timezone de sesión de
          -     # Spark (UTC por defecto en Glue), desalineada con `previous_hour()`
          +     # Spark (UTC por defecto en Glue), desalineada con `previous_hour()`
          -     # (Europe/Madrid) y con la partición de Silver que este job intenta leer.
          +     # (Europe/Madrid) y con la partición de Silver que este job intenta leer.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          +     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha`/`hora` son columnas de partición de Silver (ver
          +     # `fecha`/`hora` son columnas de partición de Silver (ver
          -     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          +     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          -     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          +     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          -     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          +     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(silver_partition_path)
          +         spark.read.parquet(silver_partition_path)
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          +     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          +     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
          +     # partition pruning si `silver_path` acota un rango de fechas concreto.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "fecha", "hora")
          +         silver_df.groupBy("station_id", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("name", ignorenulls=True).alias("name"),
          +             F.first("name", ignorenulls=True).alias("name"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("bikes_available").alias("avg_bikes_available"),
          +             F.avg("bikes_available").alias("avg_bikes_available"),
          -             F.avg("bikes_disabled").alias("avg_bikes_disabled"),
          +             F.avg("bikes_disabled").alias("avg_bikes_disabled"),
          -             F.avg("docks_available").alias("avg_docks_available"),
          +             F.avg("docks_available").alias("avg_docks_available"),
          -             F.avg("docks_disabled").alias("avg_docks_disabled"),
          +             F.avg("docks_disabled").alias("avg_docks_disabled"),
          -             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          +             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          -             F.first("docks_total", ignorenulls=True).alias("docks_total"),
          +             F.first("docks_total", ignorenulls=True).alias("docks_total"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # estación y hora, no cada pocos minutos): particionar solo por `date`
          +     # estación y hora, no cada pocos minutos): particionar solo por `date`
          -     # es suficiente para podar particiones sin generar ficheros diminutos.
          +     # es suficiente para podar particiones sin generar ficheros diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "dd61f49fdef5e187adf9e3b2cb0bcd68" -> "c843909cc91d34dcfdcf321695e074a2"
      ~ id                            = "glue-scripts/bicimad_silver_to_gold-dd61f49fdef5e187adf9e3b2cb0bcd68.py" -> (known after apply)
      ~ key                           = "glue-scripts/bicimad_silver_to_gold-dd61f49fdef5e187adf9e3b2cb0bcd68.py" -> "glue-scripts/bicimad_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bluesky_menciones_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_bluesky_menciones_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_backfill_dedup-d20c9b44b3da1387c2a6a1d6fd6a5090.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `bluesky_menciones` (tarea 077, mismo patrón que
          + `bluesky_menciones` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          - 
          + 
          - **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 057, arreglado en la tarea 076) lee solo la partición Bronze del día
          + (tarea 057, arreglado en la tarea 076) lee solo la partición Bronze del día
          - de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          + de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          - histórico", así que no sirve para reconstruir Silver desde cero. Este script
          + histórico", así que no sirve para reconstruir Silver desde cero. Este script
          - existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          + existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          - deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          + deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          - hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          + hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          - todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          + todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          - Athena real (`doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`):
          + Athena real (`doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`):
          - `n=19` para el mismo post. Se lanza una sola vez a mano (`aws glue
          + `n=19` para el mismo post. Se lanza una sola vez a mano (`aws glue
          - start-job-run`), nunca vía trigger ni schedule.
          + start-job-run`), nunca vía trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          + lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          - 
          + 
          - `post_hash` es la clave natural del dataset (SHA-256 truncado del texto, ver
          + `post_hash` es la clave natural del dataset (SHA-256 truncado del texto, ver
          - docstring de `transform.py`, "añadió `post_hash`... precisamente como" clave
          + docstring de `transform.py`, "añadió `post_hash`... precisamente como" clave
          - de deduplicación) -- `dropDuplicates(["post_hash"])` es la misma
          + de deduplicación) -- `dropDuplicates(["post_hash"])` es la misma
          - deduplicación de reingestas que ya hace `aggregate.py` en tiempo de
          + deduplicación de reingestas que ya hace `aggregate.py` en tiempo de
          - agregación (contando `post_hash` distintos), aplicada aquí a nivel de Silver
          + agregación (contando `post_hash` distintos), aplicada aquí a nivel de Silver
          - para que no siga creciendo sin límite. A diferencia de la deduplicación
          + para que no siga creciendo sin límite. A diferencia de la deduplicación
          - dentro de partición que ya hace `transform.bronze_to_silver` (ver docstring
          + dentro de partición que ya hace `transform.bronze_to_silver` (ver docstring
          - de `glue_bronze_to_silver.py`), este `dropDuplicates` opera sobre el
          + de `glue_bronze_to_silver.py`), este `dropDuplicates` opera sobre el
          - DataFrame completo, así que también colapsa duplicados que cayeron en
          + DataFrame completo, así que también colapsa duplicados que cayeron en
          - particiones de Spark distintas -- justo lo que necesita una reconstrucción
          + particiones de Spark distintas -- justo lo que necesita una reconstrucción
          - completa.
          + completa.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          + de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          - `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          + `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/bluesky_menciones/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/bluesky_menciones/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.bluesky_menciones.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.bluesky_menciones.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - from procesamiento.silver_gold.bluesky_menciones.ge_suite import run_quality_report
          + from procesamiento.silver_gold.bluesky_menciones.ge_suite import run_quality_report
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez.
          +     # el histórico de Bronze de una vez.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba, a través de todo el DataFrame (no
          +     # La deduplicación real que faltaba, a través de todo el DataFrame (no
          -     # solo dentro de partición, ver docstring del módulo). `post_hash` es la
          +     # solo dentro de partición, ver docstring del módulo). `post_hash` es la
          -     # clave natural del dataset.
          +     # clave natural del dataset.
          -     silver_df = silver_df.dropDuplicates(["post_hash"])
          +     silver_df = silver_df.dropDuplicates(["post_hash"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"bluesky_menciones_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"bluesky_menciones_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=
          +     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=
          -     # de `created_at`).
          +     # de `created_at`).
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("created_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("created_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("created_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("created_at"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo).
          +     # del módulo).
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "d20c9b44b3da1387c2a6a1d6fd6a5090" -> "2efdec7fc5aa3a4ed77dbee6c1a5e2d4"
      ~ id                            = "glue-scripts/bluesky_menciones_backfill_dedup-d20c9b44b3da1387c2a6a1d6fd6a5090.py" -> (known after apply)
      ~ key                           = "glue-scripts/bluesky_menciones_backfill_dedup-d20c9b44b3da1387c2a6a1d6fd6a5090.py" -> "glue-scripts/bluesky_menciones_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bluesky_menciones_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_bluesky_menciones_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_backfill_dedup_gold-9cfe45ea7aef30a0f20892f1bdaccb0a.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `bluesky_menciones` (tarea 077, mismo patrón que
          + `bluesky_menciones` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 057/076), que solo procesa la partición `fecha=hoy` de Silver. Este
          + tarea 057/076), que solo procesa la partición `fecha=hoy` de Silver. Este
          - job existe para recalcular Gold desde cero tras la reconstrucción
          + job existe para recalcular Gold desde cero tras la reconstrucción
          - deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          + deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          - histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
          + histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
          - Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          + Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
          - schedule.
          + schedule.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que el propio backfill de Silver ya dejó
          + `dropDuplicates`: parte de un Silver que el propio backfill de Silver ya dejó
          - sin duplicados (`post_hash` único) -- lo que hace este job es la misma
          + sin duplicados (`post_hash` único) -- lo que hace este job es la misma
          - agregación de producción de `glue_silver_to_gold.py`, solo que sobre todo el
          + agregación de producción de `glue_silver_to_gold.py`, solo que sobre todo el
          - histórico en vez de una única partición diaria, y escribiendo con
          + histórico en vez de una única partición diaria, y escribiendo con
          - `overwrite` en vez de `append`.
          + `overwrite` en vez de `append`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/bluesky_menciones_por_termino_modo_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/bluesky_menciones_por_termino_modo_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     silver_df = spark.read.parquet(args["silver_path"])
          +     silver_df = spark.read.parquet(args["silver_path"])
          - 
          + 
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("mode", "match_term", "fecha", "hora")
          +         silver_df.groupBy("mode", "match_term", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.countDistinct("post_hash").alias("mentions_count"),
          +             F.countDistinct("post_hash").alias("mentions_count"),
          -             F.sort_array(F.collect_set("lang")).alias("langs"),
          +             F.sort_array(F.collect_set("lang")).alias("langs"),
          -             F.coalesce(F.sum("like_count"), F.lit(0)).alias("total_like_count"),
          +             F.coalesce(F.sum("like_count"), F.lit(0)).alias("total_like_count"),
          -             F.coalesce(F.sum("repost_count"), F.lit(0)).alias("total_repost_count"),
          +             F.coalesce(F.sum("repost_count"), F.lit(0)).alias("total_repost_count"),
          -             F.coalesce(F.sum("reply_count"), F.lit(0)).alias("total_reply_count"),
          +             F.coalesce(F.sum("reply_count"), F.lit(0)).alias("total_reply_count"),
          -             F.coalesce(F.sum("quote_count"), F.lit(0)).alias("total_quote_count"),
          +             F.coalesce(F.sum("quote_count"), F.lit(0)).alias("total_quote_count"),
          -             F.min("created_at").alias("first_created_at"),
          +             F.min("created_at").alias("first_created_at"),
          -             F.max("created_at").alias("last_created_at"),
          +             F.max("created_at").alias("last_created_at"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo.
          +     # prefijo de destino debe estar vacío antes de lanzarlo.
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "9cfe45ea7aef30a0f20892f1bdaccb0a" -> "eaac70080a579db34ec3c54244f4e426"
      ~ id                            = "glue-scripts/bluesky_menciones_backfill_dedup_gold-9cfe45ea7aef30a0f20892f1bdaccb0a.py" -> (known after apply)
      ~ key                           = "glue-scripts/bluesky_menciones_backfill_dedup_gold-9cfe45ea7aef30a0f20892f1bdaccb0a.py" -> "glue-scripts/bluesky_menciones_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bluesky_menciones_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_bluesky_menciones_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_bronze_to_silver-e2d8897c5d4760401b16893568ac32ee.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `bluesky_menciones`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `bluesky_menciones`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad, deduplicación de duplicados exactos dentro del lote) tal cual --
          + de calidad, deduplicación de duplicados exactos dentro del lote) tal cual --
          - este módulo solo es el "pegamento" de Spark/Glue: leer Bronze, aplicar
          + este módulo solo es el "pegamento" de Spark/Glue: leer Bronze, aplicar
          - `bronze_to_silver` fila a fila vía `rdd.mapPartitions` y escribir el
          + `bronze_to_silver` fila a fila vía `rdd.mapPartitions` y escribir el
          - resultado. La deduplicación de `transform.bronze_to_silver` opera dentro de
          + resultado. La deduplicación de `transform.bronze_to_silver` opera dentro de
          - cada partición de Spark (ver `_process_partition`), no a través de todo el
          + cada partición de Spark (ver `_process_partition`), no a través de todo el
          - DataFrame -- un post repetido entre términos de búsqueda solapados de
          + DataFrame -- un post repetido entre términos de búsqueda solapados de
          - `search_district_sweep` normalmente cae en el mismo lote/objeto Bronze
          + `search_district_sweep` normalmente cae en el mismo lote/objeto Bronze
          - (mismo `write_batch`, ver `ingesta/capturas/bronze.py`), y por tanto muy
          + (mismo `write_batch`, ver `ingesta/capturas/bronze.py`), y por tanto muy
          - probablemente en la misma partición de Spark al leerlo con
          + probablemente en la misma partición de Spark al leerlo con
          - `multiLine=True`; un duplicado que caiga en particiones distintas no se
          + `multiLine=True`; un duplicado que caiga en particiones distintas no se
          - detecta aquí y sobrevive como una fila Silver adicional -- exactamente el
          + detecta aquí y sobrevive como una fila Silver adicional -- exactamente el
          - mismo caso que una reingesta entre ejecuciones distintas, que
          + mismo caso que una reingesta entre ejecuciones distintas, que
          - `aggregate.py` ya resuelve contando `post_hash` distintos
          + `aggregate.py` ya resuelve contando `post_hash` distintos
          - (`mentions_count`). Deduplicar de verdad a través de todo el DataFrame
          + (`mentions_count`). Deduplicar de verdad a través de todo el DataFrame
          - haría falta un `dropDuplicates(["post_hash"])` tras `mapPartitions`, pero
          + haría falta un `dropDuplicates(["post_hash"])` tras `mapPartitions`, pero
          - eso ya no sería reutilizar `transform.bronze_to_silver` tal cual -- se ha
          + eso ya no sería reutilizar `transform.bronze_to_silver` tal cual -- se ha
          - preferido mantener la lógica de negocio en un único sitio probado por
          + preferido mantener la lógica de negocio en un único sitio probado por
          - `unittest`.
          + `unittest`.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          + `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/bluesky_menciones/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/bluesky_menciones/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - from pyspark.sql.types import IntegerType, StringType, StructField, StructType
          + from pyspark.sql.types import IntegerType, StringType, StructField, StructType
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.bluesky_menciones.ge_suite import run_quality_report
          + from procesamiento.silver_gold.bluesky_menciones.ge_suite import run_quality_report
          - from procesamiento.silver_gold.bluesky_menciones.transform import bronze_to_silver
          + from procesamiento.silver_gold.bluesky_menciones.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("mode", StringType(), False),
          +         StructField("mode", StringType(), False),
          -         StructField("match_term", StringType(), False),
          +         StructField("match_term", StringType(), False),
          -         StructField("post_hash", StringType(), False),
          +         StructField("post_hash", StringType(), False),
          -         StructField("text", StringType(), False),
          +         StructField("text", StringType(), False),
          -         StructField("lang", StringType(), True),
          +         StructField("lang", StringType(), True),
          -         StructField("created_at", StringType(), False),
          +         StructField("created_at", StringType(), False),
          -         StructField("indexed_at", StringType(), True),
          +         StructField("indexed_at", StringType(), True),
          -         StructField("like_count", IntegerType(), True),
          +         StructField("like_count", IntegerType(), True),
          -         StructField("repost_count", IntegerType(), True),
          +         StructField("repost_count", IntegerType(), True),
          -         StructField("reply_count", IntegerType(), True),
          +         StructField("reply_count", IntegerType(), True),
          -         StructField("quote_count", IntegerType(), True),
          +         StructField("quote_count", IntegerType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         mode=silver_record["mode"],
          +         mode=silver_record["mode"],
          -         match_term=silver_record["match_term"],
          +         match_term=silver_record["match_term"],
          -         post_hash=silver_record["post_hash"],
          +         post_hash=silver_record["post_hash"],
          -         text=silver_record["text"],
          +         text=silver_record["text"],
          -         lang=silver_record["lang"],
          +         lang=silver_record["lang"],
          -         created_at=silver_record["created_at"],
          +         created_at=silver_record["created_at"],
          -         indexed_at=silver_record["indexed_at"],
          +         indexed_at=silver_record["indexed_at"],
          -         like_count=silver_record["like_count"],
          +         like_count=silver_record["like_count"],
          -         repost_count=silver_record["repost_count"],
          +         repost_count=silver_record["repost_count"],
          -         reply_count=silver_record["reply_count"],
          +         reply_count=silver_record["reply_count"],
          -         quote_count=silver_record["quote_count"],
          +         quote_count=silver_record["quote_count"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor).
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor).
          - 
          + 
          -     La deduplicación de duplicados exactos de `bronze_to_silver` opera solo
          +     La deduplicación de duplicados exactos de `bronze_to_silver` opera solo
          -     dentro de esta partición -- ver docstring del módulo.
          +     dentro de esta partición -- ver docstring del módulo.
          -     """
          +     """
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"bluesky_menciones_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"bluesky_menciones_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Particiona por la fecha/hora de la publicación (`created_at`), no por
          +     # Particiona por la fecha/hora de la publicación (`created_at`), no por
          -     # `ingested_at` -- misma razón que `aggregate.py`: la pregunta natural
          +     # `ingested_at` -- misma razón que `aggregate.py`: la pregunta natural
          -     # de este dataset es "cuándo se habló de este lugar", no "cuándo corrió
          +     # de este dataset es "cuándo se habló de este lugar", no "cuándo corrió
          -     # el barrido" (ver docstring de aggregate.py). `to_timestamp` sin
          +     # el barrido" (ver docstring de aggregate.py). `to_timestamp` sin
          -     # formato explícito acepta tanto el sufijo `Z` de Bluesky como el offset
          +     # formato explícito acepta tanto el sufijo `Z` de Bluesky como el offset
          -     # `+02:00`/`+01:00` de `ingested_at` (parser ISO-8601 por defecto de
          +     # `+02:00`/`+01:00` de `ingested_at` (parser ISO-8601 por defecto de
          -     # Spark 3.3/Glue 4.0) -- no verificado por ejecución real en esta EC2,
          +     # Spark 3.3/Glue 4.0) -- no verificado por ejecución real en esta EC2,
          -     # ver "Qué no se ha podido ejecutar" en procesamiento/README.md.
          +     # ver "Qué no se ha podido ejecutar" en procesamiento/README.md.
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("created_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("created_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("created_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("created_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "e2d8897c5d4760401b16893568ac32ee" -> "3911e443483f4b8bccf853ec600d43b6"
      ~ id                            = "glue-scripts/bluesky_menciones_bronze_to_silver-e2d8897c5d4760401b16893568ac32ee.py" -> (known after apply)
      ~ key                           = "glue-scripts/bluesky_menciones_bronze_to_silver-e2d8897c5d4760401b16893568ac32ee.py" -> "glue-scripts/bluesky_menciones_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bluesky_menciones_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_bluesky_menciones_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_silver_to_gold-8c43f4a9df541e2eea43a8456514dc10.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `bluesky_menciones` (número de
          + """Job de AWS Glue: Silver -> Gold del dataset `bluesky_menciones` (número de
          - menciones por término de búsqueda, modo, día y hora).
          + menciones por término de búsqueda, modo, día y hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/bluesky_menciones_por_termino_modo_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/bluesky_menciones_por_termino_modo_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          + from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          -     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          +     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          -     # desalineado con `today()` (Python, Europe/Madrid).
          +     # desalineado con `today()` (Python, Europe/Madrid).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          +     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          -     # nunca la raiz completa del dataset -- mismo motivo de coste que
          +     # nunca la raiz completa del dataset -- mismo motivo de coste que
          -     # Bronze->Silver (tarea 072). `fecha` en Silver es la de publicacion del
          +     # Bronze->Silver (tarea 072). `fecha` en Silver es la de publicacion del
          -     # post (`created_at`, ver glue_bronze_to_silver.py), que coincide con el
          +     # post (`created_at`, ver glue_bronze_to_silver.py), que coincide con el
          -     # dia de ingestion para este dataset (barrido casi en tiempo real, sin
          +     # dia de ingestion para este dataset (barrido casi en tiempo real, sin
          -     # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
          +     # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
          -     # vez, el dia en que ese dia es "hoy".
          +     # vez, el dia en que ese dia es "hoy".
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          +     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `hora` sí se infiere como columna de partición física (nivel inmediato
          +     # `hora` sí se infiere como columna de partición física (nivel inmediato
          -     # bajo la ruta leída), pero `fecha` no -- al acotar la lectura a
          +     # bajo la ruta leída), pero `fecha` no -- al acotar la lectura a
          -     # `fecha=<fecha>/` (tarea 076) esa partición queda fija en la ruta y
          +     # `fecha=<fecha>/` (tarea 076) esa partición queda fija en la ruta y
          -     # Spark deja de exponerla como columna. Se añade de vuelta con el valor
          +     # Spark deja de exponerla como columna. Se añade de vuelta con el valor
          -     # ya conocido -- bug real (`AnalysisException: Column 'fecha' does not
          +     # ya conocido -- bug real (`AnalysisException: Column 'fecha' does not
          -     # exist`) que ya había fallado en producción los días 2026-08-23 y
          +     # exist`) que ya había fallado en producción los días 2026-08-23 y
          -     # 2026-08-24 (ver historial real de
          +     # 2026-08-24 (ver historial real de
          -     # `madrono-tfm-dev-bluesky-menciones-silver-to-gold`; los días en que el
          +     # `madrono-tfm-dev-bluesky-menciones-silver-to-gold`; los días en que el
          -     # job "tuvo éxito" fue porque `partition_has_objects` cortó antes de
          +     # job "tuvo éxito" fue porque `partition_has_objects` cortó antes de
          -     # llegar aquí, no porque el `groupBy` funcionara), encontrado y
          +     # llegar aquí, no porque el `groupBy` funcionara), encontrado y
          -     # corregido en la tarea 090 junto con el mismo bug en
          +     # corregido en la tarea 090 junto con el mismo bug en
          -     # `cartelera_cines_estrenos`/`agenda_eventos`/`aforos_peatones_bicicletas`.
          +     # `cartelera_cines_estrenos`/`agenda_eventos`/`aforos_peatones_bicicletas`.
          -     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          - 
          + 
          -     # `mode`/`match_term` entran en la clave junto a `fecha`/`hora` -- mismo
          +     # `mode`/`match_term` entran en la clave junto a `fecha`/`hora` -- mismo
          -     # criterio que `aggregate.py`.
          +     # criterio que `aggregate.py`.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("mode", "match_term", "fecha", "hora")
          +         silver_df.groupBy("mode", "match_term", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.countDistinct("post_hash").alias("mentions_count"),
          +             F.countDistinct("post_hash").alias("mentions_count"),
          -             F.sort_array(F.collect_set("lang")).alias("langs"),
          +             F.sort_array(F.collect_set("lang")).alias("langs"),
          -             F.coalesce(F.sum("like_count"), F.lit(0)).alias("total_like_count"),
          +             F.coalesce(F.sum("like_count"), F.lit(0)).alias("total_like_count"),
          -             F.coalesce(F.sum("repost_count"), F.lit(0)).alias("total_repost_count"),
          +             F.coalesce(F.sum("repost_count"), F.lit(0)).alias("total_repost_count"),
          -             F.coalesce(F.sum("reply_count"), F.lit(0)).alias("total_reply_count"),
          +             F.coalesce(F.sum("reply_count"), F.lit(0)).alias("total_reply_count"),
          -             F.coalesce(F.sum("quote_count"), F.lit(0)).alias("total_quote_count"),
          +             F.coalesce(F.sum("quote_count"), F.lit(0)).alias("total_quote_count"),
          -             F.min("created_at").alias("first_created_at"),
          +             F.min("created_at").alias("first_created_at"),
          -             F.max("created_at").alias("last_created_at"),
          +             F.max("created_at").alias("last_created_at"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # término/modo/hora, no una por post): particionar solo por `date` es
          +     # término/modo/hora, no una por post): particionar solo por `date` es
          -     # suficiente para podar particiones sin generar ficheros diminutos --
          +     # suficiente para podar particiones sin generar ficheros diminutos --
          -     # mismo criterio que el resto del patrón (trafico, cartelera_cines_estrenos...).
          +     # mismo criterio que el resto del patrón (trafico, cartelera_cines_estrenos...).
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "8c43f4a9df541e2eea43a8456514dc10" -> "261976e04868c0265f79a78dacffb6ed"
      ~ id                            = "glue-scripts/bluesky_menciones_silver_to_gold-8c43f4a9df541e2eea43a8456514dc10.py" -> (known after apply)
      ~ key                           = "glue-scripts/bluesky_menciones_silver_to_gold-8c43f4a9df541e2eea43a8456514dc10.py" -> "glue-scripts/bluesky_menciones_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/trafico_bronze_to_silver-ae01fdf48416d1e59a499e725af5eeb4.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `trafico`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `trafico`.
          - 
          + 
          - **No ejecutado en esta tarea** (piloto de solo código/infraestructura, sin
          + **No ejecutado en esta tarea** (piloto de solo código/infraestructura, sin
          - `terraform apply`, ver `procesamiento/README.md`): este script asume el
          + `terraform apply`, ver `procesamiento/README.md`): este script asume el
          - entorno de ejecución real de un Glue Job Spark (runtime `glueetl`, Python
          + entorno de ejecución real de un Glue Job Spark (runtime `glueetl`, Python
          - 3.11 a fecha de esta tarea, con `pyspark`/`awsglue`/`great_expectations`
          + 3.11 a fecha de esta tarea, con `pyspark`/`awsglue`/`great_expectations`
          - disponibles — las dos primeras las provee el propio runtime de Glue, la
          + disponibles — las dos primeras las provee el propio runtime de Glue, la
          - tercera se instala vía `--additional-python-modules`, ver `glue.tf`). No se
          + tercera se instala vía `--additional-python-modules`, ver `glue.tf`). No se
          - ha podido importar ni ejecutar aquí (esta EC2 de desarrollo no tiene Spark
          + ha podido importar ni ejecutar aquí (esta EC2 de desarrollo no tiene Spark
          - instalado, ver restricciones de la tarea sobre disco compartido limitado).
          + instalado, ver restricciones de la tarea sobre disco compartido limitado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (reproyección,
          + Reutiliza toda la lógica de negocio de `transform.py` (reproyección,
          - normalización, puerta de calidad) tal cual — este módulo solo es el
          + normalización, puerta de calidad) tal cual — este módulo solo es el
          - "pegamento" de Spark/Glue: leer Bronze, aplicar `bronze_to_silver` fila a
          + "pegamento" de Spark/Glue: leer Bronze, aplicar `bronze_to_silver` fila a
          - fila vía `rdd.mapPartitions` (en vez de un DataFrame UDF: `transform.py`
          + fila vía `rdd.mapPartitions` (en vez de un DataFrame UDF: `transform.py`
          - opera sobre `dict` anidados de Python puro, y mapear sobre particiones
          + opera sobre `dict` anidados de Python puro, y mapear sobre particiones
          - evita tener que expresar la misma lógica de nuevo con expresiones nativas
          + evita tener que expresar la misma lógica de nuevo con expresiones nativas
          - de columnas de Spark, manteniendo una única fuente de verdad de las
          + de columnas de Spark, manteniendo una única fuente de verdad de las
          - reglas), y escribir el resultado. Ver `ge_suite.py` para la validación de
          + reglas), y escribir el resultado. Ver `ge_suite.py` para la validación de
          - Great Expectations que corre inmediatamente después, en el mismo
          + Great Expectations que corre inmediatamente después, en el mismo
          - `SparkSession`.
          + `SparkSession`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/trafico/`. Se lee de forma
          +   `s3://madrono-tfm-dev-bronze-222234418587/trafico/`. Se lee de forma
          -   recursiva (todas las particiones `fecha=/hora=` bajo ese prefijo);
          +   recursiva (todas las particiones `fecha=/hora=` bajo ese prefijo);
          -   acotar el rango de fechas a procesar es responsabilidad de quien invoque
          +   acotar el rango de fechas a procesar es responsabilidad de quien invoque
          -   el job (p.ej. pasando un prefijo más específico
          +   el job (p.ej. pasando un prefijo más específico
          -   `.../trafico/fecha=2026-08-15/`), no de este script.
          +   `.../trafico/fecha=2026-08-15/`), no de este script.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/trafico/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/trafico/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     BooleanType,
          +     BooleanType,
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - from procesamiento.silver_gold.trafico.ge_suite import run_quality_report
          + from procesamiento.silver_gold.trafico.ge_suite import run_quality_report
          - from procesamiento.silver_gold.trafico.transform import bronze_to_silver
          + from procesamiento.silver_gold.trafico.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("x", DoubleType(), True),
          +         StructField("x", DoubleType(), True),
          -         StructField("y", DoubleType(), True),
          +         StructField("y", DoubleType(), True),
          -         StructField("srid_source", StringType(), True),
          +         StructField("srid_source", StringType(), True),
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid_target", StringType(), True),
          +         StructField("srid_target", StringType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("point_id", StringType(), False),
          +         StructField("point_id", StringType(), False),
          -         StructField("subarea", StringType(), True),
          +         StructField("subarea", StringType(), True),
          -         StructField("description", StringType(), True),
          +         StructField("description", StringType(), True),
          -         StructField("access_code", StringType(), True),
          +         StructField("access_code", StringType(), True),
          -         StructField("measured_at", StringType(), False),
          +         StructField("measured_at", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -         StructField("intensity_vph", IntegerType(), True),
          +         StructField("intensity_vph", IntegerType(), True),
          -         StructField("occupancy_pct", IntegerType(), True),
          +         StructField("occupancy_pct", IntegerType(), True),
          -         StructField("load_pct", IntegerType(), True),
          +         StructField("load_pct", IntegerType(), True),
          -         StructField("service_level", IntegerType(), True),
          +         StructField("service_level", IntegerType(), True),
          -         StructField("saturation_intensity_vph", IntegerType(), True),
          +         StructField("saturation_intensity_vph", IntegerType(), True),
          -         StructField("occupancy_ratio", DoubleType(), True),
          +         StructField("occupancy_ratio", DoubleType(), True),
          -         StructField("load_ratio", DoubleType(), True),
          +         StructField("load_ratio", DoubleType(), True),
          -         StructField("intensity_ratio", DoubleType(), True),
          +         StructField("intensity_ratio", DoubleType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         point_id=silver_record["point_id"],
          +         point_id=silver_record["point_id"],
          -         subarea=silver_record["subarea"],
          +         subarea=silver_record["subarea"],
          -         description=silver_record["description"],
          +         description=silver_record["description"],
          -         access_code=silver_record["access_code"],
          +         access_code=silver_record["access_code"],
          -         measured_at=silver_record["measured_at"],
          +         measured_at=silver_record["measured_at"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         location=Row(
          +         location=Row(
          -             x=location["x"],
          +             x=location["x"],
          -             y=location["y"],
          +             y=location["y"],
          -             srid_source=location["srid_source"],
          +             srid_source=location["srid_source"],
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid_target=location["srid_target"],
          +             srid_target=location["srid_target"],
          -         ),
          +         ),
          -         intensity_vph=silver_record["intensity_vph"],
          +         intensity_vph=silver_record["intensity_vph"],
          -         occupancy_pct=silver_record["occupancy_pct"],
          +         occupancy_pct=silver_record["occupancy_pct"],
          -         load_pct=silver_record["load_pct"],
          +         load_pct=silver_record["load_pct"],
          -         service_level=silver_record["service_level"],
          +         service_level=silver_record["service_level"],
          -         saturation_intensity_vph=silver_record["saturation_intensity_vph"],
          +         saturation_intensity_vph=silver_record["saturation_intensity_vph"],
          -         occupancy_ratio=silver_record["occupancy_ratio"],
          +         occupancy_ratio=silver_record["occupancy_ratio"],
          -         load_ratio=silver_record["load_ratio"],
          +         load_ratio=silver_record["load_ratio"],
          -         intensity_ratio=silver_record["intensity_ratio"],
          +         intensity_ratio=silver_record["intensity_ratio"],
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Sin esto, `date_format(to_timestamp(...), "HH")` usa el timezone de
          +     # Sin esto, `date_format(to_timestamp(...), "HH")` usa el timezone de
          -     # sesión por defecto de Spark (UTC en el runtime de Glue) para calcular
          +     # sesión por defecto de Spark (UTC en el runtime de Glue) para calcular
          -     # `hora`, desalineado con `previous_hour()` (Europe/Madrid, igual que la
          +     # `hora`, desalineado con `previous_hour()` (Europe/Madrid, igual que la
          -     # partición real de Bronze) -- una fila medida a las 17:00+02:00 acababa
          +     # partición real de Bronze) -- una fila medida a las 17:00+02:00 acababa
          -     # escrita en `hora=15`, nunca en la partición que este mismo job acaba de
          +     # escrita en `hora=15`, nunca en la partición que este mismo job acaba de
          -     # leer de Bronze (tarea 072, bug encontrado al verificar con una
          +     # leer de Bronze (tarea 072, bug encontrado al verificar con una
          -     # ejecución real).
          +     # ejecución real).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la partición Bronze de la hora
          +     # Lectura incremental (tarea 072): solo la partición Bronze de la hora
          -     # completa anterior a esta ejecución -- nunca la raíz del dataset
          +     # completa anterior a esta ejecución -- nunca la raíz del dataset
          -     # completo, que crecía sin límite y disparó el coste real de Glue
          +     # completo, que crecía sin límite y disparó el coste real de Glue
          -     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          +     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          +     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"trafico_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"trafico_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          -     # para que un consumidor ya familiarizado con Bronze no tenga que
          +     # para que un consumidor ya familiarizado con Bronze no tenga que
          -     # aprender un esquema de partición distinto para Silver.
          +     # aprender un esquema de partición distinto para Silver.
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "ae01fdf48416d1e59a499e725af5eeb4" -> "168f6d4b74abbb184207e7548dc13bdb"
      ~ id                            = "glue-scripts/trafico_bronze_to_silver-ae01fdf48416d1e59a499e725af5eeb4.py" -> (known after apply)
      ~ key                           = "glue-scripts/trafico_bronze_to_silver-ae01fdf48416d1e59a499e725af5eeb4.py" -> "glue-scripts/trafico_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_calidad_aire_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_calidad_aire_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_backfill_dedup-6d44949bc6077a4ec6bba66eff619e0e.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `calidad_aire`.
          + `calidad_aire`.
          - 
          + 
          - **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 049, arreglado en la tarea 072) calcula internamente una única
          + (tarea 049, arreglado en la tarea 072) calcula internamente una única
          - hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          + hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          - un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          + un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          - reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          + reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          - TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          + TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          - confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          + confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          - que cada ejecución histórica del job de producción (antes del arreglo de la
          + que cada ejecución histórica del job de producción (antes del arreglo de la
          - tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          + tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          - deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          + deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          - verificado con una consulta Athena real sobre `(station_id, magnitude_code,
          + verificado con una consulta Athena real sobre `(station_id, magnitude_code,
          - measured_at)` antes de escribir este script. Se lanza una sola vez a mano
          + measured_at)` antes de escribir este script. Se lanza una sola vez a mano
          - (`aws glue start-job-run`), nunca vía trigger ni schedule.
          + (`aws glue start-job-run`), nunca vía trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          + lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          - tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          + tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          - sobrescribir un prefijo con miles de objetos preexistentes): este script
          + sobrescribir un prefijo con miles de objetos preexistentes): este script
          - escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          + escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          - de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          + de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          - con la reconstrucción.
          + con la reconstrucción.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción
          + de Spark/GX que ya usa el pipeline de producción
          - (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          + (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          - `_with_plausible_max_column`, `_write_quality_report`.
          + `_with_plausible_max_column`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/calidad_aire/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/calidad_aire/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.calidad_aire.ge_suite import run_quality_report
          + from procesamiento.silver_gold.calidad_aire.ge_suite import run_quality_report
          - from procesamiento.silver_gold.calidad_aire.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.calidad_aire.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _with_plausible_max_column,
          +     _with_plausible_max_column,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          +     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          -     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          +     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          -     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          +     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          -     # con la hora de Madrid real de `measured_at`.
          +     # con la hora de Madrid real de `measured_at`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          +     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa.
          +     # reconstrucción completa.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          +     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          -     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          +     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          -     # registro repetido cientos/miles de veces. Un trío (station_id,
          +     # registro repetido cientos/miles de veces. Un trío (station_id,
          -     # magnitude_code, measured_at) identifica de forma única una medición
          +     # magnitude_code, measured_at) identifica de forma única una medición
          -     # real de un contaminante en una estación e instante concretos.
          +     # real de un contaminante en una estación e instante concretos.
          -     silver_df = silver_df.dropDuplicates(["station_id", "magnitude_code", "measured_at"])
          +     silver_df = silver_df.dropDuplicates(["station_id", "magnitude_code", "measured_at"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"calidad_aire_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"calidad_aire_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          +     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          -     # hora de Madrid).
          +     # hora de Madrid).
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          +     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          -     # sustituto de ese borrado previo.
          +     # sustituto de ese borrado previo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "6d44949bc6077a4ec6bba66eff619e0e" -> "34fd8107fa813f83f6e1b5b6ad747653"
      ~ id                            = "glue-scripts/calidad_aire_backfill_dedup-6d44949bc6077a4ec6bba66eff619e0e.py" -> (known after apply)
      ~ key                           = "glue-scripts/calidad_aire_backfill_dedup-6d44949bc6077a4ec6bba66eff619e0e.py" -> "glue-scripts/calidad_aire_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_calidad_aire_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_calidad_aire_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_backfill_dedup_gold-879b3165bb85419fae5a2b8078c723d0.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `calidad_aire`.
          + `calidad_aire`.
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 049/072), que solo procesa la partición horaria anterior a la
          + tarea 049/072), que solo procesa la partición horaria anterior a la
          - ejecución. Este job existe para recalcular Gold desde cero tras la
          + ejecución. Este job existe para recalcular Gold desde cero tras la
          - reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          + reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          - lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          + lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          - hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          + hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          - trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          + trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          + `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          - duplicados (`(station_id, magnitude_code, measured_at)` único) -- lo que
          + duplicados (`(station_id, magnitude_code, measured_at)` único) -- lo que
          - hace este job es la misma agregación de producción de
          + hace este job es la misma agregación de producción de
          - `glue_silver_to_gold.py`, solo que sobre todo el histórico en vez de una
          + `glue_silver_to_gold.py`, solo que sobre todo el histórico en vez de una
          - única partición horaria, y escribiendo con `overwrite` en vez de `append`
          + única partición horaria, y escribiendo con `overwrite` en vez de `append`
          - (el prefijo de destino debe borrarse a mano antes de lanzarlo, igual que
          + (el prefijo de destino debe borrarse a mano antes de lanzarlo, igual que
          - Silver).
          + Silver).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/calidad_aire_por_estacion_contaminante_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/calidad_aire_por_estacion_contaminante_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          +     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          -     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          +     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          -     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          +     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- exactamente lo que necesita una
          +     # el histórico de Silver de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa de Gold.
          +     # reconstrucción completa de Gold.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(args["silver_path"])
          +         spark.read.parquet(args["silver_path"])
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # Misma agregación que el pipeline de producción
          +     # Misma agregación que el pipeline de producción
          -     # (`glue_silver_to_gold.py`): una fila por estación/contaminante/fecha/
          +     # (`glue_silver_to_gold.py`): una fila por estación/contaminante/fecha/
          -     # hora.
          +     # hora.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "pollutant", "fecha", "hora")
          +         silver_df.groupBy("station_id", "pollutant", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("station_name", ignorenulls=True).alias("station_name"),
          +             F.first("station_name", ignorenulls=True).alias("station_name"),
          -             F.first("magnitude_code", ignorenulls=True).alias("magnitude_code"),
          +             F.first("magnitude_code", ignorenulls=True).alias("magnitude_code"),
          -             F.first("pollutant_name", ignorenulls=True).alias("pollutant_name"),
          +             F.first("pollutant_name", ignorenulls=True).alias("pollutant_name"),
          -             F.first("unit", ignorenulls=True).alias("unit"),
          +             F.first("unit", ignorenulls=True).alias("unit"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("value").alias("avg_value"),
          +             F.avg("value").alias("avg_value"),
          -             F.max("value").alias("max_value"),
          +             F.max("value").alias("max_value"),
          -             F.min("value").alias("min_value"),
          +             F.min("value").alias("min_value"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          +     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          -     # que `glue_backfill_dedup.py` para Silver).
          +     # que `glue_backfill_dedup.py` para Silver).
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "879b3165bb85419fae5a2b8078c723d0" -> "b1b779d81465784f5abab97e0cbdab0c"
      ~ id                            = "glue-scripts/calidad_aire_backfill_dedup_gold-879b3165bb85419fae5a2b8078c723d0.py" -> (known after apply)
      ~ key                           = "glue-scripts/calidad_aire_backfill_dedup_gold-879b3165bb85419fae5a2b8078c723d0.py" -> "glue-scripts/calidad_aire_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_calidad_aire_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_calidad_aire_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_bronze_to_silver-4eb1972a460e5e10ae7df4a3315f52d4.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `calidad_aire`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `calidad_aire`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          - añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
          + añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
          - `_with_plausible_max_column`) y escribir el resultado.
          + `_with_plausible_max_column`) y escribir el resultado.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/calidad_aire/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/calidad_aire/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - from procesamiento.silver_gold.calidad_aire.ge_suite import run_quality_report
          + from procesamiento.silver_gold.calidad_aire.ge_suite import run_quality_report
          - from procesamiento.silver_gold.calidad_aire.transform import PLAUSIBLE_MAX_BY_POLLUTANT, bronze_to_silver
          + from procesamiento.silver_gold.calidad_aire.transform import PLAUSIBLE_MAX_BY_POLLUTANT, bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("station_id", StringType(), False),
          +         StructField("station_id", StringType(), False),
          -         StructField("station_name", StringType(), True),
          +         StructField("station_name", StringType(), True),
          -         StructField("station_address", StringType(), True),
          +         StructField("station_address", StringType(), True),
          -         StructField("magnitude_code", StringType(), True),
          +         StructField("magnitude_code", StringType(), True),
          -         StructField("pollutant", StringType(), False),
          +         StructField("pollutant", StringType(), False),
          -         StructField("pollutant_name", StringType(), True),
          +         StructField("pollutant_name", StringType(), True),
          -         StructField("unit", StringType(), True),
          +         StructField("unit", StringType(), True),
          -         StructField("value", DoubleType(), False),
          +         StructField("value", DoubleType(), False),
          -         StructField("measured_at", StringType(), False),
          +         StructField("measured_at", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         station_id=silver_record["station_id"],
          +         station_id=silver_record["station_id"],
          -         station_name=silver_record["station_name"],
          +         station_name=silver_record["station_name"],
          -         station_address=silver_record["station_address"],
          +         station_address=silver_record["station_address"],
          -         magnitude_code=silver_record["magnitude_code"],
          +         magnitude_code=silver_record["magnitude_code"],
          -         pollutant=silver_record["pollutant"],
          +         pollutant=silver_record["pollutant"],
          -         pollutant_name=silver_record["pollutant_name"],
          +         pollutant_name=silver_record["pollutant_name"],
          -         unit=silver_record["unit"],
          +         unit=silver_record["unit"],
          -         value=silver_record["value"],
          +         value=silver_record["value"],
          -         measured_at=silver_record["measured_at"],
          +         measured_at=silver_record["measured_at"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _with_plausible_max_column(silver_df):
          + def _with_plausible_max_column(silver_df):
          -     """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.
          +     """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.
          - 
          + 
          -     GX no tiene una expectation nativa de "el máximo depende del valor de
          +     GX no tiene una expectation nativa de "el máximo depende del valor de
          -     otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
          +     otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
          -     `transform.PLAUSIBLE_MAX_BY_POLLUTANT` a una expresión `when/otherwise`
          +     `transform.PLAUSIBLE_MAX_BY_POLLUTANT` a una expresión `when/otherwise`
          -     de Spark en vez de repetir la tabla como una segunda fuente de verdad --
          +     de Spark en vez de repetir la tabla como una segunda fuente de verdad --
          -     un contaminante sin entrada en la tabla (no debería ocurrir) usa
          +     un contaminante sin entrada en la tabla (no debería ocurrir) usa
          -     `float("inf")` como máximo, igual que `transform.validate_record` no
          +     `float("inf")` como máximo, igual que `transform.validate_record` no
          -     aplica ningún tope de rango en ese caso.
          +     aplica ningún tope de rango en ese caso.
          -     """
          +     """
          -     max_expr = F.lit(float("inf"))
          +     max_expr = F.lit(float("inf"))
          -     for pollutant, max_value in PLAUSIBLE_MAX_BY_POLLUTANT.items():
          +     for pollutant, max_value in PLAUSIBLE_MAX_BY_POLLUTANT.items():
          -         max_expr = F.when(F.col("pollutant") == pollutant, F.lit(float(max_value))).otherwise(max_expr)
          +         max_expr = F.when(F.col("pollutant") == pollutant, F.lit(float(max_value))).otherwise(max_expr)
          -     return silver_df.withColumn("value_over_plausible_max", F.col("value") - max_expr)
          +     return silver_df.withColumn("value_over_plausible_max", F.col("value") - max_expr)
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          +     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          -     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          +     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          -     # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
          +     # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
          -     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          +     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          -     # termina sin error pero nunca escribe la partición que espera Gold).
          +     # termina sin error pero nunca escribe la partición que espera Gold).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          +     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          -     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          +     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          -     # completo, que crecia sin limite y disparo el coste real de Glue
          +     # completo, que crecia sin limite y disparo el coste real de Glue
          -     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          +     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          +     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"calidad_aire_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"calidad_aire_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          -     # para que un consumidor ya familiarizado con Bronze no tenga que
          +     # para que un consumidor ya familiarizado con Bronze no tenga que
          -     # aprender un esquema de partición distinto para Silver.
          +     # aprender un esquema de partición distinto para Silver.
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "4eb1972a460e5e10ae7df4a3315f52d4" -> "da2056544438c70f538d76fa59f438a4"
      ~ id                            = "glue-scripts/calidad_aire_bronze_to_silver-4eb1972a460e5e10ae7df4a3315f52d4.py" -> (known after apply)
      ~ key                           = "glue-scripts/calidad_aire_bronze_to_silver-4eb1972a460e5e10ae7df4a3315f52d4.py" -> "glue-scripts/calidad_aire_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_calidad_aire_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_calidad_aire_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/calidad_aire_silver_to_gold-8333a2c7125ffd86e09976ae4db5114d.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `calidad_aire` (valor medio/máx/mín por
          + """Job de AWS Glue: Silver -> Gold del dataset `calidad_aire` (valor medio/máx/mín por
          - estación, contaminante y hora).
          + estación, contaminante y hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/calidad_aire_por_estacion_contaminante_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/calidad_aire_por_estacion_contaminante_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          +     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          -     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          +     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          +     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha`/`hora` son columnas de partición de Silver (ver
          +     # `fecha`/`hora` son columnas de partición de Silver (ver
          -     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          +     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          -     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          +     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          -     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          +     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(silver_partition_path)
          +         spark.read.parquet(silver_partition_path)
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          +     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          +     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
          +     # partition pruning si `silver_path` acota un rango de fechas concreto.
          -     # `pollutant` entra en la clave de agrupación (a diferencia del resto de
          +     # `pollutant` entra en la clave de agrupación (a diferencia del resto de
          -     # datasets del patrón): una misma estación reporta varios contaminantes
          +     # datasets del patrón): una misma estación reporta varios contaminantes
          -     # a la vez, ver docstring de `aggregate.py`.
          +     # a la vez, ver docstring de `aggregate.py`.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "pollutant", "fecha", "hora")
          +         silver_df.groupBy("station_id", "pollutant", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("station_name", ignorenulls=True).alias("station_name"),
          +             F.first("station_name", ignorenulls=True).alias("station_name"),
          -             F.first("magnitude_code", ignorenulls=True).alias("magnitude_code"),
          +             F.first("magnitude_code", ignorenulls=True).alias("magnitude_code"),
          -             F.first("pollutant_name", ignorenulls=True).alias("pollutant_name"),
          +             F.first("pollutant_name", ignorenulls=True).alias("pollutant_name"),
          -             F.first("unit", ignorenulls=True).alias("unit"),
          +             F.first("unit", ignorenulls=True).alias("unit"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("value").alias("avg_value"),
          +             F.avg("value").alias("avg_value"),
          -             F.max("value").alias("max_value"),
          +             F.max("value").alias("max_value"),
          -             F.min("value").alias("min_value"),
          +             F.min("value").alias("min_value"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # estación, contaminante y hora, no cada ~20 minutos): particionar solo
          +     # estación, contaminante y hora, no cada ~20 minutos): particionar solo
          -     # por `date` es suficiente para podar particiones sin generar ficheros
          +     # por `date` es suficiente para podar particiones sin generar ficheros
          -     # diminutos.
          +     # diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "8333a2c7125ffd86e09976ae4db5114d" -> "2aa3d2a268bb6c9d89020347d439f194"
      ~ id                            = "glue-scripts/calidad_aire_silver_to_gold-8333a2c7125ffd86e09976ae4db5114d.py" -> (known after apply)
      ~ key                           = "glue-scripts/calidad_aire_silver_to_gold-8333a2c7125ffd86e09976ae4db5114d.py" -> "glue-scripts/calidad_aire_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_cams_calidad_aire_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_backfill_dedup-69f636c9df5c3880b98dff5bf4088421.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `cams_calidad_aire` (tarea 077, mismo patrón que
          + `cams_calidad_aire` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          - 
          + 
          - **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (arreglado en la tarea 076) lee solo la partición Bronze del día de
          + (arreglado en la tarea 076) lee solo la partición Bronze del día de
          - ejecución -- no acepta un `--bronze_path` que apunte a "todo el histórico",
          + ejecución -- no acepta un `--bronze_path` que apunte a "todo el histórico",
          - así que no sirve para reconstruir Silver desde cero. Este script existe
          + así que no sirve para reconstruir Silver desde cero. Este script existe
          - únicamente para eso: leer TODO el histórico de Bronze de una vez y
          + únicamente para eso: leer TODO el histórico de Bronze de una vez y
          - deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          + deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          - hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          + hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          - todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          + todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          - Athena real (ver `doc/077-...md`): `n=10` para el mismo
          + Athena real (ver `doc/077-...md`): `n=10` para el mismo
          - (`pollutant`, `latitude`, `longitude`, `valid_datetime`, `forecast_issued_at`).
          + (`pollutant`, `latitude`, `longitude`, `valid_datetime`, `forecast_issued_at`).
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          + lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          - 
          + 
          - `(pollutant, latitude, longitude, valid_datetime, forecast_issued_at)` es la
          + `(pollutant, latitude, longitude, valid_datetime, forecast_issued_at)` es la
          - clave natural de una previsión individual real: contaminante + punto de
          + clave natural de una previsión individual real: contaminante + punto de
          - rejilla + instante previsto + corrida de modelo que la generó (ver docstring
          + rejilla + instante previsto + corrida de modelo que la generó (ver docstring
          - de `transform.py`, "Es una previsión con horizonte, no una medida del
          + de `transform.py`, "Es una previsión con horizonte, no una medida del
          - instante actual" -- `leadtime_hour` es redundante con
          + instante actual" -- `leadtime_hour` es redundante con
          - `valid_datetime - forecast_issued_at`, no hace falta en la clave).
          + `valid_datetime - forecast_issued_at`, no hace falta en la clave).
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          + de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          - `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`,
          + `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`,
          - `_with_plausible_max_column`.
          + `_with_plausible_max_column`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/cams_calidad_aire/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/cams_calidad_aire/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.cams_calidad_aire.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.cams_calidad_aire.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _with_plausible_max_column,
          +     _with_plausible_max_column,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - from procesamiento.silver_gold.cams_calidad_aire.ge_suite import run_quality_report
          + from procesamiento.silver_gold.cams_calidad_aire.ge_suite import run_quality_report
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez.
          +     # el histórico de Bronze de una vez.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba. Clave natural de una previsión
          +     # La deduplicación real que faltaba. Clave natural de una previsión
          -     # individual: contaminante + punto de rejilla + instante previsto +
          +     # individual: contaminante + punto de rejilla + instante previsto +
          -     # corrida de modelo (ver docstring del módulo).
          +     # corrida de modelo (ver docstring del módulo).
          -     silver_df = silver_df.dropDuplicates(
          +     silver_df = silver_df.dropDuplicates(
          -         ["pollutant", "latitude", "longitude", "valid_datetime", "forecast_issued_at"]
          +         ["pollutant", "latitude", "longitude", "valid_datetime", "forecast_issued_at"]
          -     )
          +     )
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"cams_calidad_aire_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"cams_calidad_aire_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Particiona por el día/hora del instante previsto (`valid_datetime`),
          +     # Particiona por el día/hora del instante previsto (`valid_datetime`),
          -     # igual que el pipeline de producción.
          +     # igual que el pipeline de producción.
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("valid_datetime"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("valid_datetime"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("valid_datetime"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("valid_datetime"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo.
          +     # prefijo de destino debe estar vacío antes de lanzarlo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "69f636c9df5c3880b98dff5bf4088421" -> "f740ec883030bc43077f1cf7c79cffd7"
      ~ id                            = "glue-scripts/cams_calidad_aire_backfill_dedup-69f636c9df5c3880b98dff5bf4088421.py" -> (known after apply)
      ~ key                           = "glue-scripts/cams_calidad_aire_backfill_dedup-69f636c9df5c3880b98dff5bf4088421.py" -> "glue-scripts/cams_calidad_aire_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_cams_calidad_aire_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_backfill_dedup_gold-fa45e88fe2d37635cc6240ef327383ff.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `cams_calidad_aire` (tarea 077, mismo patrón que
          + `cams_calidad_aire` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 076), que solo procesa la partición `fecha=hoy` de Silver. Este job
          + tarea 076), que solo procesa la partición `fecha=hoy` de Silver. Este job
          - existe para recalcular Gold desde cero tras la reconstrucción deduplicada de
          + existe para recalcular Gold desde cero tras la reconstrucción deduplicada de
          - Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el histórico de
          + Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el histórico de
          - Silver de una vez y agrega, en vez de una sola partición diaria.
          + Silver de una vez y agrega, en vez de una sola partición diaria.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/cams_calidad_aire_por_contaminante_fecha_validez/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/cams_calidad_aire_por_contaminante_fecha_validez/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     silver_df = spark.read.parquet(args["silver_path"])
          +     silver_df = spark.read.parquet(args["silver_path"])
          - 
          + 
          -     silver_with_fecha_validez = silver_df.withColumn(
          +     silver_with_fecha_validez = silver_df.withColumn(
          -         "fecha_validez", F.date_format(F.to_timestamp("valid_datetime"), "yyyy-MM-dd")
          +         "fecha_validez", F.date_format(F.to_timestamp("valid_datetime"), "yyyy-MM-dd")
          -     )
          +     )
          - 
          + 
          -     gold_df = (
          +     gold_df = (
          -         silver_with_fecha_validez.groupBy("pollutant", "fecha_validez")
          +         silver_with_fecha_validez.groupBy("pollutant", "fecha_validez")
          -         .agg(
          +         .agg(
          -             F.first("pollutant_code", ignorenulls=True).alias("pollutant_code"),
          +             F.first("pollutant_code", ignorenulls=True).alias("pollutant_code"),
          -             F.first("unit", ignorenulls=True).alias("unit"),
          +             F.first("unit", ignorenulls=True).alias("unit"),
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.avg("value").alias("avg_value"),
          +             F.avg("value").alias("avg_value"),
          -             F.max("value").alias("max_value"),
          +             F.max("value").alias("max_value"),
          -             F.sort_array(F.collect_set("leadtime_hour")).alias("leadtime_hours"),
          +             F.sort_array(F.collect_set("leadtime_hour")).alias("leadtime_hours"),
          -             F.min("forecast_issued_at").alias("first_forecast_issued_at"),
          +             F.min("forecast_issued_at").alias("first_forecast_issued_at"),
          -             F.max("forecast_issued_at").alias("last_forecast_issued_at"),
          +             F.max("forecast_issued_at").alias("last_forecast_issued_at"),
          -         )
          +         )
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo.
          +     # prefijo de destino debe estar vacío antes de lanzarlo.
          -     gold_df.write.mode("overwrite").partitionBy("pollutant").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("pollutant").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "fa45e88fe2d37635cc6240ef327383ff" -> "1a9154bc6c0c71a12b1e6c42eea25f30"
      ~ id                            = "glue-scripts/cams_calidad_aire_backfill_dedup_gold-fa45e88fe2d37635cc6240ef327383ff.py" -> (known after apply)
      ~ key                           = "glue-scripts/cams_calidad_aire_backfill_dedup_gold-fa45e88fe2d37635cc6240ef327383ff.py" -> "glue-scripts/cams_calidad_aire_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cams_calidad_aire_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_cams_calidad_aire_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_bronze_to_silver-9211d3802eca398bfda830e10b7b8ef2.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `cams_calidad_aire`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `cams_calidad_aire`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          - añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
          + añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
          - `_with_plausible_max_column`) y escribir el resultado.
          + `_with_plausible_max_column`) y escribir el resultado.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita).
          + `saveAsTextFile` necesita).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/cams_calidad_aire/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/cams_calidad_aire/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.cams_calidad_aire.ge_suite import run_quality_report
          + from procesamiento.silver_gold.cams_calidad_aire.ge_suite import run_quality_report
          - from procesamiento.silver_gold.cams_calidad_aire.transform import (
          + from procesamiento.silver_gold.cams_calidad_aire.transform import (
          -     PLAUSIBLE_MAX_BY_POLLUTANT,
          +     PLAUSIBLE_MAX_BY_POLLUTANT,
          -     bronze_to_silver,
          +     bronze_to_silver,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("pollutant", StringType(), False),
          +         StructField("pollutant", StringType(), False),
          -         StructField("pollutant_code", StringType(), False),
          +         StructField("pollutant_code", StringType(), False),
          -         StructField("value", DoubleType(), False),
          +         StructField("value", DoubleType(), False),
          -         StructField("unit", StringType(), True),
          +         StructField("unit", StringType(), True),
          -         StructField("valid_datetime", StringType(), False),
          +         StructField("valid_datetime", StringType(), False),
          -         StructField("forecast_issued_at", StringType(), False),
          +         StructField("forecast_issued_at", StringType(), False),
          -         StructField("leadtime_hour", IntegerType(), False),
          +         StructField("leadtime_hour", IntegerType(), False),
          -         StructField("model", StringType(), True),
          +         StructField("model", StringType(), True),
          -         StructField("latitude", DoubleType(), True),
          +         StructField("latitude", DoubleType(), True),
          -         StructField("longitude", DoubleType(), True),
          +         StructField("longitude", DoubleType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     return Row(**{field.name: silver_record[field.name] for field in SILVER_SCHEMA.fields})
          +     return Row(**{field.name: silver_record[field.name] for field in SILVER_SCHEMA.fields})
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _with_plausible_max_column(silver_df):
          + def _with_plausible_max_column(silver_df):
          -     """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.
          +     """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.
          - 
          + 
          -     GX no tiene una expectation nativa de "el máximo depende del valor de
          +     GX no tiene una expectation nativa de "el máximo depende del valor de
          -     otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
          +     otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
          -     `transform.PLAUSIBLE_MAX_BY_POLLUTANT` a una expresión `when/otherwise`
          +     `transform.PLAUSIBLE_MAX_BY_POLLUTANT` a una expresión `when/otherwise`
          -     de Spark en vez de repetir la tabla como una segunda fuente de verdad --
          +     de Spark en vez de repetir la tabla como una segunda fuente de verdad --
          -     un contaminante sin entrada en la tabla (no debería ocurrir) usa
          +     un contaminante sin entrada en la tabla (no debería ocurrir) usa
          -     `float("inf")` como máximo, igual que `transform.validate_record` no
          +     `float("inf")` como máximo, igual que `transform.validate_record` no
          -     aplica ningún tope de rango en ese caso.
          +     aplica ningún tope de rango en ese caso.
          -     """
          +     """
          -     max_expr = F.lit(float("inf"))
          +     max_expr = F.lit(float("inf"))
          -     for pollutant, max_value in PLAUSIBLE_MAX_BY_POLLUTANT.items():
          +     for pollutant, max_value in PLAUSIBLE_MAX_BY_POLLUTANT.items():
          -         max_expr = F.when(F.col("pollutant") == pollutant, F.lit(float(max_value))).otherwise(max_expr)
          +         max_expr = F.when(F.col("pollutant") == pollutant, F.lit(float(max_value))).otherwise(max_expr)
          -     return silver_df.withColumn("value_over_plausible_max", F.col("value") - max_expr)
          +     return silver_df.withColumn("value_over_plausible_max", F.col("value") - max_expr)
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(lambda rows: _process_partition(rows, processed_at.isoformat()))
          +     silver_rdd = bronze_df.rdd.mapPartitions(lambda rows: _process_partition(rows, processed_at.isoformat()))
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
          -     report_key = f"{args['quality_report_path'].rstrip('/')}/cams_calidad_aire_{processed_at:%Y%m%dT%H%M%S}.json"
          +     report_key = f"{args['quality_report_path'].rstrip('/')}/cams_calidad_aire_{processed_at:%Y%m%dT%H%M%S}.json"
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Particiona por el día/hora del instante **previsto** (`valid_datetime`),
          +     # Particiona por el día/hora del instante **previsto** (`valid_datetime`),
          -     # no por `forecast_issued_at` (la corrida) ni por `ingested_at` (la
          +     # no por `forecast_issued_at` (la corrida) ni por `ingested_at` (la
          -     # captura) -- responde "qué se predijo para tal fecha/hora", mismo
          +     # captura) -- responde "qué se predijo para tal fecha/hora", mismo
          -     # criterio que `aggregate.py` usa `valid_datetime` para `fecha_validez`.
          +     # criterio que `aggregate.py` usa `valid_datetime` para `fecha_validez`.
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("valid_datetime"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("valid_datetime"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("valid_datetime"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("valid_datetime"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(args["silver_path"])
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(args["silver_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "9211d3802eca398bfda830e10b7b8ef2" -> "c0577843a652fafb4ba8dc477363c545"
      ~ id                            = "glue-scripts/cams_calidad_aire_bronze_to_silver-9211d3802eca398bfda830e10b7b8ef2.py" -> (known after apply)
      ~ key                           = "glue-scripts/cams_calidad_aire_bronze_to_silver-9211d3802eca398bfda830e10b7b8ef2.py" -> "glue-scripts/cams_calidad_aire_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cams_calidad_aire_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_cams_calidad_aire_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cams_calidad_aire_silver_to_gold-f83d74685a5a4d930a50993f848d2a01.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `cams_calidad_aire` (valor
          + """Job de AWS Glue: Silver -> Gold del dataset `cams_calidad_aire` (valor
          - medio/máximo previsto por contaminante y día que predicen).
          + medio/máximo previsto por contaminante y día que predicen).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/cams_calidad_aire_por_contaminante_fecha_validez/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/cams_calidad_aire_por_contaminante_fecha_validez/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          + from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
          -     # `date_format(to_timestamp(...), ...)` de mas abajo calcularia en UTC,
          +     # `date_format(to_timestamp(...), ...)` de mas abajo calcularia en UTC,
          -     # desalineado con `today()` (Python, Europe/Madrid).
          +     # desalineado con `today()` (Python, Europe/Madrid).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          +     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          -     # nunca la raiz completa del dataset -- mismo motivo de coste que
          +     # nunca la raiz completa del dataset -- mismo motivo de coste que
          -     # Bronze->Silver (tarea 072). `fecha` en Silver es la del instante
          +     # Bronze->Silver (tarea 072). `fecha` en Silver es la del instante
          -     # **previsto** (`valid_datetime`, ver glue_bronze_to_silver.py), que
          +     # **previsto** (`valid_datetime`, ver glue_bronze_to_silver.py), que
          -     # puede caer varios dias en el futuro respecto al dia de ingestion (CAMS
          +     # puede caer varios dias en el futuro respecto al dia de ingestion (CAMS
          -     # predice hasta 96h/4 dias vista) -- pero Silver es un almacen
          +     # predice hasta 96h/4 dias vista) -- pero Silver es un almacen
          -     # persistente: cada particion `fecha=<dia>` recibe escrituras de varias
          +     # persistente: cada particion `fecha=<dia>` recibe escrituras de varias
          -     # corridas de prevision distintas mientras ese dia sigue dentro del
          +     # corridas de prevision distintas mientras ese dia sigue dentro del
          -     # horizonte, y esta lectura la visita una unica vez, el dia en que ese
          +     # horizonte, y esta lectura la visita una unica vez, el dia en que ese
          -     # dia de calendario se convierte en "hoy" (momento en que ya contiene
          +     # dia de calendario se convierte en "hoy" (momento en que ya contiene
          -     # todas las corridas que llegaron a predecirlo).
          +     # todas las corridas que llegaron a predecirlo).
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          +     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     silver_df = spark.read.parquet(silver_partition_path)
          +     silver_df = spark.read.parquet(silver_partition_path)
          - 
          + 
          -     # `fecha_validez` = día del instante previsto (`valid_datetime`), no el
          +     # `fecha_validez` = día del instante previsto (`valid_datetime`), no el
          -     # horizonte de antelación (`leadtime_hour`) ni el día de la corrida
          +     # horizonte de antelación (`leadtime_hour`) ni el día de la corrida
          -     # (`forecast_issued_at`) -- mismo criterio que `aggregate.py`.
          +     # (`forecast_issued_at`) -- mismo criterio que `aggregate.py`.
          -     silver_with_fecha_validez = silver_df.withColumn(
          +     silver_with_fecha_validez = silver_df.withColumn(
          -         "fecha_validez", F.date_format(F.to_timestamp("valid_datetime"), "yyyy-MM-dd")
          +         "fecha_validez", F.date_format(F.to_timestamp("valid_datetime"), "yyyy-MM-dd")
          -     )
          +     )
          - 
          + 
          -     gold_df = (
          +     gold_df = (
          -         silver_with_fecha_validez.groupBy("pollutant", "fecha_validez")
          +         silver_with_fecha_validez.groupBy("pollutant", "fecha_validez")
          -         .agg(
          +         .agg(
          -             F.first("pollutant_code", ignorenulls=True).alias("pollutant_code"),
          +             F.first("pollutant_code", ignorenulls=True).alias("pollutant_code"),
          -             F.first("unit", ignorenulls=True).alias("unit"),
          +             F.first("unit", ignorenulls=True).alias("unit"),
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.avg("value").alias("avg_value"),
          +             F.avg("value").alias("avg_value"),
          -             F.max("value").alias("max_value"),
          +             F.max("value").alias("max_value"),
          -             F.sort_array(F.collect_set("leadtime_hour")).alias("leadtime_hours"),
          +             F.sort_array(F.collect_set("leadtime_hour")).alias("leadtime_hours"),
          -             F.min("forecast_issued_at").alias("first_forecast_issued_at"),
          +             F.min("forecast_issued_at").alias("first_forecast_issued_at"),
          -             F.max("forecast_issued_at").alias("last_forecast_issued_at"),
          +             F.max("forecast_issued_at").alias("last_forecast_issued_at"),
          -         )
          +         )
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es mucho más pequeño que Silver (una fila por contaminante y día
          +     # Gold es mucho más pequeño que Silver (una fila por contaminante y día
          -     # previsto, no por hora/corrida): particionar por `pollutant` basta para
          +     # previsto, no por hora/corrida): particionar por `pollutant` basta para
          -     # podar particiones sin generar ficheros diminutos -- el número de
          +     # podar particiones sin generar ficheros diminutos -- el número de
          -     # contaminantes es reducido, a diferencia de particionar por
          +     # contaminantes es reducido, a diferencia de particionar por
          -     # `fecha_validez` (menos selectivo aquí: cada corrida diaria predice
          +     # `fecha_validez` (menos selectivo aquí: cada corrida diaria predice
          -     # varios días de horizonte para todos los contaminantes a la vez).
          +     # varios días de horizonte para todos los contaminantes a la vez).
          -     gold_df.write.mode("append").partitionBy("pollutant").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("pollutant").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "f83d74685a5a4d930a50993f848d2a01" -> "b314b6a6fc7c546a4c090fe2e01f052d"
      ~ id                            = "glue-scripts/cams_calidad_aire_silver_to_gold-f83d74685a5a4d930a50993f848d2a01.py" -> (known after apply)
      ~ key                           = "glue-scripts/cams_calidad_aire_silver_to_gold-f83d74685a5a4d930a50993f848d2a01.py" -> "glue-scripts/cams_calidad_aire_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cartelera_cines_estrenos_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_cartelera_cines_estrenos_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_bronze_to_silver-77e98d1cd921c208bf5ffaa29d284e32.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `cartelera_cines_estrenos`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `cartelera_cines_estrenos`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          - y escribir el resultado.
          + y escribir el resultado.
          - 
          + 
          - **Para el informe de Great Expectations se escribe directamente a S3 vía
          + **Para el informe de Great Expectations se escribe directamente a S3 vía
          - `boto3`** (`_write_quality_report`), NO con
          + `boto3`** (`_write_quality_report`), NO con
          - `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          + `sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
          - producción en la tarea 051 (el runtime de Glue no trae la clase de
          + producción en la tarea 051 (el runtime de Glue no trae la clase de
          - committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          + committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
          - `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          + `saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/cartelera_cines_estrenos/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/cartelera_cines_estrenos/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     ArrayType,
          +     ArrayType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.cartelera_cines_estrenos.ge_suite import run_quality_report
          + from procesamiento.silver_gold.cartelera_cines_estrenos.ge_suite import run_quality_report
          - from procesamiento.silver_gold.cartelera_cines_estrenos.transform import bronze_to_silver
          + from procesamiento.silver_gold.cartelera_cines_estrenos.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("cinema_id", StringType(), False),
          +         StructField("cinema_id", StringType(), False),
          -         StructField("chain", StringType(), True),
          +         StructField("chain", StringType(), True),
          -         StructField("cinema_name", StringType(), True),
          +         StructField("cinema_name", StringType(), True),
          -         StructField("address", StringType(), True),
          +         StructField("address", StringType(), True),
          -         StructField("postal_code", StringType(), True),
          +         StructField("postal_code", StringType(), True),
          -         StructField("locality", StringType(), True),
          +         StructField("locality", StringType(), True),
          -         StructField("screen_count", IntegerType(), True),
          +         StructField("screen_count", IntegerType(), True),
          -         StructField("movie_title", StringType(), False),
          +         StructField("movie_title", StringType(), False),
          -         StructField("movie_url", StringType(), True),
          +         StructField("movie_url", StringType(), True),
          -         StructField("language_version", StringType(), True),
          +         StructField("language_version", StringType(), True),
          -         StructField("experiences", ArrayType(StringType()), True),
          +         StructField("experiences", ArrayType(StringType()), True),
          -         StructField("showtime_datetime", StringType(), False),
          +         StructField("showtime_datetime", StringType(), False),
          -         StructField("showtime_id", StringType(), False),
          +         StructField("showtime_id", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         cinema_id=silver_record["cinema_id"],
          +         cinema_id=silver_record["cinema_id"],
          -         chain=silver_record["chain"],
          +         chain=silver_record["chain"],
          -         cinema_name=silver_record["cinema_name"],
          +         cinema_name=silver_record["cinema_name"],
          -         address=silver_record["address"],
          +         address=silver_record["address"],
          -         postal_code=silver_record["postal_code"],
          +         postal_code=silver_record["postal_code"],
          -         locality=silver_record["locality"],
          +         locality=silver_record["locality"],
          -         screen_count=silver_record["screen_count"],
          +         screen_count=silver_record["screen_count"],
          -         movie_title=silver_record["movie_title"],
          +         movie_title=silver_record["movie_title"],
          -         movie_url=silver_record["movie_url"],
          +         movie_url=silver_record["movie_url"],
          -         language_version=silver_record["language_version"],
          +         language_version=silver_record["language_version"],
          -         experiences=silver_record["experiences"],
          +         experiences=silver_record["experiences"],
          -         showtime_datetime=silver_record["showtime_datetime"],
          +         showtime_datetime=silver_record["showtime_datetime"],
          -         showtime_id=silver_record["showtime_id"],
          +         showtime_id=silver_record["showtime_id"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"cartelera_cines_estrenos_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"cartelera_cines_estrenos_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Particiona por la fecha/hora de la propia sesión (showtime_datetime),
          +     # Particiona por la fecha/hora de la propia sesión (showtime_datetime),
          -     # no por ingested_at: para este dataset la pregunta natural es "qué
          +     # no por ingested_at: para este dataset la pregunta natural es "qué
          -     # ponen tal día/hora", no "cuándo se capturó" (ver docstring de
          +     # ponen tal día/hora", no "cuándo se capturó" (ver docstring de
          -     # transform.py y aggregate.py).
          +     # transform.py y aggregate.py).
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("showtime_datetime"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("showtime_datetime"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("showtime_datetime"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("showtime_datetime"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "77e98d1cd921c208bf5ffaa29d284e32" -> "2b7b796b05eb81035f181fa7ae643321"
      ~ id                            = "glue-scripts/cartelera_cines_estrenos_bronze_to_silver-77e98d1cd921c208bf5ffaa29d284e32.py" -> (known after apply)
      ~ key                           = "glue-scripts/cartelera_cines_estrenos_bronze_to_silver-77e98d1cd921c208bf5ffaa29d284e32.py" -> "glue-scripts/cartelera_cines_estrenos_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_cartelera_cines_estrenos_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `cartelera_cines_estrenos`
          + """Job de AWS Glue: Silver -> Gold del dataset `cartelera_cines_estrenos`
          - (número de sesiones por película, cine y día).
          + (número de sesiones por película, cine y día).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/cartelera_cines_estrenos_por_pelicula_cine_fecha/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/cartelera_cines_estrenos_por_pelicula_cine_fecha/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          + from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
          -     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          +     # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
          -     # desalineado con `today()` (Python, Europe/Madrid).
          +     # desalineado con `today()` (Python, Europe/Madrid).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          +     # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
          -     # nunca la raiz completa del dataset -- mismo motivo de coste que
          +     # nunca la raiz completa del dataset -- mismo motivo de coste que
          -     # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio dia de
          +     # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio dia de
          -     # la sesion (`showtime_datetime`), no la de ingestion (ver
          +     # la sesion (`showtime_datetime`), no la de ingestion (ver
          -     # glue_bronze_to_silver.py) -- pero por como funciona realmente
          +     # glue_bronze_to_silver.py) -- pero por como funciona realmente
          -     # SensaCine (la cartelera scrapeada es de sesiones de hoy/muy cercanas,
          +     # SensaCine (la cartelera scrapeada es de sesiones de hoy/muy cercanas,
          -     # ver "showtime_already_passed" en transform.py, nunca semanas vista),
          +     # ver "showtime_already_passed" en transform.py, nunca semanas vista),
          -     # cada particion `fecha=<dia>` recibe practicamente todos sus datos el
          +     # cada particion `fecha=<dia>` recibe practicamente todos sus datos el
          -     # mismo dia (o el dia anterior), y esta lectura la visita el dia en que
          +     # mismo dia (o el dia anterior), y esta lectura la visita el dia en que
          -     # ese dia es "hoy" -- si alguna sesion quedase en una particion futura no
          +     # ese dia es "hoy" -- si alguna sesion quedase en una particion futura no
          -     # visitada aun, se recogeria igual cuando esa particion se convierta en
          +     # visitada aun, se recogeria igual cuando esa particion se convierta en
          -     # "hoy" (Silver es un almacen persistente, no se borra entre
          +     # "hoy" (Silver es un almacen persistente, no se borra entre
          -     # ejecuciones).
          +     # ejecuciones).
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          +     silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha` es columna de partición física de Silver (ver
          +     # `fecha` es columna de partición física de Silver (ver
          -     # glue_bronze_to_silver.py), pero al acotar la lectura a una única
          +     # glue_bronze_to_silver.py), pero al acotar la lectura a una única
          -     # partición `fecha=<fecha>/` (tarea 076, lectura incremental) Spark deja
          +     # partición `fecha=<fecha>/` (tarea 076, lectura incremental) Spark deja
          -     # de inferirla como columna -- solo `hora=` varía bajo esa ruta, mismo
          +     # de inferirla como columna -- solo `hora=` varía bajo esa ruta, mismo
          -     # motivo por el que `aparcamientos_silver_to_gold.py` recalcula sus
          +     # motivo por el que `aparcamientos_silver_to_gold.py` recalcula sus
          -     # columnas de partición tras acotar la lectura (tarea 072). Se añade de
          +     # columnas de partición tras acotar la lectura (tarea 072). Se añade de
          -     # vuelta con el valor ya conocido (`fecha`, calculado arriba) en vez de
          +     # vuelta con el valor ya conocido (`fecha`, calculado arriba) en vez de
          -     # asumir que Spark la habría inferido -- bug real encontrado en la
          +     # asumir que Spark la habría inferido -- bug real encontrado en la
          -     # verificación contra datos reales de la tarea 090 (`AnalysisException:
          +     # verificación contra datos reales de la tarea 090 (`AnalysisException:
          -     # Column 'fecha' does not exist`).
          +     # Column 'fecha' does not exist`).
          -     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
          - 
          + 
          -     # `movie_url`/`cinema_id` entran en la clave de agrupación junto a
          +     # `movie_url`/`cinema_id` entran en la clave de agrupación junto a
          -     # `fecha` (mismo criterio que `aggregate.py`: incluir ambas dimensiones
          +     # `fecha` (mismo criterio que `aggregate.py`: incluir ambas dimensiones
          -     # deja disponibles tanto la vista "por película" como "por cine" sin
          +     # deja disponibles tanto la vista "por película" como "por cine" sin
          -     # perder información en la propia agregación de Gold).
          +     # perder información en la propia agregación de Gold).
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("movie_url", "cinema_id", "fecha")
          +         silver_df.groupBy("movie_url", "cinema_id", "fecha")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.countDistinct("showtime_id").alias("sessions_count"),
          +             F.countDistinct("showtime_id").alias("sessions_count"),
          -             F.first("movie_title", ignorenulls=True).alias("movie_title"),
          +             F.first("movie_title", ignorenulls=True).alias("movie_title"),
          -             F.first("chain", ignorenulls=True).alias("chain"),
          +             F.first("chain", ignorenulls=True).alias("chain"),
          -             F.first("cinema_name", ignorenulls=True).alias("cinema_name"),
          +             F.first("cinema_name", ignorenulls=True).alias("cinema_name"),
          -             F.first("address", ignorenulls=True).alias("address"),
          +             F.first("address", ignorenulls=True).alias("address"),
          -             F.first("postal_code", ignorenulls=True).alias("postal_code"),
          +             F.first("postal_code", ignorenulls=True).alias("postal_code"),
          -             F.first("locality", ignorenulls=True).alias("locality"),
          +             F.first("locality", ignorenulls=True).alias("locality"),
          -             F.min("showtime_datetime").alias("first_showtime_datetime"),
          +             F.min("showtime_datetime").alias("first_showtime_datetime"),
          -             F.max("showtime_datetime").alias("last_showtime_datetime"),
          +             F.max("showtime_datetime").alias("last_showtime_datetime"),
          -             F.sort_array(F.collect_set("language_version")).alias("language_versions"),
          +             F.sort_array(F.collect_set("language_version")).alias("language_versions"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # película, cine y día, no una por sesión): particionar solo por `date`
          +     # película, cine y día, no una por sesión): particionar solo por `date`
          -     # es suficiente para podar particiones sin generar ficheros diminutos.
          +     # es suficiente para podar particiones sin generar ficheros diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "aa6c09b63c18f746da024c09a020b01f" -> "8d4592f5bf658249febbacc5cca7df26"
      ~ id                            = "glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py" -> (known after apply)
      ~ key                           = "glue-scripts/cartelera_cines_estrenos_silver_to_gold-aa6c09b63c18f746da024c09a020b01f.py" -> "glue-scripts/cartelera_cines_estrenos_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_meteorologia_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_meteorologia_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_backfill_dedup-1fa9eaae33ade611f68b64e9ac2dffc0.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `meteorologia`.
          + `meteorologia`.
          - 
          + 
          - **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 050, arreglado en la tarea 072) calcula internamente una única
          + (tarea 050, arreglado en la tarea 072) calcula internamente una única
          - hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          + hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          - un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          + un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          - reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          + reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          - TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          + TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          - confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          + confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          - que cada ejecución histórica del job de producción (antes del arreglo de la
          + que cada ejecución histórica del job de producción (antes del arreglo de la
          - tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          + tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          - deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          + deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          - verificado con una consulta Athena real sobre `(station_id, magnitude,
          + verificado con una consulta Athena real sobre `(station_id, magnitude,
          - measured_at)` antes de escribir este script. Se lanza una sola vez a mano
          + measured_at)` antes de escribir este script. Se lanza una sola vez a mano
          - (`aws glue start-job-run`), nunca vía trigger ni schedule.
          + (`aws glue start-job-run`), nunca vía trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          + lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          - tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          + tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          - sobrescribir un prefijo con miles de objetos preexistentes): este script
          + sobrescribir un prefijo con miles de objetos preexistentes): este script
          - escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          + escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          - de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          + de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          - con la reconstrucción.
          + con la reconstrucción.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción
          + de Spark/GX que ya usa el pipeline de producción
          - (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          + (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          - `_with_plausible_range_columns`, `_write_quality_report`.
          + `_with_plausible_range_columns`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/meteorologia/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/meteorologia/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.meteorologia.ge_suite import run_quality_report
          + from procesamiento.silver_gold.meteorologia.ge_suite import run_quality_report
          - from procesamiento.silver_gold.meteorologia.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.meteorologia.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _with_plausible_range_columns,
          +     _with_plausible_range_columns,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          +     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          -     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          +     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          -     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          +     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          -     # con la hora de Madrid real de `measured_at`.
          +     # con la hora de Madrid real de `measured_at`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          +     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa.
          +     # reconstrucción completa.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          +     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          -     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          +     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          -     # registro repetido cientos/miles de veces. Un trío (station_id,
          +     # registro repetido cientos/miles de veces. Un trío (station_id,
          -     # magnitude, measured_at) identifica de forma única una medición real de
          +     # magnitude, measured_at) identifica de forma única una medición real de
          -     # una magnitud en una estación e instante concretos.
          +     # una magnitud en una estación e instante concretos.
          -     silver_df = silver_df.dropDuplicates(["station_id", "magnitude", "measured_at"])
          +     silver_df = silver_df.dropDuplicates(["station_id", "magnitude", "measured_at"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_plausible_range_columns(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_plausible_range_columns(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"meteorologia_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"meteorologia_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          +     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          -     # hora de Madrid).
          +     # hora de Madrid).
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          +     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          -     # sustituto de ese borrado previo.
          +     # sustituto de ese borrado previo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "1fa9eaae33ade611f68b64e9ac2dffc0" -> "d0fd57ddf99e04744edfcba8d690721c"
      ~ id                            = "glue-scripts/meteorologia_backfill_dedup-1fa9eaae33ade611f68b64e9ac2dffc0.py" -> (known after apply)
      ~ key                           = "glue-scripts/meteorologia_backfill_dedup-1fa9eaae33ade611f68b64e9ac2dffc0.py" -> "glue-scripts/meteorologia_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_meteorologia_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_meteorologia_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_backfill_dedup_gold-cb6dc670fef14d383aaa366eb184d811.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `meteorologia`.
          + `meteorologia`.
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 050/072), que solo procesa la partición horaria anterior a la
          + tarea 050/072), que solo procesa la partición horaria anterior a la
          - ejecución. Este job existe para recalcular Gold desde cero tras la
          + ejecución. Este job existe para recalcular Gold desde cero tras la
          - reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          + reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          - lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          + lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          - hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          + hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          - trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          + trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          + `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          - duplicados (`(station_id, magnitude, measured_at)` único) -- lo que hace
          + duplicados (`(station_id, magnitude, measured_at)` único) -- lo que hace
          - este job es la misma agregación de producción de `glue_silver_to_gold.py`,
          + este job es la misma agregación de producción de `glue_silver_to_gold.py`,
          - solo que sobre todo el histórico en vez de una única partición horaria, y
          + solo que sobre todo el histórico en vez de una única partición horaria, y
          - escribiendo con `overwrite` en vez de `append` (el prefijo de destino debe
          + escribiendo con `overwrite` en vez de `append` (el prefijo de destino debe
          - borrarse a mano antes de lanzarlo, igual que Silver).
          + borrarse a mano antes de lanzarlo, igual que Silver).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/meteorologia_por_estacion_magnitud_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/meteorologia_por_estacion_magnitud_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          +     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          -     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          +     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          -     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          +     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- exactamente lo que necesita una
          +     # el histórico de Silver de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa de Gold.
          +     # reconstrucción completa de Gold.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(args["silver_path"])
          +         spark.read.parquet(args["silver_path"])
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # Misma agregación que el pipeline de producción
          +     # Misma agregación que el pipeline de producción
          -     # (`glue_silver_to_gold.py`): una fila por estación/magnitud/fecha/hora.
          +     # (`glue_silver_to_gold.py`): una fila por estación/magnitud/fecha/hora.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "magnitude", "fecha", "hora")
          +         silver_df.groupBy("station_id", "magnitude", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("station_name", ignorenulls=True).alias("station_name"),
          +             F.first("station_name", ignorenulls=True).alias("station_name"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("value").alias("avg_value"),
          +             F.avg("value").alias("avg_value"),
          -             F.max("value").alias("max_value"),
          +             F.max("value").alias("max_value"),
          -             F.min("value").alias("min_value"),
          +             F.min("value").alias("min_value"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -             F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          +             F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          +     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          -     # que `glue_backfill_dedup.py` para Silver).
          +     # que `glue_backfill_dedup.py` para Silver).
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "cb6dc670fef14d383aaa366eb184d811" -> "f919944ff6593ee881f3d4d2a4c57ecf"
      ~ id                            = "glue-scripts/meteorologia_backfill_dedup_gold-cb6dc670fef14d383aaa366eb184d811.py" -> (known after apply)
      ~ key                           = "glue-scripts/meteorologia_backfill_dedup_gold-cb6dc670fef14d383aaa366eb184d811.py" -> "glue-scripts/meteorologia_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_meteorologia_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_meteorologia_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_bronze_to_silver-3fcf5c38a2dd24e79206eb53af97348a.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `meteorologia`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `meteorologia`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (pivote ancho->largo,
          + Reutiliza toda la lógica de negocio de `transform.py` (pivote ancho->largo,
          - puerta de calidad) tal cual -- este módulo solo es el "pegamento" de
          + puerta de calidad) tal cual -- este módulo solo es el "pegamento" de
          - Spark/Glue: leer Bronze, aplicar `bronze_to_silver` fila a fila vía
          + Spark/Glue: leer Bronze, aplicar `bronze_to_silver` fila a fila vía
          - `rdd.mapPartitions` (una fila Bronze de entrada puede producir varias filas
          + `rdd.mapPartitions` (una fila Bronze de entrada puede producir varias filas
          - Silver de salida, una por magnitud -- ver docstring de `transform.py`),
          + Silver de salida, una por magnitud -- ver docstring de `transform.py`),
          - añadir las columnas auxiliares que necesita `ge_suite.py`
          + añadir las columnas auxiliares que necesita `ge_suite.py`
          - (`_with_plausible_range_columns`) y escribir el resultado.
          + (`_with_plausible_range_columns`) y escribir el resultado.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/meteorologia/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/meteorologia/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - from procesamiento.silver_gold.meteorologia.ge_suite import run_quality_report
          + from procesamiento.silver_gold.meteorologia.ge_suite import run_quality_report
          - from procesamiento.silver_gold.meteorologia.transform import PLAUSIBLE_RANGE_BY_MAGNITUDE, bronze_to_silver
          + from procesamiento.silver_gold.meteorologia.transform import PLAUSIBLE_RANGE_BY_MAGNITUDE, bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -         StructField("altitude_m", IntegerType(), True),
          +         StructField("altitude_m", IntegerType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("station_id", StringType(), False),
          +         StructField("station_id", StringType(), False),
          -         StructField("station_name", StringType(), True),
          +         StructField("station_name", StringType(), True),
          -         StructField("station_address", StringType(), True),
          +         StructField("station_address", StringType(), True),
          -         StructField("magnitude", StringType(), False),
          +         StructField("magnitude", StringType(), False),
          -         StructField("value", DoubleType(), False),
          +         StructField("value", DoubleType(), False),
          -         StructField("measured_at", StringType(), False),
          +         StructField("measured_at", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         station_id=silver_record["station_id"],
          +         station_id=silver_record["station_id"],
          -         station_name=silver_record["station_name"],
          +         station_name=silver_record["station_name"],
          -         station_address=silver_record["station_address"],
          +         station_address=silver_record["station_address"],
          -         magnitude=silver_record["magnitude"],
          +         magnitude=silver_record["magnitude"],
          -         value=silver_record["value"],
          +         value=silver_record["value"],
          -         measured_at=silver_record["measured_at"],
          +         measured_at=silver_record["measured_at"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -             altitude_m=location["altitude_m"],
          +             altitude_m=location["altitude_m"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor).
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor).
          - 
          + 
          -     Cada fila Bronze de entrada (una estación, un instante, hasta 8
          +     Cada fila Bronze de entrada (una estación, un instante, hasta 8
          -     magnitudes) puede producir varias filas Silver de salida -- de ahí
          +     magnitudes) puede producir varias filas Silver de salida -- de ahí
          -     `mapPartitions` en vez de un simple `map` 1:1.
          +     `mapPartitions` en vez de un simple `map` 1:1.
          -     """
          +     """
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def _with_plausible_range_columns(silver_df):
          + def _with_plausible_range_columns(silver_df):
          -     """Añade las columnas auxiliares que `ge_suite.py` valida como `<= 0`.
          +     """Añade las columnas auxiliares que `ge_suite.py` valida como `<= 0`.
          - 
          + 
          -     GX no tiene una expectation nativa de "el rango depende del valor de
          +     GX no tiene una expectation nativa de "el rango depende del valor de
          -     otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
          +     otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
          -     `transform.PLAUSIBLE_RANGE_BY_MAGNITUDE` a dos expresiones `when/otherwise`
          +     `transform.PLAUSIBLE_RANGE_BY_MAGNITUDE` a dos expresiones `when/otherwise`
          -     de Spark en vez de repetir la tabla como una segunda fuente de verdad --
          +     de Spark en vez de repetir la tabla como una segunda fuente de verdad --
          -     una magnitud sin entrada en la tabla (no debería ocurrir) usa
          +     una magnitud sin entrada en la tabla (no debería ocurrir) usa
          -     `(-inf, inf)` como rango, igual que `transform.validate_magnitude_value`
          +     `(-inf, inf)` como rango, igual que `transform.validate_magnitude_value`
          -     no aplica ningún tope en ese caso.
          +     no aplica ningún tope en ese caso.
          -     """
          +     """
          -     min_expr = F.lit(float("-inf"))
          +     min_expr = F.lit(float("-inf"))
          -     max_expr = F.lit(float("inf"))
          +     max_expr = F.lit(float("inf"))
          -     for magnitude, (min_value, max_value) in PLAUSIBLE_RANGE_BY_MAGNITUDE.items():
          +     for magnitude, (min_value, max_value) in PLAUSIBLE_RANGE_BY_MAGNITUDE.items():
          -         min_expr = F.when(F.col("magnitude") == magnitude, F.lit(float(min_value))).otherwise(min_expr)
          +         min_expr = F.when(F.col("magnitude") == magnitude, F.lit(float(min_value))).otherwise(min_expr)
          -         max_expr = F.when(F.col("magnitude") == magnitude, F.lit(float(max_value))).otherwise(max_expr)
          +         max_expr = F.when(F.col("magnitude") == magnitude, F.lit(float(max_value))).otherwise(max_expr)
          -     return silver_df.withColumn("value_below_plausible_min", min_expr - F.col("value")).withColumn(
          +     return silver_df.withColumn("value_below_plausible_min", min_expr - F.col("value")).withColumn(
          -         "value_over_plausible_max", F.col("value") - max_expr
          +         "value_over_plausible_max", F.col("value") - max_expr
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          +     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          -     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          +     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          -     # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
          +     # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
          -     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          +     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          -     # termina sin error pero nunca escribe la partición que espera Gold).
          +     # termina sin error pero nunca escribe la partición que espera Gold).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          +     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          -     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          +     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          -     # completo, que crecia sin limite y disparo el coste real de Glue
          +     # completo, que crecia sin limite y disparo el coste real de Glue
          -     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          +     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          +     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, _with_plausible_range_columns(silver_df))
          +     quality_report = run_quality_report(gx_context, _with_plausible_range_columns(silver_df))
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"meteorologia_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"meteorologia_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          -     # para que un consumidor ya familiarizado con Bronze no tenga que
          +     # para que un consumidor ya familiarizado con Bronze no tenga que
          -     # aprender un esquema de partición distinto para Silver.
          +     # aprender un esquema de partición distinto para Silver.
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "3fcf5c38a2dd24e79206eb53af97348a" -> "9f8c92a3c75695ffe310682ba8d437b0"
      ~ id                            = "glue-scripts/meteorologia_bronze_to_silver-3fcf5c38a2dd24e79206eb53af97348a.py" -> (known after apply)
      ~ key                           = "glue-scripts/meteorologia_bronze_to_silver-3fcf5c38a2dd24e79206eb53af97348a.py" -> "glue-scripts/meteorologia_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_meteorologia_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_meteorologia_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/meteorologia_silver_to_gold-4fb287e094c6f4dd3cb17585cbde692e.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `meteorologia` (valor medio/máx/mín por
          + """Job de AWS Glue: Silver -> Gold del dataset `meteorologia` (valor medio/máx/mín por
          - estación, magnitud y hora).
          + estación, magnitud y hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          + mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/meteorologia_por_estacion_magnitud_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/meteorologia_por_estacion_magnitud_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          +     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          -     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          +     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          +     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha`/`hora` son columnas de partición de Silver (ver
          +     # `fecha`/`hora` son columnas de partición de Silver (ver
          -     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          +     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          -     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          +     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          -     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          +     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(silver_partition_path)
          +         spark.read.parquet(silver_partition_path)
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          +     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          +     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
          +     # partition pruning si `silver_path` acota un rango de fechas concreto.
          -     # `magnitude` entra en la clave de agrupación (a diferencia de tráfico/
          +     # `magnitude` entra en la clave de agrupación (a diferencia de tráfico/
          -     # transporte_publico_emt/bicimad/aparcamientos): una misma estación
          +     # transporte_publico_emt/bicimad/aparcamientos): una misma estación
          -     # reporta varias magnitudes a la vez, ver docstring de `aggregate.py`.
          +     # reporta varias magnitudes a la vez, ver docstring de `aggregate.py`.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("station_id", "magnitude", "fecha", "hora")
          +         silver_df.groupBy("station_id", "magnitude", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("station_name", ignorenulls=True).alias("station_name"),
          +             F.first("station_name", ignorenulls=True).alias("station_name"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("value").alias("avg_value"),
          +             F.avg("value").alias("avg_value"),
          -             F.max("value").alias("max_value"),
          +             F.max("value").alias("max_value"),
          -             F.min("value").alias("min_value"),
          +             F.min("value").alias("min_value"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -             F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          +             F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # estación, magnitud y hora, no cada ~20 minutos): particionar solo por
          +     # estación, magnitud y hora, no cada ~20 minutos): particionar solo por
          -     # `date` es suficiente para podar particiones sin generar ficheros
          +     # `date` es suficiente para podar particiones sin generar ficheros
          -     # diminutos.
          +     # diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "4fb287e094c6f4dd3cb17585cbde692e" -> "169c14fd98eac491489861d9e5192564"
      ~ id                            = "glue-scripts/meteorologia_silver_to_gold-4fb287e094c6f4dd3cb17585cbde692e.py" -> (known after apply)
      ~ key                           = "glue-scripts/meteorologia_silver_to_gold-4fb287e094c6f4dd3cb17585cbde692e.py" -> "glue-scripts/meteorologia_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_ruido_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_ruido_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_backfill_dedup-2cf7215ae11978fc12206039bba3aece.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `ruido` (tarea 077, mismo patrón que
          + `ruido` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).
          - 
          + 
          - **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 053, arreglado en la tarea 076) lee solo la partición Bronze del día
          + (tarea 053, arreglado en la tarea 076) lee solo la partición Bronze del día
          - de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          + de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
          - histórico", así que no sirve para reconstruir Silver desde cero. Este script
          + histórico", así que no sirve para reconstruir Silver desde cero. Este script
          - existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          + existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
          - deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          + deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
          - hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          + hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
          - todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          + todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
          - Athena real (ver `doc/077-...md`): `n=6` para el mismo
          + Athena real (ver `doc/077-...md`): `n=6` para el mismo
          - (`station_id`, `period`, `measured_date`).
          + (`station_id`, `period`, `measured_date`).
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          + lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).
          - 
          + 
          - `(station_id, period, measured_date)` es la clave natural del dataset (misma
          + `(station_id, period, measured_date)` es la clave natural del dataset (misma
          - clave que agrupa `aggregate.py` para el resumen diario -- ver
          + clave que agrupa `aggregate.py` para el resumen diario -- ver
          - `glue_silver_to_gold.py`, "Resumen diario por estación+periodo+día").
          + `glue_silver_to_gold.py`, "Resumen diario por estación+periodo+día").
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          + de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
          - `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          + `SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/ruido/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/ruido/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - 
          + 
          - from procesamiento.silver_gold.ruido.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.ruido.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - from procesamiento.silver_gold.ruido.ge_suite import run_quality_report
          + from procesamiento.silver_gold.ruido.ge_suite import run_quality_report
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez.
          +     # el histórico de Bronze de una vez.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba. Clave natural: estación + periodo
          +     # La deduplicación real que faltaba. Clave natural: estación + periodo
          -     # (D/E/T/N) + día medido -- misma clave que agrupa `aggregate.py`.
          +     # (D/E/T/N) + día medido -- misma clave que agrupa `aggregate.py`.
          -     silver_df = silver_df.dropDuplicates(["station_id", "period", "measured_date"])
          +     silver_df = silver_df.dropDuplicates(["station_id", "period", "measured_date"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"ruido_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"ruido_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Partición solo por `fecha` (derivada de `measured_date`), igual que el
          +     # Partición solo por `fecha` (derivada de `measured_date`), igual que el
          -     # pipeline de producción -- esta fuente es diaria, sin hora real.
          +     # pipeline de producción -- esta fuente es diaria, sin hora real.
          -     silver_partitioned = silver_df.withColumn("fecha", silver_df["measured_date"])
          +     silver_partitioned = silver_df.withColumn("fecha", silver_df["measured_date"])
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo.
          +     # prefijo de destino debe estar vacío antes de lanzarlo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha").parquet(args["silver_path"])
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha").parquet(args["silver_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "2cf7215ae11978fc12206039bba3aece" -> "fce8661c6ea351323d8dbec6a79e1377"
      ~ id                            = "glue-scripts/ruido_backfill_dedup-2cf7215ae11978fc12206039bba3aece.py" -> (known after apply)
      ~ key                           = "glue-scripts/ruido_backfill_dedup-2cf7215ae11978fc12206039bba3aece.py" -> "glue-scripts/ruido_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_ruido_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_ruido_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_backfill_dedup_gold-db9317465c5f82d4c56c9faae1e83723.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `ruido` (tarea 077, mismo patrón que
          + `ruido` (tarea 077, mismo patrón que
          - `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          + `procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 053/076), que solo lee una ventana de los últimos
          + tarea 053/076), que solo lee una ventana de los últimos
          - `ROLLING_WINDOW_DAYS` días y escribe únicamente la fila de HOY (`append`).
          + `ROLLING_WINDOW_DAYS` días y escribe únicamente la fila de HOY (`append`).
          - Este job existe para recalcular Gold desde cero tras la reconstrucción
          + Este job existe para recalcular Gold desde cero tras la reconstrucción
          - deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          + deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
          - histórico de Silver de una vez, calcula la media móvil de 7 días con la
          + histórico de Silver de una vez, calcula la media móvil de 7 días con la
          - MISMA lógica de ventana de calendario (`Window.rangeBetween` sobre
          + MISMA lógica de ventana de calendario (`Window.rangeBetween` sobre
          - `date_epoch_days`, ver docstring de `glue_silver_to_gold.py`) pero sobre el
          + `date_epoch_days`, ver docstring de `glue_silver_to_gold.py`) pero sobre el
          - histórico completo en vez de una ventana de 8 días, y escribe TODAS las
          + histórico completo en vez de una ventana de 8 días, y escribe TODAS las
          - filas resultantes (no solo la de hoy) con `overwrite` en vez de `append` --
          + filas resultantes (no solo la de hoy) con `overwrite` en vez de `append` --
          - a diferencia del pipeline incremental, aquí no hay "días ya escritos en
          + a diferencia del pipeline incremental, aquí no hay "días ya escritos en
          - ejecuciones anteriores" que evitar duplicar: es una reconstrucción total de
          + ejecuciones anteriores" que evitar duplicar: es una reconstrucción total de
          - una sola vez.
          + una sola vez.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/ruido_por_estacion_periodo_fecha/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/ruido_por_estacion_periodo_fecha/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.window import Window
          + from pyspark.sql.window import Window
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - ROLLING_WINDOW_DAYS = 7
          + ROLLING_WINDOW_DAYS = 7
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- necesario para calcular
          +     # el histórico de Silver de una vez -- necesario para calcular
          -     # correctamente la media móvil de todos los días, no solo los últimos 8.
          +     # correctamente la media móvil de todos los días, no solo los últimos 8.
          -     silver_df = spark.read.parquet(args["silver_path"])
          +     silver_df = spark.read.parquet(args["silver_path"])
          - 
          + 
          -     daily_df = silver_df.groupBy("station_id", "period", "measured_date").agg(
          +     daily_df = silver_df.groupBy("station_id", "period", "measured_date").agg(
          -         F.count(F.lit(1)).alias("samples_count"),
          +         F.count(F.lit(1)).alias("samples_count"),
          -         F.first("station_name", ignorenulls=True).alias("station_name"),
          +         F.first("station_name", ignorenulls=True).alias("station_name"),
          -         F.first("period_name", ignorenulls=True).alias("period_name"),
          +         F.first("period_name", ignorenulls=True).alias("period_name"),
          -         F.first("district", ignorenulls=True).alias("district"),
          +         F.first("district", ignorenulls=True).alias("district"),
          -         F.first("neighbourhood", ignorenulls=True).alias("neighbourhood"),
          +         F.first("neighbourhood", ignorenulls=True).alias("neighbourhood"),
          -         F.avg("laeq_db").alias("avg_laeq_db"),
          +         F.avg("laeq_db").alias("avg_laeq_db"),
          -         F.max("laeq_db").alias("max_laeq_db"),
          +         F.max("laeq_db").alias("max_laeq_db"),
          -         F.min("laeq_db").alias("min_laeq_db"),
          +         F.min("laeq_db").alias("min_laeq_db"),
          -         F.avg("l1_db").alias("avg_l1_db"),
          +         F.avg("l1_db").alias("avg_l1_db"),
          -         F.avg("l10_db").alias("avg_l10_db"),
          +         F.avg("l10_db").alias("avg_l10_db"),
          -         F.avg("l50_db").alias("avg_l50_db"),
          +         F.avg("l50_db").alias("avg_l50_db"),
          -         F.avg("l90_db").alias("avg_l90_db"),
          +         F.avg("l90_db").alias("avg_l90_db"),
          -         F.avg("l99_db").alias("avg_l99_db"),
          +         F.avg("l99_db").alias("avg_l99_db"),
          -         F.first("location.lat", ignorenulls=True).alias("lat"),
          +         F.first("location.lat", ignorenulls=True).alias("lat"),
          -         F.first("location.lon", ignorenulls=True).alias("lon"),
          +         F.first("location.lon", ignorenulls=True).alias("lon"),
          -         F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          +         F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          -     )
          +     )
          - 
          + 
          -     daily_df = daily_df.withColumn(
          +     daily_df = daily_df.withColumn(
          -         "date_epoch_days", F.datediff(F.to_date("measured_date"), F.lit("1970-01-01"))
          +         "date_epoch_days", F.datediff(F.to_date("measured_date"), F.lit("1970-01-01"))
          -     )
          +     )
          - 
          + 
          -     rolling_window = (
          +     rolling_window = (
          -         Window.partitionBy("station_id", "period")
          +         Window.partitionBy("station_id", "period")
          -         .orderBy("date_epoch_days")
          +         .orderBy("date_epoch_days")
          -         .rangeBetween(-(ROLLING_WINDOW_DAYS - 1), 0)
          +         .rangeBetween(-(ROLLING_WINDOW_DAYS - 1), 0)
          -     )
          +     )
          - 
          + 
          -     gold_df = (
          +     gold_df = (
          -         daily_df.withColumn("laeq_rolling_7d_avg_db", F.avg("avg_laeq_db").over(rolling_window))
          +         daily_df.withColumn("laeq_rolling_7d_avg_db", F.avg("avg_laeq_db").over(rolling_window))
          -         .withColumn("laeq_rolling_7d_days", F.count("avg_laeq_db").over(rolling_window))
          +         .withColumn("laeq_rolling_7d_days", F.count("avg_laeq_db").over(rolling_window))
          -         .drop("date_epoch_days")
          +         .drop("date_epoch_days")
          -         .withColumnRenamed("measured_date", "date")
          +         .withColumnRenamed("measured_date", "date")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero, con
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero, con
          -     # TODAS las filas (no solo la de hoy, a diferencia del pipeline
          +     # TODAS las filas (no solo la de hoy, a diferencia del pipeline
          -     # incremental) -- el prefijo de destino debe estar vacío antes de
          +     # incremental) -- el prefijo de destino debe estar vacío antes de
          -     # lanzarlo.
          +     # lanzarlo.
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "db9317465c5f82d4c56c9faae1e83723" -> "f687c85eeca0b75468cfe68bb01c48c3"
      ~ id                            = "glue-scripts/ruido_backfill_dedup_gold-db9317465c5f82d4c56c9faae1e83723.py" -> (known after apply)
      ~ key                           = "glue-scripts/ruido_backfill_dedup_gold-db9317465c5f82d4c56c9faae1e83723.py" -> "glue-scripts/ruido_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_ruido_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_ruido_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_bronze_to_silver-57461bb981d80490227ccb4922409ef9.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `ruido`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `ruido`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que el resto de datasets del patrón, ver
          + sin `terraform apply`, que el resto de datasets del patrón, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
          - y escribir el resultado.
          + y escribir el resultado.
          - 
          + 
          - **Partición de Silver: solo `fecha`, sin `hora`** -- a diferencia del resto
          + **Partición de Silver: solo `fecha`, sin `hora`** -- a diferencia del resto
          - de datasets del patrón (partición `fecha=/hora=`, derivada de un
          + de datasets del patrón (partición `fecha=/hora=`, derivada de un
          - `measured_at` con instante), esta fuente es diaria (`measured_date` es una
          + `measured_at` con instante), esta fuente es diaria (`measured_date` es una
          - fecha, no un timestamp -- ver `transform.py`), así que no hay ninguna hora
          + fecha, no un timestamp -- ver `transform.py`), así que no hay ninguna hora
          - real que particionar.
          + real que particionar.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/ruido/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/ruido/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     daily_partition_uri,
          +     daily_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     today,
          +     today,
          - )
          + )
          - from procesamiento.silver_gold.ruido.ge_suite import run_quality_report
          + from procesamiento.silver_gold.ruido.ge_suite import run_quality_report
          - from procesamiento.silver_gold.ruido.transform import bronze_to_silver
          + from procesamiento.silver_gold.ruido.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -         StructField("altitude_m", IntegerType(), True),
          +         StructField("altitude_m", IntegerType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("station_id", StringType(), False),
          +         StructField("station_id", StringType(), False),
          -         StructField("station_name", StringType(), True),
          +         StructField("station_name", StringType(), True),
          -         StructField("station_address", StringType(), True),
          +         StructField("station_address", StringType(), True),
          -         StructField("district", StringType(), True),
          +         StructField("district", StringType(), True),
          -         StructField("neighbourhood", StringType(), True),
          +         StructField("neighbourhood", StringType(), True),
          -         StructField("period", StringType(), False),
          +         StructField("period", StringType(), False),
          -         StructField("period_name", StringType(), True),
          +         StructField("period_name", StringType(), True),
          -         StructField("measured_date", StringType(), False),
          +         StructField("measured_date", StringType(), False),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("laeq_db", DoubleType(), False),
          +         StructField("laeq_db", DoubleType(), False),
          -         StructField("l1_db", DoubleType(), True),
          +         StructField("l1_db", DoubleType(), True),
          -         StructField("l10_db", DoubleType(), True),
          +         StructField("l10_db", DoubleType(), True),
          -         StructField("l50_db", DoubleType(), True),
          +         StructField("l50_db", DoubleType(), True),
          -         StructField("l90_db", DoubleType(), True),
          +         StructField("l90_db", DoubleType(), True),
          -         StructField("l99_db", DoubleType(), True),
          +         StructField("l99_db", DoubleType(), True),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         station_id=silver_record["station_id"],
          +         station_id=silver_record["station_id"],
          -         station_name=silver_record["station_name"],
          +         station_name=silver_record["station_name"],
          -         station_address=silver_record["station_address"],
          +         station_address=silver_record["station_address"],
          -         district=silver_record["district"],
          +         district=silver_record["district"],
          -         neighbourhood=silver_record["neighbourhood"],
          +         neighbourhood=silver_record["neighbourhood"],
          -         period=silver_record["period"],
          +         period=silver_record["period"],
          -         period_name=silver_record["period_name"],
          +         period_name=silver_record["period_name"],
          -         measured_date=silver_record["measured_date"],
          +         measured_date=silver_record["measured_date"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         laeq_db=silver_record["laeq_db"],
          +         laeq_db=silver_record["laeq_db"],
          -         l1_db=silver_record["l1_db"],
          +         l1_db=silver_record["l1_db"],
          -         l10_db=silver_record["l10_db"],
          +         l10_db=silver_record["l10_db"],
          -         l50_db=silver_record["l50_db"],
          +         l50_db=silver_record["l50_db"],
          -         l90_db=silver_record["l90_db"],
          +         l90_db=silver_record["l90_db"],
          -         l99_db=silver_record["l99_db"],
          +         l99_db=silver_record["l99_db"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -             altitude_m=location["altitude_m"],
          +             altitude_m=location["altitude_m"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          +     # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
          -     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          +     # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
          -     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          +     # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
          -     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          +     # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
          -     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          +     # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
          -     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          +     # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
          -     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          +     # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha = today(processed_at)
          +     fecha = today(processed_at)
          -     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          +     bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"ruido_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"ruido_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Partición solo por `fecha` (derivada de `measured_date`, ya una cadena
          +     # Partición solo por `fecha` (derivada de `measured_date`, ya una cadena
          -     # "yyyy-MM-dd") -- ver docstring del módulo, esta fuente no tiene
          +     # "yyyy-MM-dd") -- ver docstring del módulo, esta fuente no tiene
          -     # ninguna hora real que particionar.
          +     # ninguna hora real que particionar.
          -     (
          +     (
          -         silver_df.withColumn("fecha", silver_df["measured_date"])
          +         silver_df.withColumn("fecha", silver_df["measured_date"])
          -         .write.mode("append")
          +         .write.mode("append")
          -         .partitionBy("fecha")
          +         .partitionBy("fecha")
          -         .parquet(args["silver_path"])
          +         .parquet(args["silver_path"])
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "57461bb981d80490227ccb4922409ef9" -> "4578e5651d5577da838113244d5be142"
      ~ id                            = "glue-scripts/ruido_bronze_to_silver-57461bb981d80490227ccb4922409ef9.py" -> (known after apply)
      ~ key                           = "glue-scripts/ruido_bronze_to_silver-57461bb981d80490227ccb4922409ef9.py" -> "glue-scripts/ruido_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_ruido_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_ruido_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/ruido_silver_to_gold-77502f7109487420c57b7e41102616e3.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `ruido` (resumen diario por
          + """Job de AWS Glue: Silver -> Gold del dataset `ruido` (resumen diario por
          - estación y periodo, más media móvil de 7 días de LAeq).
          + estación y periodo, más media móvil de 7 días de LAeq).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` + ventana
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` + ventana
          - correcta a través de múltiples particiones/ficheros de Silver necesita las
          + correcta a través de múltiples particiones/ficheros de Silver necesita las
          - primitivas nativas de reduce/window distribuido de Spark, no un
          + primitivas nativas de reduce/window distribuido de Spark, no un
          - `mapPartitions` fila a fila -- mismo motivo que el resto de datasets del
          + `mapPartitions` fila a fila -- mismo motivo que el resto de datasets del
          - patrón. `aggregate.py` sigue siendo la fuente de verdad **documental y de
          + patrón. `aggregate.py` sigue siendo la fuente de verdad **documental y de
          - test** de qué agrega Gold (incluida la media móvil de 7 días, ver su
          + test** de qué agrega Gold (incluida la media móvil de 7 días, ver su
          - docstring para el razonamiento completo); las expresiones de Spark de este
          + docstring para el razonamiento completo); las expresiones de Spark de este
          - job están escritas para producir exactamente el mismo esquema de salida que
          + job están escritas para producir exactamente el mismo esquema de salida que
          - `aggregate.aggregate_silver_to_gold`; un cambio en uno debe reflejarse en el
          + `aggregate.aggregate_silver_to_gold`; un cambio en uno debe reflejarse en el
          - otro.
          + otro.
          - 
          + 
          - La media móvil usa `Window.rangeBetween` (no `rowsBetween`) sobre
          + La media móvil usa `Window.rangeBetween` (no `rowsBetween`) sobre
          - `date_epoch_days` (días desde 1970-01-01, columna numérica auxiliar) para
          + `date_epoch_days` (días desde 1970-01-01, columna numérica auxiliar) para
          - que la ventana sea de **calendario** (día actual - 6 días hasta día actual),
          + que la ventana sea de **calendario** (día actual - 6 días hasta día actual),
          - no de "últimas 7 filas" -- un hueco de fin de semana/festivo (la Red Fija
          + no de "últimas 7 filas" -- un hueco de fin de semana/festivo (la Red Fija
          - del SIVCA no publica esos días) reduce cuántos días reales entran en la
          + del SIVCA no publica esos días) reduce cuántos días reales entran en la
          - ventana en vez de desplazarla, igual que hace `aggregate.py` en Python puro.
          + ventana en vez de desplazarla, igual que hace `aggregate.py` en Python puro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/ruido_por_estacion_periodo_fecha/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/ruido_por_estacion_periodo_fecha/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - from pyspark.sql.window import Window
          + from pyspark.sql.window import Window
          - 
          + 
          - from procesamiento.silver_gold.incremental import date_range, existing_daily_partitions, today
          + from procesamiento.silver_gold.incremental import date_range, existing_daily_partitions, today
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - ROLLING_WINDOW_DAYS = 7
          + ROLLING_WINDOW_DAYS = 7
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, `to_date`
          +     # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, `to_date`
          -     # sobre columnas con componente de hora calcularia en UTC. `measured_date`
          +     # sobre columnas con componente de hora calcularia en UTC. `measured_date`
          -     # ya es una fecha pura sin hora (ver transform.py), así que este job en
          +     # ya es una fecha pura sin hora (ver transform.py), así que este job en
          -     # concreto no depende del timezone de sesión para su cálculo actual --
          +     # concreto no depende del timezone de sesión para su cálculo actual --
          -     # se fija de todos modos por consistencia defensiva con el resto del
          +     # se fija de todos modos por consistencia defensiva con el resto del
          -     # patrón, para que un futuro cambio que añada un `to_timestamp` no
          +     # patrón, para que un futuro cambio que añada un `to_timestamp` no
          -     # reintroduzca el bug en silencio.
          +     # reintroduzca el bug en silencio.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 076) -- excepcion explicita al patron del
          +     # Lectura incremental (tarea 076) -- excepcion explicita al patron del
          -     # resto del grupo diario (leer solo la particion de Silver de hoy): la
          +     # resto del grupo diario (leer solo la particion de Silver de hoy): la
          -     # media movil de `ROLLING_WINDOW_DAYS` dias necesita, para calcular
          +     # media movil de `ROLLING_WINDOW_DAYS` dias necesita, para calcular
          -     # correctamente la fila de HOY, los `ROLLING_WINDOW_DAYS - 1` dias
          +     # correctamente la fila de HOY, los `ROLLING_WINDOW_DAYS - 1` dias
          -     # anteriores como contexto -- leer solo hoy rompería la media (un
          +     # anteriores como contexto -- leer solo hoy rompería la media (un
          -     # `Window.rangeBetween` sin las filas anteriores en el DataFrame de
          +     # `Window.rangeBetween` sin las filas anteriores en el DataFrame de
          -     # entrada simplemente no las encuentra, degradando en silencio a una
          +     # entrada simplemente no las encuentra, degradando en silencio a una
          -     # media de menos de 7 dias). Se leen los ultimos `ROLLING_WINDOW_DAYS`
          +     # media de menos de 7 dias). Se leen los ultimos `ROLLING_WINDOW_DAYS`
          -     # dias (8 con hoy incluido, un dia de margen sobre el minimo estricto de
          +     # dias (8 con hoy incluido, un dia de margen sobre el minimo estricto de
          -     # 7) en vez de todo el historico, y luego se filtra la SALIDA a la fila
          +     # 7) en vez de todo el historico, y luego se filtra la SALIDA a la fila
          -     # de hoy antes de escribir (ver mas abajo) -- así solo se reescribe una
          +     # de hoy antes de escribir (ver mas abajo) -- así solo se reescribe una
          -     # vez cada dia, sin volver a `append`-ear los dias ya calculados en
          +     # vez cada dia, sin volver a `append`-ear los dias ya calculados en
          -     # ejecuciones anteriores dentro de la ventana de lectura.
          +     # ejecuciones anteriores dentro de la ventana de lectura.
          -     fechas_ventana = date_range(processed_at, -ROLLING_WINDOW_DAYS, 0)
          +     fechas_ventana = date_range(processed_at, -ROLLING_WINDOW_DAYS, 0)
          -     s3_client = boto3.client("s3")
          +     s3_client = boto3.client("s3")
          -     existing_partitions = existing_daily_partitions(s3_client, args["silver_path"], fechas_ventana)
          +     existing_partitions = existing_daily_partitions(s3_client, args["silver_path"], fechas_ventana)
          -     if not existing_partitions:
          +     if not existing_partitions:
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     silver_df = None
          +     silver_df = None
          -     for _fecha, partition_uri in existing_partitions:
          +     for _fecha, partition_uri in existing_partitions:
          -         partition_df = spark.read.parquet(partition_uri)
          +         partition_df = spark.read.parquet(partition_uri)
          -         silver_df = partition_df if silver_df is None else silver_df.unionByName(partition_df)
          +         silver_df = partition_df if silver_df is None else silver_df.unionByName(partition_df)
          - 
          + 
          -     # Resumen diario por estación+periodo+día -- ver docstring de
          +     # Resumen diario por estación+periodo+día -- ver docstring de
          -     # `aggregate.py` para el porqué de esta clave (la fuente ya es diaria,
          +     # `aggregate.py` para el porqué de esta clave (la fuente ya es diaria,
          -     # no hay ninguna hora que agregar).
          +     # no hay ninguna hora que agregar).
          -     daily_df = silver_df.groupBy("station_id", "period", "measured_date").agg(
          +     daily_df = silver_df.groupBy("station_id", "period", "measured_date").agg(
          -         F.count(F.lit(1)).alias("samples_count"),
          +         F.count(F.lit(1)).alias("samples_count"),
          -         F.first("station_name", ignorenulls=True).alias("station_name"),
          +         F.first("station_name", ignorenulls=True).alias("station_name"),
          -         F.first("period_name", ignorenulls=True).alias("period_name"),
          +         F.first("period_name", ignorenulls=True).alias("period_name"),
          -         F.first("district", ignorenulls=True).alias("district"),
          +         F.first("district", ignorenulls=True).alias("district"),
          -         F.first("neighbourhood", ignorenulls=True).alias("neighbourhood"),
          +         F.first("neighbourhood", ignorenulls=True).alias("neighbourhood"),
          -         F.avg("laeq_db").alias("avg_laeq_db"),
          +         F.avg("laeq_db").alias("avg_laeq_db"),
          -         F.max("laeq_db").alias("max_laeq_db"),
          +         F.max("laeq_db").alias("max_laeq_db"),
          -         F.min("laeq_db").alias("min_laeq_db"),
          +         F.min("laeq_db").alias("min_laeq_db"),
          -         F.avg("l1_db").alias("avg_l1_db"),
          +         F.avg("l1_db").alias("avg_l1_db"),
          -         F.avg("l10_db").alias("avg_l10_db"),
          +         F.avg("l10_db").alias("avg_l10_db"),
          -         F.avg("l50_db").alias("avg_l50_db"),
          +         F.avg("l50_db").alias("avg_l50_db"),
          -         F.avg("l90_db").alias("avg_l90_db"),
          +         F.avg("l90_db").alias("avg_l90_db"),
          -         F.avg("l99_db").alias("avg_l99_db"),
          +         F.avg("l99_db").alias("avg_l99_db"),
          -         F.first("location.lat", ignorenulls=True).alias("lat"),
          +         F.first("location.lat", ignorenulls=True).alias("lat"),
          -         F.first("location.lon", ignorenulls=True).alias("lon"),
          +         F.first("location.lon", ignorenulls=True).alias("lon"),
          -         F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          +         F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
          -     )
          +     )
          - 
          + 
          -     # Columna numérica auxiliar para poder usar `rangeBetween` (ventana de
          +     # Columna numérica auxiliar para poder usar `rangeBetween` (ventana de
          -     # calendario, no de "últimas N filas") -- ver docstring del módulo.
          +     # calendario, no de "últimas N filas") -- ver docstring del módulo.
          -     daily_df = daily_df.withColumn(
          +     daily_df = daily_df.withColumn(
          -         "date_epoch_days", F.datediff(F.to_date("measured_date"), F.lit("1970-01-01"))
          +         "date_epoch_days", F.datediff(F.to_date("measured_date"), F.lit("1970-01-01"))
          -     )
          +     )
          - 
          + 
          -     rolling_window = (
          +     rolling_window = (
          -         Window.partitionBy("station_id", "period")
          +         Window.partitionBy("station_id", "period")
          -         .orderBy("date_epoch_days")
          +         .orderBy("date_epoch_days")
          -         .rangeBetween(-(ROLLING_WINDOW_DAYS - 1), 0)
          +         .rangeBetween(-(ROLLING_WINDOW_DAYS - 1), 0)
          -     )
          +     )
          - 
          + 
          -     gold_df = (
          +     gold_df = (
          -         daily_df.withColumn("laeq_rolling_7d_avg_db", F.avg("avg_laeq_db").over(rolling_window))
          +         daily_df.withColumn("laeq_rolling_7d_avg_db", F.avg("avg_laeq_db").over(rolling_window))
          -         .withColumn("laeq_rolling_7d_days", F.count("avg_laeq_db").over(rolling_window))
          +         .withColumn("laeq_rolling_7d_days", F.count("avg_laeq_db").over(rolling_window))
          -         .drop("date_epoch_days")
          +         .drop("date_epoch_days")
          -         .withColumnRenamed("measured_date", "date")
          +         .withColumnRenamed("measured_date", "date")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Se escribe solo la fila de HOY (no toda la ventana de lectura, ver
          +     # Se escribe solo la fila de HOY (no toda la ventana de lectura, ver
          -     # comentario de la lectura incremental arriba): los días anteriores de
          +     # comentario de la lectura incremental arriba): los días anteriores de
          -     # la ventana ya se escribieron en sus propias ejecuciones -- volver a
          +     # la ventana ya se escribieron en sus propias ejecuciones -- volver a
          -     # escribirlos aquí duplicaría filas en Gold en `mode("append")`.
          +     # escribirlos aquí duplicaría filas en Gold en `mode("append")`.
          -     gold_df_today = gold_df.filter(F.col("date") == today(processed_at))
          +     gold_df_today = gold_df.filter(F.col("date") == today(processed_at))
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # estación, periodo y día, no varias lecturas): particionar solo por
          +     # estación, periodo y día, no varias lecturas): particionar solo por
          -     # `date` es suficiente para podar particiones sin generar ficheros
          +     # `date` es suficiente para podar particiones sin generar ficheros
          -     # diminutos.
          +     # diminutos.
          -     gold_df_today.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df_today.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "77502f7109487420c57b7e41102616e3" -> "df06da27741ea0c03b88aab3ac7e0a51"
      ~ id                            = "glue-scripts/ruido_silver_to_gold-77502f7109487420c57b7e41102616e3.py" -> (known after apply)
      ~ key                           = "glue-scripts/ruido_silver_to_gold-77502f7109487420c57b7e41102616e3.py" -> "glue-scripts/ruido_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/trafico_silver_to_gold-1884fa42b9e7b491c226ccb77bb38a49.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `trafico` (media por punto y hora).
          + """Job de AWS Glue: Silver -> Gold del dataset `trafico` (media por punto y hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que `glue_bronze_to_silver.py`:
          + **No ejecutado en esta tarea** (mismas condiciones que `glue_bronze_to_silver.py`:
          - piloto de solo código/infraestructura, sin Spark disponible en esta EC2 de
          + piloto de solo código/infraestructura, sin Spark disponible en esta EC2 de
          - desarrollo — ver `procesamiento/README.md`).
          + desarrollo — ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark (`avg`/`min`/`max`/`count` sobre
          + nativas de reduce distribuido de Spark (`avg`/`min`/`max`/`count` sobre
          - `DataFrame.groupBy`), no un `mapPartitions` fila a fila como en
          + `DataFrame.groupBy`), no un `mapPartitions` fila a fila como en
          - Bronze->Silver (ahí cada fila se transforma de forma independiente; aquí
          + Bronze->Silver (ahí cada fila se transforma de forma independiente; aquí
          - hace falta combinar filas que pueden vivir en particiones/ficheros
          + hace falta combinar filas que pueden vivir en particiones/ficheros
          - distintos antes de reducir). `aggregate.py` sigue siendo la fuente de
          + distintos antes de reducir). `aggregate.py` sigue siendo la fuente de
          - verdad **documental y de test** de qué agrega Gold — sus campos y semántica
          + verdad **documental y de test** de qué agrega Gold — sus campos y semántica
          - (qué es `avg_intensity_ratio`, cómo se deriva `samples_count`, etc., ver su
          + (qué es `avg_intensity_ratio`, cómo se deriva `samples_count`, etc., ver su
          - docstring) — y las expresiones de Spark de este job están escritas para
          + docstring) — y las expresiones de Spark de este job están escritas para
          - producir exactamente el mismo esquema de salida que
          + producir exactamente el mismo esquema de salida que
          - `aggregate.aggregate_silver_to_gold`; un cambio en uno debe reflejarse en el
          + `aggregate.aggregate_silver_to_gold`; un cambio en uno debe reflejarse en el
          - otro (ver `procesamiento/README.md`, tabla de correspondencia).
          + otro (ver `procesamiento/README.md`, tabla de correspondencia).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/trafico/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/trafico/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/trafico_por_punto_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/trafico_por_punto_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que en glue_bronze_to_silver.py: sin esto, la `hora`
          +     # Mismo motivo que en glue_bronze_to_silver.py: sin esto, la `hora`
          -     # recalculada aquí desde `measured_at` usaría el timezone de sesión de
          +     # recalculada aquí desde `measured_at` usaría el timezone de sesión de
          -     # Spark (UTC por defecto en Glue), desalineada con `previous_hour()`
          +     # Spark (UTC por defecto en Glue), desalineada con `previous_hour()`
          -     # (Europe/Madrid) y con la partición de Silver que este job intenta leer.
          +     # (Europe/Madrid) y con la partición de Silver que este job intenta leer.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          +     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha`/`hora` son columnas de partición de Silver (ver
          +     # `fecha`/`hora` son columnas de partición de Silver (ver
          -     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          +     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          -     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          +     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          -     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          +     # recalculan aquí desde `measured_at`, la misma columna que las originó.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(silver_partition_path)
          +         spark.read.parquet(silver_partition_path)
          -         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver
          +     # `fecha`/`hora` ya son las columnas de partición físicas de Silver
          -     # (ver glue_bronze_to_silver.py); agrupar por ellas permite a Spark
          +     # (ver glue_bronze_to_silver.py); agrupar por ellas permite a Spark
          -     # aprovechar partition pruning si `silver_path` acota un rango de
          +     # aprovechar partition pruning si `silver_path` acota un rango de
          -     # fechas concreto.
          +     # fechas concreto.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("point_id", "fecha", "hora")
          +         silver_df.groupBy("point_id", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.first("subarea", ignorenulls=True).alias("subarea"),
          +             F.first("subarea", ignorenulls=True).alias("subarea"),
          -             F.min("measured_at").alias("first_measured_at"),
          +             F.min("measured_at").alias("first_measured_at"),
          -             F.max("measured_at").alias("last_measured_at"),
          +             F.max("measured_at").alias("last_measured_at"),
          -             F.avg("intensity_vph").alias("avg_intensity_vph"),
          +             F.avg("intensity_vph").alias("avg_intensity_vph"),
          -             F.max("intensity_vph").alias("max_intensity_vph"),
          +             F.max("intensity_vph").alias("max_intensity_vph"),
          -             F.min("intensity_vph").alias("min_intensity_vph"),
          +             F.min("intensity_vph").alias("min_intensity_vph"),
          -             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          +             F.avg("occupancy_ratio").alias("avg_occupancy_ratio"),
          -             F.avg("load_ratio").alias("avg_load_ratio"),
          +             F.avg("load_ratio").alias("avg_load_ratio"),
          -             F.avg("intensity_ratio").alias("avg_intensity_ratio"),
          +             F.avg("intensity_ratio").alias("avg_intensity_ratio"),
          -             F.avg("service_level").alias("avg_service_level"),
          +             F.avg("service_level").alias("avg_service_level"),
          -             F.first("location.lat", ignorenulls=True).alias("lat"),
          +             F.first("location.lat", ignorenulls=True).alias("lat"),
          -             F.first("location.lon", ignorenulls=True).alias("lon"),
          +             F.first("location.lon", ignorenulls=True).alias("lon"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # punto de medida y hora, no cada ~5 minutos): particionar solo por
          +     # punto de medida y hora, no cada ~5 minutos): particionar solo por
          -     # `date` es suficiente para podar particiones en consultas típicas
          +     # `date` es suficiente para podar particiones en consultas típicas
          -     # ("dame el tráfico de tal día") sin generar ficheros diminutos por
          +     # ("dame el tráfico de tal día") sin generar ficheros diminutos por
          -     # cada hora, a diferencia de Silver.
          +     # cada hora, a diferencia de Silver.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "1884fa42b9e7b491c226ccb77bb38a49" -> "60a5f338a6cc68a8c760176719c0db97"
      ~ id                            = "glue-scripts/trafico_silver_to_gold-1884fa42b9e7b491c226ccb77bb38a49.py" -> (known after apply)
      ~ key                           = "glue-scripts/trafico_silver_to_gold-1884fa42b9e7b491c226ccb77bb38a49.py" -> "glue-scripts/trafico_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup must be replaced
+/- resource "aws_s3_object" "glue_script_transporte_publico_emt_backfill_dedup" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_backfill_dedup-961447ee3174a4e4ef33f1b6e006affa.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
          - `transporte_publico_emt`.
          + `transporte_publico_emt`.
          - 
          + 
          - **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          + **NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
          - (tarea 046, arreglado en la tarea 072) calcula internamente una única
          + (tarea 046, arreglado en la tarea 072) calcula internamente una única
          - hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          + hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
          - un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          + un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
          - reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          + reconstruir Silver desde cero. Este script existe únicamente para eso: leer
          - TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          + TODO el histórico de Bronze de una vez y deduplicar de verdad, tras
          - confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          + confirmar (tarea 075, ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`)
          - que cada ejecución histórica del job de producción (antes del arreglo de la
          + que cada ejecución histórica del job de producción (antes del arreglo de la
          - tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          + tarea 072) reprocesaba y reescribía todo el histórico acumulado sin
          - deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          + deduplicar -- mismo patrón que `bicimad`/`trafico` (tareas 072-074), aquí
          - verificado con una consulta Athena real sobre `(stop_id, line, bus_id,
          + verificado con una consulta Athena real sobre `(stop_id, line, bus_id,
          - ingested_at)` antes de escribir este script. Se lanza una sola vez a mano
          + ingested_at)` antes de escribir este script. Se lanza una sola vez a mano
          - (`aws glue start-job-run`), nunca vía trigger ni schedule.
          + (`aws glue start-job-run`), nunca vía trigger ni schedule.
          - 
          + 
          - Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          + Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
          - lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          + lanzarlo (borrado manual con `aws s3 rm --recursive`, mismo criterio que la
          - tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          + tarea 074 tras el fallo intermitente de `MultiObjectDeleteException` al
          - sobrescribir un prefijo con miles de objetos preexistentes): este script
          + sobrescribir un prefijo con miles de objetos preexistentes): este script
          - escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          + escribe con `mode("overwrite")`, no `append` -- si el prefijo no está vacío
          - de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          + de antemano, el resultado seguiría mezclando el dato viejo (ya duplicado)
          - con la reconstrucción.
          + con la reconstrucción.
          - 
          + 
          - Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          + Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
          - de Spark/GX que ya usa el pipeline de producción
          + de Spark/GX que ya usa el pipeline de producción
          - (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          + (`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
          - `_write_quality_report`.
          + `_write_quality_report`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen completo, p.ej.
          + - `bronze_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/transporte_publico_emt/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/transporte_publico_emt/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON, igual que el pipeline de
          +   validación de Great Expectations (un JSON, igual que el pipeline de
          -   producción).
          +   producción).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql.functions import date_format, to_timestamp
          + from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          - from procesamiento.silver_gold.transporte_publico_emt.ge_suite import run_quality_report
          + from procesamiento.silver_gold.transporte_publico_emt.ge_suite import run_quality_report
          - from procesamiento.silver_gold.transporte_publico_emt.glue_bronze_to_silver import (
          + from procesamiento.silver_gold.transporte_publico_emt.glue_bronze_to_silver import (
          -     SILVER_SCHEMA,
          +     SILVER_SCHEMA,
          -     _process_partition,
          +     _process_partition,
          -     _write_quality_report,
          +     _write_quality_report,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          +     # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
          -     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          +     # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
          -     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          +     # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
          -     # con la hora de Madrid real de `ingested_at`.
          +     # con la hora de Madrid real de `ingested_at`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          +     # el histórico de Bronze de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa.
          +     # reconstrucción completa.
          -     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          +     bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          - 
          + 
          -     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          +     # La deduplicación real que faltaba: reprocesar el mismo histórico de
          -     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          +     # Bronze en cada ejecución (antes de la tarea 072) dejaba el mismo
          -     # registro repetido decenas de veces. Un cuarteto (stop_id, line, bus_id,
          +     # registro repetido decenas de veces. Un cuarteto (stop_id, line, bus_id,
          -     # ingested_at) identifica de forma única una estimación de llegada real
          +     # ingested_at) identifica de forma única una estimación de llegada real
          -     # de un mismo lote de ingesta.
          +     # de un mismo lote de ingesta.
          -     silver_df = silver_df.dropDuplicates(["stop_id", "line", "bus_id", "ingested_at"])
          +     silver_df = silver_df.dropDuplicates(["stop_id", "line", "bus_id", "ingested_at"])
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"transporte_publico_emt_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"transporte_publico_emt_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          +     # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
          -     # hora de Madrid).
          +     # hora de Madrid).
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          +     # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
          -     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          +     # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
          -     # sustituto de ese borrado previo.
          +     # sustituto de ese borrado previo.
          -     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "961447ee3174a4e4ef33f1b6e006affa" -> "23abd9cec70fa40fd164acace5643b81"
      ~ id                            = "glue-scripts/transporte_publico_emt_backfill_dedup-961447ee3174a4e4ef33f1b6e006affa.py" -> (known after apply)
      ~ key                           = "glue-scripts/transporte_publico_emt_backfill_dedup-961447ee3174a4e4ef33f1b6e006affa.py" -> "glue-scripts/transporte_publico_emt_backfill_dedup.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup_gold must be replaced
+/- resource "aws_s3_object" "glue_script_transporte_publico_emt_backfill_dedup_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_backfill_dedup_gold-318da358079d2d12e5b8c55e656eb079.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          + """Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
          - `transporte_publico_emt`.
          + `transporte_publico_emt`.
          - 
          + 
          - **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          + **No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
          - tarea 046/072), que solo procesa la partición horaria anterior a la
          + tarea 046/072), que solo procesa la partición horaria anterior a la
          - ejecución. Este job existe para recalcular Gold desde cero tras la
          + ejecución. Este job existe para recalcular Gold desde cero tras la
          - reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          + reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
          - lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          + lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
          - hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          + hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
          - trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          + trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.
          - 
          + 
          - A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          + A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
          - `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          + `dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
          - duplicados (`(stop_id, line, bus_id, ingested_at)` único) -- lo que hace
          + duplicados (`(stop_id, line, bus_id, ingested_at)` único) -- lo que hace
          - este job es la misma agregación de producción de `glue_silver_to_gold.py`,
          + este job es la misma agregación de producción de `glue_silver_to_gold.py`,
          - solo que sobre todo el histórico en vez de una única partición horaria, y
          + solo que sobre todo el histórico en vez de una única partición horaria, y
          - escribiendo con `overwrite` en vez de `append` (el prefijo de destino debe
          + escribiendo con `overwrite` en vez de `append` (el prefijo de destino debe
          - borrarse a mano antes de lanzarlo, igual que Silver).
          + borrarse a mano antes de lanzarlo, igual que Silver).
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen completo, p.ej.
          + - `silver_path`: prefijo S3 de origen completo, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/transporte_publico_emt_por_parada_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/transporte_publico_emt_por_parada_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          +     # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
          -     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          +     # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
          -     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          +     # de Spark en el runtime de Glue) en vez de Europe/Madrid.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          +     # A diferencia del pipeline incremental, este job de un solo uso lee TODO
          -     # el histórico de Silver de una vez -- exactamente lo que necesita una
          +     # el histórico de Silver de una vez -- exactamente lo que necesita una
          -     # reconstrucción completa de Gold.
          +     # reconstrucción completa de Gold.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(args["silver_path"])
          +         spark.read.parquet(args["silver_path"])
          -         .withColumn("fecha", F.date_format(F.to_timestamp("ingested_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("ingested_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("ingested_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("ingested_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # Misma agregación que el pipeline de producción
          +     # Misma agregación que el pipeline de producción
          -     # (`glue_silver_to_gold.py`): una fila por parada/línea/fecha/hora.
          +     # (`glue_silver_to_gold.py`): una fila por parada/línea/fecha/hora.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("stop_id", "line", "fecha", "hora")
          +         silver_df.groupBy("stop_id", "line", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.min("ingested_at").alias("first_ingested_at"),
          +             F.min("ingested_at").alias("first_ingested_at"),
          -             F.max("ingested_at").alias("last_ingested_at"),
          +             F.max("ingested_at").alias("last_ingested_at"),
          -             F.avg("estimate_arrive_sec").alias("avg_estimate_arrive_sec"),
          +             F.avg("estimate_arrive_sec").alias("avg_estimate_arrive_sec"),
          -             F.min("estimate_arrive_sec").alias("min_estimate_arrive_sec"),
          +             F.min("estimate_arrive_sec").alias("min_estimate_arrive_sec"),
          -             F.max("estimate_arrive_sec").alias("max_estimate_arrive_sec"),
          +             F.max("estimate_arrive_sec").alias("max_estimate_arrive_sec"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          +     # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
          -     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          +     # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
          -     # que `glue_backfill_dedup.py` para Silver).
          +     # que `glue_backfill_dedup.py` para Silver).
          -     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "318da358079d2d12e5b8c55e656eb079" -> "fe90bd1230ec95accd5efc6836a9c7f5"
      ~ id                            = "glue-scripts/transporte_publico_emt_backfill_dedup_gold-318da358079d2d12e5b8c55e656eb079.py" -> (known after apply)
      ~ key                           = "glue-scripts/transporte_publico_emt_backfill_dedup_gold-318da358079d2d12e5b8c55e656eb079.py" -> "glue-scripts/transporte_publico_emt_backfill_dedup_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_transporte_publico_emt_bronze_to_silver must be replaced
+/- resource "aws_s3_object" "glue_script_transporte_publico_emt_bronze_to_silver" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_bronze_to_silver-5b3c3602b3f60bf9ff3ef5cfe1c8d6a9.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Bronze -> Silver del dataset `transporte_publico_emt`.
          + """Job de AWS Glue: Bronze -> Silver del dataset `transporte_publico_emt`.
          - 
          + 
          - **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          + **No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
          - sin `terraform apply`, que `trafico/glue_bronze_to_silver.py`, ver
          + sin `terraform apply`, que `trafico/glue_bronze_to_silver.py`, ver
          - `procesamiento/README.md`): este script asume el entorno de ejecución real
          + `procesamiento/README.md`): este script asume el entorno de ejecución real
          - de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          + de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
          - `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          + `great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
          - (esta EC2 de desarrollo no tiene Spark instalado).
          + (esta EC2 de desarrollo no tiene Spark instalado).
          - 
          + 
          - Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          + Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
          - de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          + de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
          - leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          + leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
          - y escribir el resultado. Ver `ge_suite.py` para la validación de Great
          + y escribir el resultado. Ver `ge_suite.py` para la validación de Great
          - Expectations que corre inmediatamente después, en el mismo `SparkSession`.
          + Expectations que corre inmediatamente después, en el mismo `SparkSession`.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `bronze_path`: prefijo S3 de origen, p.ej.
          + - `bronze_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-bronze-222234418587/transporte_publico_emt/`.
          +   `s3://madrono-tfm-dev-bronze-222234418587/transporte_publico_emt/`.
          - - `silver_path`: prefijo S3 de destino, p.ej.
          + - `silver_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          - - `quality_report_path`: prefijo S3 donde se escribe el informe de
          + - `quality_report_path`: prefijo S3 donde se escribe el informe de
          -   validación de Great Expectations (un JSON por ejecución del job).
          +   validación de Great Expectations (un JSON por ejecución del job).
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import json
          + import json
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - import great_expectations as gx
          + import great_expectations as gx
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import Row, SparkSession
          + from pyspark.sql import Row, SparkSession
          - from pyspark.sql.types import (
          + from pyspark.sql.types import (
          -     BooleanType,
          +     BooleanType,
          -     DoubleType,
          +     DoubleType,
          -     IntegerType,
          +     IntegerType,
          -     LongType,
          +     LongType,
          -     StringType,
          +     StringType,
          -     StructField,
          +     StructField,
          -     StructType,
          +     StructType,
          - )
          + )
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - from procesamiento.silver_gold.transporte_publico_emt.ge_suite import run_quality_report
          + from procesamiento.silver_gold.transporte_publico_emt.ge_suite import run_quality_report
          - from procesamiento.silver_gold.transporte_publico_emt.transform import bronze_to_silver
          + from procesamiento.silver_gold.transporte_publico_emt.transform import bronze_to_silver
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - LOCATION_SCHEMA = StructType(
          + LOCATION_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("lat", DoubleType(), True),
          +         StructField("lat", DoubleType(), True),
          -         StructField("lon", DoubleType(), True),
          +         StructField("lon", DoubleType(), True),
          -         StructField("srid", StringType(), True),
          +         StructField("srid", StringType(), True),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - SILVER_SCHEMA = StructType(
          + SILVER_SCHEMA = StructType(
          -     [
          +     [
          -         StructField("schema_version", IntegerType(), False),
          +         StructField("schema_version", IntegerType(), False),
          -         StructField("source", StringType(), True),
          +         StructField("source", StringType(), True),
          -         StructField("stop_id", StringType(), False),
          +         StructField("stop_id", StringType(), False),
          -         StructField("line", StringType(), False),
          +         StructField("line", StringType(), False),
          -         StructField("bus_id", LongType(), True),
          +         StructField("bus_id", LongType(), True),
          -         StructField("destination", StringType(), True),
          +         StructField("destination", StringType(), True),
          -         StructField("ingested_at", StringType(), False),
          +         StructField("ingested_at", StringType(), False),
          -         StructField("processed_at", StringType(), False),
          +         StructField("processed_at", StringType(), False),
          -         StructField("estimate_arrive_sec", IntegerType(), True),
          +         StructField("estimate_arrive_sec", IntegerType(), True),
          -         StructField("distance_bus_m", IntegerType(), True),
          +         StructField("distance_bus_m", IntegerType(), True),
          -         StructField("is_head", BooleanType(), True),
          +         StructField("is_head", BooleanType(), True),
          -         StructField("deviation_sec", IntegerType(), True),
          +         StructField("deviation_sec", IntegerType(), True),
          -         StructField("position_type_bus", StringType(), True),
          +         StructField("position_type_bus", StringType(), True),
          -         StructField("location", LOCATION_SCHEMA, False),
          +         StructField("location", LOCATION_SCHEMA, False),
          -     ]
          +     ]
          - )
          + )
          - 
          + 
          - 
          + 
          - def _to_silver_row(silver_record: dict) -> Row:
          + def _to_silver_row(silver_record: dict) -> Row:
          -     location = silver_record["location"]
          +     location = silver_record["location"]
          -     return Row(
          +     return Row(
          -         schema_version=silver_record["schema_version"],
          +         schema_version=silver_record["schema_version"],
          -         source=silver_record["source"],
          +         source=silver_record["source"],
          -         stop_id=silver_record["stop_id"],
          +         stop_id=silver_record["stop_id"],
          -         line=silver_record["line"],
          +         line=silver_record["line"],
          -         bus_id=silver_record["bus_id"],
          +         bus_id=silver_record["bus_id"],
          -         destination=silver_record["destination"],
          +         destination=silver_record["destination"],
          -         ingested_at=silver_record["ingested_at"],
          +         ingested_at=silver_record["ingested_at"],
          -         processed_at=silver_record["processed_at"],
          +         processed_at=silver_record["processed_at"],
          -         estimate_arrive_sec=silver_record["estimate_arrive_sec"],
          +         estimate_arrive_sec=silver_record["estimate_arrive_sec"],
          -         distance_bus_m=silver_record["distance_bus_m"],
          +         distance_bus_m=silver_record["distance_bus_m"],
          -         is_head=silver_record["is_head"],
          +         is_head=silver_record["is_head"],
          -         deviation_sec=silver_record["deviation_sec"],
          +         deviation_sec=silver_record["deviation_sec"],
          -         position_type_bus=silver_record["position_type_bus"],
          +         position_type_bus=silver_record["position_type_bus"],
          -         location=Row(
          +         location=Row(
          -             lat=location["lat"],
          +             lat=location["lat"],
          -             lon=location["lon"],
          +             lon=location["lon"],
          -             srid=location["srid"],
          +             srid=location["srid"],
          -         ),
          +         ),
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          + def _write_quality_report(report_uri: str, quality_report: dict) -> None:
          -     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          +     """Escribe el informe de Great Expectations directamente a S3 vía boto3.
          - 
          + 
          -     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          +     Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
          -     único JSON pequeño no necesita el protocolo de commit distribuido de
          +     único JSON pequeño no necesita el protocolo de commit distribuido de
          -     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          +     Spark/Hadoop, que en el runtime de AWS Glue falla buscando
          -     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          +     `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
          -     `hadoop-aws` ausente en Glue) — ver tarea 051.
          +     `hadoop-aws` ausente en Glue) — ver tarea 051.
          -     """
          +     """
          -     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          +     bucket, _, key = report_uri.removeprefix("s3://").partition("/")
          -     boto3.client("s3").put_object(
          +     boto3.client("s3").put_object(
          -         Bucket=bucket,
          +         Bucket=bucket,
          -         Key=key,
          +         Key=key,
          -         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          +         Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
          -         ContentType="application/json",
          +         ContentType="application/json",
          -     )
          +     )
          - 
          + 
          - 
          + 
          - def _process_partition(rows, processed_at_iso: str):
          + def _process_partition(rows, processed_at_iso: str):
          -     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          +     """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
          -     processed_at = datetime.fromisoformat(processed_at_iso)
          +     processed_at = datetime.fromisoformat(processed_at_iso)
          -     bronze_records = [row.asDict(recursive=True) for row in rows]
          +     bronze_records = [row.asDict(recursive=True) for row in rows]
          -     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          +     silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
          -     return [_to_silver_row(r) for r in silver_records]
          +     return [_to_silver_row(r) for r in silver_records]
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(
          +     args = getResolvedOptions(
          -         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          +         sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
          -     )
          +     )
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          +     # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
          -     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          +     # en el timezone de sesión por defecto de Spark (UTC en el runtime de
          -     # Glue), desalineado con la hora de Madrid real de `ingested_at` -- ver
          +     # Glue), desalineado con la hora de Madrid real de `ingested_at` -- ver
          -     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          +     # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
          -     # termina sin error pero nunca escribe la partición que espera Gold).
          +     # termina sin error pero nunca escribe la partición que espera Gold).
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          +     # Lectura incremental (tarea 072): solo la particion Bronze de la hora
          -     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          +     # completa anterior a esta ejecucion -- nunca la raiz del dataset
          -     # completo, que crecia sin limite y disparo el coste real de Glue
          +     # completo, que crecia sin limite y disparo el coste real de Glue
          -     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          +     # documentado en doc/072-arreglo-lectura-incremental-glue.md.
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          +     bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # Cada objeto Bronze es un array JSON de registros (ver
          +     # Cada objeto Bronze es un array JSON de registros (ver
          -     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          +     # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
          -     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          +     # que Spark expanda ese array en filas en vez de esperar NDJSON.
          -     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          +     bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)
          - 
          + 
          -     silver_rdd = bronze_df.rdd.mapPartitions(
          +     silver_rdd = bronze_df.rdd.mapPartitions(
          -         lambda rows: _process_partition(rows, processed_at.isoformat())
          +         lambda rows: _process_partition(rows, processed_at.isoformat())
          -     )
          +     )
          -     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          +     silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
          -     silver_df.cache()
          +     silver_df.cache()
          - 
          + 
          -     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          +     # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
          -     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          +     # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
          -     # `bronze_to_silver`, en el mismo SparkSession.
          +     # `bronze_to_silver`, en el mismo SparkSession.
          -     gx_context = gx.get_context(mode="ephemeral")
          +     gx_context = gx.get_context(mode="ephemeral")
          -     quality_report = run_quality_report(gx_context, silver_df)
          +     quality_report = run_quality_report(gx_context, silver_df)
          -     report_key = (
          +     report_key = (
          -         f"{args['quality_report_path'].rstrip('/')}/"
          +         f"{args['quality_report_path'].rstrip('/')}/"
          -         f"transporte_publico_emt_{processed_at:%Y%m%dT%H%M%S}.json"
          +         f"transporte_publico_emt_{processed_at:%Y%m%dT%H%M%S}.json"
          -     )
          +     )
          -     _write_quality_report(report_key, quality_report)
          +     _write_quality_report(report_key, quality_report)
          - 
          + 
          -     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          +     # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
          -     # para que un consumidor ya familiarizado con Bronze no tenga que
          +     # para que un consumidor ya familiarizado con Bronze no tenga que
          -     # aprender un esquema de partición distinto para Silver.
          +     # aprender un esquema de partición distinto para Silver.
          -     from pyspark.sql.functions import date_format, to_timestamp
          +     from pyspark.sql.functions import date_format, to_timestamp
          - 
          + 
          -     silver_partitioned = silver_df.withColumn(
          +     silver_partitioned = silver_df.withColumn(
          -         "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
          +         "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
          -     ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))
          +     ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))
          - 
          + 
          -     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          +     silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
          -         args["silver_path"]
          +         args["silver_path"]
          -     )
          +     )
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "5b3c3602b3f60bf9ff3ef5cfe1c8d6a9" -> "227b9894b2fc66730ce2cbb6a7a9f6a3"
      ~ id                            = "glue-scripts/transporte_publico_emt_bronze_to_silver-5b3c3602b3f60bf9ff3ef5cfe1c8d6a9.py" -> (known after apply)
      ~ key                           = "glue-scripts/transporte_publico_emt_bronze_to_silver-5b3c3602b3f60bf9ff3ef5cfe1c8d6a9.py" -> "glue-scripts/transporte_publico_emt_bronze_to_silver.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_transporte_publico_emt_silver_to_gold must be replaced
+/- resource "aws_s3_object" "glue_script_transporte_publico_emt_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/transporte_publico_emt_silver_to_gold-7cd0d472adb8dfd5d48cc79dfad6acdb.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
          - """Job de AWS Glue: Silver -> Gold del dataset `transporte_publico_emt` (espera por parada/línea/hora).
          + """Job de AWS Glue: Silver -> Gold del dataset `transporte_publico_emt` (espera por parada/línea/hora).
          - 
          + 
          - **No ejecutado en esta tarea** (mismas condiciones que
          + **No ejecutado en esta tarea** (mismas condiciones que
          - `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          + `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
          - disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          + disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
          - 
          + 
          - A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          + A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
          - `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          + `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
          - través de múltiples particiones/ficheros de Silver necesita las primitivas
          + través de múltiples particiones/ficheros de Silver necesita las primitivas
          - nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          + nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
          - mismo motivo que `trafico/glue_silver_to_gold.py`. `aggregate.py` sigue
          + mismo motivo que `trafico/glue_silver_to_gold.py`. `aggregate.py` sigue
          - siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          + siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
          - expresiones de Spark de este job están escritas para producir exactamente el
          + expresiones de Spark de este job están escritas para producir exactamente el
          - mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          + mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
          - en uno debe reflejarse en el otro.
          + en uno debe reflejarse en el otro.
          - 
          + 
          - Parámetros del job (`--<nombre>`, ver `glue.tf`):
          + Parámetros del job (`--<nombre>`, ver `glue.tf`):
          - 
          + 
          - - `JOB_NAME`: nombre del job (estándar de Glue).
          + - `JOB_NAME`: nombre del job (estándar de Glue).
          - - `silver_path`: prefijo S3 de origen, p.ej.
          + - `silver_path`: prefijo S3 de origen, p.ej.
          -   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          +   `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
          - - `gold_path`: prefijo S3 de destino, p.ej.
          + - `gold_path`: prefijo S3 de destino, p.ej.
          -   `s3://madrono-tfm-dev-gold-222234418587/transporte_publico_emt_por_parada_hora/`.
          +   `s3://madrono-tfm-dev-gold-222234418587/transporte_publico_emt_por_parada_hora/`.
          - """
          + """
          - 
          + 
          - from __future__ import annotations
          + from __future__ import annotations
          - 
          + 
          - import sys
          + import sys
          - from datetime import datetime
          + from datetime import datetime
          - from zoneinfo import ZoneInfo
          + from zoneinfo import ZoneInfo
          - 
          + 
          - import boto3
          + import boto3
          - from awsglue.context import GlueContext
          + from awsglue.context import GlueContext
          - from awsglue.job import Job
          + from awsglue.job import Job
          - from awsglue.utils import getResolvedOptions
          + from awsglue.utils import getResolvedOptions
          - from pyspark.context import SparkContext
          + from pyspark.context import SparkContext
          - from pyspark.sql import SparkSession
          + from pyspark.sql import SparkSession
          - from pyspark.sql import functions as F
          + from pyspark.sql import functions as F
          - 
          + 
          - from procesamiento.silver_gold.incremental import (
          + from procesamiento.silver_gold.incremental import (
          -     hourly_partition_uri,
          +     hourly_partition_uri,
          -     partition_has_objects,
          +     partition_has_objects,
          -     previous_hour,
          +     previous_hour,
          - )
          + )
          - 
          + 
          - MADRID_TZ = ZoneInfo("Europe/Madrid")
          + MADRID_TZ = ZoneInfo("Europe/Madrid")
          - 
          + 
          - 
          + 
          - def main() -> None:
          + def main() -> None:
          -     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          +     args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
          - 
          + 
          -     sc = SparkContext()
          +     sc = SparkContext()
          -     glue_context = GlueContext(sc)
          +     glue_context = GlueContext(sc)
          -     spark: SparkSession = glue_context.spark_session
          +     spark: SparkSession = glue_context.spark_session
          -     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          +     # Mismo motivo que glue_bronze_to_silver.py (tarea 072/075): fija el
          -     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          +     # timezone de sesión de Spark antes de recalcular `fecha`/`hora`.
          -     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          +     spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
          -     job = Job(glue_context)
          +     job = Job(glue_context)
          -     job.init(args["JOB_NAME"], args)
          +     job.init(args["JOB_NAME"], args)
          - 
          + 
          -     processed_at = datetime.now(MADRID_TZ)
          +     processed_at = datetime.now(MADRID_TZ)
          - 
          + 
          -     fecha, hora = previous_hour(processed_at)
          +     fecha, hora = previous_hour(processed_at)
          -     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          +     silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
          -     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          +     if not partition_has_objects(boto3.client("s3"), silver_partition_path):
          -         job.commit()
          +         job.commit()
          -         return
          +         return
          - 
          + 
          -     # `fecha`/`hora` son columnas de partición de Silver (ver
          +     # `fecha`/`hora` son columnas de partición de Silver (ver
          -     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          +     # glue_bronze_to_silver.py); al narrowear la lectura a una única
          -     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          +     # partición (tarea 072), Spark ya no las infiere de la ruta -- se
          -     # recalculan aquí desde `ingested_at`, la misma columna que las originó.
          +     # recalculan aquí desde `ingested_at`, la misma columna que las originó.
          -     silver_df = (
          +     silver_df = (
          -         spark.read.parquet(silver_partition_path)
          +         spark.read.parquet(silver_partition_path)
          -         .withColumn("fecha", F.date_format(F.to_timestamp("ingested_at"), "yyyy-MM-dd"))
          +         .withColumn("fecha", F.date_format(F.to_timestamp("ingested_at"), "yyyy-MM-dd"))
          -         .withColumn("hora", F.date_format(F.to_timestamp("ingested_at"), "HH"))
          +         .withColumn("hora", F.date_format(F.to_timestamp("ingested_at"), "HH"))
          -     )
          +     )
          - 
          + 
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          +     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          +     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
          +     # partition pruning si `silver_path` acota un rango de fechas concreto.
          -     gold_df = (
          +     gold_df = (
          -         silver_df.groupBy("stop_id", "line", "fecha", "hora")
          +         silver_df.groupBy("stop_id", "line", "fecha", "hora")
          -         .agg(
          +         .agg(
          -             F.count(F.lit(1)).alias("samples_count"),
          +             F.count(F.lit(1)).alias("samples_count"),
          -             F.min("ingested_at").alias("first_ingested_at"),
          +             F.min("ingested_at").alias("first_ingested_at"),
          -             F.max("ingested_at").alias("last_ingested_at"),
          +             F.max("ingested_at").alias("last_ingested_at"),
          -             F.avg("estimate_arrive_sec").alias("avg_estimate_arrive_sec"),
          +             F.avg("estimate_arrive_sec").alias("avg_estimate_arrive_sec"),
          -             F.min("estimate_arrive_sec").alias("min_estimate_arrive_sec"),
          +             F.min("estimate_arrive_sec").alias("min_estimate_arrive_sec"),
          -             F.max("estimate_arrive_sec").alias("max_estimate_arrive_sec"),
          +             F.max("estimate_arrive_sec").alias("max_estimate_arrive_sec"),
          -         )
          +         )
          -         .withColumnRenamed("fecha", "date")
          +         .withColumnRenamed("fecha", "date")
          -         .withColumn("hour", F.col("hora").cast("int"))
          +         .withColumn("hour", F.col("hora").cast("int"))
          -         .drop("hora")
          +         .drop("hora")
          -         .withColumn("schema_version", F.lit(1))
          +         .withColumn("schema_version", F.lit(1))
          -         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          +         .withColumn("processed_at", F.lit(processed_at.isoformat()))
          -     )
          +     )
          - 
          + 
          -     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          +     # Gold es órdenes de magnitud más pequeño que Silver (una fila por
          -     # parada/línea/hora, no cada pocos minutos): particionar solo por `date`
          +     # parada/línea/hora, no cada pocos minutos): particionar solo por `date`
          -     # es suficiente para podar particiones sin generar ficheros diminutos.
          +     # es suficiente para podar particiones sin generar ficheros diminutos.
          -     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          +     gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
          - 
          + 
          -     job.commit()
          +     job.commit()
          - 
          + 
          - 
          + 
          - if __name__ == "__main__":
          + if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "7cd0d472adb8dfd5d48cc79dfad6acdb" -> "31a48a9152356f0fb479193b278e8d0c"
      ~ id                            = "glue-scripts/transporte_publico_emt_silver_to_gold-7cd0d472adb8dfd5d48cc79dfad6acdb.py" -> (known after apply)
      ~ key                           = "glue-scripts/transporte_publico_emt_silver_to_gold-7cd0d472adb8dfd5d48cc79dfad6acdb.py" -> "glue-scripts/transporte_publico_emt_silver_to_gold.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (11 unchanged attributes hidden)
    }

  # aws_s3_object.procesamiento_source will be updated in-place
  ~ resource "aws_s3_object" "procesamiento_source" {
      ~ etag                          = "a7ba99ac9375c8f81e041af4185355c9" -> "38ac40cf3a7a2950bd8beefe827db5b5"
        id                            = "glue-libs/procesamiento.zip"
        tags                          = {}
      + version_id                    = (known after apply)
        # (24 unchanged attributes hidden)
    }

Plan: 48 to add, 67 to change, 48 to destroy.

Warning: Resource targeting is in effect

You are creating a plan with the -target option, which means that the result
of this plan may not represent all of the changes requested by the current
configuration.

The -target option is not for routine use, and is provided only for
exceptional situations such as recovering from errors or mistakes, or when
Terraform specifically suggests to use it as part of an error message.

─────────────────────────────────────────────────────────────────────────────

Note: You didn't use the -out option to save this plan, so Terraform can't
guarantee to take exactly these actions if you run "terraform apply" now.
```
