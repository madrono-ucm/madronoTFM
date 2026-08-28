---
kind: vic-index
owner: Víctor (Pista Memoria)
created_at: "2026-08-28"
---

# `VIC_*` tickets — Memoria (thesis document) track

`documents/Memoria_TFM FV.docx` is dated June 2026 and describes an
architecture that in several places was **not built** (Kafka/Flink/Delta
Lake, MLflow, Power BI). Decision (28/8, `NEXT_STEPS.md` §5.2): **rewrite to
the real system as a justified cost-0 design choice**, and move the
unbuilt pieces to §7.5 *Futuras líneas*.

These `VIC_*` tickets are **outside the autonomous `madrono-agent` queue**
(the daemon only picks up `^\d+-[a-z0-9-]+\.md$`). Víctor works them in
parallel with the Sistema track — they don't depend on new code, and each
one points at the **living technical sources** so the memoria tracks the
real state of the repo as it evolves.

## How to use each ticket

Every ticket lists: the section(s) to write, the **fuente técnica** to read
first (`doc/NNN-*.md`, `PLATFORM_SCHEMA.md`, the module READMEs,
`NEXT_STEPS.md`), the key claims that must change vs the June draft, and
what stays. Coordinate edits on the `.docx` per `PLAN.md` (turn-taking /
Word Online) — it does not merge in git.

## Tickets

| Ticket | Sección(es) | Depende de |
|---|---|---|
| `VIC_01` | §5 Arquitectura (rewrite to real stack) | — |
| `VIC_02` | §6.1–6.4 Fuentes, preparación, flujos | — |
| `VIC_03` | §6.5 Orquestación · §6.6 Almacenamiento y consulta | — |
| `VIC_04` | §6.7 Explotación · §6.8 Ética/legal | FIL_06 landing helps §6.7/§6.8 |
| `VIC_05` | §7.1–7.3 Resultados, métricas, comparativas | ML Tier 1 + Tier 2 outputs |
| `VIC_06` | §7.4 Limitaciones · §7.5 Futuras líneas | — (can draft now, refine later) |
| `VIC_07` | §1 Resumen · §2 Palabras clave · §3–4 Introducción/Metodología (consistency pass) | after VIC_01–06 |

## Cross-cutting: claims in the June draft that must change

- "Apache Kafka / Kafka Connect / Avro" → EventBridge Scheduler + Lambda;
  Kafka → §7.5.
- "Flink/KSQL ruta caliente / streaming en ventana" → **no hay ruta
  caliente**; el estado "instantáneo" es la última fila Gold horaria.
- "tablas Delta / Delta Lake" → Parquet + catálogo Glue + Athena Partition
  Projection.
- "MLflow / Evidently / ONNX" → sí se usan, pero descríbelos sobre el
  pipeline real de `modelado/` (no como capa genérica). Ver ML tickets.
- "cuadro de mando en Power BI" → retirado, §7.5.
- "observación por satélite" (enriquecimiento europeo) → §7.5; CAMS
  (previsión) es el sustrato europeo real usado.
- Afluencia de lugares vía `populartimes`/Google → **señal derivada** de
  sensores vía el grafo (tarea 089 + FIL_06); la discusión de "zona gris"
  de §6.8 pasa a ser una *futura línea* (proveedor comercial), no una
  dependencia activa.
