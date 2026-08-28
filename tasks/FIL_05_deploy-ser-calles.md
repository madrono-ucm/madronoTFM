---
kind: fil
title: "Deploy ser_calles producer end-to-end + assess for disponibilidad_aparcamiento"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
depends_on: [FIL_02]
created_at: "2026-08-28"
---

> **Estado 28/8: 🟡 Ingesta hecha.** Lambda `madrono-tfm-dev-ser_calles`
> (512 MB / 300 s por el CSV de ~15 MB) + schedule semanal desplegados;
> invocada → Bronze real (34.486 tramos). PR #151, `doc/FIL-03-05`.
> **Pendiente**: Silver/Gold + la valoración de si mejora
> `disponibilidad_aparcamiento` (la ocupación en vivo sigue necesitando
> "SER. Tiques de aparcamiento", aparte).

## Context

`ser_calles_madrid.py` captures the streets/plazas of Madrid's regulated
on-street parking service (SER, dataset `218228-0`). Task 090 verified a real
capture (10 segments) and fixed two real source bugs (resource-id ≠ year;
corrupted `gis_x/gis_y` needing `/1e10`). Code-only today.

This gives **static** on-street parking capacity/zoning — NOT live occupancy.
Per `doc/090`, live occupancy would need a separate dataset ("SER. Tiques de
aparcamiento"), which is a candidate but not in scope here.

## Goal

`ser_calles` flows Bronze → Silver → Gold on a low-frequency schedule; the
Gold table is a usable static reference for capacity by zone/street, and the
ticket ends with a written verdict on whether it can meaningfully improve the
`disponibilidad_aparcamiento` assistant tool (which today only reads the
off-street `aparcamientos` table).

## Scope

1. **Lambda + schedule** (`lambda.tf`): `local.producers` +
   `local.schedules`, weekly cadence.
2. **Silver/Gold** (`procesamiento/silver_gold/ser_calles/`): Silver = one
   row per street segment (street, zone/colour, regulation type, capacity if
   present, lat/lon from the recovered coords, `date` partition). Gold =
   `ser_calles_por_zona` (aggregate capacity + segment count per SER zone /
   barrio). Same structure as `procesamiento/silver_gold/aparcamientos/`.
3. **Glue + Athena wiring** in `glue.tf` / `glue_scheduling.tf` /
   `athena.tf` — full per-dataset block, partition projection from
   `2026-08-01`.
4. **Deploy**: plan → review → apply. Invoke Lambda once, run Glue jobs once,
   verify Bronze/Silver/Gold.
5. **Athena verify**: `SELECT count(*) FROM ser_calles_por_zona` > 0.
6. **Assessment**: short section in the `doc/` write-up — can SER street
   capacity + the existing off-street `aparcamientos` occupancy be combined
   into a better `disponibilidad_aparcamiento` answer? If yes, note what a
   follow-up ticket would change in `asistente/`. If the real blocker is
   live occupancy (SER tickets dataset), say so and leave it for the
   decision-making backlog in `NEXT_STEPS.md`.

## Acceptance

- Bronze + Silver + Gold populated; Gold queryable in Athena.
- Weekly schedule `ENABLED`.
- `doc/` write-up includes the `disponibilidad_aparcamiento` verdict.
- `terraform plan` clean afterwards.

## Constraints

- `allow_infra_apply: true`, this dataset only.
- Keep the `/1e10` coord-recovery fix from task 090 — add a regression test
  in `ingesta/tests/` if there isn't one.
