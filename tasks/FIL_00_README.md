---
kind: fil-index
owner: Filippos (interactive, NOT the autonomous queue)
created_at: "2026-08-28"
---

# `FIL_*` tickets — interactive data-foundation work

These tickets are **outside the autonomous `madrono-agent` queue**. The daemon
only picks up files matching `^\d+-[a-z0-9-]+\.md$` (see
`tasks/scripts/tasks_store.py:21`), so `FIL_*` files are ignored by it and are
worked interactively by Filippos, in any order the dependencies allow, without
waiting for the numbered queue.

## Why this set exists

Session of 2026-08-28: health-check of every integrated Madrid source + a
codebase/doc scan for planned-but-missing datapoints, done because the ML
phase of the TFM (memoria objective: *"entrenar modelos predictivos de
afluencia, congestión y calidad del aire"*) needs a solid, complete data
foundation first. Findings and the full decision-making picture are in
`NEXT_STEPS.md` (section "Foundation gaps — 2026-08-28").

## Tickets

| Ticket | What | Depends on |
|---|---|---|
| `FIL_01` | Fix `aemet_prevision` silver→gold Glue job (failing in prod) | — |
| `FIL_02` | Add `lambda_handler` + Bronze writer to the 3 task-090 capture modules | — |
| `FIL_03` | Deploy `emt_incidencias` producer end-to-end (Lambda + schedule + Glue B→S→G) | FIL_02 |
| `FIL_04` | Deploy `parques_jardines` producer + add park `:Lugar` to the graph | FIL_02 |
| `FIL_05` | Deploy `ser_calles` producer end-to-end | FIL_02 |
| `FIL_06` | Rework `afluencia_lugares`: retire Google Maps, materialise estimated-afluencia Gold time-series | graph reload w/ aforos (done 2026-08-28) |
| `FIL_07` | `transporte_publico_emt`: capture more than one stop | — |

## Deployment note

`FIL_03`–`FIL_06` include real `terraform apply` / Lambda / Glue changes.
Same guardrail as task 098: run `terraform plan`, review every change, apply,
verify data lands in Bronze→Silver→Gold and is queryable in Athena. AWS creds:
`AWS_PROFILE=madrono` (`eu-west-1`), user `madrono-terraform-deployer`.
