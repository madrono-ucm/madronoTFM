# 064 — Diseñar y escribir (sin aplicar) el scheduling de Silver/Gold para los 14 datasets

## Contexto

Con las tareas 051/052 (lote 1) y 061/062/063 (lote 2) verificadas contra AWS
real, los 28 jobs de Glue (Bronze→Silver + Silver→Gold × 14 datasets) solo se
habían lanzado a mano (`aws glue start-job-run`). Esta tarea diseña y escribe
el scheduling recurrente — **sin `terraform apply`**, mismo patrón que la
tarea 041 (piloto) o la 029 (Lambda/EventBridge antes de aplicarse en la 030).

## Qué se ha hecho

Fichero nuevo `infra/terraform/glue_scheduling.tf` (no se ha ampliado
`glue.tf`, que ya supera las 6800 líneas): 28 recursos `aws_glue_trigger`, dos
por dataset (`SCHEDULED` + `CONDITIONAL` encadenado), referenciando los jobs
ya definidos en `glue.tf` por el propio recurso Terraform
(`aws_glue_job.<x>.name`), no por un string reconstruido a mano.

- **`SCHEDULED`** (cron): lanza el job Bronze→Silver.
- **`CONDITIONAL`**: predicado sobre ese mismo job Bronze→Silver en estado
  `SUCCEEDED`, lanza el job Silver→Gold — así Silver→Gold nunca corre sobre
  un Silver a medias o corrupto. No hace falta `aws_glue_workflow`: un
  trigger `CONDITIONAL` standalone que vigila un job y lanza otro es un
  patrón soportado directamente por la API de Glue (confirmado contra la
  documentación de Terraform/AWS antes de escribir el código).

Ambos con `start_on_creation = true` (quedan activos en cuanto se aplique,
sin paso manual — coherente con `aws_scheduler_schedule` de `lambda.tf`).

## Cadencia elegida (decisión ya fijada por el enunciado, no reabierta)

- **Grupo horario** (`trafico`, `transporte_publico_emt`, `bicimad`,
  `aparcamientos`, `calidad_aire`, `meteorologia`): cada hora, minuto 10 —
  `cron(10 * * * ? *)`.
- **Grupo diario** (`ruido`, `cartelera_cines_estrenos`, `agenda_eventos`,
  `bluesky_menciones`, `aemet_prevision_avisos`, `cams_calidad_aire`,
  `afluencia_lugares`, `aforos_peatones_bicicletas`): 1x/día, contrastado
  dataset a dataset contra `local.schedules` (`lambda.tf`) tal como pedía el
  enunciado. Por defecto 08:00 CEST, con dos ajustes necesarios:
  - `cartelera_cines_estrenos` y `aemet_prevision_avisos`: su Bronze más
    tardío del día llega justo a las 08:00 Madrid (mismo instante que el
    valor por defecto) — se retrasan 15 min para no competir con él.
  - `cams_calidad_aire`: se define directamente en UTC (09:15 UTC, 15 min
    tras su Bronze más tardío a las 09:00 UTC) en vez de convertir desde
    Madrid, igual que ya hace su propio schedule de Bronze.

`aemet_prevision_avisos` comparte una única pareja de triggers, no dos
independientes: a diferencia de Bronze (donde Lambda sí separa "previsión" y
"avisos" con cadencias propias), Silver/Gold de este dataset ya es un único
job Glue por etapa que procesa ambas formas en la misma ejecución (tarea
058), así que no hay dos jobs Silver/Gold entre los que repartir triggers.

## Hallazgo verificado durante el diseño: `aws_glue_trigger` no admite zona horaria

A diferencia de `aws_scheduler_schedule` (EventBridge Scheduler, usado por
`lambda.tf` para Bronze), el campo `schedule` de `aws_glue_trigger` se
interpreta **siempre en UTC** — sin ningún parámetro de zona horaria
(verificado contra la documentación de AWS antes de escribir el código, no
asumido). Por eso todos los cron de este fichero están en UTC, no en
`Europe/Madrid`:

- Grupo horario: sin impacto — "cada hora, minuto 10" es la misma cadencia
  en cualquier zona horaria (el desfase Madrid-UTC es siempre un número
  entero de horas).
- Grupo diario: limitación real y documentada, no corregida en esta tarea.
  Los cron están calculados para las 08:00/08:15 en horario de verano
  (CEST, vigente en agosto 2026); en horario de invierno (CET) la misma
  ejecución caerá una hora más tarde en local (09:00/09:15 CET). Alternar
  dos cron a mano dos veces al año excedía el alcance de esta tarea (que
  pide implementar la cadencia ya decidida, no diseñar un mecanismo de
  DST); un desfase de hasta una hora es aceptable para un job diario cuyo
  único requisito es correr después del último Bronze del día.

## Verificación

`terraform init -backend=false` + `terraform validate` limpio;
`terraform fmt -check -diff glue_scheduling.tf` sin diferencias. No se ha
ejecutado `terraform plan`/`apply` ni ningún comando `aws`. Artefactos de
`terraform init` (`.terraform/`, `.terraform.lock.hcl`, `build/`) eliminados
al terminar.

## Documentación

`procesamiento/README.md`: nueva sección "Scheduling de Silver/Gold" con la
tabla de cadencia por grupo, el razonamiento de los dos ajustes horarios y la
limitación de zona horaria; nuevo bullet en "Relevante para tareas futuras"
señalando que, antes de aplicar `glue_scheduling.tf`, conviene corregir
primero los bugs ya documentados y sin resolver de las tareas 052
(`aparcamientos_silver_to_gold`) y 063 (`cartelera_cines_estrenos_silver_to_gold`
con Silver vacío, `afluencia_lugares_silver_to_gold` sin `--extra-py-files`)
— si no, empezarían a fallar en cada ejecución recurrente en vez de solo en
la ejecución puntual que los descubrió.

## Restricciones respetadas

- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se han tocado los `aws_glue_job` en sí ni el código de `procesamiento/`
  — solo triggers, en un fichero nuevo.
- No se han reabierto las decisiones de cadencia/mecanismo ya fijadas por el
  enunciado; los dos ajustes horarios y la excepción UTC de `cams_calidad_aire`
  están documentados con su motivo concreto, no son un cambio de diseño.
- No queda nada programado (cron/systemd/bucle) en esta EC2: el único cron
  escrito es código Terraform sin aplicar.
