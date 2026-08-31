# Fuentes de datos y licencias

Todas las fuentes que alimentan Madroño son **datos abiertos**. Este fichero
las lista con su licencia y su uso en el proyecto (lo pide `FIL_36` para el
eje "un análisis sobre el grafo de Madrid").

## Fuentes municipales / regionales (ingesta continua → Bronze/Silver/Gold)

| Fuente | Organismo | Licencia | Uso |
|---|---|---|---|
| Tráfico tiempo real (puntos de medida) | Ayuntamiento de Madrid — `datos.madrid.es` | Condiciones de uso de datos abiertos del Ayto. de Madrid (reutilización libre con atribución) | `trafico_por_punto_hora`; señal `avg_service_level` del STGNN de tráfico y de las tools `trafico_*` |
| Calidad del aire tiempo real | Ayuntamiento de Madrid — `datos.madrid.es` | ídem | `calidad_aire_por_estacion_contaminante_hora`; STGNN de calidad del aire, tools `calidad_aire_*` |
| Estaciones de control de aire | Ayuntamiento de Madrid — `datos.madrid.es` | ídem | coordenadas de estación |
| Meteorología tiempo real (dataset 300392) + estaciones (300360) | Ayuntamiento de Madrid — `datos.madrid.es` | ídem | `meteorologia_por_estacion_magnitud_hora`; features exógenas del feature store, ticker meteo del mapa animado |
| Contaminación acústica (Red de vigilancia) | Ayuntamiento de Madrid — `datos.madrid.es` | ídem | `ruido_por_estacion_periodo_fecha`; capa de ruido (diaria, por distrito) del mapa |
| BiciMAD | EMT Madrid | ídem | ocupación de estaciones |
| Aparcamientos (PMR, rotación, disuasorios) | Ayuntamiento de Madrid | ídem | `disponibilidad_aparcamiento` |
| Distritos y barrios (límites administrativos) | Ayuntamiento de Madrid — `sigma.madrid.es` / `datos.madrid.es` (dataset 300497) | ídem | polígonos de distrito del grafo y del mapa (`viz/assets/distritos_madrid.geojson`), relación `UBICADO_EN` del grafo |
| Calendario laboral | Ayuntamiento de Madrid | ídem | feature `es_festivo` |
| Agenda de eventos, parques y jardines, incidencias EMT, SER (tiques), aforos peatones/bici, callejero, POIs | Ayuntamiento de Madrid | ídem | contexto del grafo / tools |
| Avisos y previsión meteorológica | AEMET — API OpenData | [Nota legal AEMET](https://www.aemet.es/es/nota_legal) (reutilización con atribución, sin uso comercial de la marca) | features de previsión exógena |
| Transporte público (CRTM / EMT) | Consorcio Regional de Transportes / EMT | condiciones de datos abiertos CRTM | paradas del grafo |
| CAMS (calidad del aire, satélite/modelo) | Copernicus Atmosphere Monitoring Service | [Licencia Copernicus](https://atmosphere.copernicus.eu/sites/default/files/2019-07/CAMS_2018_CATALOGUE_ENTRY_Atmosphere_Data_Store.pdf) (reutilización libre con atribución) | comparación de calidad del aire |
| Menciones (Bluesky) | Bluesky / AT Protocol | Términos de Bluesky | señal de contexto social (experimental) |

Atribución sugerida: *«Contiene datos del Ayuntamiento de Madrid
(datos.madrid.es) y de AEMET»*.

## Slices congelados en el repo

`viz/data/gold_slices/` — export puntual de la capa Gold
(`viz/export_gold_slices.py`, `FIL_33`/G1) para que el mapa animado sea
reproducible después de que la *partition projection* deslizante deje de
servir las particiones de agosto 2026. Mismo origen y licencia que las filas
"Ayuntamiento de Madrid" de arriba. `viz/data/gold_slices/MANIFEST.json`
tiene el detalle (rango de fechas, nº de filas).

## Datasets externos

| Dataset | Autoría | Licencia | DOI / URL | Uso |
|---|---|---|---|---|
| *Enriched Traffic Datasets for Madrid* (MTD) v4 | Iván Gómez, Sergio Ilarri (Univ. de Zaragoza) | **CC BY 4.0** | `10.17632/697ht4f65b.4` (Mendeley Data) | `FIL_38` — backtest del STGNN sobre ~29 meses / 300 sensores (`modelado/training/backtest_stgnn_mtd.py`, `doc/FIL-38-...md`). Ficheros en `modelado/_data/mtd/` (no versionados). |
| Red de Calidad del Aire — datos meteorológicos horarios históricos (desde 2020) | Comunidad de Madrid | **CC BY 4.0** | `datos.comunidad.madrid` (catálogo `calidad_aire_datos_meteo_historico`) | encuadre — sólo haría falta si el backtest se reconstruyera desde el CSV crudo de MTD (MTD ya trae meteo alineada). |

## Modelos vendorizados

`asistente/modelos/*.onnx` (+ `.meta.json`) — exportados de modelos
entrenados en `modelado/` con los datos de arriba. Sin dependencia de red
en runtime.
