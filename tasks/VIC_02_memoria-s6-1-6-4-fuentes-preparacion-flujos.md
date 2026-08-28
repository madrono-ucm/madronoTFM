---
kind: vic
title: "Memoria §6.1–6.4 — Fuentes, preparación de datos, flujos, procesamiento"
owner: Víctor
status: pending
created_at: "2026-08-28"
---

## Secciones

§6.1 Fuentes de datos · §6.2 Preparación de datos · §6.3 Flujos de datos ·
§6.4 Procesamiento (batch, streaming).

## Fuente técnica (leer primero)

- `ingesta/README.md` — una sección por productor (25 módulos de captura).
- `PLATFORM_SCHEMA.md` — datasets Silver/Gold en producción.
- `NEXT_STEPS.md` §"Estado a 28/8" §1 (14 productores continuos, cadencias) y
  §2 (gaps: `afluencia_lugares` derivado, 3 productores por desplegar,
  `aforos` descontinuado, EMT 1 parada).
- `doc/002`–`doc/024` (capturas), `doc/034`–`doc/040` (hora de Madrid en
  Bronze), `doc/046`–`doc/060` (Silver/Gold por dataset), `doc/072`–`doc/077`
  (incidente de lectura incremental / duplicados — buen caso de validación
  para §7).
- Puertas de calidad: `procesamiento/silver_gold/*/ge_suite.py`.

## Qué cambia respecto al borrador de junio

- **§6.1** — el borrador agrupa las fuentes en 4 categorías sin números.
  Concretar: ~24 fuentes implementadas, **14 en producción continua**
  (tráfico, calidad aire, meteo, BiciMAD, aparcamientos, EMT llegadas,
  ruido, agenda eventos, Bluesky, cartelera, CAMS, avisos/previsión AEMET),
  + fuentes de referencia estáticas (callejero, barrios/distritos, POI,
  CRTM, calendario laboral) + 3 nuevas por desplegar (`emt_incidencias`,
  `parques_jardines`, `ser_calles`, tarea 090 / `FIL_03`–`FIL_05`).
  - **Afluencia de lugares**: ya **no** es Google `populartimes`. Es una
    señal derivada de sensores próximos vía el grafo (tarea 089 + `FIL_06`).
  - **Aforos peatones/bicicletas**: fuente municipal **congelada el
    2024-06-30**; se usa como histórico (83 estaciones), no como señal viva.
  - Enriquecimiento europeo real = **CAMS** (previsión de calidad del aire).
    "Observación por satélite" → §7.5.
- **§6.2** — mantener la idea de escala relativa común 0–100 % para
  afluencia/congestión y las puertas de calidad. Precisar que la puerta es
  **Great Expectations** por dataset en el paso Bronze→Silver, y que un lote
  que no la pasa **no progresa a Gold** (verificable en
  `silver/_quality_reports/`). Citar como ejemplo real el incidente
  `doc/072`–`doc/077` (lectura incremental + duplicados) y cómo se cerró.
- **§6.3** — hay **un solo flujo real: batch**. El borrador describe
  streaming + batch confluyendo en Gold; reescribir: fuentes → Lambda
  (programada) → Bronze (Parquet particionado por fecha/hora de Madrid) →
  Glue Bronze→Silver (limpieza + GE) → Glue Silver→Gold (agregación
  horaria/diaria) → Athena / Neo4j / modelado. No hay Kafka ni ventana
  streaming.
- **§6.4** — el batch con Glue genera las features históricas y (nuevo)
  alimenta el **feature store de `modelado/`** y la construcción del grafo.
  El "procesamiento en streaming calcula el estado instantáneo" se sustituye
  por "la última agregación horaria de Gold es el estado más reciente
  disponible".

## Qué se mantiene

- Bronze conserva el dato original; Silver limpia/tipa/normaliza; Gold es la
  única superficie que consultan las capas de explotación.
- La homogeneización de marcas temporales a hora de Madrid (`doc/034`–`040`)
  y de sistemas de referencia geográfica.

## Aceptación

- §6.1 da un recuento concreto y coherente con `PLATFORM_SCHEMA.md` /
  `ingesta/README.md`.
- §6.3/§6.4 no afirman que exista procesamiento en streaming.
- La afluencia de lugares se describe como señal derivada, con su fórmula
  marcada como aproximación.
