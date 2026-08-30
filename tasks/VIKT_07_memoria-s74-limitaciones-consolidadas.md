---
kind: vikt
title: "Memoria §7.4 — lista consolidada y autoritativa de limitaciones (post-congelación)"
owner: Pista Memoria — documentación (interactivo)
status: pending
created_at: "2026-08-30"
depends_on: [VIKT_09]
---

## Contexto

§7.4 tiene 7 limitaciones (escritas por `VIC_06`/`VIKT_03`). Desde entonces
han aparecido varias más y algunas han cambiado. Hace falta **una sola
lista, revisada, sin solapes**, que un tribunal pueda usar como checklist
de honestidad del trabajo.

## Objetivo

Reescribir §7.4 con la lista completa. Candidatas a incluir/actualizar:

- **Ventana de datos corta** (14/8–30/8, ~2 semanas horarias) → sólo
  horizonte corto; sin estacionalidad larga. *(ya está — mantener)*
- **Pipeline congelado el 30/8** (`pipeline_enabled=false`) para acotar el
  gasto AWS de cara a la entrega — la ingesta "en producción continua" que
  describe §5/§6 corrió del 14/8 al 30/8. **Nuevo, importante.**
- **Hueco horario del 29/8** por el incidente `FIL_09` — **ya rellenado**
  vía `--backfill_fecha` (`doc/FIL-09` §"Completitud por hora"): mencionar
  como incidente resuelto, no como hueco abierto.
- **STGNN no exportable a ONNX** (`torch.export`) → el modelo de grafo se
  evalúa en §7.2 pero **no se sirve** por el asistente; sólo los LightGBM.
  *(mover de §7.5 a §7.4 como limitación de serving.)*
- **Sin alertado de salud del pipeline** — los incidentes se detectaron por
  QA manual (ver `FIL_16`).
- **`transporte_publico_emt` sondea una sola parada** (`FIL_07`, nunca
  hecho) → señal EMT pobre.
- **`aemet_avisos`**: AEMET sólo ha emitido avisos "verde" en la ventana →
  la tabla de avisos amarillo/naranja/rojo queda casi vacía (no es un bug,
  `doc/FIL-11`).
- **`bluesky_menciones`** estuvo caído ~28 h hasta añadir autenticación
  (Bluesky cerró el acceso anónimo a `searchPosts`).
- **`afluencia`**: la Gold derivada (FIL_06) tiene poco histórico → sin
  previsión propia robusta (según cierre `FIL_14`).
- **Enriquecimiento OSM de `:Lugar`** sigue en 0 (captura Overpass no hecha).

## Criterios de aceptación

- §7.4 con la lista consolidada, cada punto con una frase de causa y una de
  impacto. Sin duplicar líneas de §7.5.
- `VIKT_09` cerrado antes (para no listar algo ya arreglado).

## Restricciones

- Edita el `.docx` con `python-docx`. Avisar en el chat + `git pull` antes.
