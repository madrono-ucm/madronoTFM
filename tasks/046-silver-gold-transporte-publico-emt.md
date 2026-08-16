---
id: 46
slug: silver-gold-transporte-publico-emt
title: "Silver/Gold: transporte público EMT (siguiendo el patrón de la tarea 041)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-16T09:30:00+00:00"
updated_at: "2026-08-16T09:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

La tarea 041 estableció el patrón Bronze→Silver→Gold (AWS Glue + Great
Expectations, código en `procesamiento/silver_gold/<dataset>/`) con tráfico
como piloto. Lee primero `procesamiento/README.md` completo — documenta el
patrón, las decisiones de diseño (Python puro para la lógica de negocio,
PySpark solo en los entry points de Glue, dónde vive la puerta de calidad) y
por qué. Esta tarea replica exactamente ese patrón para
`transporte_publico_emt` (llegadas de EMT a una parada, `ingesta/capturas/
transporte_publico_madrid.py`, ver `doc/003-...md`, `doc/024-...md` y la
sección correspondiente de `ingesta/README.md`).

**Diferencia relevante frente a tráfico**: este productor ya entrega
`location` en WGS84 (`lat`/`lon` estándar), no en EPSG:25830 — **no hace
falta ningún `geo.py`/reproyección** para este dataset.

## Objetivo

Crear `procesamiento/silver_gold/transporte_publico_emt/` con la misma
estructura que `procesamiento/silver_gold/trafico/` (salvo `geo.py`, que no
aplica aquí):

- `transform.py`: normalización + puerta de calidad (`validate_record`) —
  campos clave no nulos (`stop_id`, `line`, `measured_at`), tiempos de espera
  en rango plausible (p.ej. 0-120 minutos), descarta registros con
  `accessToken`/error de autenticación en vez de un tiempo de llegada real.
- `aggregate.py`: agregación Silver→Gold por `(stop_id, line, fecha, hora)` —
  tiempo medio/mínimo de espera observado y número de llegadas registradas en
  esa hora.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  expresadas de forma declarativa (mismo criterio doble-fuente-de-la-misma-
  regla que la tarea 041, ver su `ge_suite.py` como referencia).
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue, mismo patrón que los de tráfico.
- Tests en `procesamiento/tests/` (fixture con datos de ejemplo tomados de
  `ingesta/capturas/samples/transporte_publico_madrid_sample.json` o
  similar), cubriendo la puerta de calidad y la agregación, sin depender de
  `pyspark`/Great Expectations instalados (igual que la tarea 041).
- Añade el bloque correspondiente a `infra/terraform/glue.tf` (job de Glue x2,
  rol IAM acotado por prefijo `bronze/transporte_publico_emt/*`,
  `silver/transporte_publico_emt/*`, `gold/transporte_publico_emt_por_parada_hora/*`,
  catálogo Silver/Gold) — **sin aplicar** (`terraform validate` limpio con
  `terraform init -backend=false` es suficiente).

## Restricciones

- Alcance: solo este dataset. No toques `procesamiento/silver_gold/trafico/`
  ni ningún otro subpaquete.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2 (riesgo de disco
  compartido, mismo motivo que la tarea 041).
- Si algo de lo que hizo la tarea 041 (patrón, decisión de diseño) no encaja
  bien para este dataset, documenta por qué te desvías en vez de forzarlo.

## Criterios de aceptación

- `procesamiento/silver_gold/transporte_publico_emt/` completo, con tests en
  verde (`python3 -m unittest discover -s procesamiento/tests -t .`).
- `infra/terraform/glue.tf` extendido con el bloque de este dataset,
  `terraform validate` limpio, sin aplicar.
- `procesamiento/README.md` actualizado para reflejar que ya no es solo un
  piloto de un dataset.
