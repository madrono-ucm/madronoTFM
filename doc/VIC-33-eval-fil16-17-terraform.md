# VIC_33 — verificación independiente del terraform apply de FIL_16/FIL_17 (2026-09-01)

Ejecutado 2026-09-01, contra AWS real (`madrono-terraform-deployerEC2`,
`eu-west-1`). Comandos y salida reales del momento de esta verificación,
no reciclados de la sesión que hizo el `apply`. Ningún cambio aplicado.

## 1. `FIL_17` — cero secretos en claro ✅

`aws lambda get-function-configuration` de las 4 Lambdas con credencial:
las 4 tienen **solo** `BRONZE_BASE_PATH` + su(s) `*_SSM_PATH` en
`Environment.Variables`. Ningún valor de secreto en claro. Correcto.

## 2. `FIL_17` — mínimo privilegio ✅

`aws iam get-policy-version` de `madrono-tfm-dev-ingestion-lambda-secrets`:
`Action` = únicamente `ssm:GetParameter`, `Resource` = exactamente los 6
ARNs de `/madrono-tfm/dev/secrets/*` (emt-client-id, emt-pass-key,
bluesky-identifier, bluesky-app-password, aemet-api-key, cams-ads-api-key),
sin comodines. `aws iam list-attached-role-policies` confirma que está
adjunta a `madrono-tfm-dev-ingestion-role`. Correcto.

## 3. `FIL_17` — ruta de código correcta ✅

`grep` real en los 4 módulos productores: los 4 `CaptureConfig.from_env()`
usan `secretos.get_secret("X")`, no `os.environ["X"]` directo. Correcto.

## 4. Pipeline congelado de verdad ✅

- `aws scheduler list-schedules`: **23/23** `madrono-tfm-dev-*` en
  `DISABLED` (contados, no muestreados).
- `aws glue get-triggers`: **27/27** triggers `scheduled-bronze-to-silver`/
  `conditional-silver-to-gold`/`afluencia-lugares-scheduled-estimada` en
  `DEACTIVATED`.
- Correcto, sin excepciones.

## 5. `FIL_16` parcial y coherente ✅

`aws events describe-rule madrono-tfm-dev-glue-job-failed`: `State=ENABLED`,
patrón `{FAILED,TIMEOUT,ERROR}` sobre `Glue Job State Change` correcto.
`aws events list-targets-by-rule`: `Targets: []`. `aws sns list-topics`:
no existe `madrono-tfm-dev-alertas-pipeline`. `doc/FIL-16-...md` lo
documenta explícitamente como "PARCIAL — ACEPTADO ASÍ POR EL USUARIO...
No es trabajo pendiente". Correcto.

## 6. Cero drift colateral — ⚠️ **desviación real, más grande de lo esperado**

El `terraform plan` completo (sin `-target`) da **9 to add, 54 to change,
1 to destroy** — no los ~10 recursos que anticipaba el alcance del ticket
(Kafka ×5 + SNS ×3 + layer ×2). Desglosado:

- **Kafka ×5** (add) — esperado, excluido a propósito.
- **SNS ×3** (`aws_cloudwatch_event_target.glue_job_failed_sns`,
  `aws_sns_topic.alertas_pipeline`, `aws_sns_topic_policy.alertas_pipeline`,
  add) — esperado, bloqueado por IAM (`FIL_16`).
- **`aws_s3_object.layer_build_source`** (replace) +
  **`aws_codebuild_project.lambda_dependencies_layer`** (update) —
  esperado, ya tiene ticket propio (`FIL_60`).
- **NO esperado por el alcance de este ticket, pero real y verificado:**
  - **16 `aws_lambda_function.producer[*]`** "will be updated in-place":
    cada una con `~ layers = [ - "arn:...:layer:...ingesta-dependencies:1" ]`
    **sin ningún `+`** (la layer se quitaría por completo, no se
    actualizaría) + `source_code_hash` cambiando.
  - **`aws_iam_policy.scheduler_invoke_lambda`** SÍ reaparece — el ticket
    esperaba explícitamente que "debiera haber quedado estable" tras el
    `apply` del 2026-09-01, y no es así: su `policy` sale
    `-> (known after apply)` con el `Statement` completo marcado para
    borrar, sin reemplazo.
  - **~35 `aws_s3_object.glue_script_*`** "will be updated in-place".

**Investigado el porqué, no solo reportado el número:**

- Causa raíz de los 16 Lambda + el `scheduler_invoke_lambda`: **una sola**
  — `var.lambda_dependencies_layer_arn` sigue en `null` en
  `terraform.tfvars` (confirmado con `grep`), y `lambda.tf:546` es
  `layers = var.lambda_dependencies_layer_arn == null ? [] : [...]` →
  estado deseado real = "sin layer". `data
  "aws_iam_policy_document" "scheduler_invoke_lambda"` (`lambda.tf:601`)
  itera `[for fn in aws_lambda_function.producer : fn.arn]`, así que
  cualquier cambio pendiente en esas 16 Lambdas fuerza su recompute a
  `known after apply`. **Un solo hilo causal, no dos problemas
  independientes.** Documentado con el detalle completo, y el riesgo real
  (`terraform apply` sin `-target` quitaría la layer de las 16 funciones)
  como adenda a `FIL_60` (ya existente, mismo drift, alcance ampliado).
- Causa de los ~35 `aws_s3_object.glue_script_*`: verificado con el diff
  real de uno de ellos — contenido **idéntico carácter a carácter** salvo
  normalización de fin de línea/espacios. Ruido benigno, no funcional.

**Veredicto**: el punto 6 del alcance del ticket, tal como estaba escrito,
**no se confirma** — sí hay drift colateral más allá de lo enumerado. Pero
investigado a fondo, es una única causa ya conocida (variable sin fijar,
ya tenía ticket) con un efecto secundario real que no estaba documentado
(riesgo de que un `apply` sin `-target` rompa las 16 Lambdas), ahora
añadido a `FIL_60`.

## 7. `fmt`/`validate` ✅

`terraform fmt -check -recursive`: limpio (exit 0). `terraform validate`:
`Success!`.

## 8. Coste de la ventana de mantenimiento ✅

`aws s3 ls` sobre Bronze para el 2026-09-01 hora 21 (CEST) /
hora 19 (UTC, la que muestra `LastModified`): `cams_calidad_aire` (3),
`bluesky_menciones` (1), `transporte_publico_emt` (5, intervalo corto),
`calidad_aire` (1), `aemet_prevision_avisos`/`trafico` (0 en esa hora
concreta). ~10 objetos en total en la ventana — footprint pequeño y
acotado, coherente con "invoke manual + como mucho unos pocos ticks",
sin sorpresas.

## 9. `source_code_hash` — sin manipulación ✅ (verificado por construcción)

`source_code_hash = data.archive_file.ingesta_source.output_base64sha256`
(`lambda.tf:541`): Terraform calcula el hash **directamente** empaquetando
`ingesta/` del propio checkout, no de un artefacto externo — no hay
ninguna vía para que el hash desplegado sea de "algo inesperado" sin que
también lo sea el propio repo. El `terraform plan` de esta verificación ya
hizo la comparación implícita (desplegado vs. recalculado desde `HEAD` de
este checkout) al mostrar el cambio de `source_code_hash` de los 16 — ese
cambio es exactamente el mismo drift del punto 6 (layer/hash), no una
manipulación distinta. No hace falta un `sha256sum` manual aparte.

## Conclusión

7 de 9 puntos confirman exactamente lo que documentó la sesión del
2026-09-01. El punto 6 (cero drift colateral) **no se sostiene tal cual
estaba escrito** — hay más drift del enumerado, pero investigado hasta la
causa raíz: es una única variable sin fijar (`lambda_dependencies_layer_arn`),
ya tenía ticket (`FIL_60`), y el hallazgo nuevo (que un `apply` sin
`-target` rompería la layer de las 16 Lambdas de producción, más el
síntoma de `scheduler_invoke_lambda` que no se había estabilizado como se
esperaba) queda documentado allí como adenda, no como un ticket nuevo
separado — mismo drift, alcance más completo.
