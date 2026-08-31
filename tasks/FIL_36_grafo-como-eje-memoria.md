---
kind: fil
title: "El grafo como eje de la memoria — figura, DATA_SOURCES, promoción de ítems de encuadre"
owner: Filippos (interactive) + coordinación VIKT
status: done
resolved_at: "2026-08-31"
nota: "Sistema hecho (DATA_SOURCES.md, viz/README.md, README raíz). Parte editorial de la memoria -> VIKT_10; ampliación de la sección Beneficiarios -> FIL_45."
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_35]
milestone: M5
target: "2026-09-13"
---

## Objetivo

Cerrar el círculo en la memoria: el TFM se lee como "un análisis sobre el
grafo de Madrid", con el mapa animado como artefacto tangible.

## Alcance (parte editorial se coordina con VIKT_10)

- **Figura de la memoria**: la tira `viz/mapa_frames.png` + subsección
  "Visualización animada de la previsión sobre el grafo" (alimenta `VIKT_06`
  / demo de defensa).
- **`DATA_SOURCES.md`** en la raíz: atribución CC BY 4.0 de las fuentes
  externas usadas o citadas — MTD (Gómez & Ilarri, `10.17632/697ht4f65b.4`),
  meteo histórica de la Comunidad de Madrid — además de las municipales ya
  documentadas.
- **Promoción de ítems de encuadre** (decidido 2026-08-30):
  - **city-planner inputs** → *entregado*: la vista agregada de importancia
    de aristas es un artefacto de planificación; se describe como demostrado,
    no como trabajo futuro.
  - **hosted endpoint** → *entregado parcial*: el mapa está en una URL
    (Pages). Una API de predicción de producción sigue siendo trabajo futuro.
  - **open dataset** y **cyclist / movilidad reducida routing** → siguen
    siendo encuadre; se refuerza el texto ("el sustrato de datos ya existe")
    sin comprometer entregable.
- **Limitaciones a declarar explícitamente** (§7.4, salen de los gaps de
  `FIL_33`): ventana de datos ~14 días (partition projection deslizante),
  ruido sólo diario y por distrito (no animado), aire IDW desde ~24
  estaciones (superficie suave, no calle), importancia de aristas estática,
  grafo `coords-knn8` y no `PROXIMO_A`.
- Reestructura ligera del índice de la memoria hacia el eje del grafo
  (construcción → señales → previsión → recomendación → servido → resultados).

## Coste

Cero AWS.

## Entregable / progreso

Milestone **M5** en `viz/PROGRESO_MAPA.md`.

## Ampliación pendiente — encuadre de justicia ambiental + "Beneficiarios" (`FIL_45`/`FIL_46`)

Añadir a la memoria (coordinado con `VIKT_10`):

- **Párrafo de justicia ambiental**: la exposición al aire y al ruido en
  Madrid no se reparte igual; este trabajo hace la *previsión* legible por
  banda de umbral y por perfil de sensibilidad (capa `FIL_45`), pero **no**
  hace el análisis distribucional formal (exposición × vulnerabilidad
  socioeconómica con test) — se deja explícitamente como límite y trabajo
  futuro, sin cruzar datos personales ni señalar barrios.
- **Sección "Beneficiarios"**:
  - Personas con **asma / EPOC**, **mayores**, **infancia**,
    **ciclistas y peatones**, **movilidad reducida**, **trabajo al aire
    libre** — la capa social les da "cuándo" y "por dónde" con su propio
    umbral.
  - **Administración de movilidad** — la vista agregada de importancia de
    aristas + el pulso de distrito son input de planificación.
  - **Comunidad de datos abiertos** — todo reproducible desde fuentes
    públicas; se cita y valida MTD (`FIL_38`).
  - Alineado con los **ODS 3** (salud) y **11** (ciudades sostenibles).
- Citar `FIL_46` como trabajo futuro (acceso en lenguaje natural + alertas
  anticipadas por distrito) — sustrato hecho, falta canal de notificación y
  política de umbral.
