---
kind: fil
title: "Deploy parques_jardines producer + add park :Lugar nodes to the graph"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
depends_on: [FIL_02]
created_at: "2026-08-28"
---

> **Estado 28/8: ✅ HECHO.** Lambda + schedule semanal → Bronze (203
> parques). `grafo/`: `fetch_parques_bronze`, `lugar_from_parque_bronze`
> (`tipo="parque"`), en `cargar_grafo.py`, tests (PR #151). Sus relaciones
> `PROXIMO_A` quedaron bloqueadas por cortes de AuraDB Free hasta que
> `FIL_08` (recarga por lotes `UNWIND`) lo arregló: recarga limpia en ~9 min,
> **203 `:Lugar {tipo:"parque"}`, 199 con `PROXIMO_A` a un sensor** (antes 0),
> 203 con `UBICADO_EN`. Ver `doc/FIL-08`.

## Context

`parques_jardines_madrid.py` captures municipal parks and gardens (dataset
`200761-0`). Task 090 verified a real capture (8 parks) but left it code-only.
This is the direct fix for the **"places have only a small sample"** problem:
today there is **no park `:Lugar` in the graph at all**, and the
`afluencia_estimada` / `eventos_cercanos` tools can't reason about "un paseo
por el parque" — one of the canonical use cases in the memoria.

This is a reference dataset (changes rarely), so treat it like
`poi_madrid` / `crtm_red_transporte_madrid`: low-frequency capture, Silver/Gold
optional, main value is as a graph node source.

## Goal

1. Parks land in Bronze on a low-frequency schedule (weekly).
2. Parks become `:Lugar` nodes in Neo4j (`tipo = "parque"`), enriched with
   OSM tags where available, and picked up by `PROXIMO_A` so nearby sensors
   attach.

## Scope

1. **Lambda + schedule** (`lambda.tf`): `local.producers` entry (`module =
   "parques_jardines_madrid"`, `dataset = "parques_jardines"`),
   `local.schedules` entry — weekly (`cron(0 5 ? * MON *)` Madrid).
2. **Silver/Gold**: optional. If the raw feed is clean enough to be a node
   source directly (name + geometry + address), skip Silver/Gold like
   `poi_madrid` does and read Bronze directly in `grafo/extract.py`. Decide
   and document. If a Gold table is wanted for the Power BI side, mirror the
   `poi_madrid` → (no gold) decision explicitly.
3. **Graph** (`grafo/`):
   - `grafo/extract.py`: `fetch_parques_bronze()` (S3 JSON read, same as
     `fetch_poi_bronze`).
   - `grafo/nodos.py`: `lugar_from_parque_bronze` / `lugares_from_parques_bronze`
     (`id = "parques_jardines:<id>"`, `tipo = "parque"`), same contract as
     `lugar_from_poi_bronze`.
   - `grafo/cargar_grafo.py`: add `lugares_from_parques_bronze(...)` to the
     `lugares` union (so it also gets OSM enrichment + `UBICADO_EN` +
     `PROXIMO_A`).
   - Tests in `grafo/tests/` mirroring the POI node tests.
4. **Deploy**: `terraform plan` → review → `apply`. Invoke Lambda once,
   confirm Bronze lands.
5. **Reload graph**: `python -m grafo.cargar_grafo` against the real instance
   (AWS + Neo4j creds from SSM, `AWS_PROFILE=madrono`). Verify with Cypher:
   `MATCH (l:Lugar {tipo:"parque"}) RETURN count(l)` > 0, and at least one
   park has a `PROXIMO_A` edge to a sensor.
6. `doc/` write-up + update `grafo/README.md` "Orígenes por tipo de nodo".

## Acceptance

- Bronze partition for parks exists.
- `MATCH (l:Lugar {tipo:"parque"}) RETURN count(l)` ≥ 8 in the live graph.
- Weekly schedule `ENABLED`.
- `terraform plan` clean afterwards.

## Constraints

- `allow_infra_apply: true` for this dataset + the graph reload only.
- The graph reload is a `MERGE` (non-destructive) but a real write to the
  production Neo4j instance — verify counts before and after.
- Don't reintroduce a narrow Athena partition-projection window if a Gold
  table is added.
