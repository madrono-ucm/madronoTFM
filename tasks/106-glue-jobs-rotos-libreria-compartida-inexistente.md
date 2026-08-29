---
id: 106
slug: glue-jobs-rotos-libreria-compartida-inexistente
title: "URGENTE — QA: 37 de 48 jobs de Glue (77%) fallan en LAUNCH ERROR desde hace >24h, la libreria compartida procesamiento.zip no existe en S3"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-29T19:30:00+00:00"
updated_at: "2026-08-29T19:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Hallazgo de QA (verificado en vivo, incidente activo)

Investigando la factura real de AWS (`herramientas/costes/desglose_glue.py`)
como parte de una ronda de QA, se detectaron **seis jobs `bronze_to_silver`
fallando de forma simultánea hoy (29/8) entre las 18:10:01 y las
18:10:43** (tráfico, bicimad, transporte_publico_emt, meteorologia,
calidad_aire, aparcamientos) — demasiado simultáneo para ser coincidencia.

**Causa raíz confirmada**: los 48 jobs de Glue reales usan un argumento
`--extra-py-files` que apunta a un fichero compartido
`s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/
procesamiento-<hash>.zip`. Verificado con `aws glue get-jobs` +
`aws s3 ls`:

- **27 jobs** apuntan a `procesamiento-72e35fd9...zip` — **no existe en
  S3**.
- **10 jobs** apuntan a `procesamiento-1ba560b7...zip` — **tampoco
  existe**.
- **1 job** apunta a `procesamiento-a7ba99ac...zip` — este sí existe
  (subido el 28/8 15:19:29) y es el único que funciona.
- 10 jobs no usan `--extra-py-files` (no dependen de este fichero, no
  afectados).

Es decir, **37 de 48 jobs (77 %) fallan en `LAUNCH ERROR` antes incluso
de arrancar Spark** (`Error downloading from S3... The specified key
does not exist`) — no es un bug en el código de `procesamiento/`, el
job ni siquiera llega a ejecutarlo.

**Terraform confirma el origen**: el `state` real tiene registrado
`glue-libs/procesamiento-a7ba99ac...zip` (coincide con el único objeto
real en S3), pero el `main` actual del repositorio ya calcula un cuarto
hash distinto (`procesamiento-38ac40cf...zip`, ni siquiera subido
todavía) — o sea, ha habido **como mínimo 3-4 generaciones** de este
fichero compartido en poco tiempo, y varios jobs de Glue se quedaron
"anclados" a generaciones distintas y ya inexistentes. Encaja con el
patrón ya visto en las tareas 093/098/100: aplicaciones de Terraform
parciales (`-target=...` sobre un subconjunto de recursos) que dejan al
resto de jobs sin actualizar su referencia al fichero compartido cuando
éste cambia.

**Desde cuándo está roto**: fallos confirmados ya el 28/8 a las 15:13-15:14
(antes incluso de que se subiera la versión `a7ba99ac` a las 15:19) y de
nuevo hoy 29/8 a las 18:10 — **al menos 28 horas continuas** de
Bronze→Silver roto para estos 6 datasets (posiblemente más, no se ha
comprobado más atrás). Esto explica también por qué la verificación en
vivo de `calidad_aire_prevista` (misma sesión de QA) encontró que Gold
de calidad del aire no tiene datos más allá de 2026-08-28 15:00 —
coincide exactamente.

## Impacto real

- Silver/Gold de **tráfico, bicimad, transporte_publico_emt,
  meteorologia, calidad_aire y aparcamientos** (6 de los 16 "productores
  en producción continua" que describe la memoria, `VIC_02`/`VIKT_03`)
  llevan >24h sin datos frescos.
- El reentrenamiento nocturno de `ML_10` (cuando se despliegue, ticket
  `105`) fallaría o entrenaría sobre un panel obsoleto si depende de
  estos datasets.
- Coste ya perdido: `desglose_glue.py` reporta 23,02 USD del histórico
  disponible en ejecuciones sin resultado útil.

## Objetivo

Reconciliar el estado real de Terraform con lo desplegado para que los
48 jobs de Glue apunten a un único fichero compartido existente,
consistente con `main`.

## Alcance concreto

1. `git pull` primero. Confirma que no hay `__pycache__` local que rompa
   `terraform plan` (tarea 092, ya corregido en el código, pero
   verifícalo en tu propio entorno).
2. `terraform init -backend-config=backend.hcl` + `terraform plan` sin
   acotar. Revisa el plan completo línea a línea antes de aplicar nada
   — es un cambio de ~49 add / 66 change / 44 destroy (excluyendo los 5
   recursos de Kafka, que siguen sin aplicarse a propósito, ver tareas
   042/098).
3. Excluye Kafka del `apply` con el mismo truco que la tarea 098
   (`terraform state list` menos `data.*` como `-target` repetido, ya
   que esta versión de Terraform no soporta `-exclude`).
4. **Pide confirmación explícita al usuario antes de aplicar** — es
   `terraform apply` real sobre infraestructura de producción con
   `allow_infra_apply: true` ya marcado en esta tarea, pero la
   aprobación humana en el momento de ejecutar sigue siendo obligatoria
   (mismo criterio que las tareas 098/100).
5. Tras aplicar, verifica en vivo (no solo el código de salida de
   `terraform apply`):
   - `aws glue get-jobs` — todos los jobs con `--extra-py-files`
     apuntan al mismo hash, y ese objeto existe en S3.
   - Lanza (o espera al siguiente disparo programado) al menos uno de
     los 6 jobs que fallaban y confirma `SUCCEEDED`.
   - Athena: `calidad_aire`/`trafico`/etc. tienen filas con fecha/hora
     posteriores a 2026-08-28 15:00.
6. Documenta en `doc/106-...md` el resultado, incluida la causa raíz
   completa (aplicaciones parciales de Terraform dejando jobs en
   generaciones distintas del fichero compartido).

## Restricciones

- No toques la infraestructura de Kafka (tarea 042) — sigue excluida a
  propósito.
- Verifica el resultado contra AWS/Athena real, no solo contra
  `terraform apply` en verde.
- Si el `apply` no cierra por completo el problema (p. ej. sigue habiendo
  jobs con hashes distintos), no lo des por bueno — investiga por qué en
  vez de reintentar a ciegas.

## Criterios de aceptación

- 0 de 48 jobs de Glue con `--extra-py-files` apuntando a un objeto S3
  inexistente.
- Al menos una ejecución real `SUCCEEDED` de cada uno de los 6 jobs que
  estaban fallando, verificada tras el `apply` (no antes).
- Datos frescos en Athena (posteriores a 2026-08-28 15:00) para los 6
  datasets afectados.
- `doc/106-...md` con la causa raíz y la verificación completa.
