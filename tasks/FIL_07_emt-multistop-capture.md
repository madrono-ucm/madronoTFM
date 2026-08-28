---
kind: fil
title: "transporte_publico_emt: capture more than one bus stop"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
created_at: "2026-08-28"
---

## Context

`transporte_publico_emt_por_parada_hora` Gold has exactly **1 distinct
`stop_id`** (`"71"`). Investigated 2026-08-28: not a source limit, not a bug —
`ingesta/capturas/transporte_publico_madrid.py` hits the EMT arrivals
endpoint `/v2/transport/busemtmad/stops/{stop_id}/arrives/` (one stop per
call) and both `capture_all()` and `lambda_handler()` use a single
`config.stop_id` (default `"71"`, from the tasks 003/024 sample). EMT
publishes thousands of stops.

This is thin as an ML mobility feature and as an assistant signal
(`opciones_movilidad` reports "sin datos" for most origin/destination pairs).

## Goal

The producer captures arrivals for a curated set of stops (tens–low
hundreds), Gold has that many distinct `stop_id`, without tripping the
MobilityLabs rate limit.

## Scope

1. **Stop list**: derive a bounded set of `stop_id`s. Options, pick one:
   - the EMT stops master endpoint (`/v1/transport/busemtmad/stops/...`) →
     filter to a bounding box / a set of key corridors;
   - the already-ingested `crtm_red_transporte_madrid` bus stops
     (`grafo/extract.fetch_paradas_crtm_bronze`) filtered to EMT operator.
   Store the list as a small committed JSON, not fetched every run (same
   pattern as the OSM sample) — or fetch the master list on a separate weekly
   schedule and cache to Bronze.
2. **Capture loop**: `capture_all()` iterates the stop list, one API call per
   stop, with a small sleep / concurrency cap to respect the rate limit.
   `HTTP_MAX_RETRIES` already handles transient failures; a single stop
   failing must not abort the batch (log + skip).
3. **Config**: `EMT_STOP_IDS` env (comma-separated) overrides the file, same
   spirit as the current `EMT_STOP_ID`.
4. **Silver/Gold**: no schema change — `stop_id` is already a column and a
   Gold group key. Confirm the aggregate handles N stops.
5. **Deploy**: plan → review → apply (Lambda timeout / memory may need a
   bump for the loop — check). Invoke once, confirm Bronze has N stops, run
   Glue, confirm Gold `COUNT(DISTINCT stop_id)` = N.
6. `doc/` write-up + update `grafo/README.md` "Hallazgo real 1" and
   `NEXT_STEPS.md` Priority 7.

## Acceptance

- Gold `SELECT COUNT(DISTINCT stop_id) FROM
  transporte_publico_emt_por_parada_hora` ≥ 30 for today's partition.
- No rate-limit errors in the Lambda logs across a full run.
- Lambda still completes within its timeout.
- `terraform plan` clean afterwards.

## Constraints

- `allow_infra_apply: true` for the Lambda config + any schedule change.
- Respect MobilityLabs rate limits — if the curated list has to stay small
  (e.g. ≤50) to stay safe, that's fine; document the ceiling.
- Keep `stop_id = "71"` working (don't break existing history continuity).
