# FIL-16 — Observabilidad: fallos de Glue + frescura de Gold

Los incidentes `FIL_09` (37/48 jobs de Glue en `LAUNCH ERROR` 28 h) y
`FIL_11` (Gold de ruido/avisos escribiendo 0 filas con el job en
`SUCCEEDED`) se encontraron por QA manual. Dos señales mínimas cierran ese
hueco: una para "el job falló", otra para "el job dice OK pero no hay dato".

## 1. Frescura de Gold — `herramientas/salud/frescura_gold.py`

Mira el **dato**, no el estado del job. Por cada tabla Gold consulta la
partición (`max(date)`) o `max(processed_at)` más reciente y clasifica el
desfase contra un umbral por cadencia:

| Cadencia | Umbral | Tablas |
|---|---|---|
| horaria | 30 h | tráfico, calidad aire, BiciMAD, aparcamientos, meteo, EMT, bluesky, afluencia |
| diaria | 50 h | avisos/previsión AEMET, CAMS, agenda eventos, cartelera, **ruido (192 h)** |
| descontinuada | — | `aforos_peatones_bicicletas` (fuente municipal cortada 2024-06-30, doc/087) |

Detalles que el **run en vivo** obligó a afinar:

- **Datasets con partición hacia el futuro** (agenda de eventos, estrenos de
  cine, avisos por vigencia, previsión por leadtime): `max(date)` da una
  fecha futura, no mide frescura → se usa `max(processed_at)`.
- **Ruido**: la fuente municipal publica con ~1 semana de retraso
  (constatado en `FIL_11`); su `max(date)` va legítimamente días por detrás
  aunque el pipeline esté vivo → umbral propio de 192 h.
- **`aforos`**: descontinuada; se espera estancada **siempre**. Lo anómalo
  sería que apareciera fresca (→ `descontinuada_con_datos_nuevos`).

Código de salida:

- **Producción** (sin flag): cualquier tabla estancada → **exit 1**. Es la
  señal que habría cazado `FIL_11` el primer día.
- **Pipeline congelado** (`--pipeline-congelado`, o `PIPELINE_ENABLED=false`
  en el entorno): el estancamiento horario/diario es esperado → **exit 0**;
  se reporta igualmente y se cuenta cuántas "habrían alertado en
  producción". Sólo `descontinuada_con_datos_nuevos` sigue siendo exit 1.

### Verificación en vivo (2026-08-30, Athena real)

```
Frescura de Gold @ 2026-08-30T13:51  (0 alertarían en producción)
  ... 14 tablas fresca / ruido fresca (109.9 h < 192) / aforos descontinuada_ok
```

Todas frescas: la ingesta se congeló ese mismo día, así que Gold aún estaba
al día. Conforme la ventana congelada envejezca, el chequeo empezará a
marcar `estancada` (con `--pipeline-congelado` seguirá en exit 0). Tests:
`herramientas/salud/tests/test_frescura_gold.py` (11).

## 2. Fallos de Glue — `infra/terraform/observabilidad.tf`

`aws_cloudwatch_event_rule` sobre `Glue Job State Change` con
`state ∈ {FAILED, TIMEOUT, ERROR}` → `aws_cloudwatch_event_target` con
`input_transformer` (email legible: job, estado, run, motivo) →
`aws_sns_topic` → `aws_sns_topic_subscription` email (opcional, sólo si
`var.alertas_email` está puesta). `aws_sns_topic_policy` deja publicar a
`events.amazonaws.com` restringido al ARN de la regla.

**Estado: diseñado, sin `terraform apply`** — mismo patrón que
`glue_scheduling.tf` (tarea 064):

- El pipeline está congelado (`pipeline_enabled = false`): ningún job corre,
  la regla no dispararía.
- La suscripción por email necesita confirmación manual desde el buzón, que
  no se puede hacer en el `apply`.

Al reanudar la ingesta: poner `alertas_email` en el `.tfvars` local,
`terraform apply -target=aws_sns_topic.alertas_pipeline -target=aws_sns_topic_policy.alertas_pipeline -target=aws_cloudwatch_event_rule.glue_job_failed -target=aws_cloudwatch_event_target.glue_job_failed_sns -target=aws_sns_topic_subscription.alertas_email`
y confirmar la suscripción. Coste ~0 (SNS: 1000 emails/mes gratis;
EventBridge no cobra por reglas de eventos AWS). `terraform validate` +
`fmt -check` en verde.

## Fuera de alcance (§7.5)

Dashboards (CloudWatch/Grafana), alarma de coste (`ce:GetCostAndUsage` sigue
sin permisos, doc/098), métricas de calidad de dato por columna.
