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
`NEXT_STEPS.md`, sección "Estado a 28/8".

## Tickets — estado a 2026-08-28

| Ticket | Qué | Estado |
|---|---|---|
| `FIL_01` | Fix `aemet_prevision` silver→gold (fallo en prod) | ✅ **HECHO** — IAM aplicado, job → SUCCEEDED, Gold fresco (PR #151, `doc/FIL-01`) |
| `FIL_02` | `lambda_handler` + BronzeWriter en los 3 módulos de la tarea 090 | ✅ **HECHO** (PR #150) |
| `FIL_03` | Desplegar `emt_incidencias` | 🟡 **Ingesta hecha** — Lambda + schedule 30 min → Bronze real (~110 incidencias). Silver/Gold aplazado (PR #151, `doc/FIL-03-05`) |
| `FIL_04` | Desplegar `parques_jardines` + parques `:Lugar` en el grafo | 🟡 **Casi** — Lambda + schedule → Bronze (203 parques); 203 `:Lugar {tipo:"parque"}` cargados en Neo4j; **falta** crear sus `PROXIMO_A` (recarga de `cargar_grafo.py` cae por `SessionExpired` en AuraDB Free — ver `doc/FIL-06` "Problema abierto") (PR #151) |
| `FIL_05` | Desplegar `ser_calles` | 🟡 **Ingesta hecha** — Lambda + schedule semanal (512 MB) → Bronze (34.486 tramos). Silver/Gold + valoración `disponibilidad_aparcamiento` aplazados (PR #151) |
| `FIL_06` | `afluencia_lugares`: retirar Google Maps, señal derivada como Gold | 🟡 **Parte 1/2 hecha** — productor Google Popular Times retirado y aplicado (Lambda/schedule/SSM destruidos), `populartimes` fuera. Fórmula compartida `nivel.py` + tests. **Parte 2/2** (Glue job horario) especificada en `doc/FIL-06`, sin construir (PR #152) |
| `FIL_07` | `transporte_publico_emt`: capturar más de una parada | ⬜ **Sin empezar** (prioridad más baja) |
| `FIL_08` | `cargar_grafo.py` resiliente a cortes de AuraDB Free (`UNWIND` + reintento) | ⬜ **Sin empezar** — bloquea el cierre de `FIL_04` y la parte 2 de `FIL_06` |

### Seguimiento surgido en la ejecución

- **Recarga de Neo4j poco fiable**: `cargar_grafo.py` cae por
  `neo4j.exceptions.SessionExpired` en recargas largas contra AuraDB Free
  (falló 3 veces el 28/8). Bloquea el cierre de `FIL_04` y la parte 2 de
  `FIL_06`. Sugerido: `FIL_08` — hacer `cargar_grafo.py` resiliente (`UNWIND`
  para agrupar los `MERGE`, reconexión/reintento por lote).
- **Silver/Gold de `emt_incidencias` / `ser_calles`**: bloque `glue.tf` +
  `aggregate.py` + `ge_suite.py` + tabla Athena. Solo si la fase de ML lo
  necesita agregado; el JSON de Bronze ya es consumible.

## Deployment note

`FIL_03`–`FIL_06` include real `terraform apply` / Lambda / Glue changes.
Same guardrail as task 098: run `terraform plan`, review every change, apply,
verify data lands in Bronze→Silver→Gold and is queryable in Athena. AWS creds:
`AWS_PROFILE=madrono` (`eu-west-1`), user `madrono-terraform-deployer`.
