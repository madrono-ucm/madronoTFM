---
kind: fil
title: "Deploy emt_incidencias producer end-to-end (Lambda + schedule + Glue B→S→G)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
depends_on: [FIL_02]
created_at: "2026-08-28"
---

> **Estado 28/8: 🟡 Ingesta hecha.** Lambda `madrono-tfm-dev-emt_incidencias`
> + schedule `rate(30 minutes)` desplegados (`terraform apply -target`);
> invocada de verdad → Bronze real (~110 incidencias). PR #151,
> `doc/FIL-03-05-deploy-productores-tarea-090.md`.
> **Pendiente**: Silver/Gold (bloque `glue.tf` + `aggregate.py` + `ge_suite.py`
> + tabla Athena) — solo si la fase de ML lo necesita agregado.

## Context

`emt_incidencias_madrid.py` captures the live RSS feed of EMT service
disruptions (dataset `202992-0`). Verified in task 090 as a real, live feed
(10 active incidents at capture time). It is a direct signal for the
`opciones_movilidad` assistant tool (avoid recommending a line with a
suppressed stop) and a useful ML feature (disruption → traffic / afluencia
shift near affected corridors).

Currently: code only, no Bronze/Silver/Gold, no Lambda, no schedule.

## Goal

`emt_incidencias` flows Bronze → Silver → Gold on a schedule, queryable in
Athena, same shape as the other 14 live producers.

## Scope

1. **Lambda + schedule** (`infra/terraform/lambda.tf`): add an entry to
   `local.producers` (`module = "emt_incidencias_madrid"`, `dataset =
   "emt_incidencias"`) and to `local.schedules`. Cadence: every 15–30 min
   (incidents are time-sensitive but low-volume) — pick one, document why.
2. **Silver/Gold** (`procesamiento/silver_gold/emt_incidencias/`): new
   `glue_bronze_to_silver.py` + `glue_silver_to_gold.py` + `aggregate.py`,
   same structure as `procesamiento/silver_gold/agenda_eventos/`. Silver:
   one row per incident (id, line(s) affected, start/end, description,
   geometry if present, `date`/`hora` partitions). Gold: suggested
   `emt_incidencias_por_linea_fecha` — per line per day: count of incidents,
   total disruption minutes, current-active flag.
3. **Glue wiring** (`infra/terraform/glue.tf` + `glue_scheduling.tf`): the
   full per-dataset block (S3 script objects, IAM role + data-access policy
   scoped to `bronze/emt_incidencias/*`, `silver/emt_incidencias/*`,
   `gold/emt_incidencias_por_linea_fecha/*`, `_quality_reports/...`), the two
   Glue jobs, the `scheduled-bronze-to-silver` trigger and
   `conditional-silver-to-gold` trigger. Copy the newest dataset block
   (`bluesky_menciones` or `agenda_eventos`) as the template.
4. **Athena** (`infra/terraform/athena.tf`): partition-projection table for
   the Gold table, `projection.<partcol>.range` starting `2026-08-01` (not a
   narrow 14-day window — see the aforos partition-projection bug, task 098).
5. **Deploy**: `terraform plan` → review every change → `apply` (target if
   `main` shows unrelated drift). Invoke the Lambda once manually
   (`aws lambda invoke`), confirm Bronze object lands. Run the Glue jobs
   once, confirm Silver + Gold populate.
6. **Verify**: Athena `SELECT count(*), max(processed_at) FROM
   emt_incidencias_por_linea_fecha` returns real rows.
7. `doc/` write-up.

## Acceptance

- Bronze partition for today exists with real incident data.
- Both Glue jobs `SUCCEEDED`; Gold queryable in Athena with fresh
  `processed_at`.
- Schedule (`aws scheduler get-schedule`) is `ENABLED`.
- `terraform plan` clean afterwards (only Kafka pending, as per `NEXT_STEPS`).

## Constraints

- `allow_infra_apply: true`, scoped to this dataset's resources only.
- Don't widen or touch other datasets' Terraform.
- If the RSS feed shape differs from the task-090 sample, fix the parser in
  `ingesta/capturas/emt_incidencias_madrid.py` (with a test) rather than
  forcing the Glue script to absorb it.
