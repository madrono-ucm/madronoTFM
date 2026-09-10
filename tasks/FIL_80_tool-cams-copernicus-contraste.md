---
kind: fil
title: "MCP: calidad del aire de Copernicus CAMS como referencia independiente + contraste con el modelo propio"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_79]
milestone: "M7"
target: "2026-09-22"
---

## Motivación

La Gold `cams_calidad_aire_por_contaminante_fecha_validez` (previsión del
modelo atmosférico **Copernicus CAMS**, `pollutant` partición,
`fecha_validez`, `avg_value`/`max_value`, `leadtime_hours`) está ingerida y
**no la usa ninguna tool**. Es una previsión de calidad del aire
*independiente* de los modelos propios (LightGBM/STGNN): tenerla permite
(a) una segunda opinión y (b) un contraste "modelo propio vs CAMS" que da
solidez a la sección de resultados.

## Alcance

1. **`calidad_aire_cams(contaminante, fecha=None)`** — 17.ª tool MCP +
   `GET /calidad-aire-cams`. Lee la Gold CAMS (nivel ciudad, sin lat/lon —
   la rejilla CAMS es de área). Devuelve `avg`/`max` por `fecha_validez`,
   unidad, `leadtime`, y la fecha de emisión (`last_forecast_issued_at`).
2. **Contraste en `calidad_aire_prevista`**: campo opcional
   `referencia_cams` con el valor CAMS para el mismo contaminante y fecha, y
   el `delta` (modelo propio − CAMS). No cambia el veredicto; es contexto.
3. **Frescura**: el pipeline está congelado desde 2026-08-30 → sin `fecha`
   explícita, la tool devuelve la última `fecha_validez` disponible y un
   `motivo` claro ("última previsión CAMS disponible: AAAA-MM-DD; pipeline
   pausado"). Encaja con el contrato de frescura de FIL_73.
4. Normalización de nombre de contaminante compartida con FIL_72
   (`ozono|o3|o₃ → O3`).

## Verificación

- `asistente/tests/test_cams.py`: parseo de la fila Gold (incl.
  `leadtime_hours` array), selección de última fecha, delta bien signado.
  Sin red (Athena mockeada).
- Registrada (17 tools) — mismos sitios que FIL_79.
- `curl` en vivo (aunque devuelva la ventana congelada): "previsión CAMS de
  NO₂" y "previsión de calidad del aire cerca de Retiro" con `referencia_cams`.
