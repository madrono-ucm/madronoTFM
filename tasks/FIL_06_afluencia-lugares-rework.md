---
kind: fil
title: "Rework afluencia_lugares: retire Google Maps, materialise estimated-afluencia Gold time-series"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
created_at: "2026-08-28"
---

## Context — this is the headline foundation gap

`afluencia_lugares` is the memoria's answer to *"¿merece la pena ir a un
lugar?"* and it is **dead**: `ingesta/capturas/afluencia_lugares_madrid.py`
is 100% built on Google Maps `populartimes` (Places API + undocumented
scraping), the environment has no `GOOGLE_MAPS_API_KEY` and never will
(task 083: cost-0 is impossible), the committed sample is all
`is_mock: true`, and the Gold table
`afluencia_lugares_por_lugar_fecha_hora` has **0 rows**. The Lambda + Glue
jobs are deployed and "succeed" on mock/empty input, which hides the gap.

Task 089 already built the real replacement *methodology* as an on-demand
assistant tool: `afluencia_estimada(lugar)` resolves the place in the graph,
follows `PROXIMO_A` to nearby sensors, and combines traffic + noise + BiciMAD
+ air-quality into a `bajo/medio/alto` level. What's missing is
**materialising that as a historical Gold time-series** so it can (a) back a
Power BI view and (b) be a training target/feature for the ML phase.

## Goal

A real `afluencia_lugares` Gold table, refreshed hourly, with one row per
`:Lugar` per hour: the estimated-afluencia level + the component sensor
values it was derived from + a `data_completeness` score (how many of the 4
signals were available). No Google dependency anywhere in the path.

## Scope

1. **Retire the Google Maps producer**: delete / archive
   `ingesta/capturas/afluencia_lugares_madrid.py`'s live path, remove
   `populartimes` from `ingesta/requirements.txt`, remove the
   `afluencia_lugares_patron_tipico` producer from `local.producers` /
   `local.schedules` in `lambda.tf`. Keep the module's schema doc as history.
2. **New batch job** `procesamiento/afluencia_lugares/` (or a Glue job):
   hourly, for every `:Lugar` in the graph —
   - read the place + its `PROXIMO_A` sensor neighbours from Neo4j (reuse
     `asistente/neo4j_client.py` query shapes from task 089),
   - read each neighbour's latest Gold value (traffic `avg_load_ratio`,
     noise `avg_value`, bicimad `avg_occupancy_ratio`, calidad_aire
     `avg_value`) via Athena,
   - compute the same `nivel_estimado` formula as `afluencia_estimada`
     (import it, don't re-derive),
   - write one Gold row: `lugar_id, lat, lon, date, hora, nivel_estimado,
     n_trafico, n_ruido, n_bicimad, n_calidad_aire, <component avgs>,
     data_completeness, processed_at`.
   Table: `afluencia_lugares_por_lugar_fecha_hora` (reuse the name — the
   partition-projection table already exists in `athena.tf`; widen its
   `range` to `2026-08-01,NOW+1DAY` if still narrow).
3. **Schedule** it hourly (Glue trigger or EventBridge → Glue).
4. **Point the assistant** `afluencia_estimada` tool at this table as a fast
   path when a recent row exists, falling back to the live graph query
   otherwise (optional — can be a follow-up).
5. **Deploy**: plan → review → apply. Run once, verify Athena has rows for
   every `:Lugar` for the current hour.
6. `doc/` write-up + update `asistente/README.md` +
   `NEXT_STEPS.md` (Priority 2 / afluencia_lugares row) + memoria §6.7 note
   that afluencia is now a real derived signal, not Google.

## Acceptance

- `SELECT count(distinct lugar_id), max(processed_at) FROM
  afluencia_lugares_por_lugar_fecha_hora` returns ~all `:Lugar` and a fresh
  timestamp.
- No reference to `populartimes` / `GOOGLE_MAPS_API_KEY` anywhere in
  `ingesta/`, `infra/`, `requirements`.
- Rows accumulate hour over hour (check again next day).
- `terraform plan` clean afterwards.

## Constraints

- `allow_infra_apply: true` for the pipeline swap only.
- The formula is an explicit approximation — document its limits the same way
  task 089 / task 079 (`indice_calidad`) did. Don't present it as measured
  footfall.
- Depends on the graph having good `:Lugar` coverage — run after FIL_04
  (parks) for a fuller place set, but doesn't strictly block on it.
