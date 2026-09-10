---
kind: fil
title: "MCP: tool de meteorología cercana + tool de avisos meteorológicos AEMET"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_65]
milestone: "M7"
target: "2026-09-23"
---

## Motivación

Dos Gold ingeridas y **sin ninguna tool**:
- `meteorologia_por_estacion_magnitud_hora` (por estación, con lat/lon,
  `magnitude` ∈ temperature_c/wind_speed_ms/precipitation_lm2/humidity_pct,
  `hour`, `date`) — solo la usa el *ticker* del mapa, no el asistente.
- `aemet_avisos_por_zona_fecha_nivel` (`zone`, `level`
  verde/amarillo/naranja/rojo, `phenomena` array, ventanas de vigencia,
  `fecha`).

El grafo ya tiene `:EstacionMedida{meteo}` con `PROXIMO_A` (FIL_65) → la
resolución "cerca de un lugar" sale del grafo, como el resto de tools.

## Alcance

1. **`meteo_cercana(lugar, radio_m=1500)`** — 18.ª tool + `GET /meteo-cercana`.
   Resuelve el lugar → estaciones meteo `PROXIMO_A` (o por haversine sobre
   la Gold si el grafo no llega) → última hora disponible de cada magnitud
   (temp, viento, precip, humedad), con la estación y la hora del dato.
2. **`avisos_meteo(zona=None, fecha=None)`** — 19.ª tool + `GET /avisos-meteo`.
   Avisos activos por zona AEMET (Madrid). Devuelve `nivel` más alto,
   fenómenos, y ventana de vigencia. Sin `fecha` → el último día con datos +
   `motivo` de frescura (pipeline congelado, contrato FIL_73).
3. Ambas: fiabilidad MEDIA (dato observacional) salvo frescura → BAJA.
4. `contexto_urbano` incluye un resumen meteo de la estación más cercana.

## Verificación

- `asistente/tests/test_meteo_avisos.py`: agregación por magnitud/última
  hora, orden de niveles de aviso (rojo > naranja > amarillo > verde),
  degradación sin datos. Sin red.
- Registradas (19 tools) — `server.py`, `test_mcp_*`, `README.md`.
- `curl` en vivo: "tiempo cerca de Atocha", "¿hay avisos meteorológicos en
  Madrid?".
