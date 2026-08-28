---
kind: fil
title: "Fix aemet_prevision silver→gold Glue job (failing in production)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
created_at: "2026-08-28"
---

## Context

Health-check on 2026-08-28 found the Glue job
`madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold` **FAILED on its last
run** (started 2026-08-28T08:19 CEST):

```
An error occurred while calling o160.parquet. Failed to delete key: aemet_prevision_por_municipio_leadtime
```

The `aemet_avisos` half of the same job path is fine (Gold table
`aemet_avisos_por_zona_fecha_nivel` has 52 rows, partitioned by `fecha`). The
broken half is `aemet_prevision_por_municipio_leadtime` — Gold has only 4
rows, partitioned by `municipio_code`, and is not refreshing because the job
keeps failing at the write step.

`bronze-to-silver` for this dataset SUCCEEDS; Bronze is fresh (hourly). Only
the silver→gold write is broken.

## Goal

`madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold` runs green and
`aemet_prevision_por_municipio_leadtime` Gold refreshes with current
forecast data.

## Scope

1. Read `procesamiento/silver_gold/aemet_prevision_avisos/glue_silver_to_gold.py`
   — the "Failed to delete key" on a `.parquet` write is almost always one of:
   an overwrite against an S3 prefix the job's IAM role can't `DeleteObject`
   on; a `mode("overwrite")` + dynamic partition overwrite mismatch; or a
   partition-column/`partitionBy` change that left orphan objects.
2. Check the Glue role `madrono-tfm-dev-aemet-prevision-avisos-*-glue-role`
   data-access policy in `infra/terraform/glue.tf` — confirm it grants
   `s3:DeleteObject` on `gold/aemet_prevision_por_municipio_leadtime/*` (the
   `aemet_avisos` sibling prefix may be covered while this one isn't, or the
   `_$folder$` marker key isn't covered).
3. Fix the root cause (IAM policy in `glue.tf`, and/or the write mode in the
   Glue script). If it's IAM: `terraform plan` → review → `apply`.
4. Re-run the job (`aws glue start-job-run`) and confirm `SUCCEEDED`.
5. Verify in Athena: `SELECT count(*), max(processed_at) FROM
   aemet_prevision_por_municipio_leadtime` shows a fresh `processed_at` and a
   plausible row count (one row per municipio × leadtime bucket).

## Acceptance

- Last run of the job is `SUCCEEDED`.
- Gold table queryable in Athena with a `processed_at` from the fix run.
- Root cause written up in `doc/` (new `doc/FIL-01-*.md` or fold into the
  next numbered doc) — say whether it was IAM, write-mode, or partition drift.

## Constraints

- `allow_infra_apply: true` for the IAM/Glue change only. No unrelated
  Terraform drift — target the plan (`-target`) if `main` still shows other
  pending changes.
- Don't touch the `aemet_avisos` path — it works.
