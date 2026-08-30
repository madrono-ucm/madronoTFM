---
kind: fil
title: "Add lambda_handler + BronzeWriter to the 3 task-090 capture modules"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-28"
resolved_at: "2026-08-30"  # frontmatter alineado con FIL_00_README (ya estaba HECHO)
---

> **Estado 28/8: ✅ HECHO.** `capture_all()` + `lambda_handler()` +
> `DATASET_NAME` en los 3 módulos; 3 clases de test nuevas; smoke test en
> vivo (110 / 203 / 34.486 registros). PR #150. 844 tests en verde.

## Context

Task 090 (25/8) added three capture modules but **only in "sample" form** —
they write a local JSON fixture via `_write_json`, have no `lambda_handler`,
and never call `BronzeWriter`. No Lambda, no schedule, no Bronze data exists
for any of them:

- `ingesta/capturas/emt_incidencias_madrid.py` — EMT service-disruption RSS
  feed (live)
- `ingesta/capturas/parques_jardines_madrid.py` — municipal parks (reference)
- `ingesta/capturas/ser_calles_madrid.py` — SER regulated-parking streets
  (reference)

This ticket is the **code-only prerequisite** for FIL_03/04/05 (which deploy
the infra). No AWS changes here.

## Goal

Each of the three modules exposes a `lambda_handler(event, context)` that
does a full capture and writes to real Bronze via `BronzeWriter`, following
the exact pattern of an existing producer (`ingesta/capturas/bicimad.py` for
a live feed; `ingesta/capturas/aparcamientos_madrid.py` for the retry/parse
shape). Tests cover the handler path with mocked HTTP + a fake `BronzeWriter`.

## Scope

For each module:

1. Add `DATASET_NAME` constant (Bronze prefix). Suggested:
   `emt_incidencias`, `parques_jardines`, `ser_calles` (plain, no suffix —
   avoid the `afluencia_lugares_patron_tipico` mismatch trap noted in
   `glue.tf`).
2. Add `capture_all(config) -> list[dict]` (full capture, no sample slice) if
   the module only has `capture_sample` today.
3. Add `lambda_handler(event, context)`:
   ```python
   config = CaptureConfig.from_env()
   records = capture_all(config)
   writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
   out_path = writer.write_batch(records)
   return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}
   ```
   (copy the shape from `transporte_publico_madrid.py::lambda_handler`).
4. `parques_jardines` and `ser_calles` are reference datasets that change
   rarely — the handler is still a full re-capture; cadence (weekly/monthly)
   is decided in the deploy ticket, not here.
5. Tests in `ingesta/tests/`: mock `requests`, inject a fake `BronzeWriter`,
   assert the handler returns the right `records_written` and calls
   `write_batch` once. Reuse the committed sample fixtures as HTTP response
   bodies where possible.
6. Update `ingesta/README.md` sections for the 3 modules — they currently say
   "carga batch puntual, muestra"; note the added handler.

## Acceptance

- `python -m unittest discover -s ingesta/tests` green, with new handler tests.
- No infra files touched (`infra/terraform/` untouched).
- Each module importable as `ingesta.capturas.<mod>` with a `lambda_handler`
  attribute (matches `handler = "ingesta.capturas.${module}.lambda_handler"`
  in `lambda.tf`).

## Constraints

- No `--interval`/loop/cron in the modules (EC2 disk guardrail,
  `tasks/README.md`).
- Don't deploy anything — that's FIL_03/04/05.
